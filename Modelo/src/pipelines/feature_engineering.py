"""
Feature Engineering Biológico - Sistema MINSAL
==============================================

Genera variables predictivas alineadas con el esquema del PROJECT_CONTEXT.md:
  - TempMin_Lag_4D: temperatura mínima de T-4 días de CALENDARIO
    (incubación viral post-frente frío polar)
  - MP2_5_Lag_2D: PM2.5 de T-2 días de CALENDARIO
    (efecto acumulado de smog/humo de leña)
  - Frio_Polar_Flag: booleano si TempMin ≤ 2°C
  - Lluvia_Intensa_Flag: booleano si Precipitacion > percentil 90 regional,
    con el umbral calculado SOLO sobre el período de train (Fecha < 2025-01-01)
  - Alerta_MP25_Flag: booleano si MP2_5 > umbral WHO (15 μg/m³)

NOTA DE SEMÁNTICA (fix de bugs climáticos)
------------------------------------------
El dataset de entrada tiene ~152 filas por (Región, Fecha) (una por causa
DEIS/establecimiento), así que las operaciones de lag y rolling se calculan
sobre una SERIE CALENDARIO DEDUPLICADA (1 fila por Región+Fecha, ordenada
cronológicamente) y luego se hace merge de vuelta al df multi-fila. Un
shift/rolling sobre FILAS retrocedería ~152 filas/día y mediría fracciones
de día, no días. Los umbrales aprendidos de datos (percentil de lluvia) se
calculan solo con Fecha < TRAIN_END para no contaminar el test 2025.

Input:  data/interim/df_unificado.parquet
Output: data/processed/df_modelo.parquet (dataset listo para ML)

Autor: Ignacio Fernández (Nafery) - ML Lead
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("feature_engineering.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("feature_engineering")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# ---------------------------------------------------------------------------
# Configuración de features biológicos
# ---------------------------------------------------------------------------
LAG_TEMP_MIN_DAYS: int = 4   # TempMin_Lag_4D — incubación viral
LAG_MP25_DAYS: int = 2       # MP2_5_Lag_2D — acumulación smog/humo leña
PRECIP_INTENSIVE_PERCENTILE: float = 0.90  # Lluvia_Intensa_Flag
WHO_PM25_THRESHOLD: float = 15.0           # μg/m³ — Alerta_MP25_Flag
FRIOPOLAR_TEMP_THRESHOLD: float = 2.0     # °C — frentes fríos polares

# Protocolo de split temporal: train = 2024, test = 2025.
# Los umbrales aprendidos de datos (p.ej. percentil 90 de precipitación)
# se calculan SOLO con Fecha < TRAIN_END y se congelan para todas las
# filas: incluir el test 2025 en el umbral sería transductivo (data snooping).
TRAIN_END = pd.Timestamp("2025-01-01")

# Regiones prioritarias (zona centro-sur con mayor saturación según notebook)
REGIONES_OBJETIVO = [
    "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
    "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble",
    "Biobío", "La Araucanía", "Los Ríos", "Los Lagos",
    "Aysén", "Magallanes",
]

# Tipo de establecimiento prioritario (urgencias clave)
TIPOS_ESTABLECIMIENTO = [
    "Hospital", "Clínica", "SAPU", "Posta Médica", "Centro de Salud",
]


# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------
def _serie_calendario(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Serie calendario deduplicada: 1 fila por (Región, Fecha).

    El df de entrada tiene ~152 filas por (Región, Fecha) (una por causa
    DEIS); lag/rolling deben operar sobre una fila por fecha, no sobre
    filas. Devuelve el frame con la columna `_fecha_key` (datetime) para
    calcular desplazamientos de días calendario y mergear de vuelta al df
    multi-fila por (Región, Fecha).
    """
    cal = df[["Region", "Fecha", *cols]].drop_duplicates(subset=["Region", "Fecha"]).copy()
    cal["_fecha_key"] = pd.to_datetime(cal["Fecha"])
    return cal.sort_values(["Region", "_fecha_key"]).reset_index(drop=True)


def create_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea variables de retardo (lags) a nivel región sobre el CALENDARIO.

    - TempMin_Lag_4D: temperatura mínima de T-4 días de calendario
      (incubación viral polar)
    - MP2_5_Lag_2D: PM2.5 de T-2 días de calendario (humo de leña)

    El df tiene ~152 filas por (Región, Fecha): un `shift(n)` sobre FILAS
    retrocede ~n filas ≈ la MISMA fecha (bug corregido). Los lags se
    calculan sobre la serie calendario deduplicada (1 fila por Región+Fecha,
    ordenada cronológicamente) restando n días a la FECHA (T-n) y luego se
    hace merge de vuelta por (Región, Fecha).

    Anti-fuga: solo se usa información de T-n (estrictamente pasado). Si una
    región no tiene datos en T-n, el lag queda NaN (esas filas — p.ej. los
    primeros 4 días calendario por región — las elimina después
    `filter_and_clean` vía `dropna(subset=["TempMin_Lag_4D"])`).

    Args:
        df: DataFrame unificado con columnas mínimas:
            ['Region', 'Fecha', 'TempMin', 'MP2_5']

    Returns:
        DataFrame con columnas de lag agregadas.
    """
    logger.info("Creando variables de retardo (lags) sobre el calendario...")

    # Asegurar orden cronológico por región
    df = df.sort_values(["Region", "Fecha"]).reset_index(drop=True)

    # Serie calendario: 1 fila por (Región, Fecha) con clave datetime
    cols = [c for c in ("TempMin", "MP2_5") if c in df.columns]
    cal = _serie_calendario(df, cols)
    df["_fecha_key"] = pd.to_datetime(df["Fecha"])

    for col, n_dias, salida in [
        ("TempMin", LAG_TEMP_MIN_DAYS, "TempMin_Lag_4D"),
        ("MP2_5", LAG_MP25_DAYS, "MP2_5_Lag_2D"),
    ]:
        if col not in df.columns:
            continue
        # La clave AVANZA n días: la fila de ref (d, valor(d)) se publica con
        # clave d+n, de modo que al mergear la fecha T toma valor(T-n).
        ref = cal[["Region", "_fecha_key", col]].copy()
        ref["_fecha_key"] = ref["_fecha_key"] + pd.Timedelta(days=n_dias)
        ref = ref.rename(columns={col: salida})
        df = df.drop(columns=[salida], errors="ignore").merge(
            ref, on=["Region", "_fecha_key"], how="left",
        )
        logger.info(
            "  → %s creado (lag calendárico de %d días)", salida, n_dias
        )

    return df.drop(columns=["_fecha_key"])


def create_binary_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea variables binarias de alerta basadas en umbrales biológicos.

    - Frio_Polar_Flag: 1 si TempMin ≤ 2°C (frente frío polar)
    - Lluvia_Intensa_Flag: 1 si precipitación > percentil 90 regional,
      con el umbral por región calculado SOLO sobre el período de train
      (Fecha < TRAIN_END = 2025-01-01; protocolo train 2024 / test 2025)
      y congelado para aplicarlo a todas las filas. Calcular el percentil
      sobre TODO el df incluiría el test 2025 en el umbral (transductivo,
      data snooping). Si una región no tiene valores de precipitación en
      train, su umbral queda NaN y el flag es 0 (sin evidencia de lluvia
      intensa).
    - Alerta_MP25_Flag: 1 si MP2.5 > 15 μg/m³ (OMS)

    Args:
        df: DataFrame con columnas climáticas.

    Returns:
        DataFrame con columnas de flag agregadas.
    """
    logger.info("Creando flags binarias de alerta...")

    # Frio_Polar_Flag
    if "TempMin" in df.columns:
        df["Frio_Polar_Flag"] = (
            df["TempMin"].fillna(999) <= FRIOPOLAR_TEMP_THRESHOLD
        ).astype(int)
        logger.info("  → Frio_Polar_Flag creado (umbral ≤ %.1f°C)", FRIOPOLAR_TEMP_THRESHOLD)

    # Alerta_MP25_Flag
    if "MP2_5" in df.columns:
        df["Alerta_MP25_Flag"] = (
            df["MP2_5"].fillna(-1) > WHO_PM25_THRESHOLD
        ).astype(int)
        logger.info("  → Alerta_MP25_Flag creado (umbral > %.1f μg/m³)", WHO_PM25_THRESHOLD)

    # Lluvia_Intensa_Flag (percentil regional — umbral train-only)
    if "Precipitacion_mm" in df.columns:
        # Umbral = q90 por región calculado SOLO con Fecha < TRAIN_END
        # (train 2024); se congelan los umbrales y se aplican a todas las
        # filas (train + test). NaN del umbral → flag 0 (comparación con
        # NaN da False, sin relleno: rellenar con -1 marcaría como "intensa"
        # cualquier lluvia de regiones sin datos de train).
        es_train = pd.to_datetime(df["Fecha"]) < TRAIN_END
        umbrales_train = (
            df.loc[es_train]
            .groupby("Region")["Precipitacion_mm"]
            .quantile(PRECIP_INTENSIVE_PERCENTILE)
        )
        umbral = df["Region"].map(umbrales_train)
        df["Lluvia_Intensa_Flag"] = (
            df["Precipitacion_mm"].fillna(-1) > umbral
        ).astype(int)
        logger.info(
            "  → Lluvia_Intensa_Flag creado (percentil=%.0f, umbral train-only < %s)",
            PRECIP_INTENSIVE_PERCENTILE * 100,
            TRAIN_END.date(),
        )

    return df


def discretize_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """
    Discretiza temperaturas en categorías ordinales.

    - 'Muy Frío' (< -5°C)
    - 'Frío' (-5 a 5°C)
    - 'Templado' (5 a 15°C)
    - 'Cálido' (15 a 25°C)
    - 'Caluroso' (> 25°C)

    Args:
        df: DataFrame con columna TempMin.

    Returns:
        DataFrame con columna Cat_TempMin agregada.
    """
    logger.info("Discretizando temperaturas...")

    if "TempMin" not in df.columns:
        logger.warning("No hay TempMin para discretizar")
        return df

    bins = [-np.inf, -5, 5, 15, 25, np.inf]
    labels = ["Muy Frío", "Frío", "Templado", "Cálido", "Caluroso"]

    df["Cat_TempMin"] = pd.cut(
        df["TempMin"].fillna(-999),
        bins=bins,
        labels=labels,
        include_lowest=True,
    ).astype(str)

    logger.info("  → Cat_TempMin creado con bins: %s", labels)
    return df


def add_regional_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega features estadísticos a nivel regional (ventana calendario 7d).

    - Region_Media_7d_TempMin: media móvil de 7 DÍAS de CALENDARIO de
      TempMin por región (ventana [T-6..T], INCLUYE el día T)
    - Region_Media_7d_MP25: idem para MP2.5

    El df tiene ~152 filas por (Región, Fecha): un `rolling(7)` sobre FILAS
    cubre <1 día (bug corregido). Se calcula sobre la serie calendario
    deduplicada (1 fila por Región+Fecha), reindexada al calendario diario
    completo de cada región para ser robusta ante fechas faltantes
    (`min_periods=1` promedia los valores observados dentro de la ventana),
    y luego se hace merge de vuelta por (Región, Fecha).

    Args:
        df: DataFrame con lags.

    Returns:
        DataFrame con columnas de ventana móvil.
    """
    logger.info("Calculando estadísticos regionales (rolling 7d calendario)...")

    df = df.sort_values(["Region", "Fecha"]).reset_index(drop=True)
    df["_fecha_key"] = pd.to_datetime(df["Fecha"])

    pares = [
        ("TempMin", "Region_Media_7d_TempMin"),
        ("MP2_5", "Region_Media_7d_MP25"),
    ]
    cols = [c for c, _ in pares if c in df.columns]
    cal = _serie_calendario(df, cols)

    for col, new_col in pares:
        if col not in df.columns:
            continue
        partes = []
        for region, g in cal.groupby("Region", sort=False):
            g = g.set_index("_fecha_key").sort_index()
            # Calendario diario completo de la región (robusto ante huecos)
            completo = pd.date_range(g.index.min(), g.index.max(), freq="D")
            serie = g[col].reindex(completo)
            roll = serie.rolling(window=7, min_periods=1).mean()
            partes.append(pd.DataFrame({
                "Region": region,
                "_fecha_key": roll.index,
                new_col: roll.to_numpy(),
            }))
        ref = pd.concat(partes, ignore_index=True)
        df = df.drop(columns=[new_col], errors="ignore").merge(
            ref, on=["Region", "_fecha_key"], how="left",
        )
        logger.info("  → %s creado (ventana calendario [T-6..T])", new_col)

    return df.drop(columns=["_fecha_key"])


def filter_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra filas con datos suficientes para modelado y limpia nulos.

    - Elimina filas sin TempMin_Lag_4D (necesario para el lag): con el lag
      calendárico esto incluye los primeros 4 días de calendario por región
      (no tienen T-4) y los días cuyo T-4 no tiene TempMin
    - Elimina regiones con pocos datos
    - Limpia establecimientos sin nombre

    Args:
        df: DataFrame con todos los features.

    Returns:
        DataFrame limpio y filtrado.
    """
    logger.info("Filtrando y limpiando datos...")

    initial_rows = len(df)

    # Filtrar región objetivo (zona centro-sur priorizada)
    df = df[df["Region"].isin(REGIONES_OBJETIVO)].copy()

    # Eliminar filas sin lag de temperatura (necesario para el modelo)
    df = df.dropna(subset=["TempMin_Lag_4D"])

    # Eliminar establecimientos sin nombre
    df = df.dropna(subset=["IdEstablecimiento", "Region"])
    df["IdEstablecimiento"] = df["IdEstablecimiento"].astype(str)
    df = df[df["IdEstablecimiento"] != "nan"]

    # Fill NaNs restantes
    numeric_cols = ["TempMin", "TempMax", "Precipitacion_mm", "MP2_5", "MP10"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    final_rows = len(df)
    logger.info("  → Filas: %d → %d (eliminadas %d)", initial_rows, final_rows, initial_rows - final_rows)

    return df


def build_modeling_dataset(
    input_file: str = "df_unificado.parquet",
    output_file: str = "df_modelo.parquet",
) -> str:
    """
    Pipeline completo de feature engineering.

    Lee el dataset unificado y aplica:
    1. Lags calendario (TempMin_Lag_4D, MP2_5_Lag_2D) sobre serie deduplicada
    2. Flags binarios (Frio_Polar_Flag, Lluvia_Intensa_Flag train-only,
       Alerta_MP25_Flag)
    3. Discretización de temperatura
    4. Estadísticos regionales (rolling 7d de calendario)
    5. Filtrado y limpieza

    Args:
        input_file: Nombre del archivo unificado en data/interim/
        output_file: Nombre del archivo de salida en data/processed/

    Returns:
        Path al archivo de salida (dataset listo para ML).
    """
    logger.info("=" * 60)
    logger.info("INICIANDO FEATURE ENGINEERING")
    logger.info("=" * 60)

    input_path = INTERIM_DIR / input_file
    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró: {input_path}")

    logger.info("Cargando datos unificados...")
    df = pd.read_parquet(input_path)
    logger.info("Datos cargados: %d filas, %d columnas", len(df), len(df.columns))

    # Aplicar feature engineering
    df = create_lag_features(df)
    df = create_binary_flags(df)
    df = discretize_temperature(df)
    df = add_regional_aggregates(df)
    df = filter_and_clean(df)

    # Agregar target por rango etario (para extensión futura multi-target)
    age_cols = ["Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas"]
    for col in age_cols:
        if col not in df.columns:
            df[col] = 0

    # Reordenar columnas
    final_cols = [
        # Identificadores
        "IdEstablecimiento", "NEstablecimiento", "TipoEstablecimiento",
        "CodigoRegion", "Region", "CodigoComuna", "Fecha",
        # Target
        "Total", "Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas",
        # Clima original
        "TempMin", "TempMax", "Precipitacion_mm",
        # Contaminación original
        "MP2_5", "MP10",
        # Features biológicos
        "TempMin_Lag_4D", "MP2_5_Lag_2D",
        "Frio_Polar_Flag", "Lluvia_Intensa_Flag", "Alerta_MP25_Flag",
        "Cat_TempMin",
        # Estadísticos regionales
        "Region_Media_7d_TempMin", "Region_Media_7d_MP25",
        # Flag
        "es_respiratoria",
    ]

    available_cols = [c for c in final_cols if c in df.columns]
    df = df[available_cols].copy()

    # Guardar
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / output_file
    df.to_parquet(output_path, index=False)

    logger.info("=" * 60)
    logger.info("FEATURE ENGINEERING COMPLETADO")
    logger.info("Archivo: %s", output_path)
    logger.info("Rows: %d, Cols: %d", len(df), len(df.columns))
    logger.info("=" * 60)

    return str(output_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    output = build_modeling_dataset()
    print(f"\n✅ Dataset listo para modelado: {output}")

    # Quick stats
    df = pd.read_parquet(output)
    print(f"\n📊 Estadísticas:")
    print(f"   Filas: {len(df):,}")
    print(f"   Regiones: {df['Region'].nunique()}")
    print(f"   Establecimientos: {df['IdEstablecimiento'].nunique()}")
    print(f"   Fechas: {df['Fecha'].min()} → {df['Fecha'].max()}")
    print(f"\n   Features clave:")
    for col in ["TempMin_Lag_4D", "MP2_5_Lag_2D", "Frio_Polar_Flag", "Lluvia_Intensa_Flag", "Alerta_MP25_Flag"]:
        if col in df.columns:
            print(f"   {col}: {df[col].describe().to_dict()}")
