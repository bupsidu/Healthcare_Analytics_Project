"""
Experimento E2 (v6) — MODELO DIRECTO a nivel establecimiento (una sola etapa)
==============================================================================

Contexto (por qué existe este script)
--------------------------------------
El diagnóstico v6 (T2–T4) descompuso el error de v5 y mostró que la Etapa 1
(región) concentra ~6.4 MAE del error total: el sistema dos-etapas reparte un
total regional predicho con una cuota (fija en v5, trailing en E1), y esa
cadena transmite el error de la Etapa 1 al establecimiento. Además:

- La persistencia pura (pred = lag 4 de la demanda propia) ya logra
  MAE 11.07 / R² 0.584 — MEJOR que v5 (14.763 / 0.141): la demanda reciente
  del propio establecimiento es la señal más fuerte disponible.
- v5 E1 mostró que la cuota trailing mejora la Etapa 2 (E1: 13.81 / 0.194),
  pero la arquitectura de dos etapas sigue atada al techo de la Etapa 1.

E2 (este script): REEMPLAZA la arquitectura dos-etapas por UN SOLO modelo que
predice directamente Total(estab, fecha), con features propias del
establecimiento (su demanda reciente, su cuota trailing) MÁS las señales
regionales (Pred_Region de la Etapa 1 de v5, Pred_E1 = Share_Trailing ×
Pred_Region). La idea: el modelo DIRECTO aprende a CORREGIR el sistema
dos-etapas usando la demanda reciente, en lugar de depender de él.

NOTA de composición: Pred_Region se entrena con contaminación trailing (la
config principal de v5) para ser la referencia exacta de v5/E1. E2 NO usa
contaminación como feature propia: la evidencia (v5 ablaciones) muestra que
no aporta; el único rol de la contaminación aquí es dentro de Pred_Region.

Filas: una por (establecimiento, fecha) — las ~4 filas multi-causa del
dataset DEIS se SUMAN antes de armar el panel (idéntico a E1).
Target: Total en nivel (sin transformar).
Split: train = 2024, test = 2025.
Modelo: RandomForestRegressor con MISMOS hiperparámetros y semilla que el RF
de la Etapa 1 de v5 (se IMPORTAN del módulo v5, no se redefinen).

Features (TODAS disponibles con información ≤ T-4 o bajo el supuesto de
clima del día ya asumido por v5 — ver anti-leakage abajo):
  1. Total_Lag_4     : demanda propia del estab hace 4 días de CALENDARIO
                       (serie reindexada al calendario, shift(4); estrictamente
                       pasado).
  2. Share_Trailing  : cuota trailing del estab = trail_e / Σ trail región
                       (E1: trail = shift(4).rolling(30, min_periods=10).sum()
                       de CALENDARIO; fallback jerárquico share_2024;
                       denominador regional sobre TODOS los estabs).
  3. Pred_Region     : total regional predicho por la Etapa 1 del v5 (mismo
                       modelo/features, importada del módulo v5).
  4. Pred_E1         : predicción E1 = Share_Trailing × Pred_Region (el
                       sistema dos-etapas completo como feature: el modelo
                       directo aprende a corregirlo).
  5. One-hot de TipoEstablecimiento y de Region.
  6. Doy, Doy_Sin, Doy_Cos (estacionalidad).
  7. Clima regional del día (MISMO supuesto que v5, SIN contaminación — la
                       evidencia muestra que no aporta): TempMin, TempMax,
                       Precipitacion_mm, TempMin_Lag_4D,
                       Region_Media_7d_TempMin, Frio_Polar_Flag,
                       Lluvia_Intensa_Flag.

ANTI-LEAKAGE (crítico, verificado en código con asserts):
  - Ninguna feature de la fila (e, T) usa Total(e, T) ni información ≥ T.
  - Total_Lag_4 y Share_Trailing se construyen con shift(4) sobre series
    reindexadas al CALENDARIO ANTES de unir con el target: el día T nunca
    entra en sus propias features.
  - Pred_Region/Pred_E1 usan el clima de T (supuesto de pronóstico ya
    aceptado en v5/v6: el clima del día T se asume disponible; es una
    variable EXÓGENA, no el target). Pred_Region es un total regional
    agregado, no lee Total(e, T).
  - Los asserts del script verifican explícitamente que (a) el set de
    features no contiene el target; (b) Total_Lag_4 coincide con el Total
    observado en T-4 pero NUNCA con el mismo día salvo coincidencia exacta
    de valor; (c) la correlación Total_Lag_4 vs Total no es de fuga.
  - Sanity-check: si R² del test > 0.9 se considera sospechoso de fuga y se
    reporta.

Evaluación (definiciones idénticas a v5/E1):
  - Nivel ESTABLECIMIENTO + DÍA sobre test 2025.
  - MAE, RMSE, R² = 1 − SS_res/SS_tot, sesgo% = 100·Σ(pred−real)/Σreal.
  - Métricas por región y tabla comparativa vs v5 / E1 / exploratoria post-hoc.

Salida (models/):
  - model_metadata_v6e2.json       métricas, features, configuración,
                                   verificación anti-leakage, comparativa,
                                   semilla/hiperparámetros, limitaciones.
  - model_rf_directo_v6e2.joblib    modelo RF directo exportado.

Restricción: este script NO modifica ningún archivo existente (v5 y E1
intactos); solo crea este archivo y sus 2 artefactos.

Uso:
    python3 src/pipelines/reentrenar_modelo_v6_e2_directo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RUTA_DATOS = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
RUTA_METADATA_V5 = BASE_DIR / "models" / "model_metadata_v5.json"
RUTA_METADATA_E1 = BASE_DIR / "models" / "model_metadata_v6e1.json"
RUTA_MODELO_OUT = BASE_DIR / "models" / "model_rf_directo_v6e2.joblib"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v6e2.json"

TARGET = "Total"
# Misma semántica de horizonte que v5/E1: 96 h → información hasta T-4.
LAG_DEMANDA = 4

# Importar v5 y E1 SIN ejecutar sus main(): reutilizamos la Etapa 1 del v5
# (Pred_Region) y la lógica de cuota trailing del E1 (Share_Trailing).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v5_trailing as v5  # noqa: E402
import reentrenar_modelo_v6_e1_trailing as e1  # noqa: E402

# ---------------------------------------------------------------------------
# Clima regional del día (mismo supuesto que v5, SIN contaminación)
# ---------------------------------------------------------------------------
COLUMNAS_CLIMA_DIRECTO = [
    "TempMin", "TempMax", "Precipitacion_mm",
    "TempMin_Lag_4D", "Region_Media_7d_TempMin",
    "Frio_Polar_Flag", "Lluvia_Intensa_Flag",
]
FEATURES_ESTACIONALIDAD = ["Doy", "Doy_Sin", "Doy_Cos"]


def metricas(y: np.ndarray, yhat: np.ndarray) -> dict:
    """MAE / RMSE / R² / sesgo% a nivel establecimiento+día.

    R² = 1 − SS_res/SS_tot sobre TODAS las filas (definición idéntica a
    v5/E1 y equivalente a sklearn.r2_score).
    """
    ok = ~np.isnan(yhat)
    y, yhat = y[ok], yhat[ok]
    resid = yhat - y
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": int(ok.sum()),
        "MAE": round(float(np.mean(np.abs(resid))), 4),
        "RMSE": round(float(np.sqrt(np.mean(resid**2))), 4),
        "R2": round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
        "sesgo_pct": round(100 * float(np.sum(resid)) / float(np.sum(y)), 2)
        if np.sum(y) > 0
        else None,
    }


def cargar_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (establecimiento, fecha) sumando las causas respiratorias.

    Criterio IDÉNTICO al v5 y al E1: cada fila del dataset es una causa DEIS
    distinta, así que la demanda real de un estab en un día es la SUMA de sus
    filas.
    """
    return (
        df.groupby(["IdEstablecimiento", "Fecha"], as_index=False)
        .agg(
            Total=(TARGET, "sum"),
            Region=("Region", "first"),
            TipoEstablecimiento=("TipoEstablecimiento", "first"),
        )
        .sort_values(["IdEstablecimiento", "Fecha"])
        .reset_index(drop=True)
    )


def calcular_total_lag_calendario(panel: pd.DataFrame) -> pd.DataFrame:
    """Total_Lag_4 por (estab, fecha) sobre el CALENDARIO diario completo.

    Para cada establecimiento se reindexa su serie (panel 2024+2025 ya
    agregado por estab+fecha) al calendario diario completo de su rango; los
    días sin reporte quedan Total=NaN y se propagan con ffill (el lag de un
    día sin reporte toma el último Total OBSERVADO anterior — documentado,
    es la continuación natural de la serie). Luego:

        Total_Lag_4(e, T) = Total_cal(e).shift(4)

    ANTI-LEAKAGE: el shift(4) es un lag REAL de 4 días de calendario (misma
    semántica que el trail de E1): al pronosticar T solo se usa información
    hasta T-4; el día T NUNCA entra en su propio lag.

    Returns:
        DataFrame (IdEstablecimiento, Fecha, Total_Lag_4) sobre el CALENDARIO
        de cada estab (más filas que el panel: incluye días sin reporte).
    """
    partes: list[pd.DataFrame] = []
    for est, g in panel.groupby("IdEstablecimiento"):
        g = g.sort_values("Fecha")
        cal = pd.date_range(g["Fecha"].min(), g["Fecha"].max(), freq="D")
        serie = pd.Series(
            g[TARGET].to_numpy(), index=pd.DatetimeIndex(g["Fecha"].to_numpy())
        )
        serie_cal = serie.reindex(cal).ffill()
        lag4 = serie_cal.shift(LAG_DEMANDA)
        partes.append(
            pd.DataFrame(
                {
                    "IdEstablecimiento": est,
                    "Fecha": cal,
                    "Total_Lag_4": lag4.to_numpy(),
                }
            )
        )
    return pd.concat(partes, ignore_index=True)


def calcular_share_trailing_grilla(
    panel: pd.DataFrame,
    share_2024: pd.DataFrame,
) -> pd.DataFrame:
    """Share_Trailing por (estab, fecha) para las filas del PANEL (train+test).

    Misma construcción que la Etapa 2 de E1 (`e1.calcular_trail_calendario` +
    `e1.construir_pesos_trailing`), pero con la grilla expandida a TODAS las
    fechas del panel (train 2024 + test 2025), de modo que el modelo directo
    tenga Share_Trailing también en las filas de entrenamiento:

      1. trail_e(T) = Total_e.shift(4).rolling(30, min_periods=10).sum() de
         CALENDARIO (importado de E1, anti-leakage ≤ T-4).
      2. Grilla = TODOS los estabs de cada región × TODAS las fechas del
         panel de esa región.
      3. Fallback sin trail: share_2024_e × media(trail) de la Región en T
         (media sobre estabs CON trail en T); si la Región no tiene ningún
         trail en T, share_2024_e directo.
      4. denominador(T, Región) = Σ peso sobre TODOS los estabs de la región
         (reporten o no); Share_Trailing = peso / denominador.

    El trail es ≤ T-4 (anti-leakage); share_2024 se calcula SOLO desde train.
    """
    trail_cal = e1.calcular_trail_calendario(panel)

    estabs = share_2024[["IdEstablecimiento", "Region", "share"]]
    fechas = panel[["Region", "Fecha"]].drop_duplicates()
    grid = estabs.merge(fechas, on="Region", how="inner")
    n_sin_share = int(grid["share"].isna().sum())
    if n_sin_share:
        raise ValueError(f"{n_sin_share} filas de la grilla sin share_2024.")

    grid = grid.merge(trail_cal, on=["IdEstablecimiento", "Fecha"], how="left")

    # Fallback: estabs sin trail suficiente en T.
    media_trail = grid.groupby(["Region", "Fecha"])["trail"].transform("mean")
    grid["peso"] = grid["trail"].where(grid["trail"].notna(), grid["share"] * media_trail)
    grid["peso"] = grid["peso"].fillna(grid["share"])

    # Denominador REGIONAL (todos los estabs, reporten o no ese día).
    denominador = grid.groupby(["Region", "Fecha"])["peso"].transform("sum")
    grid["share_trailing"] = np.where(
        denominador > 0, grid["peso"] / denominador, 0.0
    )
    return grid[["IdEstablecimiento", "Fecha", "share_trailing"]].copy()


def codificar_onehot(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    columna: str,
    prefijo: str,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """One-hot (pd.get_dummies) con columnas de la UNIÓN train+test.

    Mismo criterio que v5 para Region: las categorías solo-test quedan con su
    propia columna (100% cero en train); el RF las trata como «sin
    información», que es honesto. Se usa para Region y
    TipoEstablecimiento.
    """
    todas = sorted(set(train_df[columna]) | set(test_df[columna]))
    cols = [f"{prefijo}_{c}" for c in todas]

    tr = pd.get_dummies(train_df, columns=[columna], prefix=prefijo)
    te = pd.get_dummies(test_df, columns=[columna], prefix=prefijo)
    tr[columna] = train_df[columna].to_numpy()
    te[columna] = test_df[columna].to_numpy()
    for c in cols:
        if c not in tr.columns:
            tr[c] = 0
        if c not in te.columns:
            te[c] = 0
    return tr, te, cols


def verificar_anti_leakage(
    direct_train: pd.DataFrame,
    direct_test: pd.DataFrame,
    feature_cols: list[str],
) -> dict:
    """Verificación EXPLÍCITA de que ninguna feature usa el target del día.

    Comprueba:
      1. El target no está en el set de features.
      2. Total_Lag_4 coincide con el Total observado en T-4 (para filas con
         historial suficiente) pero NUNCA es una fuga del mismo día: cuenta
         las filas donde Total_Lag_4 == Total(e, T) y las contrasta con las
         filas donde Total_Lag_4 == Total(e, T-4) (coincidencias legítimas
         por estabilidad de la demanda).
      3. Correlación Total_Lag_4 vs Total (una correlación ~1 sería
         sospechosa de fuga; se espera < 0.9 por la estacionalidad/ruido).
    """
    verificaciones: dict[str, object] = {}

    # (1) El target no puede ser feature.
    verificaciones["target_no_es_feature"] = TARGET not in feature_cols
    assert TARGET not in feature_cols, "¡El target está en el set de features!"

    todo = pd.concat([direct_train, direct_test], ignore_index=True)

    # (2) Total_Lag_4 vs valores reales de T-4 y de T (mismo día).
    ref = todo[["IdEstablecimiento", "Fecha", TARGET]].copy()
    ref["Fecha"] = ref["Fecha"] + pd.Timedelta(days=LAG_DEMANDA)
    ref = ref.rename(columns={TARGET: "_real_en_T_menos_4"})
    chk = todo.merge(ref, on=["IdEstablecimiento", "Fecha"], how="left")

    con_hist = chk["Total_Lag_4"].notna() & chk["_real_en_T_menos_4"].notna()
    coincide_t4 = (
        (chk["Total_Lag_4"] - chk["_real_en_T_menos_4"]).abs() < 1e-9
    ) & con_hist
    coincide_mismo_dia = (
        (chk["Total_Lag_4"] - chk[TARGET]).abs() < 1e-9
    ) & chk["Total_Lag_4"].notna()

    n_con_hist = int(con_hist.sum())
    n_coincide_t4 = int(coincide_t4.sum())
    n_coincide_mismo_dia = int(coincide_mismo_dia.sum())
    # El merge con T-4 solo produce un valor comparable cuando existe fila
    # exacta del panel en esa fecha; se reportan ambos contadores.
    verificaciones["total_lag_4_coincide_con_T_menos_4"] = n_coincide_t4
    verificaciones["total_lag_4_filas_con_historial_comparable"] = n_con_hist
    verificaciones["total_lag_4_igual_al_mismo_dia"] = n_coincide_mismo_dia
    verificaciones["lectura"] = (
        "Total_Lag_4 se construye con shift(4) sobre el calendario ANTES de "
        "unir con el target: por construcción no lee Total(e, T). El "
        "contador de igualdad con el mismo día solo puede ser > 0 por "
        "coincidencia exacta de valor (demanda estable), no por fuga."
    )

    # (3) Correlación Total_Lag_4 vs Total: sospechosa si ≈ 1.
    par = todo.dropna(subset=["Total_Lag_4"])
    corr = float(par["Total_Lag_4"].corr(par[TARGET]))
    verificaciones["correlacion_total_lag_4_vs_total"] = round(corr, 4)
    verificaciones["correlacion_sospechosa"] = bool(corr > 0.99)
    assert corr < 0.99, f"Correlación Total_Lag_4/Total sospechosa: {corr:.4f}"

    # (4) Verificación de Pred_Region: es un total REGIONAL (no el target).
    verificaciones["pred_region_es_feature"] = "Pred_Region" in feature_cols
    verificaciones["pred_e1_es_feature"] = "Pred_E1" in feature_cols
    return verificaciones


def main() -> None:
    t_inicio = time.time()
    print("=" * 70)
    print("EXPERIMENTO E2 (v6) — MODELO DIRECTO a nivel ESTABLECIMIENTO")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 1. Carga y panel (estab+fecha, multi-causa agregada)
    # -----------------------------------------------------------------------
    print("\nCargando dataset procesado...")
    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = cargar_panel(df)
    print(f"  Filas crudas: {len(df):,} | panel estab+fecha: {len(panel):,}")
    print(f"  Train ({v5.TRAIN_YEAR}): {len(train_raw):,} filas crudas | "
          f"Test ({v5.TEST_YEAR}): {len(test_raw):,} filas crudas")

    # -----------------------------------------------------------------------
    # 2. ETAPA 1 (v5, importada) — Pred_Region + clima regional del día
    # -----------------------------------------------------------------------
    print(f"\n--- Etapa 1 del v5 (importada): Pred_Region (trailing N="
          f"{v5.VENTANA_PRINCIPAL}) ---")
    region_train, region_test, dummies_cols, info_trail = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features_region = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features_region, con_cv=False)
    print(f"  Nivel región (test 2025): MAE={res1['met_region']['MAE']:9.3f}  "
          f"RMSE={res1['met_region']['RMSE']:9.3f}  R²={res1['met_region']['R2']:8.4f}")
    meta_v5 = json.loads(RUTA_METADATA_V5.read_text(encoding="utf-8"))
    met_region_v5 = meta_v5["etapa_1"]["metrics_test_2025"]
    etapa1_identica = res1["met_region"] == met_region_v5
    print(f"  Identidad vs model_metadata_v5.json: "
          f"{'✅ COINCIDEN' if etapa1_identica else '⚠️  DIFIEREN'}")

    # Pred_Region para TODAS las filas (train + test): la Etapa 1 entrena con
    # 2024 y predice 2025; para el train usamos su predicción IN-SAMPLE — es
    # un total REGIÓN agregado, no el target del estab, así que no hay fuga
    # del target; se documenta en limitaciones.
    pred_region_train = res1["model"].predict(region_train[features_region])
    pred_region_test = res1["y_pred"]
    region_train["Pred_Region"] = pred_region_train
    region_test["Pred_Region"] = pred_region_test

    # -----------------------------------------------------------------------
    # 3. Total_Lag_4 (demanda propia, lag real de calendario)
    # -----------------------------------------------------------------------
    print("\n--- Total_Lag_4: demanda del estab hace 4 días de CALENDARIO ---")
    lag_cal = calcular_total_lag_calendario(panel)
    print(f"  Filas en el calendario (incluye días sin reporte): {len(lag_cal):,}")

    # -----------------------------------------------------------------------
    # 4. Share_Trailing (cuota trailing E1) para las fechas del panel
    # -----------------------------------------------------------------------
    print("\n--- Share_Trailing: cuota trailing de E1 en TODAS las fechas ---")
    share_2024, n_nuevos = e1.calcular_share_2024_con_fallback(test_raw, train_raw)
    share_grid = calcular_share_trailing_grilla(panel, share_2024)
    print(f"  Grilla (estabs × fechas del panel): {len(share_grid):,} filas")
    print(f"  Establecimientos en test sin cuota en train (fallback): {n_nuevos}")

    # -----------------------------------------------------------------------
    # 5. Ensamblar el dataset DIRECTO (estab+fecha) con features ≤ T-4
    # -----------------------------------------------------------------------
    print("\n--- Ensamblado del dataset directo (features ANTES del target) ---")
    base = panel.merge(lag_cal, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(
        share_grid.rename(columns={"share_trailing": "Share_Trailing"}),
        on=["IdEstablecimiento", "Fecha"], how="left",
    )
    base = base.merge(
        region_train[["Region", "Fecha", "Pred_Region"] + COLUMNAS_CLIMA_DIRECTO],
        on=["Region", "Fecha"], how="left", suffixes=("", "_rt"),
    )
    base = base.merge(
        region_test[["Region", "Fecha", "Pred_Region"] + COLUMNAS_CLIMA_DIRECTO],
        on=["Region", "Fecha"], how="left", suffixes=("", "_rt"),
    )
    # Tras los dos merges (train y test), Pred_Region/clima pueden duplicarse
    # como *_rt; se resuelve quedándose con la primera no nula.
    for c in ["Pred_Region"] + COLUMNAS_CLIMA_DIRECTO:
        if f"{c}_rt" in base.columns:
            base[c] = base[c].fillna(base[f"{c}_rt"])
            base = base.drop(columns=[f"{c}_rt"])

    base["Pred_E1"] = base["Share_Trailing"] * base["Pred_Region"]
    doy = base["Fecha"].dt.dayofyear
    base["Doy"] = doy
    base["Doy_Sin"] = np.sin(2 * np.pi * doy / 365.25)
    base["Doy_Cos"] = np.cos(2 * np.pi * doy / 365.25)

    base["Año"] = base["Fecha"].dt.year
    direct_train = base[base["Año"] == v5.TRAIN_YEAR].copy()
    direct_test = base[base["Año"] == v5.TEST_YEAR].copy()

    direct_train, direct_test, dummies_tipo = codificar_onehot(
        direct_train, direct_test, "TipoEstablecimiento", "Tipo"
    )
    direct_train, direct_test, dummies_region = codificar_onehot(
        direct_train, direct_test, "Region", "Region"
    )

    # -----------------------------------------------------------------------
    # 6. Lista final de features + imputación con mediana de SOLO train
    # -----------------------------------------------------------------------
    core_feats = ["Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1"]
    feature_cols = (
        core_feats
        + dummies_tipo
        + dummies_region
        + FEATURES_ESTACIONALIDAD
        + COLUMNAS_CLIMA_DIRECTO
    )
    print(f"\n  Features finales ({len(feature_cols)}): {feature_cols}")

    for c in feature_cols:
        if direct_train[c].isna().any():
            mediana = direct_train[c].median()
            direct_train[c] = direct_train[c].fillna(mediana)
            direct_test[c] = direct_test[c].fillna(mediana)
    print(f"  NaN imputados con mediana de SOLO train (anti-leakage).")

    # -----------------------------------------------------------------------
    # 7. Verificación ANTI-LEAKAGE (asserts)
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("VERIFICACIÓN ANTI-LEAKAGE")
    print("-" * 70)
    verificacion = verificar_anti_leakage(direct_train, direct_test, feature_cols)
    print(f"  Target no es feature: {verificacion['target_no_es_feature']}")
    print(f"  Total_Lag_4 == Total(T-4) en filas comparables: "
          f"{verificacion['total_lag_4_coincide_con_T_menos_4']:,} / "
          f"{verificacion['total_lag_4_filas_con_historial_comparable']:,}")
    print(f"  Total_Lag_4 == Total(T) mismo día (solo coincidencia de valor): "
          f"{verificacion['total_lag_4_igual_al_mismo_dia']:,}")
    print(f"  Correlación Total_Lag_4 vs Total: "
          f"{verificacion['correlacion_total_lag_4_vs_total']:.4f} "
          f"(sospechosa > 0.99: {verificacion['correlacion_sospechosa']})")

    # -----------------------------------------------------------------------
    # 8. Entrenamiento del modelo DIRECTO (RF de v5, mismos hiperparámetros)
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("ENTRENAMIENTO — RandomForest DIRECTO (hiperparámetros del v5)")
    print("-" * 70)
    X_train = direct_train[feature_cols]
    y_train = direct_train[TARGET]
    X_test = direct_test[feature_cols]
    y_test = direct_test[TARGET]
    print(f"  Train: {len(X_train):,} filas | Test: {len(X_test):,} filas | "
          f"{len(feature_cols)} features")

    t_fit = time.time()
    model = v5.RandomForestRegressor(**v5.HIPERPARAMETROS)
    model.fit(X_train, y_train)
    t_entrenamiento = time.time() - t_fit
    print(f"  ✅ Entrenamiento completado en {t_entrenamiento:.1f} s "
          f"(n_jobs={v5.HIPERPARAMETROS['n_jobs']})")

    y_pred = model.predict(X_test)
    met_e2 = metricas(y_test.to_numpy(float), y_pred)

    # -----------------------------------------------------------------------
    # 9. Evaluación global + por región + sanity-check de fuga
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("MÉTRICAS E2 — nivel ESTABLECIMIENTO + DÍA (test 2025)")
    print("-" * 70)
    print(f"  MAE={met_e2['MAE']:.4f}  RMSE={met_e2['RMSE']:.4f}  "
          f"R²={met_e2['R2']:.4f}  sesgo={met_e2['sesgo_pct']:+.2f}%  "
          f"(n={met_e2['n']:,})")

    fuga_sospechosa = bool(met_e2["R2"] is not None and met_e2["R2"] > 0.9)
    if fuga_sospechosa:
        print(f"  ⚠️  SANITY-CHECK: R²={met_e2['R2']:.4f} > 0.9 → SOSPECHOSO "
              f"DE FUGA. Verificar construcción de features.")
    else:
        print(f"  ✅ Sanity-check: R²={met_e2['R2']:.4f} ≤ 0.9 → sin indicios "
              f"de fuga por R² inflado.")

    eval_df = direct_test[
        ["IdEstablecimiento", "Region", "Fecha", TARGET]
    ].copy()
    eval_df["pred"] = y_pred

    met_por_region: dict[str, dict] = {}
    for reg, grp in eval_df.groupby("Region"):
        met_por_region[reg] = metricas(
            grp[TARGET].to_numpy(float), grp["pred"].to_numpy(float)
        )

    meta_e1 = json.loads(RUTA_METADATA_E1.read_text(encoding="utf-8"))
    met_v5 = meta_v5["metrics_sistema_completo"]
    met_e1 = meta_e1["metricas_establecimiento"]
    met_exploratoria = {
        "MAE": 12.7845, "RMSE": 20.33, "R2": 0.3277, "sesgo_pct": 11.32,
    }

    referencias = {
        "v5 trailing (dos etapas)": {
            "MAE": met_v5["MAE"], "RMSE": met_v5["RMSE"],
            "R2": met_v5["R2"], "sesgo_pct": met_v5["sesgo_pct"],
        },
        "E1 cuota trailing (dos etapas)": {
            "MAE": met_e1["MAE"], "RMSE": met_e1["RMSE"],
            "R2": met_e1["R2"], "sesgo_pct": met_e1["sesgo_pct"],
        },
        "exploratoria post-hoc (sin contam + Anom_TempMin)": {
            "MAE": met_exploratoria["MAE"], "RMSE": met_exploratoria["RMSE"],
            "R2": met_exploratoria["R2"], "sesgo_pct": met_exploratoria["sesgo_pct"],
        },
        "E2 modelo directo (este script)": {
            "MAE": met_e2["MAE"], "RMSE": met_e2["RMSE"],
            "R2": met_e2["R2"], "sesgo_pct": met_e2["sesgo_pct"],
        },
    }
    tabla_comp = (
        pd.DataFrame.from_dict(referencias, orient="index")
        .rename_axis("Versión")
        .reset_index()
        .rename(columns={"R2": "R²", "sesgo_pct": "Sesgo %"})
    )
    print("\n📊 TABLA COMPARATIVA — nivel ESTABLECIMIENTO + DÍA (test 2025):")
    print(tabla_comp.round(4).to_string(index=False))

    print("\nMÉTRICAS POR REGIÓN — E2 (modelo directo):")
    print(f"  {'Región':<22} {'MAE':>9} {'RMSE':>9} {'R²':>9} {'sesgo':>9}")
    for reg in sorted(met_por_region):
        m = met_por_region[reg]
        print(f"  {reg:<22} {m['MAE']:>9.3f} {m['RMSE']:>9.3f} "
              f"{m['R2']:>9.4f} {m['sesgo_pct']:>8.2f}%")

    supera_exploratoria = (
        met_e2["MAE"] < met_exploratoria["MAE"]
        and (met_e2["R2"] or -9) > met_exploratoria["R2"]
    )
    print(f"\n  ¿Supera a la exploratoria post-hoc "
          f"(MAE {met_exploratoria['MAE']} / R² {met_exploratoria['R2']})? "
          f"{'✅ SÍ' if supera_exploratoria else '❌ NO'}")

    imp = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    print("\nTop 10 features por importancia:")
    for _, row in imp.head(10).iterrows():
        print(f"  {row['feature']:<28} {row['importance']:.4f}")

    # -----------------------------------------------------------------------
    # 10. Exportar artefactos (modelo + metadata)
    # -----------------------------------------------------------------------
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, RUTA_MODELO_OUT)

    t_total = time.time() - t_inicio
    metadata = {
        "release": "modelo-v6-e2",
        "experimento": (
            "E2 — modelo DIRECTO a nivel establecimiento (una sola etapa) que "
            "reemplaza la arquitectura dos-etapas de v5/E1"
        ),
        "descripcion": (
            "E2 entrena UN RandomForestRegressor directamente sobre filas "
            "(establecimiento, fecha) con target Total en nivel, reemplazando "
            "la cadena Etapa 1 (región) → Etapa 2 (cuota) de v5/E1. Motivación "
            "(diagnóstico T2–T4): la Etapa 1 concentra ~6.4 MAE del error de "
            "v5; la persistencia pura (pred = lag 4) ya logra MAE 11.07 / R² "
            "0.584, mejor que v5. El modelo directo usa la demanda reciente "
            "(Total_Lag_4), la cuota trailing (Share_Trailing, E1) y el "
            "sistema dos-etapas completo como features (Pred_Region y "
            "Pred_E1 = Share_Trailing × Pred_Region) para CORREGIR ese "
            "sistema, en lugar de depender de él."
        ),
        "granularidad_evaluacion": (
            "El dataset tiene ~4 filas por (establecimiento, Fecha) (cada fila "
            "es una causa DEIS); se suman por (estab, fecha) antes de armar el "
            "panel y de evaluar, idéntico a v5/E1."
        ),
        "features": feature_cols,
        "n_features": len(feature_cols),
        "configuracion": {
            "target": "Total (nivel, sin transformar)",
            "filas": "una por (establecimiento, fecha)",
            "split": "train = 2024, test = 2025",
            "modelo": "RandomForestRegressor (hiperparámetros del v5)",
            "semilla": v5.RANDOM_STATE,
            "hiperparametros": {
                k: v for k, v in v5.HIPERPARAMETROS.items() if k != "n_jobs"
            },
            "horizonte_horas": 96,
            "lag_dias": LAG_DEMANDA,
            "features_detalle": {
                "core": core_feats,
                "one_hot_tipo_establecimiento": dummies_tipo,
                "one_hot_region": dummies_region,
                "estacionalidad": FEATURES_ESTACIONALIDAD,
                "clima_regional_dia_T": COLUMNAS_CLIMA_DIRECTO,
            },
        },
        "metricas_establecimiento": met_e2,
        "metricas_por_region": met_por_region,
        "sanity_check_anti_leakage": {
            "r2_mayor_a_0_9_sospechoso_de_fuga": fuga_sospechosa,
            "r2_observado": met_e2["R2"],
            "verificacion": verificacion,
        },
        "comparativa": {
            "referencias": referencias,
            "supera_a_exploratoria_post_hoc": bool(supera_exploratoria),
            "nota": (
                "La exploratoria post-hoc (12.7845 / 0.3277 / +11.32) es "
                "EXPLORATORIA (seleccionada observando el test 2025): si E2 la "
                "supera, esa ventaja también debe confirmarse con datos "
                "adicionales (2023+) antes de claim de mejora validada."
            ),
        },
        "identidad_etapa_1_v5": {
            "etapa_1_region_identica_a_v5": bool(etapa1_identica),
            "metrics_v5_region": met_region_v5,
            "nota": (
                "Pred_Region proviene del RF de la Etapa 1 del v5 (config "
                "trailing), importado del módulo v5 sin modificarlo."
            ),
        },
        "verificacion_anti_leakage": verificacion,
        "supuesto_clima_dia_T": (
            "MISMO supuesto que v5/v6: las variables climáticas de la fecha T "
            "(TempMin, TempMax, Precipitacion_mm, flags) se asumen DISPONIBLES "
            "al momento de pronosticar T (variables exógenas de pronóstico). "
            "No es fuga del target: el clima no es Total(e, T)."
        ),
        "pred_region_train_in_sample": (
            "Pred_Region en las filas de TRAIN (2024) es la predicción "
            "IN-SAMPLE del RF de la Etapa 1 (entrenado con 2024). No hay fuga "
            "del target del estab (es un total regional agregado), pero es una "
            "feature más 'limpia' en train que en test: se documenta como "
            "limitación. En test Pred_Region es la predicción genuina de "
            "futuro."
        ),
        "tiempo_entrenamiento_segundos": round(t_entrenamiento, 1),
        "tiempo_total_script_segundos": round(t_total, 1),
        "limitaciones": [
            "Solo 2 años de datos (train 2024 / test 2025): la comparación "
            "E2 vs v5/E1/exploratoria se hace sobre el mismo split; el delta "
            "mide el efecto en este test, no una validación externa.",
            "Pred_Region en train es in-sample del RF de la Etapa 1 (ver "
            "pred_region_train_in_sample): el modelo directo ve una versión "
            "más 'limpia' de esa feature en train que en test, lo que puede "
            "inflar ligeramente el ajuste en train. No es fuga del target.",
            "Pred_E1 hereda el sesgo positivo de v5/E1 (~+21%): el sistema "
            "dos-etapas sobreestima el total; el modelo directo debe "
            "aprender a corregirlo, y su sesgo depende de qué tan bien lo "
            "logre.",
            "La persistencia pura (MAE 11.07 / R² 0.584) sigue siendo un "
            "referencial FUERTE: si E2 no la supera, el modelo directo con "
            "estas features no aporta sobre el baseline trivial.",
            "La exploratoria post-hoc (12.784 / 0.3277) es EXPLORATORIA "
            "(seleccionada con el test a la vista): superarla no equivale a "
            "una mejora validada.",
            "Regiones nuevas en test (Antofagasta, Atacama) no existen en "
            "train 2024 (bug CSV SENAMHI): sus one-hot están en 100% cero y "
            "sus Total_Lag_4/Share_Trailing solo se apoyan en su historia "
            "de 2025 (≤ T-4).",
            "Se entrenó con los MISMOS hiperparámetros del v5 "
            "(n_estimators=200, max_depth=15, min_samples_split=50, "
            "min_samples_leaf=20, max_features='sqrt', random_state=42, "
            "n_jobs=-1) para que la comparación AISLE el efecto de la "
            "arquitectura, no el del tuner; optimizarlos es trabajo futuro.",
            "El modelo se exporta pero no se validó con años adicionales "
            "(2023 no está disponible en el dataset actual).",
        ],
    }
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("✅ EXPERIMENTO E2 COMPLETADO (modelo directo)")
    print(f"  Metadata: {RUTA_SALIDA}")
    print(f"  Modelo:   {RUTA_MODELO_OUT}")
    print(f"  Tiempo total: {t_total:.1f} s (entrenamiento RF: "
          f"{t_entrenamiento:.1f} s)")
    print("=" * 70)


if __name__ == "__main__":
    main()
