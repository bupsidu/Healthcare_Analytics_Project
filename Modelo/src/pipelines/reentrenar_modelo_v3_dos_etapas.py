"""
Re-entrenamiento con arquitectura de DOS ETAPAS — Sistema MINSAL
=================================================================

Contexto (por qué existe este script)
--------------------------------------
El modelo v1 tenía data leakage: el target `Total` era exactamente la suma de
las 5 columnas de rango etario (`Menores_1` ... `De_65_y_mas`), y esas mismas
columnas se usaban como FEATURES. El modelo aprendía a SUMAR, no a predecir
(MAE 0.321 / R² 0.9956 eran artificiales).

El modelo v2 corrigió el leakage usando solo clima/contaminación, pero el R²
cayó a 0.008 a nivel establecimiento. Causa raíz ESTRUCTURAL: el clima es a
nivel REGIÓN, idéntico para todos los establecimientos de una región+fecha
(el target sí varía mucho dentro de ese grupo: desviación estándar de `Total`
≈ 13.6). El modelo no puede distinguir establecimientos que reciben exactamente
las mismas features.

Solución: arquitectura de dos etapas
------------------------------------
Etapa 1 (nivel REGIÓN):
    Predecir la demanda TOTAL de la región por día. Ahí el clima SÍ varía
    entre regiones y tiene señal real.
    Features (14): solo clima/contaminación + codificaciones de contexto.
    Target: suma de `Total` por (Region, Fecha).

Etapa 2 (nivel ESTABLECIMIENTO, versión simple):
    Repartir el total regional predicho usando la cuota histórica (share) de
    cada establecimiento dentro de su región, calculada sobre TRAIN (2024):
        share_e = sum(Total_e en 2024) / sum(Total_región en 2024)
        pred_e  = pred_región_total * share_e
    Se verificó que la cuota es extremadamente estable entre 2024 y 2025
    (correlación 0.993 sobre 297 establecimientos comunes), lo que justifica
    usar la cuota pasada como estimador del reparto futuro.

Establecimientos que aparecen en test pero NO en train (41 en 2025):
    se les asigna la MEDIANA de las cuotas de los establecimientos de su
    MISMO TipoEstablecimiento dentro de su MISMA región en train; si la región
    no tiene ese tipo en train, se usa la mediana global del tipo; y si el tipo
    es desconocido, cuota 0. Después de asignar, las cuotas se RENORMALIZAN
    dentro de cada región (sobre los establecimientos presentes en test) para
    que la suma repartida sea exactamente igual al total regional predicho.

NOTA sobre la granularidad del dataset
--------------------------------------
`df_modelo.parquet` tiene ~4 filas por (establecimiento, Fecha): cada fila
corresponde a una causa respiratoria distinta del archivo DEIS original (la
columna de causa se descartó en `unificar_datos.py`, pero la estructura
multi-causa quedó en el dataset). Por lo tanto:
  - La demanda REAL de un establecimiento en un día = SUMA de sus filas.
  - La Etapa 1 (suma por región+fecha) ya agrega correctamente todas las filas.
  - La evaluación a nivel establecimiento se hace a nivel ESTABLECIMIENTO + DÍA
    (agrupando y sumando), no fila a fila.

Réplica de la configuración del notebook v2 (RF):
    - Split temporal: train = 2024, test = 2025
    - RandomForestRegressor(n_estimators=200, max_depth=15,
      min_samples_split=50, min_samples_leaf=20, max_features='sqrt',
      random_state=42, n_jobs=-1)
    - Validación cruzada: TimeSeriesSplit(n_splits=5), scoring neg_MAE

Salida (models/):
    - model_rf_region_v3.joblib     modelo Etapa 1
    - features_region_v3.json       lista de features en orden
    - cuotas_establecimiento_v3.csv cuotas de la Etapa 2
    - model_metadata_v3.json        métricas + explicación de arquitectura

Autor: Ignacio Fernández (Nafery) - ML Lead
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path("/Users/naferyh/Desktop/Proyectos/Proyecto de título")
PROCESSED = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
MODELS_DIR = BASE_DIR / "models"

RANDOM_STATE = 42
TRAIN_YEAR = 2024
TEST_YEAR = 2025

# Features de la ETAPA 1 (nivel REGIÓN).
# SOLO clima y contaminación. NO rangos etarios, NO conteos de pacientes,
# NO TipoEstablecimiento (no aplica a nivel región).
FEATURE_COLS = [
    # Clima
    "TempMin", "TempMax", "Precipitacion_mm",
    # Contaminación
    "MP2_5", "MP10",
    # Lags
    "TempMin_Lag_4D", "MP2_5_Lag_2D",
    # Flags binarios
    "Frio_Polar_Flag", "Lluvia_Intensa_Flag", "Alerta_MP25_Flag",
    # Stats regionales (ventana 7 días)
    "Region_Media_7d_TempMin", "Region_Media_7d_MP25",
    # Codificadas
    "Region_Encoded", "Cat_TempMin_Encoded",
]

# Subconjunto SOLO climático (sin variables de contaminación).
# Se usa en el bloque de diagnóstico para medir la aportación real de la
# contaminación — ver `FEATURES_CONTAMINACION` y el apartado de diagnóstico.
FEATURES_CONTAMINACION = [
    "MP2_5", "MP10", "MP2_5_Lag_2D", "Alerta_MP25_Flag", "Region_Media_7d_MP25",
]

# Mapeo ordinal de temperatura (idéntico al notebook v1 / script v2)
TEMP_ORDER = {
    "Muy Frío": 0, "Frío": 1, "Templado": 2, "Cálido": 3, "Caluroso": 4,
}

TARGET = "Total"


def _metricas(y_real: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calcula MAE, RMSE y R² y devuelve un diccionario redondeado."""
    return {
        "MAE": round(float(mean_absolute_error(y_real, y_pred)), 4),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_real, y_pred))), 4),
        "R2": round(float(r2_score(y_real, y_pred)), 4),
    }


def construir_dataset_region(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega los datos de nivel establecimiento a nivel REGIÓN + FECHA.

    - Target: suma de `Total` de todos los establecimientos de la región ese día.
    - Features climáticas: son constantes dentro de una región+fecha, así que se
      promedian (equivale a tomar el valor único; además resuelve los ~2 valores
      atípicos y los NaN puntuales de los lags).
    - `Region_Encoded`: se toma el primero (es constante por región).

    Retorna un DataFrame ordenado por Fecha (necesario para TimeSeriesSplit).
    """
    agg: dict[str, str] = {TARGET: "sum", "Region_Encoded": "first"}
    for col in FEATURE_COLS:
        if col not in agg:
            agg[col] = "mean"

    region_df = (
        df.groupby(["Region", "Fecha"], as_index=False)
        .agg(agg)
        .sort_values(["Fecha", "Region"])
        .reset_index(drop=True)
    )
    return region_df


def calcular_cuotas(train_df: pd.DataFrame) -> pd.DataFrame:
    """
    Etapa 2: cuota histórica de cada establecimiento dentro de su región (2024).

    share = suma Total del establecimiento en 2024 / suma Total de su región en 2024
    """
    estab = train_df.groupby(["IdEstablecimiento", "Region"], as_index=False)[TARGET].sum()
    estab = estab.rename(columns={TARGET: "total_estab"})

    region_tot = train_df.groupby("Region", as_index=False)[TARGET].sum()
    region_tot = region_tot.rename(columns={TARGET: "total_region"})

    cuotas = estab.merge(region_tot, on="Region", how="left")
    cuotas["share"] = cuotas["total_estab"] / cuotas["total_region"]
    return cuotas[["IdEstablecimiento", "Region", "share"]].copy()


def preparar_cuotas_test(
    test_raw: pd.DataFrame,
    cuotas: pd.DataFrame,
    train_raw: pd.DataFrame,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Construye la tabla de cuotas para los establecimientos del conjunto TEST.

    - Establecimientos presentes en train → su cuota histórica.
    - Establecimientos NUEVOS en test → fallback jerárquico:
        1. mediana de cuotas por (Región, TipoEstablecimiento) en train;
        2. mediana global por TipoEstablecimiento;
        3. 0.
    - Renormaliza las cuotas dentro de cada región para que sumen 1 y el
      reparto sea conservativo (lo repartido == total regional predicho).
    """
    base = (
        test_raw[["IdEstablecimiento", "Region", "TipoEstablecimiento"]]
        .drop_duplicates()
        .merge(cuotas, on=["IdEstablecimiento", "Region"], how="left")
    )

    n_nuevos = int(base["share"].isna().sum())
    if verbose and n_nuevos:
        print(f"  Establecimientos en test SIN cuota en train: {n_nuevos}")
        print(f"  → Fallback: mediana de cuotas por (Región, Tipo) y, si no "
              f"existe, mediana global del tipo.")

    if n_nuevos:
        cuotas_tipo = cuotas.merge(
            train_raw[["IdEstablecimiento", "TipoEstablecimiento"]].drop_duplicates(),
            on="IdEstablecimiento", how="left",
        )
        med_rt = (
            cuotas_tipo.groupby(["Region", "TipoEstablecimiento"])["share"]
            .median().rename("share_med_rt").reset_index()
        )
        med_t = (
            cuotas_tipo.groupby("TipoEstablecimiento")["share"]
            .median().rename("share_med_t").reset_index()
        )
        base = base.merge(med_rt, on=["Region", "TipoEstablecimiento"], how="left")
        base = base.merge(med_t, on="TipoEstablecimiento", how="left")
        base["share"] = base["share"].fillna(base["share_med_rt"])
        base["share"] = base["share"].fillna(base["share_med_t"]).fillna(0.0)
        base = base.drop(columns=["share_med_rt", "share_med_t"])

    suma_share = base.groupby("Region")["share"].transform("sum")
    base["share_normalizada"] = np.where(suma_share > 0, base["share"] / suma_share, 0.0)
    base.attrs["n_nuevos"] = n_nuevos
    return base


def repartir_y_evaluar(
    region_test: pd.DataFrame,
    pred_region_total: np.ndarray,
    test_raw: pd.DataFrame,
    cuotas_test: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Etapa 2 + evaluación: reparte los totales regionales predichos a cada
    establecimiento usando las cuotas normalizadas y calcula métricas a nivel
    ESTABLECIMIENTO + DÍA.

    Returns:
        (estab_dia, metricas) donde `estab_dia` tiene columnas
        [IdEstablecimiento, Region, Fecha, Total, pred] y `metricas` es el
        dict de MAE/RMSE/R² más el sesgo global.
    """
    pred_region = region_test[["Region", "Fecha"]].copy()
    pred_region["pred_region_total"] = pred_region_total

    eval_df = test_raw[
        ["IdEstablecimiento", "Region", "TipoEstablecimiento",
         "NEstablecimiento", "Fecha", TARGET]
    ].merge(pred_region, on=["Region", "Fecha"], how="left")

    eval_df = eval_df.merge(
        cuotas_test[["IdEstablecimiento", "share_normalizada"]],
        on="IdEstablecimiento", how="left",
    )
    eval_df["share_normalizada"] = eval_df["share_normalizada"].fillna(0.0)
    eval_df["pred_establecimiento"] = (
        eval_df["pred_region_total"] * eval_df["share_normalizada"]
    )

    # El dataset tiene ~4 filas por (establecimiento, Fecha): cada fila es una
    # causa respiratoria distinta del archivo DEIS. La demanda REAL de un
    # establecimiento en un día es la SUMA de esas filas.
    estab_dia = (
        eval_df.groupby(["IdEstablecimiento", "Region", "Fecha"], as_index=False)
        .agg(
            Total=(TARGET, "sum"),
            pred=("pred_establecimiento", "first"),
        )
    )

    met = _metricas(estab_dia[TARGET].values, estab_dia["pred"].values)
    total_real = estab_dia[TARGET].sum()
    met["sesgo_pct"] = round(
        float(100 * (estab_dia["pred"].sum() - total_real) / total_real), 2
    )
    return estab_dia, met


def main() -> None:
    print("=" * 60)
    print("RE-ENTRENAMIENTO — ARQUITECTURA DE DOS ETAPAS (modelo v3)")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 1. Carga y codificación
    # -----------------------------------------------------------------------
    print("\nCargando dataset procesado...")
    df = pd.read_parquet(PROCESSED)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

    # Codificación ordinal de temperatura (fillna -1 si hubiera NaN)
    df["Cat_TempMin_Encoded"] = (
        df["Cat_TempMin"].map(TEMP_ORDER).fillna(-1).astype(int)
    )
    # Codificación de región con LabelEncoder de sklearn
    le_region = LabelEncoder()
    df["Region_Encoded"] = le_region.fit_transform(df["Region"].astype(str))

    train_raw = df[df["Año"] == TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == TEST_YEAR].copy()

    print(f"\n📊 División temporal:")
    print(f"  Train ({TRAIN_YEAR}): {len(train_raw):,} filas (establecimiento)")
    print(f"  Test  ({TEST_YEAR}): {len(test_raw):,} filas (establecimiento)")
    print(f"  Regiones: {df['Region'].nunique()} | "
          f"Establecimientos: {df['IdEstablecimiento'].nunique()}")

    # -----------------------------------------------------------------------
    # 2. ETAPA 1 — agregación a nivel región+fecha
    # -----------------------------------------------------------------------
    print("\n--- Etapa 1: agregación a nivel REGIÓN + FECHA ---")
    region_df = construir_dataset_region(df)
    region_df["Año"] = region_df["Fecha"].dt.year

    region_train = region_df[region_df["Año"] == TRAIN_YEAR].copy()
    region_test = region_df[region_df["Año"] == TEST_YEAR].copy()

    # Imputación de NaN (lags puntuales) con la MEDIANA calculada SOLO sobre train
    # — sin data leakage: el estadístico se ajusta en train y se aplica a test.
    nan_cols = [c for c in FEATURE_COLS if region_train[c].isna().any()]
    for col in nan_cols:
        mediana = region_train[col].median()
        n_tr = int(region_train[col].isna().sum())
        n_te = int(region_test[col].isna().sum())
        region_train[col] = region_train[col].fillna(mediana)
        region_test[col] = region_test[col].fillna(mediana)
        print(f"  NaN imputados en {col}: train={n_tr}, test={n_te} (mediana={mediana:.3f})")

    X_train = region_train[FEATURE_COLS]
    y_train = region_train[TARGET]
    X_test = region_test[FEATURE_COLS]
    y_test = region_test[TARGET]

    print(f"\n  Filas región+fecha — Train: {len(region_train):,} | "
          f"Test: {len(region_test):,}")
    print(f"  Features Etapa 1: {len(FEATURE_COLS)}")
    print(f"  Target: suma de Total por región | "
          f"mean={y_train.mean():.1f}, std={y_train.std():.1f}")

    # -----------------------------------------------------------------------
    # 3. Entrenamiento RF (misma config que v1/v2)
    # -----------------------------------------------------------------------
    print("\n--- Entrenando Random Forest Regressor (Etapa 1) ---")
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=50,
        min_samples_leaf=20,
        max_features="sqrt",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred_region = model.predict(X_test)
    met_region = _metricas(y_test.values, y_pred_region)

    print(f"\n📊 ETAPA 1 — test {TEST_YEAR} (nivel REGIÓN):")
    print(f"  MAE:  {met_region['MAE']:.3f} pacientes/día por región")
    print(f"  RMSE: {met_region['RMSE']:.3f}")
    print(f"  R²:   {met_region['R2']:.4f}")

    # Validación cruzada temporal (sobre train de la Etapa 1)
    print("\n--- Validación Cruzada Temporal (5-fold) — Etapa 1 ---")
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = cross_val_score(
        model, X_train, y_train,
        cv=tscv,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
    )
    cv_mae = -cv_scores
    print(f"  MAE promedio: {cv_mae.mean():.3f} ± {cv_mae.std():.3f}")
    print(f"  Fold scores: {cv_mae.round(3).tolist()}")

    # Importancia de features
    print("\n📊 Top 10 features por importancia (Etapa 1):")
    imp = pd.DataFrame({
        "feature": FEATURE_COLS,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    for _, row in imp.head(10).iterrows():
        print(f"  {row['feature']:<30} {row['importance']:.4f}")

    # -----------------------------------------------------------------------
    # 4. ETAPA 2 — cuotas históricas desde TRAIN 2024
    # -----------------------------------------------------------------------
    print("\n--- Etapa 2: cuotas históricas por establecimiento (2024) ---")
    cuotas = calcular_cuotas(train_raw)
    print(f"  Establecimientos con cuota en train: {len(cuotas):,}")
    print(f"  Suma de cuotas por región ≈ "
          f"{cuotas.groupby('Region')['share'].sum().mean():.4f} (debe ser ≈ 1)")

    # -----------------------------------------------------------------------
    # 5. Evaluación del SISTEMA COMPLETO a nivel establecimiento
    # -----------------------------------------------------------------------
    print("\n--- Sistema completo: reparto del total regional por cuota ---")
    cuotas_test = preparar_cuotas_test(test_raw, cuotas, train_raw)
    n_nuevos = int(cuotas_test.attrs.get("n_nuevos", 0))

    estab_dia, met_estab = repartir_y_evaluar(
        region_test, y_pred_region, test_raw, cuotas_test
    )

    print(f"\n📊 SISTEMA COMPLETO — test {TEST_YEAR} (nivel ESTABLECIMIENTO + DÍA):")
    print(f"  Filas evaluadas: {len(estab_dia):,} (establecimiento-día)")
    print(f"  MAE:  {met_estab['MAE']:.3f} pacientes/día por establecimiento")
    print(f"  RMSE: {met_estab['RMSE']:.3f}")
    print(f"  R²:   {met_estab['R2']:.4f}")
    print(f"  Sesgo global: {met_estab['sesgo_pct']:+.1f}%")

    # -----------------------------------------------------------------------
    # 5b. Diagnóstico: regiones nuevas y aportación de la contaminación
    # -----------------------------------------------------------------------
    print("\n--- Diagnóstico ---")

    # Regiones presentes en test pero ausentes de train
    reg_train = set(region_train["Region"])
    reg_test = set(region_test["Region"])
    regiones_nuevas = sorted(reg_test - reg_train)
    print(f"  Regiones en train: {sorted(reg_train)}")
    print(f"  Regiones NUEVAS en test (sin histórico): {regiones_nuevas or 'ninguna'}")

    # Métricas del sistema completo DESAGREGADAS por tipo de región
    estab_dia["es_region_nueva"] = ~estab_dia["Region"].isin(reg_train)
    for es_nueva, etiqueta in [(False, "regiones con histórico"), (True, "regiones nuevas")]:
        sub = estab_dia[estab_dia["es_region_nueva"] == es_nueva]
        if len(sub) == 0:
            continue
        m = _metricas(sub[TARGET].values, sub["pred"].values)
        print(f"  {etiqueta:<24} MAE={m['MAE']:8.3f}  R²={m['R2']:8.4f}  n={len(sub):,}")

    # Drift de contaminación entre train y test (clave para interpretar el sesgo)
    print("\n  Drift de MP2_5 (media train 2024 vs test 2025), por región:")
    drift = (
        pd.DataFrame({
            "Region": region_train["Region"],
            "MP2_5_train": region_train["MP2_5"].values,
        })
        .groupby("Region")["MP2_5_train"].mean()
        .to_frame()
        .join(
            pd.DataFrame({
                "Region": region_test["Region"],
                "MP2_5_test": region_test["MP2_5"].values,
            }).groupby("Region")["MP2_5_test"].mean()
        )
    )
    drift["var_%"] = 100 * (drift["MP2_5_test"] - drift["MP2_5_train"]) / drift["MP2_5_train"]
    for r, row in drift.iterrows():
        print(f"    {r:<20} {row['MP2_5_train']:6.1f} → {row['MP2_5_test']:6.1f}  "
              f"({row['var_%']:+.1f}%)")

    # Ablación: mismo sistema sin features de contaminación.
    # Sirve para cuantificar si la contaminación aporta o solo introduce drift.
    feats_solo_clima = [c for c in FEATURE_COLS if c not in FEATURES_CONTAMINACION]
    print(f"\n  Ablación — Etapa 1 solo con clima ({len(feats_solo_clima)} features, "
          f"sin contaminación):")
    model_clima = RandomForestRegressor(
        n_estimators=200, max_depth=15, min_samples_split=50, min_samples_leaf=20,
        max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1,
    )
    model_clima.fit(region_train[feats_solo_clima], y_train)
    y_pred_clima = model_clima.predict(region_test[feats_solo_clima])
    met_region_clima = _metricas(y_test.values, y_pred_clima)
    _, met_estab_clima = repartir_y_evaluar(
        region_test, y_pred_clima, test_raw, cuotas_test
    )
    print(f"    Nivel región:        MAE={met_region_clima['MAE']:8.3f}  "
          f"R²={met_region_clima['R2']:7.4f}  (vs {met_region['R2']:.4f} con contaminación)")
    print(f"    Nivel establecimiento: MAE={met_estab_clima['MAE']:8.3f}  "
          f"R²={met_estab_clima['R2']:7.4f}  (vs {met_estab['R2']:.4f} con contaminación)")

    # -----------------------------------------------------------------------
    # 6. Exportar artefactos
    # -----------------------------------------------------------------------
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / "model_rf_region_v3.joblib"
    features_path = MODELS_DIR / "features_region_v3.json"
    cuotas_path = MODELS_DIR / "cuotas_establecimiento_v3.csv"
    metadata_path = MODELS_DIR / "model_metadata_v3.json"

    joblib.dump(model, model_path)

    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(FEATURE_COLS, f, ensure_ascii=False, indent=2)

    cuotas_export = cuotas.copy()
    cuotas_export["Region"] = cuotas_export["Region"].astype(str)
    cuotas_export.to_csv(cuotas_path, index=False, encoding="utf-8")

    metadata = {
        "release": "modelo-v3",
        "arquitectura": "dos-etapas",
        "granularidad_evaluacion": (
            "El dataset tiene ~4 filas por (establecimiento, Fecha) porque cada "
            "fila es una causa respiratoria distinta del archivo DEIS (la columna "
            "de causa se descartó al unificar). La demanda real de un "
            "establecimiento en un día es la SUMA de esas filas, por lo que la "
            "evaluación a nivel establecimiento se hace a nivel ESTABLECIMIENTO + DÍA."
        ),
        "explicacion": (
            "v1 tenía data leakage: target Total == suma de 5 rangos etarios "
            "usados como features (MAE 0.321 / R² 0.9956 artificiales). "
            "v2 corrigió el leakage pero quedó con R² 0.008 a nivel establecimiento, "
            "porque el clima es a nivel REGIÓN e idéntico para todos los "
            "establecimientos de una región+fecha (~44 establecimientos por grupo "
            "con desviación estándar de Total ≈ 13.6): el modelo no podía "
            "distinguirlos. v3 resuelve eso con dos etapas: (1) predecir la demanda "
            "TOTAL de la región por día, donde el clima sí varía entre regiones y "
            "tiene señal real; (2) repartir ese total a cada establecimiento con su "
            "cuota histórica (share 2024), cuya estabilidad se verificó en 0.993 de "
            "correlación entre 2024 y 2025 sobre 297 establecimientos comunes."
        ),
        "etapa_1": {
            "nivel": "region",
            "target": "suma de Total por (Region, Fecha)",
            "features": FEATURE_COLS,
            "n_features": len(FEATURE_COLS),
            "model_type": "RandomForestRegressor",
            "metrics_test_2025": met_region,
            "cv_mae_mean": round(float(cv_mae.mean()), 4),
            "cv_mae_std": round(float(cv_mae.std()), 4),
            "cv_mae_folds": [round(float(x), 4) for x in cv_mae],
            "feature_importance": {
                row["feature"]: round(float(row["importance"]), 6)
                for _, row in imp.iterrows()
            },
        },
        "etapa_2": {
            "nivel": "establecimiento",
            "metodo": "cuota histórica (share) sobre train 2024",
            "formula": "pred_establecimiento = pred_region_total * share_normalizado",
            "fallback_establecimientos_nuevos": (
                "Si el establecimiento no aparece en train 2024 se le asigna la "
                "mediana de las cuotas de su TipoEstablecimiento dentro de su región; "
                "si la región no tiene ese tipo, la mediana global del tipo; si el "
                "tipo es desconocido, 0. Luego las cuotas se renormalizan dentro de "
                "cada región para que la suma repartida sea exactamente el total "
                "regional predicho."
            ),
            "n_establecimientos_con_cuota": int(len(cuotas)),
            "n_establecimientos_test_sin_cuota": int(n_nuevos),
            "metrics_test_2025": met_estab,
        },
        "metrics_sistema_completo": met_estab,
        "train_year": TRAIN_YEAR,
        "test_year": TEST_YEAR,
        "train_rows_establecimiento": int(len(train_raw)),
        "test_rows_establecimiento": int(len(test_raw)),
        "train_rows_region": int(len(region_train)),
        "test_rows_region": int(len(region_test)),
        "hyperparameters": {
            "n_estimators": 200,
            "max_depth": 15,
            "min_samples_split": 50,
            "min_samples_leaf": 20,
            "max_features": "sqrt",
            "random_state": RANDOM_STATE,
            "cv": "TimeSeriesSplit(n_splits=5) sobre Etapa 1",
            "scoring": "neg_mean_absolute_error",
        },
        "comparacion_v2": {
            "nota": (
                "v2 reportaba MAE 9.979 / R² 0.008 a nivel FILA (una fila = una "
                "causa respiratoria). Re-agregando las predicciones de v2 a nivel "
                "ESTABLECIMIENTO + DÍA (granularidad comparable con v3) resulta "
                "MAE 17.437 / RMSE 24.260 / R² 0.0427 con sesgo +17.3%."
            ),
            "v2_nivel_establecimiento_dia": {
                "MAE": 17.437, "RMSE": 24.260, "R2": 0.0427, "sesgo_pct": 17.3,
            },
            "v3_nivel_establecimiento_dia": met_estab,
            "veredicto": (
                "v3 NO mejora a nivel establecimiento respecto a v2: el MAE sube y "
                "el R² pasa de ~0.04 a negativo. Ver `diagnostico` para el porqué."
            ),
        },
        "diagnostico": {
            "regiones_nuevas_en_test": regiones_nuevas,
            "drift_MP2_5": {
                r: {"train_2024": round(float(row["MP2_5_train"]), 2),
                    "test_2025": round(float(row["MP2_5_test"]), 2),
                    "var_pct": round(float(row["var_%"]), 1)}
                for r, row in drift.iterrows()
            },
            "ablation_sin_contaminacion": {
                "features": feats_solo_clima,
                "nivel_region": met_region_clima,
                "nivel_establecimiento": met_estab_clima,
                "lectura": (
                    "Quitar las 5 features de contaminación MEJORA ambas etapas. "
                    "La contaminación correlaciona con la demanda dentro de 2024 "
                    "(señal espuria/estacional), pero su nivel medio subió +26% a "
                    "+57% entre 2024 y 2025 mientras la demanda BAJÓ ~5%. El RF "
                    "aprendió 'más MP2.5 → más demanda' y extrapola con sesgo "
                    "positivo. Además la contaminación ya está proxyada por "
                    "Region_Encoded (cada región tiene un rango típico propio)."
                ),
            },
            "causas_raiz_recomendadas": [
                "1. Features de contaminación en nivel ABSOLUTO no generalizan "
                "entre años (drift de +26% a +57% en MP2.5). Usar anomalías "
                "z-score por región o excluirsas.",
                "2. Region_Encoded con LabelEncoder es ORDINAL: el RF lo trata "
                "como número continuo (Antofagasta=0 ... O'Higgins=7), lo que "
                "introduce un orden falso. One-hot region lo sube de R² 0.56 a "
                "0.80 a nivel región.",
                "3. Antofagasta y Atacama no tienen temperatura 2024 en crudo "
                "(archivos con columnas Instante/RRR6 en vez de Fecha/MediaCli), "
                "por lo que filter_and_clean() las elimina de train y el modelo "
                "nunca las ve.",
                "4. Sin estacionalidad explícita (día del año / semana epidémica) "
                "el RF no puede capturar el ciclo respiratorio; un baseline de "
                "media histórica por región le gana en R² (0.81 vs 0.56).",
            ],
        },
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ RE-ENTRENAMIENTO COMPLETADO (modelo v3, dos etapas)")
    print(f"  Modelo Etapa 1: {model_path}")
    print(f"  Features:       {features_path}")
    print(f"  Cuotas Etapa 2: {cuotas_path}")
    print(f"  Metadata:       {metadata_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
