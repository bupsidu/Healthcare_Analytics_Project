"""
Re-entrenamiento v4 — arquitectura de DOS ETAPAS con features de ANOMALÍA ESTACIONAL
====================================================================================

Contexto (por qué existe este script)
--------------------------------------
Historial de versiones:

- v1 (ROTO — data leakage): usaba las 5 columnas de rango etario como FEATURES,
  pero el target `Total` era exactamente su suma. El modelo aprendía a SUMAR
  (MAE 0.321 / R² 0.9956 eran artificiales). NUNCA se usan rangos etarios.

- v2 (sin leakage, pero débil): solo clima/contaminación a nivel ESTABLECIMIENTO.
  MAE 17.437 / R² 0.0427 / sesgo +17.3% (re-agregado a establecimiento+día).
  Problema estructural: el clima es a nivel REGIÓN, idéntico para todos los
  establecimientos de una región+fecha (~44 establecimientos con desviación
  estándar de Total ≈ 13.6): el modelo no puede distinguirlos.

- v3 (dos etapas, pero contaminación ABSOLUTA — empeoró): MAE 20.119 /
  R² -1.979 / sesgo +34.6%. CAUSA RAÍZ: la contaminación en nivel absoluto es
  señal ESPURIA — actúa como PROXY DE LA ESTACIÓN. En invierno sube la leña
  (MP2.5 ↑) Y suben las urgencias respiratorias por la misma causa de fondo
  (frío + aglomeración interior). El RF aprendió "más contaminación → más
  demanda" dentro de 2024, pero entre 2024 y 2025 el MP2.5 subió +26% a +57%
  en 5 de 6 regiones mientras la demanda BAJÓ ~5% → extrapolación con sesgo
  fuerte positivo. La ablación sin contaminación lo confirmó: MAE 12.7 /
  R² 0.4460 (mejora real sobre v2). Además: Region_Encoded con LabelEncoder es
  ORDINAL (Antofagasta=0 … O'Higgins=7) y el RF lo trata como continuo
  (falso orden); y falta estacionalidad explícita.

v4 (este script): conserva la contaminación y la temperatura, pero transformadas
--------------------------------------------------------------------------------
Idea central: los niveles ABSOLUTOS de contaminación y temperatura cambian con
el tiempo (calentamiento global, adaptación, cambios de matriz energética). Un
nivel que hoy es "alto", el próximo año puede ser "normal". Por eso se usan
features de ANOMALÍA (desviación respecto del baseline estacional por región),
que son robustas al desplazamiento de los niveles base.

Cambios respecto de v3 (Etapa 1):
  1. ANOMALÍAS en vez de absolutos de contaminación: Anom_TempMin, Anom_MP2_5,
     Anom_MP10. Se descartan los absolutos MP2_5 / MP10 (la anomalía los
     reemplaza). Se CONSERVA el absoluto TempMin porque el frío absoluto es
     fisiológicamente relevante (umbral de demanda) y su drift interanual es
     pequeño comparado con la contaminación.
  2. ESTACIONALIDAD EXPLÍCITA: Doy_Sin / Doy_Cos (codificación cíclica del día
     del año). Permite al modelo separar "efecto invierno" de "efecto
     contaminación" — en v3 no había estacionalidad explícita y un baseline de
     media histórica le ganaba en R² (0.81 vs 0.56).
  3. ONE-HOT de Región (pd.get_dummies), NO LabelEncoder: corrige el falso
     orden ordinal que afectó a v3.
  4. Se elimina Cat_TempMin_Encoded: Cat_TempMin se deriva por umbrales de
     TempMin, es 100% redundante con la feature TempMin.

MÉTODO ANTI-LEAKAGE DE LOS BASELINES ESTACIONALES (documentación obligatoria):
  - El baseline estacional de cada variable (TempMin, MP2_5, MP10) se calcula
    SOLO con datos de TRAIN (año 2024). NUNCA se usan datos de test (2025).
  - Procedimiento: por región y día-del-año (1..366), se promedia el valor de
    2024; los huecos internos se interpolan linealmente (algunas region+fecha
    faltan en 2024: 2185 combos de 2196 posibles); luego se aplica una
    ventana móvil CENTRAL de 15 días sobre la serie de días-del-año (suavizado,
    min_periods=1 en los bordes). Esto produce una curva estacional suave por
    región y variable.
  - Ese baseline se aplica tanto a train (2024) como a test (2025): para cada
    fila, baseline = curva suavizada[región, día-del-año de su fecha].
    anomalía = valor absoluto − baseline.
  - Regiones presentes en test pero AUSENTES en train (Antofagasta, Atacama):
    no tienen baseline propio. Se les asigna el baseline NACIONAL, definido
    como el promedio entre las curvas de las 6 regiones de train (mismo
    suavizado). Es la mejor estimación disponible sin tocar test.
  - Nota honesta: si el nivel base de MP2.5 en 2025 subió respecto de 2024, la
    anomalía de 2025 absorbe parcialmente ese drift (anomalía media > 0). La
    ventaja respecto de v3 es que la correlación espuria estación↔demanda queda
    explicada por Doy_Sin/Doy_Cos, no por la contaminación; la ablación de este
    script cuantifica si la anomalía aporta o no en la práctica.

Etapa 2 (idéntica a v3, verificada estable):
  - Cuota histórica share_e = sum(Total_e en 2024) / sum(Total_región en 2024),
    calculada SOLO desde train.
  - pred_establecimiento = pred_region_total * share.
  - Establecimientos en test sin cuota (41 en 2025: 21 Antofagasta, 15 Atacama,
    1 Arica, 3 Metropolitana, 1 O'Higgins): fallback jerárquico — mediana de
    cuotas por (Región, Tipo) en train → mediana global del tipo → 0; luego
    renormalización dentro de cada región (suma = 1).

NOTA sobre la granularidad del dataset
--------------------------------------
`df_modelo.parquet` tiene ~4 filas por (establecimiento, Fecha): cada fila es
una causa respiratoria distinta del archivo DEIS (la columna de causa se
descartó al unificar). Por lo tanto:
  - La demanda REAL de un establecimiento en un día = SUMA de sus filas.
  - La Etapa 1 (suma por región+fecha) agrega correctamente todas las filas.
  - La evaluación a nivel establecimiento es a ESTABLECIMIENTO + DÍA.

Configuración (réplica de v2/v3):
  - Split temporal: train = 2024, test = 2025
  - RandomForestRegressor(n_estimators=200, max_depth=15,
    min_samples_split=50, min_samples_leaf=20, max_features='sqrt',
    random_state=42, n_jobs=-1)
  - Validación cruzada: TimeSeriesSplit(n_splits=5), scoring neg_MAE

Salida (models/):
  - model_rf_region_v4.joblib      modelo Etapa 1
  - features_region_v4.json        lista de features EN ORDEN (incluye one-hot)
  - cuotas_establecimiento_v4.csv  cuotas Etapa 2
  - model_metadata_v4.json         métricas + diagnóstico + comparación v2/v3/v4

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

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path("/Users/naferyh/Desktop/Proyectos/Proyecto de título")
PROCESSED = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
MODELS_DIR = BASE_DIR / "models"

RANDOM_STATE = 42
TRAIN_YEAR = 2024
TEST_YEAR = 2025

# Ventana de suavizado (central) del baseline estacional, en días-del-año.
VENTANA_BASELINE = 15

# Variables a las que se les calcula baseline estacional + anomalía.
VARIABLES_ANOMALIA = ["TempMin", "MP2_5", "MP10"]

# Features climáticas/de contaminación conservadas de v3 (nivel absoluto).
# MP2_5 y MP10 en ABSOLUTO se excluyen a propósito: son las que introducían
# el sesgo espuria-estación de v3; se reemplazan por Anom_MP2_5 / Anom_MP10.
FEATURES_BASE = [
    "TempMin",                      # absoluto: umbral fisiológico de frío
    "TempMax", "Precipitacion_mm",
    # Lags (absolutos, conservalos de v3)
    "TempMin_Lag_4D", "MP2_5_Lag_2D",
    # Flags binarios (conservalos de v3)
    "Frio_Polar_Flag", "Lluvia_Intensa_Flag", "Alerta_MP25_Flag",
    # Rolling 7d regionales (conservalos de v3)
    "Region_Media_7d_TempMin", "Region_Media_7d_MP25",
]

# Anomalías (valor absoluto − baseline estacional de 2024, anti-leakage).
FEATURES_ANOMALIA = ["Anom_TempMin", "Anom_MP2_5", "Anom_MP10"]

# Estacionalidad explícita: codificación cíclica del día del año.
FEATURES_ESTACIONALIDAD = ["Doy_Sin", "Doy_Cos"]

# Features de contaminación (absolutas o derivadas). Se usan en la ablación
# para medir si la contaminación POR ANOMALÍA aporta o no.
FEATURES_CONTAMINACION = [
    "Anom_MP2_5", "Anom_MP10", "MP2_5_Lag_2D",
    "Alerta_MP25_Flag", "Region_Media_7d_MP25",
]

# Solo las features de contaminación en NIVEL ABSOLUTO (conservadas por
# especificación de v3). La ablación "anomalías solo" las quita para aislar
# el efecto de las anomalías puras.
ABS_CONTAMINACION = ["MP2_5_Lag_2D", "Alerta_MP25_Flag", "Region_Media_7d_MP25"]

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
      promedian (equivale a tomar el valor único; además resuelve NaN puntuales
      de los lags).

    Retorna un DataFrame ordenado por Fecha (necesario para TimeSeriesSplit).
    """
    columnas_clima = (
        FEATURES_BASE + VARIABLES_ANOMALIA
        + ["Region_Media_7d_TempMin", "Region_Media_7d_MP25"]
    )
    # Deduplicar preservando orden (Region_Media_7d_* ya están en FEATURES_BASE)
    vistas: set[str] = set()
    agg: dict[str, str] = {TARGET: "sum"}
    for col in columnas_clima:
        if col not in agg and col not in vistas:
            agg[col] = "mean"
            vistas.add(col)

    region_df = (
        df.groupby(["Region", "Fecha"], as_index=False)
        .agg(agg)
        .sort_values(["Fecha", "Region"])
        .reset_index(drop=True)
    )
    return region_df


def calcular_baseline_estacional(
    region_train: pd.DataFrame,
    variables: list[str],
    ventana: int = VENTANA_BASELINE,
) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    """
    Calcula el baseline estacional de cada variable SOLO con TRAIN (anti-leakage).

    Método:
      1. Por región y día-del-año (doy = 1..366), promediar el valor de 2024.
      2. Reindexar a la grilla completa de doys; interpolar linealmente los
         huecos internos (algunas region+fecha faltan en 2024) y propagar
         bordes (ffill/bfill).
      3. Suavizar con ventana móvil CENTRAL de `ventana` días (min_periods=1).

    Returns:
        (baselines, baseline_nacional): `baselines[var]` es un DataFrame con
        índice = región y columnas = doy (1..366); `baseline_nacional` es una
        Serie por doy con el promedio entre las curvas de las regiones de
        train — se usa como fallback para regiones ausentes en train
        (Antofagasta, Atacama).
    """
    tmp = region_train.copy()
    tmp["doy"] = tmp["Fecha"].dt.dayofyear
    doys = np.arange(1, 367)  # 2024 es bisiesto: 366 días

    baselines: dict[str, pd.DataFrame] = {}
    nacionales: list[pd.Series] = []

    for var in variables:
        # 1. media por región × doy
        tabla = tmp.groupby(["Region", "doy"], as_index=False)[var].mean()
        mat = tabla.pivot(index="Region", columns="doy", values=var)
        # 2. grilla completa + interpolación de huecos
        mat = mat.reindex(columns=doys)
        mat = mat.interpolate(axis=1, limit_direction="both")
        # 3. suavizado central de 15 días
        suav = mat.rolling(ventana, center=True, min_periods=1).mean()
        baselines[var] = suav
        nacionales.append(suav.mean(axis=0).rename(var))

    baseline_nacional = pd.concat(nacionales, axis=1)
    baseline_nacional.index.name = "doy"
    return baselines, baseline_nacional


def aplicar_anomalias(
    region_df: pd.DataFrame,
    baselines: dict[str, pd.DataFrame],
    baseline_nacional: pd.Series,
    variables: list[str] = VARIABLES_ANOMALIA,
) -> pd.DataFrame:
    """
    Aplica los baseline de TRAIN a train y test, y crea las columnas Anom_*.

    baseline por fila = curva[región, doy]; si la región no está en train
    (Antofagasta/Atacama), se usa baseline_nacional[doy].
    anomalía = valor absoluto − baseline.
    """
    out = region_df.copy()
    out["doy"] = out["Fecha"].dt.dayofyear

    regiones_train = set(baselines[variables[0]].index)
    es_region_nueva = ~out["Region"].isin(regiones_train)

    for var in variables:
        suav = baselines[var]
        # Lookup por región+doy; regiones ausentes → NaN → fallback nacional
        base_lookup = out.apply(
            lambda row: suav.at[row["Region"], row["doy"]]
            if row["Region"] in regiones_train
            else np.nan,
            axis=1,
        )
        base_nac = out["doy"].map(baseline_nacional[var])
        base_final = base_lookup.fillna(base_nac)
        out[f"Anom_{var}"] = out[var] - base_final

    out.attrs["n_regiones_nuevas"] = int(es_region_nueva.sum())
    return out


def codificar_region_onehot(
    region_train: pd.DataFrame,
    region_test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """
    Codifica `Region` con ONE-HOT (pd.get_dummies), NO LabelEncoder.

    LabelEncoder produce un entero ordinal que el RF trata como continuo
    (falso orden Antofagasta=0 … O'Higgins=7); eso afectó a v3. El one-hot
    elimina el orden falso. Se usa la unión de regiones de train+test para
    fijar las columnas (las regiones solo-test, Antofagasta/Atacama, quedan
    con su propia columna aunque en train sea 100% cero: el RF las trata como
    "sin información de región", que es honesto — nunca las vio).
    """
    todas = sorted(set(region_train["Region"]) | set(region_test["Region"]))
    dummies_cols = [f"Region_{r}" for r in todas]

    tr = pd.get_dummies(region_train, columns=["Region"], prefix="Region")
    te = pd.get_dummies(region_test, columns=["Region"], prefix="Region")
    # Conservar la columna Region original (get_dummies la consume): la
    # necesitan el reparto de la Etapa 2 y el bloque de diagnóstico.
    tr["Region"] = region_train["Region"]
    te["Region"] = region_test["Region"]
    # Alinear columnas: train+test pueden diferir en presencia de dummies
    for col in dummies_cols:
        if col not in tr.columns:
            tr[col] = 0
        if col not in te.columns:
            te[col] = 0
    return tr, te, dummies_cols


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
    print("RE-ENTRENAMIENTO — DOS ETAPAS + ANOMALÍAS ESTACIONALES (modelo v4)")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 1. Carga y split temporal
    # -----------------------------------------------------------------------
    print("\nCargando dataset procesado...")
    df = pd.read_parquet(PROCESSED)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

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

    # -----------------------------------------------------------------------
    # 3. Baselines estacionales SOLO desde train (anti-leakage) + anomalías
    # -----------------------------------------------------------------------
    print(f"\n--- Baselines estacionales anti-leakage (solo {TRAIN_YEAR}) ---")
    print(f"  Método: media {TRAIN_YEAR} por región × día-del-año, huecos "
          f"interpolados, suavizado central de {VENTANA_BASELINE} días.")
    print(f"  Se aplica a train Y a test; anomalía = valor − baseline.")

    baselines, baseline_nacional = calcular_baseline_estacional(
        region_train, VARIABLES_ANOMALIA, ventana=VENTANA_BASELINE,
    )
    region_train = aplicar_anomalias(region_train, baselines, baseline_nacional)
    region_test = aplicar_anomalias(region_test, baselines, baseline_nacional)

    reg_train_set = set(region_train["Region"])
    reg_test_set = set(region_test["Region"])
    regiones_nuevas = sorted(reg_test_set - reg_train_set)
    print(f"  Regiones sin baseline propio (usan baseline nacional): "
          f"{regiones_nuevas or 'ninguna'}")

    # -----------------------------------------------------------------------
    # 4. One-hot de Región + estacionalidad cíclica
    # -----------------------------------------------------------------------
    print("\n--- Codificación: one-hot de Región + estacionalidad cíclica ---")
    region_train, region_test, dummies_cols = codificar_region_onehot(
        region_train, region_test
    )
    for rdf in (region_train, region_test):
        rdf["Doy_Sin"] = np.sin(2 * np.pi * rdf["Fecha"].dt.dayofyear / 365.25)
        rdf["Doy_Cos"] = np.cos(2 * np.pi * rdf["Fecha"].dt.dayofyear / 365.25)

    FEATURE_COLS = FEATURES_BASE + FEATURES_ANOMALIA + FEATURES_ESTACIONALIDAD + dummies_cols
    print(f"  Columnas one-hot: {dummies_cols}")

    # Imputación de NaN (lags puntuales) con la MEDIANA calculada SOLO sobre
    # train — sin data leakage.
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
    print(f"  Features Etapa 1: {len(FEATURE_COLS)} "
          f"({len(FEATURES_BASE)} base + {len(FEATURES_ANOMALIA)} anomalías + "
          f"{len(FEATURES_ESTACIONALIDAD)} estacionalidad + {len(dummies_cols)} one-hot)")
    print(f"  Target: suma de Total por región | "
          f"mean={y_train.mean():.1f}, std={y_train.std():.1f}")

    # -----------------------------------------------------------------------
    # 5. Entrenamiento RF (misma config que v2/v3)
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
    print("\n📊 Top 12 features por importancia (Etapa 1):")
    imp = pd.DataFrame({
        "feature": FEATURE_COLS,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    for _, row in imp.head(12).iterrows():
        print(f"  {row['feature']:<30} {row['importance']:.4f}")

    # -----------------------------------------------------------------------
    # 6. ETAPA 2 — cuotas históricas desde TRAIN 2024
    # -----------------------------------------------------------------------
    print("\n--- Etapa 2: cuotas históricas por establecimiento (2024) ---")
    cuotas = calcular_cuotas(train_raw)
    print(f"  Establecimientos con cuota en train: {len(cuotas):,}")
    print(f"  Suma de cuotas por región ≈ "
          f"{cuotas.groupby('Region')['share'].sum().mean():.4f} (debe ser ≈ 1)")

    # -----------------------------------------------------------------------
    # 7. Evaluación del SISTEMA COMPLETO a nivel establecimiento
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
    # 7b. Diagnóstico: drift, ablación sin contaminación, comparación
    # -----------------------------------------------------------------------
    print("\n--- Diagnóstico ---")
    print(f"  Regiones en train: {sorted(reg_train_set)}")
    print(f"  Regiones NUEVAS en test (sin histórico): {regiones_nuevas or 'ninguna'}")

    # Métricas del sistema DESAGREGADAS por tipo de región
    estab_dia["es_region_nueva"] = ~estab_dia["Region"].isin(reg_train_set)
    for es_nueva, etiqueta in [(False, "regiones con histórico"), (True, "regiones nuevas")]:
        sub = estab_dia[estab_dia["es_region_nueva"] == es_nueva]
        if len(sub) == 0:
            continue
        m = _metricas(sub[TARGET].values, sub["pred"].values)
        print(f"  {etiqueta:<24} MAE={m['MAE']:8.3f}  R²={m['R2']:8.4f}  n={len(sub):,}")

    # Drift de contaminación (contexto para interpretar el sesgo)
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
        if pd.notna(row["MP2_5_train"]) and pd.notna(row["MP2_5_test"]):
            print(f"    {r:<20} {row['MP2_5_train']:6.1f} → {row['MP2_5_test']:6.1f}  "
                  f"({row['var_%']:+.1f}%)")

    # Ablación: mismo sistema SIN features de contaminación (ni absolutas ni
    # anomalías). Cuantifica si la contaminación POR ANOMALÍA aporta o no.
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
    print(f"    Nivel región:          MAE={met_region_clima['MAE']:8.3f}  "
          f"R²={met_region_clima['R2']:7.4f}  (vs {met_region['R2']:.4f} con contaminación)")
    print(f"    Nivel establecimiento: MAE={met_estab_clima['MAE']:8.3f}  "
          f"R²={met_estab_clima['R2']:7.4f}  (vs {met_estab['R2']:.4f} con contaminación)")

    # Segunda ablación: quitar SOLO los absolutos de contaminación y conservar
    # las anomalías. Aísla la pregunta: ¿la contaminación POR ANOMALÍA aporta?
    feats_solo_anomalias = [c for c in FEATURE_COLS if c not in ABS_CONTAMINACION]
    print(f"\n  Ablación — Etapa 1 con anomalías pero SIN absolutos de "
          f"contaminación ({len(feats_solo_anomalias)} features):")
    model_anom = RandomForestRegressor(
        n_estimators=200, max_depth=15, min_samples_split=50, min_samples_leaf=20,
        max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1,
    )
    model_anom.fit(region_train[feats_solo_anomalias], y_train)
    y_pred_anom = model_anom.predict(region_test[feats_solo_anomalias])
    met_region_anom = _metricas(y_test.values, y_pred_anom)
    _, met_estab_anom = repartir_y_evaluar(
        region_test, y_pred_anom, test_raw, cuotas_test
    )
    print(f"    Nivel región:          MAE={met_region_anom['MAE']:8.3f}  "
          f"R²={met_region_anom['R2']:7.4f}")
    print(f"    Nivel establecimiento: MAE={met_estab_anom['MAE']:8.3f}  "
          f"R²={met_estab_anom['R2']:7.4f}  "
          f"sesgo={met_estab_anom['sesgo_pct']:+.1f}%")

    # -----------------------------------------------------------------------
    # 8. Exportar artefactos
    # -----------------------------------------------------------------------
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / "model_rf_region_v4.joblib"
    features_path = MODELS_DIR / "features_region_v4.json"
    cuotas_path = MODELS_DIR / "cuotas_establecimiento_v4.csv"
    metadata_path = MODELS_DIR / "model_metadata_v4.json"

    joblib.dump(model, model_path)

    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(FEATURE_COLS, f, ensure_ascii=False, indent=2)

    cuotas_export = cuotas.copy()
    cuotas_export["Region"] = cuotas_export["Region"].astype(str)
    cuotas_export.to_csv(cuotas_path, index=False, encoding="utf-8")

    # Veredicto dinámico sobre la aportación de la contaminación
    solo_clima_mejor = (
        met_estab_clima["MAE"] < met_estab["MAE"]
        and met_estab_clima["R2"] > met_estab["R2"]
    )
    anomalias_mejoran = (
        met_estab_anom["MAE"] < met_estab_clima["MAE"]
        and met_estab_anom["R2"] > met_estab_clima["R2"]
    )
    if solo_clima_mejor:
        veredicto_contaminacion = (
            "HONESTO: la contaminación EMPEORA el sistema incluso en forma de "
            "anomalía (el solo-clima tiene mejor MAE y R² a nivel "
            "establecimiento que el v4 completo). Causa probable: el baseline "
            "está fijado en los niveles de 2024, por lo que el drift de MP2.5 "
            "(+26% a +57% entre 2024 y 2025) se filtra a las anomalías de test "
            "(anomalía media > 0 en 2025) y el modelo proyecta al alza la "
            "relación corto-plazo aprendida dentro de 2024."
        )
    else:
        veredicto_contaminacion = (
            "La contaminación por anomalía SÍ aporta: el v4 completo supera al "
            "solo-clima en MAE y R² a nivel establecimiento."
        )
    if not anomalias_mejoran:
        veredicto_contaminacion += (
            " Además, quitar solo los absolutos (conservando anomalías) tampoco "
            "mejora al solo-clima: el problema no es solo el nivel absoluto."
        )

    metadata = {
        "release": "modelo-v4",
        "arquitectura": "dos-etapas + anomalías estacionales",
        "granularidad_evaluacion": (
            "El dataset tiene ~4 filas por (establecimiento, Fecha) porque cada "
            "fila es una causa respiratoria distinta del archivo DEIS (la columna "
            "de causa se descartó al unificar). La demanda real de un "
            "establecimiento en un día es la SUMA de esas filas, por lo que la "
            "evaluación a nivel establecimiento se hace a nivel ESTABLECIMIENTO + DÍA."
        ),
        "explicacion": (
            "v4 conserva la arquitectura de dos etapas de v3 (Etapa 1 predice el "
            "total regional por día; Etapa 2 reparte por cuota histórica), pero "
            "corrige la causa raíz del fracaso de v3: la contaminación en nivel "
            "ABSOLUTO era señal espuria (proxy de la estación) con drift "
            "interanual de +26% a +57% en MP2.5 mientras la demanda bajaba ~5%, "
            "lo que sesgaba las predicciones al alza. v4 usa ANOMALÍAS "
            "(valor − baseline estacional de 2024) más estacionalidad cíclica "
            "explícita (Doy_Sin/Doy_Cos) y one-hot de región, de modo que el "
            "modelo separa el efecto estacional del efecto de la contaminación "
            "y es robusto al desplazamiento de niveles base entre años."
        ),
        "metodo_anomalias_anti_leakage": {
            "descripcion": (
                "El baseline estacional de cada variable (TempMin, MP2_5, MP10) "
                "se calcula SOLO con datos de train (2024): media por región × "
                "día-del-año (1..366), huecos interpolados linealmente y "
                "suavizado con ventana móvil CENTRAL de 15 días. Ese baseline se "
                "aplica a train y a test por (región, día-del-año de la fecha). "
                "anomalía = valor absoluto − baseline. Nunca se usa información "
                "de test (2025) para calcular los baselines."
            ),
            "ventana_suavizado_dias": VENTANA_BASELINE,
            "variables": VARIABLES_ANOMALIA,
            "fallback_regiones_sin_baseline": (
                "Antofagasta y Atacama no existen en train 2024 (sus CSV SENAMHI "
                "2024 tienen columnas Instante/RRR6 y filter_and_clean() los "
                "descarta), por lo que se les asigna el baseline NACIONAL: "
                "promedio entre las curvas suavizadas de las 6 regiones de train."
            ),
            "absolutos_conservados": (
                "Se conserva TempMin en nivel absoluto porque el frío absoluto "
                "es fisiológicamente relevante y su drift interanual es pequeño. "
                "Los absolutos MP2_5 y MP10 se REEMPLAZAN por sus anomalías."
            ),
        },
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
        "comparacion_v2_v3_v4": {
            "nota": (
                "Todas las métricas a nivel ESTABLECIMIENTO + DÍA sobre test 2025 "
                "(granularidad comparable). v2 y v3 son valores de referencia ya "
                "verificados en sesiones anteriores."
            ),
            "v2_nivel_establecimiento_dia": {
                "MAE": 17.437, "RMSE": 24.260, "R2": 0.0427, "sesgo_pct": 17.3,
            },
            "v3_nivel_establecimiento_dia": {
                "MAE": 20.119, "RMSE": 42.796, "R2": -1.979, "sesgo_pct": 34.6,
            },
            "v4_nivel_establecimiento_dia": met_estab,
            "referencia_ablacion_v3_sin_contaminacion": {
                "MAE": 12.7, "R2": 0.4460,
                "nota": (
                    "Ablación de v3 sin features de contaminación absoluta "
                    "(referencia verificada en sesiones anteriores)."
                ),
            },
        },
        "diagnostico": {
            "hallazgo_contaminacion_spuria": (
                "En v3 la contaminación en nivel absoluto correlacionaba con la "
                "demanda DENTRO de 2024 porque ambas cosas suben en invierno "
                "(proxy de la estación), no porque la contaminación cause la "
                "demanda de forma aislada. Entre 2024 y 2025 el MP2.5 subió +26% "
                "a +57% en 5 de 6 regiones mientras la demanda bajó ~5%: el RF "
                "extrapoló la correlación espuria con sesgo fuerte positivo "
                "(+34.6% en v3). v4 usa anomalías (robustas al nivel base) y "
                "estacionalidad cíclica explícita para que el modelo separe "
                "'efecto invierno' de 'efecto contaminación'."
            ),
            "regiones_nuevas_en_test": regiones_nuevas,
            "establecimientos_test_sin_cuota": int(n_nuevos),
            "drift_MP2_5": {
                r: {"train_2024": round(float(row["MP2_5_train"]), 2),
                    "test_2025": round(float(row["MP2_5_test"]), 2),
                    "var_pct": round(float(row["var_%"]), 1)}
                for r, row in drift.iterrows()
                if pd.notna(row["MP2_5_train"]) and pd.notna(row["MP2_5_test"])
            },
            "ablation_v4_sin_contaminacion": {
                "features": feats_solo_clima,
                "nivel_region": met_region_clima,
                "nivel_establecimiento": met_estab_clima,
                "lectura": (
                    "Compara el sistema v4 CON y SIN features de contaminación "
                    "(anomalías + lag + flags + rolling). Si MAE/R² con "
                    "contaminación son mejores, la anomalía aporta señal real; "
                    "si son peores, la contaminación sigue siendo ruido/drift "
                    "incluso en forma de anomalía."
                ),
            },
            "ablation_v4_anomalias_solo": {
                "features": feats_solo_anomalias,
                "nivel_region": met_region_anom,
                "nivel_establecimiento": met_estab_anom,
                "lectura": (
                    "Quita SOLO los absolutos de contaminación (MP2_5_Lag_2D, "
                    "Alerta_MP25_Flag, Region_Media_7d_MP25) conservando las "
                    "anomalías Anom_MP2_5 / Anom_MP10. Aísla el efecto de las "
                    "anomalías puras sobre el sistema completo."
                ),
            },
            "veredicto_contaminacion": veredicto_contaminacion,
            "correcciones_respecto_v3": [
                "1. Contaminación por ANOMALÍA (valor − baseline estacional "
                "2024) en vez de absoluto: elimina el proxy-estación y el drift "
                "de nivel base.",
                "2. Estacionalidad explícita Doy_Sin/Doy_Cos: en v3 el RF no "
                "tenía forma de representar el ciclo anual (un baseline de media "
                "histórica por región le ganaba en R²).",
                "3. One-hot de Región en vez de LabelEncoder: v3 trataba la "
                "región como número continuo con un orden falso.",
                "4. Se elimina Cat_TempMin_Encoded (100% redundante con TempMin).",
            ],
        },
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ RE-ENTRENAMIENTO COMPLETADO (modelo v4, dos etapas + anomalías)")
    print(f"  Modelo Etapa 1: {model_path}")
    print(f"  Features:       {features_path}")
    print(f"  Cuotas Etapa 2: {cuotas_path}")
    print(f"  Metadata:       {metadata_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
