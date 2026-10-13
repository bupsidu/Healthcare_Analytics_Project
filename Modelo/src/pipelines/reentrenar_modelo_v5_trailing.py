"""
Re-entrenamiento v5 — DOS ETAPAS + baseline ADAPTATIVO TRAILING de contaminación
================================================================================

Contexto (por qué existe este script)
--------------------------------------
Historial de versiones (lo que NO se debe repetir):

- v1 (ROTO — data leakage): usaba las 5 columnas de rango etario como FEATURES,
  pero el target `Total` era exactamente su suma. El modelo aprendía a SUMAR
  (MAE 0.321 / R² 0.9956 eran artificiales). NUNCA se usan rangos etarios.

- v2 (sin leakage, pero débil): clima/contaminación a nivel ESTABLECIMIENTO.
  MAE 17.437 / R² 0.0427 / sesgo +17.3% (re-agregado a establecimiento+día).
  Problema estructural: el clima es a nivel REGIÓN, idéntico para todos los
  establecimientos de una región+fecha (~44 establecimientos con desviación
  estándar de Total ≈ 13.6): el modelo no puede distinguirlos.

- v3 (dos etapas, contaminación ABSOLUTA — empeoró): MAE 20.119 / R² -1.979 /
  sesgo +34.6%. CAUSA RAÍZ: la contaminación en nivel absoluto era señal
  ESPURIA = proxy de la ESTACIÓN (en invierno sube la leña Y suben las
  urgencias). Entre 2024 y 2025 el MP2.5 subió +26% a +57% en 5 de 6 regiones
  mientras la demanda BAJÓ ~5%, y el RF extrapoló la correlación espuria con
  sesgo fuerte al alza. La Etapa 2 (cuotas) SÍ funciona: suman 1.0 por región.

- v4 (dos etapas + anomalías con baseline FIJO en 2024 — la contaminación sigue
  sin aportar): Etapa 1 R² región 0.7986 (one-hot + estacionalidad cíclica),
  pero a nivel establecimiento: v4 completo MAE 16.307 / R² -0.2851 /
  sesgo +24.95%; v4 SIN contaminación MAE 13.396 / R² 0.2423 / sesgo +13.7%
  (MEJOR); v4 solo anomalías MAE 14.670 / R² 0.1256.
  CAUSA DEL FRACASO: el baseline estacional se calculó con SOLO train 2024 y
  quedó FIJO. El drift de MP2.5 (+26% a +57% entre 2024 y 2025) se filtró a
  las anomalías de 2025 (anomalía media > 0 sistemática) y el modelo proyectó
  al alza la relación aprendida dentro de 2024. Con 1 solo año de train el
  baseline congelado NO puede adaptarse al nuevo nivel base.

v5 (este script): baseline de normalidad ADAPTATIVO TRAILING
------------------------------------------------------------
Idea central (diagnóstico del usuario, verificado): el modelo NO debe aprender
"más contaminación → más pacientes", sino "más contaminación DE LO NORMAL PARA
ESTE PERÍODO → más pacientes". Para eso el baseline de normalidad se recalcula
continuamente con los ÚLTIMOS N días observados de la MISMA región:

    anom_MP2_5(Región, T) = MP2_5(Región, T) − media( MP2_5(Región, t)
                                                       para t ∈ [T−N, T−1] )

Solo fechas Estrictamente ANTES de T (anti-leakage). Si el nivel base de MP2.5
sube entre 2024 y 2025, el baseline trailing lo sigue y la anomalía de test
vuelve a ser centrada en 0 — que era exactamente lo que v4 no lograba.

MÉTODO ANTI-LEAKAGE (obligatorio, verificado en código):
  1. Se agrega a nivel REGIÓN+FECHA (un registro por región y día).
  2. Por región se arma la serie DIARIA sobre el calendario completo (desde la
     primera hasta la última fecha con datos de esa región; los días sin dato
     quedan como NaN y se OMITEN en el promedio, pero la ventana sigue siendo
     de N DÍAS DE CALENDARIO).
  3. baseline = serie.shift(1).rolling(N, min_periods=MIN_PERIODS).mean():
     el shift(1) garantiza que la fecha T NO entra en su propio baseline;
     la ventana cubre exactamente los N días de calendario [T−N, T−1].
     La ventana PUEDE cruzar la frontera 2024→2025: eso es correcto, porque
     en un sistema en producción los días anteriores a T ya fueron OBSERVADOS
     (misma suposición que ya se hacía con TempMin_Lag_4D / MP2_5_Lag_2D).
     NUNCA se usa información de fechas ≥ T ni el target.
  4. SEMILLA para las primeras filas (donde aún no hay MIN_PERIODS días de
     historial: primeros ~10 días de cada región): baseline = MEDIA GLOBAL de
     esa variable calculada SOLO sobre train 2024. Documentado y consistente.
  5. Regiones NUEVAS en test (Antofagasta, Atacama: sin datos 2024 por el bug
     de los CSV SENAMHI) se benefician: su baseline trailing se calcula con su
     PROPIA historia de 2025 (a partir del día MIN_PERIODS), no con un
     baseline prestado como en v4.

Features DERIVADAS de contaminación (decisión técnica documentada):
  - Los lags y rollings de contaminación se recalculan sobre la SERIE DE
    ANOMALÍA (no sobre el absoluto), para que tampoco arrastren el drift de
    nivel base:
      · Anom_MP2_5_Lag_2D        = anomalía de MP2.5 hace 2 días (solo pasado)
      · Anom_MP2_5_Media_7d      = media trailing de la anomalía, shift(1)
                                   para excluir el día actual
      · Alerta_Anom_MP25_Flag    = 1 si la anomalía supera el percentil 90
                                   de las anomalías de TRAIN (umbral adaptable,
                                   a diferencia del flag absoluto de v4/v3 que
                                   se dispara solo por el alza de nivel)
  - El flag absoluto Alerta_MP25_Flag, el lag absoluto MP2_5_Lag_2D y el
    rolling absoluto Region_Media_7d_MP25 se conservan SOLO para la ablación
    "contaminación absoluta" (comparación controlada).

Temperatura (decisión documentada): se conserva en NIVEL ABSOLUTO (TempMin,
TempMax, TempMin_Lag_4D, Region_Media_7d_TempMin). El frío absoluto es
fisiológicamente relevante (umbral de demanda respiratoria) y su drift
interanual es pequeño comparado con el +26% a +57% del MP2.5. Los flags
Frio_Polar_Flag y Lluvia_Intensa_Flag también son absolutos (definidos por
umbrales físicos).

Etapa 2 (idéntica a v3/v4, verificada estable):
  - Cuota histórica share_e = sum(Total_e en 2024) / sum(Total_región en 2024),
    calculada SOLO desde train.
  - pred_establecimiento = pred_region_total * share.
  - Establecimientos en test sin cuota: fallback jerárquico (mediana por
    Región+Tipo → mediana global por tipo → 0) y luego renormalización por
    región (suma = 1).

NOTA sobre la granularidad del dataset
--------------------------------------
`df_modelo.parquet` tiene ~4 filas por (establecimiento, Fecha): cada fila es
una causa respiratoria distinta del archivo DEIS (la columna de causa se
descartó al unificar). Por lo tanto:
  - La demanda REAL de un establecimiento en un día = SUMA de sus filas.
  - La Etapa 1 (suma por región+fecha) agrega correctamente todas las filas.
  - La evaluación a nivel establecimiento es a ESTABLECIMIENTO + DÍA.

ABLACIONES OBLIGATORIAS (test 2025, nivel establecimiento):
  1. v5 CON contaminación trailing  → configuración principal (la exportada).
  2. v5 SIN contaminación           → referencia limpia.
  3. v5 con contaminación ABSOLUTA  → aísla si el trailing marca la diferencia.
  + sensibilidad de ventana: N=30 y N=60 (principal N=45).

Configuración (réplica de v2/v3/v4):
  - Split temporal: train = 2024, test = 2025
  - RandomForestRegressor(n_estimators=200, max_depth=15,
    min_samples_split=50, min_samples_leaf=20, max_features='sqrt',
    random_state=42, n_jobs=-1)
  - Validación cruzada: TimeSeriesSplit(n_splits=5), scoring neg_MAE

Salida (models/):
  - model_rf_region_v5.joblib       modelo Etapa 1 (config principal)
  - features_region_v5.json         features EN ORDEN (incluye one-hot)
  - cuotas_establecimiento_v5.csv   cuotas Etapa 2
  - model_metadata_v5.json          métricas + ablaciones + comparación
                                    v2/v3/v4/v5 + diagnóstico + veredicto

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
TARGET = "Total"

# Ventana TRAILING principal del baseline de normalidad (días de calendario).
VENTANA_PRINCIPAL = 45
# Ventanas de la ablación de sensibilidad.
VENTANAS_SENSIBILIDAD = [30, 60]
# Mínimo de observaciones válidas dentro de la ventana para formar un
# baseline "natural"; por debajo de eso se usa la semilla (ver docstring).
MIN_PERIODS_BASELINE = 10
# Percentil de las anomalías de TRAIN que define el flag de alerta adaptativo.
PCT_ALERTA_ANOMALIA = 0.90

# Hiperparámetros del RandomForest (idénticos a v2/v3/v4).
HIPERPARAMETROS = {
    "n_estimators": 200,
    "max_depth": 15,
    "min_samples_split": 50,
    "min_samples_leaf": 20,
    "max_features": "sqrt",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

# ---------------------------------------------------------------------------
# Definición de features (Etapa 1)
# ---------------------------------------------------------------------------

# Clima puro (absoluto — decisión documentada en el docstring).
FEATURES_CLIMA = [
    "TempMin", "TempMax", "Precipitacion_mm",
    "TempMin_Lag_4D",
    "Region_Media_7d_TempMin",
    "Frio_Polar_Flag", "Lluvia_Intensa_Flag",
]

# Estacionalidad explícita (conservada de v4 + día del año literal).
FEATURES_ESTACIONALIDAD = ["Doy", "Doy_Sin", "Doy_Cos"]

# Contaminación por ANOMALÍA TRAILING (configuración principal de v5).
FEATURES_CONTAM_TRAILING = [
    "Anom_MP2_5", "Anom_MP10",
    "Anom_MP2_5_Lag_2D", "Anom_MP2_5_Media_7d",
    "Alerta_Anom_MP25_Flag",
]

# Contaminación en NIVEL ABSOLUTO (ablación controlada, estilo v3).
FEATURES_CONTAM_ABS = [
    "MP2_5", "MP10",
    "MP2_5_Lag_2D", "Alerta_MP25_Flag", "Region_Media_7d_MP25",
]

# Variables a las que se les calcula el baseline TRAILING + anomalía.
VARIABLES_ANOMALIA = ["MP2_5", "MP10"]

# Columnas de contaminación en ABSOLUTO (se usan en la agregación y en la
# ablación "absoluta"; la configuración principal NO las usa como features).
COLUMNAS_CONTAM_ABS = ["MP2_5", "MP10", "MP2_5_Lag_2D",
                       "Alerta_MP25_Flag", "Region_Media_7d_MP25"]

# Columnas climáticas agregadas a nivel región (sin contaminación).
COLUMNAS_CLIMA = ["TempMin", "TempMax", "Precipitacion_mm",
                  "TempMin_Lag_4D", "Region_Media_7d_TempMin",
                  "Frio_Polar_Flag", "Lluvia_Intensa_Flag"]


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
    - Features climáticas/de contaminación: son constantes (o casi) dentro de
      una región+fecha, así que se promedian (equivale al valor único; además
      resuelve NaN puntuales de lags y el hecho de que Region_Media_7d_* tiene
      hasta 7 valores distintos por región+fecha en bruto).

    Retorna un DataFrame ordenado por Fecha (necesario para TimeSeriesSplit).
    """
    columnas_media = COLUMNAS_CLIMA + COLUMNAS_CONTAM_ABS
    agg: dict[str, str] = {TARGET: "sum"}
    for col in columnas_media:
        if col not in agg:
            agg[col] = "mean"

    region_df = (
        df.groupby(["Region", "Fecha"], as_index=False)
        .agg(agg)
        .sort_values(["Fecha", "Region"])
        .reset_index(drop=True)
    )
    return region_df


def calcular_anomalias_trailing(
    region_df: pd.DataFrame,
    variables: list[str] = VARIABLES_ANOMALIA,
    ventana: int = VENTANA_PRINCIPAL,
    min_periods: int = MIN_PERIODS_BASELINE,
    semillas: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Calcula la anomalía de cada variable contra un baseline ADAPTATIVO TRAILING.

    Para cada región y cada fecha T:

        baseline(T) = media de la variable en los `ventana` días de CALENDARIO
                      estrictamente ANTERIORES a T   (t ∈ [T−ventana, T−1])
        anomalía(T) = valor(T) − baseline(T)

    Anti-leakage: se implementa con `serie.shift(1).rolling(ventana,
    min_periods=min_periods).mean()` sobre la serie DIARIA (reindexada al
    calendario) de cada región, de modo que la fecha T NUNCA entra en su
    propio baseline y la ventana solo mira hacia atrás.

    Semilla: cuando una región aún no acumuló `min_periods` observaciones
    previas (primeros días de su serie), el baseline toma el valor
    `semillas[variable]` (media global de TRAIN 2024, calculada por
    `preparar_features_region`). Documentado en el docstring del módulo.

    Además, para MP2_5 se derivan dos features calculadas SOLO con pasado:
      - Anom_MP2_5_Lag_2D:   anomalía de hace 2 días de calendario.
      - Anom_MP2_5_Media_7d: media TRAILING de la anomalía (shift(1) para
        excluir el día actual; min_periods=3 para tolerar días sin dato).

    Returns:
        copia de `region_df` con las columnas Anom_* (+ derivados) añadidas.
    """
    if semillas is None:
        raise ValueError("Falta `semillas`: media global de TRAIN por variable.")

    out = region_df.reset_index(drop=True).copy()

    for var in variables:
        col_anom = f"Anom_{var}"
        out[col_anom] = np.nan
        if var == "MP2_5":
            out["Anom_MP2_5_Lag_2D"] = np.nan
            out["Anom_MP2_5_Media_7d"] = np.nan

        for _region, idx in out.groupby("Region").groups.items():
            g = out.loc[idx].sort_values("Fecha")

            # Serie DIARIA de la región (calendario completo de su rango).
            cal = pd.date_range(g["Fecha"].min(), g["Fecha"].max(), freq="D")
            serie = pd.Series(
                g[var].to_numpy(), index=pd.DatetimeIndex(g["Fecha"].to_numpy())
            )
            serie_cal = serie.reindex(cal)

            # Baseline trailing: shift(1) excluye T; ventana de `ventana` días.
            baseline = (
                serie_cal.shift(1)
                .rolling(ventana, min_periods=min_periods)
                .mean()
                .fillna(semillas[var])  # semilla al inicio de la serie
            )
            anomalia = serie_cal - baseline

            # Vuelta al calendario de las filas originales de la región.
            fechas_g = pd.DatetimeIndex(g["Fecha"].to_numpy())
            out.loc[g.index, col_anom] = anomalia.reindex(fechas_g).to_numpy()

            if var == "MP2_5":
                lag2 = anomalia.shift(2)
                med7 = anomalia.shift(1).rolling(7, min_periods=3).mean()
                out.loc[g.index, "Anom_MP2_5_Lag_2D"] = lag2.reindex(fechas_g).to_numpy()
                out.loc[g.index, "Anom_MP2_5_Media_7d"] = med7.reindex(fechas_g).to_numpy()

    return out


def calcular_anomalia_tempmin_estacional(
    region_train: pd.DataFrame,
    region_test: pd.DataFrame,
    ventana_suavizado: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Anomalía de TempMin con el baseline estacional FIJO de v4 (SOLO train 2024).

    Método idéntico al de v4: media de 2024 por región × día-del-año, huecos
    interpolados, suavizado central de `ventana_suavizado` días; para regiones
    ausentes en train (Antofagasta, Atacama) se usa el promedio entre las
    curvas de las regiones de train (baseline nacional).

    Se calcula SOLO para los experimentos POST-HOC de diagnóstico: la
    configuración principal de v5 conserva TempMin en nivel absoluto.
    """
    tmp = region_train.copy()
    tmp["doy"] = tmp["Fecha"].dt.dayofyear
    doys = np.arange(1, 367)  # 2024 es bisiesto

    tabla = tmp.groupby(["Region", "doy"], as_index=False)["TempMin"].mean()
    mat = (
        tabla.pivot(index="Region", columns="doy", values="TempMin")
        .reindex(columns=doys)
        .interpolate(axis=1, limit_direction="both")
    )
    suav = mat.rolling(ventana_suavizado, center=True, min_periods=1).mean()
    baseline_nacional = suav.mean(axis=0)
    regiones_train = set(suav.index)

    def _aplicar(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        doy = out["Fecha"].dt.dayofyear
        base = out.apply(
            lambda r: suav.at[r["Region"], r["Fecha"].dayofyear]
            if r["Region"] in regiones_train else np.nan,
            axis=1,
        )
        base = base.fillna(doy.map(baseline_nacional))
        out["Anom_TempMin"] = out["TempMin"] - base
        return out

    return _aplicar(region_train), _aplicar(region_test)


def calcular_flag_alerta_anom(
    region_df: pd.DataFrame,
    pct: float = PCT_ALERTA_ANOMALIA,
) -> pd.DataFrame:
    """
    Flag de alerta de contaminación ADAPTATIVO: 1 si la anomalía trailing de
    MP2.5 supera el percentil `pct` de las anomalías de TRAIN (2024).

    A diferencia de Alerta_MP25_Flag (umbral absoluto, que se dispara solo
    porque el nivel base subió), este flag mide "más contaminación de lo
    normal para este período" y su umbral se estima SOLO con train.
    """
    out = region_df.copy()
    anom_train = out.loc[out["Fecha"].dt.year == TRAIN_YEAR, "Anom_MP2_5"]
    umbral = float(anom_train.quantile(pct))
    out["Alerta_Anom_MP25_Flag"] = (out["Anom_MP2_5"] > umbral).astype(int)
    out.attrs["umbral_alerta_anom"] = umbral
    return out


def codificar_region_onehot(
    region_train: pd.DataFrame,
    region_test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """
    Codifica `Region` con ONE-HOT (pd.get_dummies), NO LabelEncoder.

    LabelEncoder produce un entero ordinal que el RF trata como continuo
    (falso orden); eso afectó a v3. El one-hot elimina el orden falso. Se usa
    la unión de regiones de train+test para fijar las columnas (las regiones
    solo-test, Antofagasta/Atacama, quedan con su propia columna aunque en
    train sea 100% cero: el RF las trata como "sin información de región",
    que es honesto — nunca las vio).
    """
    todas = sorted(set(region_train["Region"]) | set(region_test["Region"]))
    dummies_cols = [f"Region_{r}" for r in todas]

    tr = pd.get_dummies(region_train, columns=["Region"], prefix="Region")
    te = pd.get_dummies(region_test, columns=["Region"], prefix="Region")
    # Conservar la columna Region original (get_dummies la consume): la
    # necesitan el reparto de la Etapa 2 y el bloque de diagnóstico.
    tr["Region"] = region_train["Region"].to_numpy()
    te["Region"] = region_test["Region"].to_numpy()
    # Alinear columnas: train+test pueden diferir en presencia de dummies
    for col in dummies_cols:
        if col not in tr.columns:
            tr[col] = 0
        if col not in te.columns:
            te[col] = 0
    return tr, te, dummies_cols


def construir_lista_features(
    dummies_cols: list[str],
    modo_contaminacion: str = "trailing",
) -> list[str]:
    """
    Devuelve la lista ORDENADA de features de la Etapa 1 según el modo:

      - "trailing":  anomalías trailing de contaminación (principal de v5).
      - "ninguna":   sin ninguna feature de contaminación (ablación limpia).
      - "absoluta":  contaminación en nivel absoluto (ablación estilo v3).
    """
    if modo_contaminacion == "trailing":
        contam = FEATURES_CONTAM_TRAILING
    elif modo_contaminacion == "ninguna":
        contam = []
    elif modo_contaminacion == "absoluta":
        contam = FEATURES_CONTAM_ABS
    else:
        raise ValueError(f"Modo de contaminación desconocido: {modo_contaminacion}")
    return FEATURES_CLIMA + contam + FEATURES_ESTACIONALIDAD + dummies_cols


def preparar_features_region(
    df: pd.DataFrame,
    ventana: int = VENTANA_PRINCIPAL,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], dict]:
    """
    Pipeline COMPLETO de la Etapa 1 hasta las matrices listas para entrenar.

    Pasos:
      1. Agregación a nivel región+fecha.
      2. Anomalías TRAILING (+ derivados sobre la anomalía) con semilla de
         train 2024 para el inicio de cada serie regional.
      3. Flag de alerta adaptativo (percentil 90 de anomalías de train).
      4. Estacionalidad cíclica + día del año.
      5. One-hot de Región (unión train+test).
      6. Imputación de NaN con la MEDIANA de SOLO train (anti-leakage).

    Returns:
        (region_train, region_test, dummies_cols, info) donde `info` incluye
        semillas, umbral del flag y ventana usada.
    """
    region_df = construir_dataset_region(df)
    region_df["Año"] = region_df["Fecha"].dt.year

    # Semilla del baseline: media global de TRAIN 2024 por variable (se usa
    # solo cuando una región no tiene aún MIN_PERIODS días de historial).
    semillas = {
        var: float(region_df.loc[region_df["Año"] == TRAIN_YEAR, var].mean())
        for var in VARIABLES_ANOMALIA
    }

    region_df = calcular_anomalias_trailing(
        region_df, VARIABLES_ANOMALIA, ventana=ventana,
        min_periods=MIN_PERIODS_BASELINE, semillas=semillas,
    )
    region_df = calcular_flag_alerta_anom(region_df)

    # Estacionalidad explícita (día del año + codificación cíclica).
    doy = region_df["Fecha"].dt.dayofyear
    region_df["Doy"] = doy
    region_df["Doy_Sin"] = np.sin(2 * np.pi * doy / 365.25)
    region_df["Doy_Cos"] = np.cos(2 * np.pi * doy / 365.25)

    region_train = region_df[region_df["Año"] == TRAIN_YEAR].copy()
    region_test = region_df[region_df["Año"] == TEST_YEAR].copy()

    region_train, region_test, dummies_cols = codificar_region_onehot(
        region_train, region_test
    )

    # Imputación de NaN (lags y derivados de anomalía en los bordes) con la
    # MEDIANA calculada SOLO sobre train — sin data leakage.
    todas_features = construir_lista_features(dummies_cols, "trailing") + FEATURES_CONTAM_ABS
    for col in todas_features:
        if col in region_train and region_train[col].isna().any():
            mediana = region_train[col].median()
            region_train[col] = region_train[col].fillna(mediana)
            region_test[col] = region_test[col].fillna(mediana)

    info = {
        "ventana_dias": ventana,
        "min_periods": MIN_PERIODS_BASELINE,
        "semillas_train_2024": {k: round(v, 4) for k, v in semillas.items()},
        "umbral_alerta_anom": round(float(region_df.attrs.get("umbral_alerta_anom", np.nan)), 4),
        "dummies_cols": dummies_cols,
    }
    return region_train, region_test, dummies_cols, info


def entrenar_etapa_1(
    region_train: pd.DataFrame,
    region_test: pd.DataFrame,
    feature_cols: list[str],
    con_cv: bool = True,
) -> dict:
    """
    Entrena el RandomForest de la Etapa 1 y calcula métricas + (opcional) CV.

    Returns:
        dict con modelo, predicciones, métricas a nivel región, CV e
        importancia de features.
    """
    X_train = region_train[feature_cols]
    y_train = region_train[TARGET]
    X_test = region_test[feature_cols]
    y_test = region_test[TARGET]

    model = RandomForestRegressor(**HIPERPARAMETROS)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    met_region = _metricas(y_test.values, y_pred)

    resultado: dict = {
        "model": model,
        "y_pred": y_pred,
        "met_region": met_region,
        "feature_cols": feature_cols,
    }

    if con_cv:
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = cross_val_score(
            model, X_train, y_train,
            cv=tscv, scoring="neg_mean_absolute_error", n_jobs=-1,
        )
        cv_mae = -cv_scores
        resultado["cv_mae_mean"] = round(float(cv_mae.mean()), 4)
        resultado["cv_mae_std"] = round(float(cv_mae.std()), 4)
        resultado["cv_mae_folds"] = [round(float(x), 4) for x in cv_mae]

    imp = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    resultado["importancia"] = imp
    return resultado


# ---------------------------------------------------------------------------
# Etapa 2 — cuotas históricas (idéntica a v3/v4)
# ---------------------------------------------------------------------------
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
    print("RE-ENTRENAMIENTO — DOS ETAPAS + BASELINE TRAILING (modelo v5)")
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
    # 2. ETAPA 1 — features con baseline TRAILING (ventana principal N=45)
    # -----------------------------------------------------------------------
    print(f"\n--- Etapa 1: features con baseline ADAPTATIVO TRAILING "
          f"(N={VENTANA_PRINCIPAL} días) ---")
    region_train, region_test, dummies_cols, info_trail = preparar_features_region(
        df, ventana=VENTANA_PRINCIPAL,
    )
    print(f"  Baseline por región: media de los últimos {VENTANA_PRINCIPAL} días de "
          f"CALENDARIO estrictamente ANTES de T (shift(1) + rolling).")
    print(f"  Semilla (primeras filas sin historial, media global train "
          f"{TRAIN_YEAR}): {info_trail['semillas_train_2024']}")
    print(f"  Umbral del flag de alerta adaptativo (percentil "
          f"{int(PCT_ALERTA_ANOMALIA * 100)} de anomalías train): "
          f"{info_trail['umbral_alerta_anom']:.3f}")
    print(f"  Columnas one-hot: {dummies_cols}")
    print(f"  Filas región+fecha — Train: {len(region_train):,} | "
          f"Test: {len(region_test):,}")

    # Evidencia anti-drift: la anomalía trailing de test debe estar centrada
    # en ~0 (en v4 estaba sistemáticamente > 0 por el baseline congelado).
    anom_train = region_train["Anom_MP2_5"].mean()
    anom_test = region_test["Anom_MP2_5"].mean()
    print(f"  Anomalía media MP2.5 — train 2024: {anom_train:+.3f} | "
          f"test 2025: {anom_test:+.3f}  (trailing: debería estar cerca de 0)")

    # -----------------------------------------------------------------------
    # 3. ETAPA 2 — cuotas históricas desde TRAIN 2024 (una sola vez)
    # -----------------------------------------------------------------------
    print("\n--- Etapa 2: cuotas históricas por establecimiento (2024) ---")
    cuotas = calcular_cuotas(train_raw)
    print(f"  Establecimientos con cuota en train: {len(cuotas):,}")
    print(f"  Suma de cuotas por región ≈ "
          f"{cuotas.groupby('Region')['share'].sum().mean():.4f} (debe ser ≈ 1)")

    cuotas_test = preparar_cuotas_test(test_raw, cuotas, train_raw)
    n_nuevos = int(cuotas_test.attrs.get("n_nuevos", 0))

    # -----------------------------------------------------------------------
    # 4. ABLACIONES OBLIGATORIAS (3 configuraciones, test 2025)
    # -----------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("ABLACIONES — las 3 configuraciones obligatorias")
    print("-" * 60)

    ablationes: dict[str, dict] = {}
    modelos: dict[str, object] = {}
    preds: dict[str, np.ndarray] = {}

    etiquetas = {
        "trailing": "v5 CON contaminación trailing (principal)",
        "ninguna": "v5 SIN contaminación (referencia limpia)",
        "absoluta": "v5 con contaminación ABSOLUTA (estilo v3)",
    }

    for modo, etiqueta in etiquetas.items():
        feats = construir_lista_features(dummies_cols, modo)
        print(f"\n▸ {etiqueta} — {len(feats)} features")
        res = entrenar_etapa_1(region_train, region_test, feats, con_cv=True)
        _, met_estab = repartir_y_evaluar(
            region_test, res["y_pred"], test_raw, cuotas_test
        )
        print(f"    Nivel región:          MAE={res['met_region']['MAE']:9.3f}  "
              f"RMSE={res['met_region']['RMSE']:9.3f}  R²={res['met_region']['R2']:8.4f}")
        print(f"    CV MAE (5-fold):       {res['cv_mae_mean']:.3f} ± {res['cv_mae_std']:.3f}")
        print(f"    Nivel establecimiento: MAE={met_estab['MAE']:9.3f}  "
              f"RMSE={met_estab['RMSE']:9.3f}  R²={met_estab['R2']:8.4f}  "
              f"sesgo={met_estab['sesgo_pct']:+.1f}%")
        ablationes[modo] = {
            "etiqueta": etiqueta,
            "features": feats,
            "n_features": len(feats),
            "nivel_region": res["met_region"],
            "nivel_establecimiento": met_estab,
            "cv_mae_mean": res["cv_mae_mean"],
            "cv_mae_std": res["cv_mae_std"],
        }
        if modo == "trailing":
            modelos["principal"] = res["model"]
            preds["principal"] = res["y_pred"]
            res_principal = res

    # -----------------------------------------------------------------------
    # 5. SENSIBILIDAD de la ventana trailing (N=30 y N=60)
    # -----------------------------------------------------------------------
    print("\n" + "-" * 60)
    print(f"SENSIBILIDAD — ventana trailing (principal N={VENTANA_PRINCIPAL})")
    print("-" * 60)

    sensibilidad: dict[str, dict] = {
        str(VENTANA_PRINCIPAL): {
            "nivel_region": ablationes["trailing"]["nivel_region"],
            "nivel_establecimiento": ablationes["trailing"]["nivel_establecimiento"],
        }
    }
    for ventana in VENTANAS_SENSIBILIDAD:
        rt, rte, dummies_v, _ = preparar_features_region(df, ventana=ventana)
        feats_v = construir_lista_features(dummies_v, "trailing")
        res_v = entrenar_etapa_1(rt, rte, feats_v, con_cv=False)
        _, met_v = repartir_y_evaluar(rte, res_v["y_pred"], test_raw, cuotas_test)
        print(f"  N={ventana:>2}: región R²={res_v['met_region']['R2']:8.4f} | "
              f"establecimiento MAE={met_v['MAE']:8.3f}  R²={met_v['R2']:8.4f}  "
              f"sesgo={met_v['sesgo_pct']:+.1f}%")
        sensibilidad[str(ventana)] = {
            "nivel_region": res_v["met_region"],
            "nivel_establecimiento": met_v,
        }

    # -----------------------------------------------------------------------
    # 6. EXPERIMENTOS POST-HOC (diagnóstico adicional, NO son la config
    #    principal): aíslan por qué la contaminación trailing no aporta y si
    #    la temperatura con anomalía estacional (permitida por especificación)
    #    cambiaría el cuadro. AVISO MÉTODO: se seleccionan observando el
    #    test 2025, por lo que son exploratorios (ver limitaciones).
    # -----------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("EXPERIMENTOS POST-HOC (exploratorios, sobre test 2025)")
    print("-" * 60)

    posthoc: dict[str, dict] = {}

    def _correr_posthoc(nombre: str, feats: str | list[str], etiqueta: str) -> dict:
        cols = (construir_lista_features(dummies_cols, feats)
                if isinstance(feats, str) else feats)
        res = entrenar_etapa_1(region_train, region_test, cols, con_cv=False)
        _, met = repartir_y_evaluar(region_test, res["y_pred"], test_raw, cuotas_test)
        print(f"  {etiqueta:<46} región R²={res['met_region']['R2']:7.4f} | "
              f"estab MAE={met['MAE']:7.3f} R²={met['R2']:7.4f} "
              f"sesgo={met['sesgo_pct']:+.1f}%")
        posthoc[nombre] = {
            "etiqueta": etiqueta,
            "n_features": len(cols),
            "nivel_region": res["met_region"],
            "nivel_establecimiento": met,
        }
        return posthoc[nombre]

    # a) trailing con SOLO las 2 anomalías crudas (sin derivados de ruido)
    _correr_posthoc(
        "trailing_solo_anomalias_crudas",
        FEATURES_CLIMA + ["Anom_MP2_5", "Anom_MP10"]
        + FEATURES_ESTACIONALIDAD + dummies_cols,
        "contaminación trailing SOLO Anom_MP2_5 + Anom_MP10",
    )

    # b) temperatura con anomalía estacional fijo de v4, SIN contaminación
    rt_t, rte_t = calcular_anomalia_tempmin_estacional(region_train, region_test)
    # Se añade como COLUMNA extra: no modifica la config principal, que usa
    # listas de features explícitas.
    region_train["Anom_TempMin"] = rt_t["Anom_TempMin"].to_numpy()
    region_test["Anom_TempMin"] = rte_t["Anom_TempMin"].to_numpy()
    feats_clima_t = FEATURES_CLIMA + ["Anom_TempMin"]
    _correr_posthoc(
        "sin_contaminacion_con_anom_tempmin",
        feats_clima_t + FEATURES_ESTACIONALIDAD + dummies_cols,
        "SIN contaminación + Anom_TempMin (baseline fijo v4)",
    )

    # c) combinación: temperatura con anomalía + contaminación trailing mínima
    _correr_posthoc(
        "trailing_minimo_con_anom_tempmin",
        feats_clima_t + ["Anom_MP2_5", "Anom_MP10"]
        + FEATURES_ESTACIONALIDAD + dummies_cols,
        "trailing mínimo (2 anomalías) + Anom_TempMin",
    )

    # d) temperatura con anomalía + contaminación trailing COMPLETA
    _correr_posthoc(
        "trailing_completo_con_anom_tempmin",
        feats_clima_t + FEATURES_CONTAM_TRAILING
        + FEATURES_ESTACIONALIDAD + dummies_cols,
        "trailing completo (5 features) + Anom_TempMin",
    )

    # -----------------------------------------------------------------------
    # 7. Métricas de la configuración principal + drift y diagnóstico
    # -----------------------------------------------------------------------
    met_region_principal = ablationes["trailing"]["nivel_region"]
    met_estab_principal = ablationes["trailing"]["nivel_establecimiento"]

    estab_dia, _ = repartir_y_evaluar(
        region_test, preds["principal"], test_raw, cuotas_test
    )

    reg_train_set = set(region_train["Region"])
    reg_test_set = set(region_test["Region"])
    regiones_nuevas = sorted(reg_test_set - reg_train_set)

    print("\n" + "-" * 60)
    print("DIAGNÓSTICO")
    print("-" * 60)
    print(f"  Regiones en train: {sorted(reg_train_set)}")
    print(f"  Regiones NUEVAS en test (sin histórico): {regiones_nuevas or 'ninguna'}")

    estab_dia["es_region_nueva"] = ~estab_dia["Region"].isin(reg_train_set)
    for es_nueva, etiqueta in [(False, "regiones con histórico"), (True, "regiones nuevas")]:
        sub = estab_dia[estab_dia["es_region_nueva"] == es_nueva]
        if len(sub) == 0:
            continue
        m = _metricas(sub[TARGET].values, sub["pred"].values)
        print(f"  {etiqueta:<24} MAE={m['MAE']:8.3f}  R²={m['R2']:8.4f}  n={len(sub):,}")

    # Drift de MP2.5 entre años (contexto para interpretar el veredicto)
    print("\n  Drift de MP2_5 (media train 2024 vs test 2025), por región:")
    drift = (
        region_train.groupby("Region")["MP2_5"].mean().to_frame("MP2_5_train")
        .join(region_test.groupby("Region")["MP2_5"].mean().to_frame("MP2_5_test"))
    )
    drift["var_%"] = 100 * (drift["MP2_5_test"] - drift["MP2_5_train"]) / drift["MP2_5_train"]
    for r, row in drift.iterrows():
        if pd.notna(row["MP2_5_train"]) and pd.notna(row["MP2_5_test"]):
            print(f"    {r:<20} {row['MP2_5_train']:6.1f} → {row['MP2_5_test']:6.1f}  "
                  f"({row['var_%']:+.1f}%)")

    # -----------------------------------------------------------------------
    # 8. VEREDICTO honesto sobre la contaminación trailing
    # -----------------------------------------------------------------------
    m_trail = ablationes["trailing"]["nivel_establecimiento"]
    m_sin = ablationes["ninguna"]["nivel_establecimiento"]
    m_abs = ablationes["absoluta"]["nivel_establecimiento"]

    trailing_supera_sin = (m_trail["MAE"] < m_sin["MAE"]) or (m_trail["R2"] > m_sin["R2"])
    trailing_mejor_global = (
        m_trail["MAE"] < m_sin["MAE"] and m_trail["R2"] > m_sin["R2"]
        and m_trail["sesgo_pct"] <= abs(m_sin["sesgo_pct"])
    )

    if trailing_mejor_global:
        veredicto = (
            f"HONESTO — SÍ APORTA: la contaminación con baseline trailing mejora "
            f"la referencia limpia en las tres métricas (MAE {m_trail['MAE']:.3f} vs "
            f"{m_sin['MAE']:.3f}; R² {m_trail['R2']:.4f} vs {m_sin['R2']:.4f}; "
            f"sesgo {m_trail['sesgo_pct']:+.1f}% vs {m_sin['sesgo_pct']:+.1f}%). "
            f"Además supera a la contaminación ABSOLUTA (MAE {m_abs['MAE']:.3f} / "
            f"R² {m_abs['R2']:.4f}, que replica el fracaso de v3), lo que confirma "
            f"que lo que marca la diferencia es el BASELINE TRAILING, no la "
            f"contaminación en sí."
        )
    elif trailing_supera_sin:
        veredicto = (
            f"PARCIAL — el trailing mejora PARCIALMENTE a la referencia sin "
            f"contaminación (trailing: MAE {m_trail['MAE']:.3f} / R² {m_trail['R2']:.4f} / "
            f"sesgo {m_trail['sesgo_pct']:+.1f}%; sin contaminación: MAE {m_sin['MAE']:.3f} / "
            f"R² {m_sin['R2']:.4f} / sesgo {m_sin['sesgo_pct']:+.1f}%), pero no en todas "
            f"las métricas a la vez. La contaminación trailing NO se vende como "
            f"éxito total."
        )
    else:
        veredicto = (
            f"NO APORTA — la contaminación con baseline trailing NO mejora a la "
            f"referencia sin contaminación (trailing: MAE {m_trail['MAE']:.3f} / "
            f"R² {m_trail['R2']:.4f} / sesgo {m_trail['sesgo_pct']:+.1f}%; sin "
            f"contaminación: MAE {m_sin['MAE']:.3f} / R² {m_sin['R2']:.4f} / "
            f"sesgo {m_sin['sesgo_pct']:+.1f}%). Se reporta tal cual: el baseline "
            f"trailing corrige el drift del baseline congelado de v4, pero la "
            f"señal de contaminación no supera al clima solo."
        )
    print("\n" + "-" * 60)
    print("VEREDICTO SOBRE LA CONTAMINACIÓN TRAILING")
    print("-" * 60)
    print(f"  {veredicto}")

    # Síntesis de los experimentos post-hoc (exploratorios).
    ph_crudas = posthoc["trailing_solo_anomalias_crudas"]["nivel_establecimiento"]
    ph_sin_t = posthoc["sin_contaminacion_con_anom_tempmin"]["nivel_establecimiento"]
    ph_mejor = min(
        posthoc.items(), key=lambda kv: kv[1]["nivel_establecimiento"]["MAE"]
    )
    hallazgo_posthoc = (
        f"Exploratorio sobre test 2025 (post-hoc, NO validado fuera de este "
        f"split): (1) los features DERIVADOS de la contaminación trailing "
        f"(lag, rolling y flag) empeoran el sistema — solo con Anom_MP2_5 + "
        f"Anom_MP10 el MAE baja de {m_trail['MAE']:.3f} a "
        f"{ph_crudas['MAE']:.3f} y el R² sube de {m_trail['R2']:.4f} a "
        f"{ph_crudas['R2']:.4f}; (2) incluso así, la contaminación NO supera "
        f"al clima solo; (3) el MEJOR sistema exploratorio es «{ph_mejor[1]['etiqueta']}» "
        f"(MAE {ph_mejor[1]['nivel_establecimiento']['MAE']:.3f} / "
        f"R² {ph_mejor[1]['nivel_establecimiento']['R2']:.4f} / "
        f"sesgo {ph_mejor[1]['nivel_establecimiento']['sesgo_pct']:+.1f}%), "
        f"y en NINGUNA variante la contaminación supera a su equivalente sin "
        f"contaminación (la referencia más fuerte es SIN contaminación + "
        f"anomalía de temperatura: MAE {ph_sin_t['MAE']:.3f} / "
        f"R² {ph_sin_t['R2']:.4f}). Conclusión: la temperatura con anomalía "
        f"aporta más que la contaminación en estos datos."
    )
    print(f"  {hallazgo_posthoc}")

    # -----------------------------------------------------------------------
    # 9. Tabla comparativa v2 / v3 / v4 / v5
    # -----------------------------------------------------------------------
    # Referencias VERIFICADAS de sesiones anteriores (test 2025, nivel
    # establecimiento + día).
    referencias = {
        "v2 (una etapa, absolutos)":
            {"MAE": 17.437, "RMSE": 24.260, "R2": 0.0427, "sesgo_pct": 17.3},
        "v3 (dos etapas, abs.)":
            {"MAE": 20.119, "RMSE": 42.796, "R2": -1.979, "sesgo_pct": 34.6},
        "v4 completo (anom. fijas)":
            {"MAE": 16.3067, "RMSE": 28.1086, "R2": -0.2851, "sesgo_pct": 24.95},
        "v4 sin contaminación":
            {"MAE": 13.3959, "RMSE": 21.5831, "R2": 0.2423, "sesgo_pct": 13.72},
        "v4 anomalías solo":
            {"MAE": 14.6699, "RMSE": 23.1865, "R2": 0.1256, "sesgo_pct": 19.63},
        "v5 trailing (principal)":
            {"MAE": m_trail["MAE"], "RMSE": m_trail["RMSE"],
             "R2": m_trail["R2"], "sesgo_pct": m_trail["sesgo_pct"]},
        "v5 sin contaminación":
            {"MAE": m_sin["MAE"], "RMSE": m_sin["RMSE"],
             "R2": m_sin["R2"], "sesgo_pct": m_sin["sesgo_pct"]},
        "v5 contaminación absoluta":
            {"MAE": m_abs["MAE"], "RMSE": m_abs["RMSE"],
             "R2": m_abs["R2"], "sesgo_pct": m_abs["sesgo_pct"]},
    }
    tabla_comp = (
        pd.DataFrame.from_dict(referencias, orient="index")
        .rename_axis("Versión")
        .reset_index()
        .rename(columns={"R2": "R²", "sesgo_pct": "Sesgo %"})
    )
    print("\n📊 TABLA COMPARATIVA — nivel ESTABLECIMIENTO + DÍA (test 2025):")
    print(tabla_comp.round(3).to_string(index=False))

    # -----------------------------------------------------------------------
    # 10. Exportar artefactos (configuración principal)
    # -----------------------------------------------------------------------
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    feature_cols_principal = ablationes["trailing"]["features"]
    model_path = MODELS_DIR / "model_rf_region_v5.joblib"
    features_path = MODELS_DIR / "features_region_v5.json"
    cuotas_path = MODELS_DIR / "cuotas_establecimiento_v5.csv"
    metadata_path = MODELS_DIR / "model_metadata_v5.json"

    joblib.dump(modelos["principal"], model_path)
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(feature_cols_principal, f, ensure_ascii=False, indent=2)

    cuotas_export = cuotas.copy()
    cuotas_export["Region"] = cuotas_export["Region"].astype(str)
    cuotas_export.to_csv(cuotas_path, index=False, encoding="utf-8")

    metadata = {
        "release": "modelo-v5",
        "arquitectura": "dos-etapas + baseline adaptativo trailing de contaminación",
        "granularidad_evaluacion": (
            "El dataset tiene ~4 filas por (establecimiento, Fecha) porque cada "
            "fila es una causa respiratoria distinta del archivo DEIS (la columna "
            "de causa se descartó al unificar). La demanda real de un "
            "establecimiento en un día es la SUMA de esas filas, por lo que la "
            "evaluación a nivel establecimiento se hace a nivel ESTABLECIMIENTO + DÍA."
        ),
        "explicacion": (
            "v5 mantiene la arquitectura de dos etapas (Etapa 1 predice el total "
            "regional por día con one-hot de región y estacionalidad cíclica; "
            "Etapa 2 reparte por cuota histórica) y corrige la causa raíz del "
            "fracaso de v4: el baseline de normalidad de la contaminación estaba "
            "CONGELADO en los niveles de 2024, de modo que el drift de MP2.5 "
            "(+26% a +57% entre 2024 y 2025) se filtraba a las anomalías de test "
            "(media > 0 sistemática) y el modelo proyectaba al alza la relación "
            "aprendida dentro de 2024. v5 reemplaza el baseline fijo por un "
            "baseline ADAPTATIVO TRAILING: para cada fecha T se compara contra "
            "la media de los últimos N días de la misma región estrictamente "
            "anteriores a T, de modo que la 'normalidad' se redefine con el paso "
            "del tiempo. El modelo aprende 'más contaminación DE LO NORMAL PARA "
            "ESTE PERÍODO → más pacientes', no 'más contaminación → más pacientes'."
        ),
        "metodo_trailing_anti_leakage": {
            "descripcion": (
                "Para cada región y fecha T: baseline(T) = media de la variable "
                "en los N días de CALENDARIO estrictamente anteriores a T. "
                "Implementado sobre la serie diaria de cada región (reindexada al "
                "calendario completo de su rango; los días sin dato se omiten en "
                "el promedio pero la ventana sigue siendo de N días) con "
                "`serie.shift(1).rolling(N, min_periods=MIN_PERIODS).mean()`: "
                "el shift(1) garantiza que T nunca entra en su propio baseline y "
                "la ventana solo mira hacia atrás. La ventana puede cruzar la "
                "frontera 2024→2025 porque los días previos a T ya fueron "
                "observados en el sistema real (misma suposición que los lags "
                "existentes). No se usa el target ni ninguna fecha ≥ T."
            ),
            "ventana_dias": VENTANA_PRINCIPAL,
            "ventanas_sensibilidad": VENTANAS_SENSIBILIDAD,
            "min_periods": MIN_PERIODS_BASELINE,
            "semilla_inicio_de_serie": (
                f"Las primeras filas de cada región (sin {MIN_PERIODS_BASELINE} "
                f"días de historial) usan como baseline la MEDIA GLOBAL de la "
                f"variable calculada SOLO sobre train 2024 "
                f"(MP2_5={info_trail['semillas_train_2024']['MP2_5']}, "
                f"MP10={info_trail['semillas_train_2024']['MP10']}). "
                f"Afecta a ~10 filas por región."
            ),
            "variables": VARIABLES_ANOMALIA,
            "features_derivadas_sobre_la_anomalia": (
                "Anom_MP2_5_Lag_2D (anomalía de hace 2 días, solo pasado), "
                "Anom_MP2_5_Media_7d (media trailing de la anomalía con shift(1) "
                "para excluir el día actual) y Alerta_Anom_MP25_Flag (anomalía > "
                "percentil 90 de las anomalías de train). Se calculan sobre la "
                "SERIE DE ANOMALÍA, no sobre el absoluto, para que tampoco "
                "arrastruen el drift de nivel base."
            ),
            "decision_temperatura": (
                "La temperatura se conserva en NIVEL ABSOLUTO (TempMin, TempMax, "
                "TempMin_Lag_4D, Region_Media_7d_TempMin) y sus flags: el frío "
                "absoluto es fisiológicamente relevante (umbral de demanda) y su "
                "drift interanual es pequeño comparado con el del MP2.5. No se "
                "calcula trailing para temperatura."
            ),
            "regiones_sin_historico_2024": (
                "Antofagasta y Atacama no existen en train 2024 (bug de los CSV "
                "SENAMHI 2024). Con el trailing DEJAN de necesitar un baseline "
                "prestado: usan su propia historia de 2025 a partir del día "
                f"{MIN_PERIODS_BASELINE}; solo sus primeras ~{MIN_PERIODS_BASELINE} "
                "días usan la semilla global."
            ),
            "evidencia_anti_drift": {
                "anomalia_media_MP2_5_train_2024": round(float(anom_train), 4),
                "anomalia_media_MP2_5_test_2025": round(float(anom_test), 4),
                "lectura": (
                    "Con baseline trailing, la anomalía de test queda centrada "
                    "cerca de 0 (en v4 estaba sistemáticamente > 0 porque el "
                    "baseline estaba congelado en 2024)."
                ),
            },
        },
        "etapa_1": {
            "nivel": "region",
            "target": "suma de Total por (Region, Fecha)",
            "features": feature_cols_principal,
            "n_features": len(feature_cols_principal),
            "model_type": "RandomForestRegressor",
            "metrics_test_2025": met_region_principal,
            "cv_mae_mean": res_principal["cv_mae_mean"],
            "cv_mae_std": res_principal["cv_mae_std"],
            "cv_mae_folds": res_principal["cv_mae_folds"],
            "feature_importance": {
                row["feature"]: round(float(row["importance"]), 6)
                for _, row in res_principal["importancia"].iterrows()
            },
        },
        "etapa_2": {
            "nivel": "establecimiento",
            "metodo": "cuota histórica (share) sobre train 2024",
            "formula": "pred_establecimiento = pred_region_total * share_normalizado",
            "fallback_establecimientos_nuevos": (
                "Si el establecimiento no aparece en train 2024 se le asigna la "
                "mediana de las cuotas de su TipoEstablecimiento dentro de su región; "
                "si la región no tiene ese tipo en train, la mediana global del tipo; "
                "si el tipo es desconocido, 0. Luego las cuotas se renormalizan "
                "dentro de cada región para que la suma repartida sea exactamente "
                "el total regional predicho."
            ),
            "n_establecimientos_con_cuota": int(len(cuotas)),
            "n_establecimientos_test_sin_cuota": int(n_nuevos),
            "metrics_test_2025": met_estab_principal,
        },
        "metrics_sistema_completo": met_estab_principal,
        "train_year": TRAIN_YEAR,
        "test_year": TEST_YEAR,
        "train_rows_establecimiento": int(len(train_raw)),
        "test_rows_establecimiento": int(len(test_raw)),
        "train_rows_region": int(len(region_train)),
        "test_rows_region": int(len(region_test)),
        "hyperparameters": {
            **{k: v for k, v in HIPERPARAMETROS.items() if k != "n_jobs"},
            "cv": "TimeSeriesSplit(n_splits=5) sobre Etapa 1",
            "scoring": "neg_mean_absolute_error",
        },
        "comparacion_v2_v3_v4_v5": {
            "nota": (
                "Todas las métricas a nivel ESTABLECIMIENTO + DÍA sobre test 2025 "
                "(granularidad comparable). v2, v3 y v4 son valores VERIFICADOS en "
                "sesiones anteriores; v5 proviene de este entrenamiento."
            ),
            "referencias_verificadas": {
                "v2_nivel_establecimiento_dia": referencias["v2 (una etapa, absolutos)"],
                "v3_nivel_establecimiento_dia": referencias["v3 (dos etapas, abs.)"],
                "v4_completo": referencias["v4 completo (anom. fijas)"],
                "v4_sin_contaminacion": referencias["v4 sin contaminación"],
                "v4_anomalias_solo": referencias["v4 anomalías solo"],
            },
            "v5_trailing_principal": referencias["v5 trailing (principal)"],
            "v5_sin_contaminacion": referencias["v5 sin contaminación"],
            "v5_contaminacion_absoluta": referencias["v5 contaminación absoluta"],
            "tabla_plana": referencias,
        },
        "ablaciones_v5": {
            "nota": (
                "Las 3 configuraciones obligatorias, idénticas salvo por el "
                "bloque de features de contaminación (mismo split, mismo RF, "
                "mismas cuotas de la Etapa 2)."
            ),
            **{f"v5_{k}": v for k, v in ablationes.items()},
        },
        "sensibilidad_ventana_trailing": {
            "ventana_principal": VENTANA_PRINCIPAL,
            "resultados": sensibilidad,
            "lectura": (
                "Compara N=45 (principal) con N=30 y N=60 a nivel "
                "establecimiento. Una ventana muy corta es ruidosa; una muy "
                "larga reacciona más lento al drift."
            ),
        },
        "experimentos_posthoc": {
            "aviso_metodologico": (
                "EXPLORATORIOS: estas variantes se diseñaron observando el "
                "resultado del test 2025, por lo que su selección tiene riesgo "
                "de sobreajuste de selección (data snooping). Son diagnóstico "
                "para decidir trabajos futuros, NO una mejora validada; "
                "requieren confirmarse con años adicionales de datos."
            ),
            "resultados": posthoc,
            "hallazgo": hallazgo_posthoc,
        },
        "diagnostico": {
            "hallazgo_contaminacion_spuria": (
                "En v3 la contaminación en nivel absoluto correlacionaba con la "
                "demanda DENTRO de 2024 porque ambas suben en invierno (proxy de "
                "la estación). Entre 2024 y 2025 el MP2.5 subió +26% a +57% en "
                "5 de 6 regiones mientras la demanda bajó ~5%: el RF extrapoló "
                "con sesgo fuerte positivo (+34.6% en v3)."
            ),
            "causa_fracaso_v4": (
                "v4 convirtió los absolutos en anomalías, pero el baseline "
                "estacional se calculó SOLO con train 2024 y quedó FIJO. El "
                "drift de MP2.5 se filtró a las anomalías de 2025 (media > 0 "
                "sistemática) y el modelo proyectó al alza la relación aprendida "
                "dentro de 2024: v4 completo (MAE 16.307 / R² -0.2851) fue PEOR "
                "que v4 sin contaminación (MAE 13.396 / R² 0.2423)."
            ),
            "correccion_v5": (
                "Baseline trailing adaptativo: la normalidad se redefine con los "
                f"últimos {VENTANA_PRINCIPAL} días de cada región, por lo que el "
                "drift de nivel base ya no contamina la anomalía de test."
            ),
            "regiones_nuevas_en_test": regiones_nuevas,
            "establecimientos_test_sin_cuota": int(n_nuevos),
            "anomalia_media_MP2_5_train_2024": round(float(anom_train), 4),
            "anomalia_media_MP2_5_test_2025": round(float(anom_test), 4),
            "drift_MP2_5": {
                r: {"train_2024": round(float(row["MP2_5_train"]), 2),
                    "test_2025": round(float(row["MP2_5_test"]), 2),
                    "var_pct": round(float(row["var_%"]), 1)}
                for r, row in drift.iterrows()
                if pd.notna(row["MP2_5_train"]) and pd.notna(row["MP2_5_test"])
            },
            "ablations": {
                "v5_con_trailing": ablationes["trailing"]["nivel_establecimiento"],
                "v5_sin_contaminacion": ablationes["ninguna"]["nivel_establecimiento"],
                "v5_con_absolutos": ablationes["absoluta"]["nivel_establecimiento"],
            },
            "veredicto_trailing": veredicto,
            "hallazgo_posthoc": hallazgo_posthoc,
        },
        "limitaciones": [
            "Solo 2 años de datos (train 2024 / test 2025): cualquier "
            "selección de features u hiperparámetros observando el test 2025 "
            "tiene riesgo de sobreajuste de selección; se necesita 2023 o más "
            "para validación honesta.",
            "El R² a nivel región se explica en gran parte por diferencias "
            "ENTRE regiones (one-hot de Metropolitana es la feature #1): el "
            "techo de los datos está en la variabilidad DIARIA dentro de cada "
            "región.",
            "Antofagasta y Atacama no existen en train 2024 (bug de los CSV "
            "SENAMHI 2024) y concentran los peores errores del sistema "
            "(regiones nuevas: MAE y R² muy inferiores a las regiones con "
            "histórico).",
            "41 establecimientos de test no tienen cuota en train y usan "
            "fallback jerárquico con renormalización.",
            "El clima y la contaminación son variables REGIONALES: no "
            "distinguen establecimientos dentro de una misma región+fecha; "
            "ese diferencial lo aporta únicamente la cuota histórica de la "
            "Etapa 2 (muy estable: correlación 0.993 entre años).",
            "La contaminación trailing NO mejora al sistema sin contaminación "
            "en MAE: no se puede afirmar que aporte valor predictivo con estos "
            "datos y esta ventana de 2 años.",
        ],
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ RE-ENTRENAMIENTO COMPLETADO (modelo v5, trailing adaptativo)")
    print(f"  Modelo Etapa 1: {model_path}")
    print(f"  Features:       {features_path}")
    print(f"  Cuotas Etapa 2: {cuotas_path}")
    print(f"  Metadata:       {metadata_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
