"""
Feature Engineering Biológico - Sistema MINSAL
==============================================

Genera variables predictivas alineadas con el esquema del PROJECT_CONTEXT.md:
  - TempMin_Lag_4D (shift(4)): incubación viral post-frente frío polar
  - MP2_5_Lag_2D (shift(2)): efecto acumulado de smog/humo de leña
  - Frio_Polar_Flag: booleano si TempMin ≤ 2°C
  - Lluvia_Intensa_Flag: booleano si Precipitacion > percentil 90
  - Alerta_MP25_Flag: booleano si MP2_5 > umbral WHO (15 μg/m³)

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
BASE_DIR = Path("/Users/naferyh/Desktop/Proyectos/Proyecto de título")
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
def create_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea variables de retardo (lags) a nivel región.

    - TempMin_Lag_4D: temperatura mínima 4 días atrás (incubación viral polar)
    - MP2_5_Lag_2D: PM2.5 2 días atrás (acumulación humo de leña)

    Los lags se calculan por región (no por establecimiento) ya que los
    datos climáticos son a nivel regional.

    Args:
        df: DataFrame unificado con columnas mínimas:
            ['Region', 'Fecha', 'TempMin', 'MP2_5']

    Returns:
        DataFrame con columnas de lag agregadas.
    """
    logger.info("Creando variables de retardo (lags)...")

    # Asegurar orden cronológico por región
    df = df.sort_values(["Region", "Fecha"]).reset_index(drop=True)

    # TempMin_Lag_4D
    if "TempMin" in df.columns:
        df["TempMin_Lag_4D"] = (
            df.groupby("Region")["TempMin"]
            .shift(LAG_TEMP_MIN_DAYS)
        )
        logger.info("  → TempMin_Lag_4D creado (shift=%d)", LAG_TEMP_MIN_DAYS)

    # MP2_5_Lag_2D
    if "MP2_5" in df.columns:
        df["MP2_5_Lag_2D"] = (
            df.groupby("Region")["MP2_5"]
            .shift(LAG_MP25_DAYS)
        )
        logger.info("  → MP2_5_Lag_2D creado (shift=%d)", LAG_MP25_DAYS)

    return df


def create_binary_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea variables binarias de alerta basadas en umbrales biológicos.

    - Frio_Polar_Flag: 1 si TempMin ≤ 2°C (frente frío polar)
    - Lluvia_Intensa_Flag: 1 si precipitación > percentil 90 regional
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

    # Lluvia_Intensa_Flag (percentil regional)
    if "Precipitacion_mm" in df.columns:
        # Calcular percentil 90 dentro de cada región
        regional_threshold = (
            df.groupby("Region")["Precipitacion_mm"]
            .transform(lambda x: x.quantile(PRECIP_INTENSIVE_PERCENTILE))
        )
        df["Lluvia_Intensa_Flag"] = (
            df["Precipitacion_mm"].fillna(-1) > regional_threshold.fillna(-1)
        ).astype(int)
        logger.info("  → Lluvia_Intensa_Flag creado (percentil=%.0f)", PRECIP_INTENSIVE_PERCENTILE * 100)

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
    Agrega features estadísticos a nivel regional (rolling window).

    - Region_Media_7d_TempMin: media 7-días móvil de TempMin por región
    - Region_Media_7d_MP25: media 7-días móvil de MP2.5 por región

    Args:
        df: DataFrame con lags.

    Returns:
        DataFrame con columnas de ventana móvil.
    """
    logger.info("Calculando estadísticos regionales (rolling 7d)...")

    df = df.sort_values(["Region", "Fecha"]).reset_index(drop=True)

    for col, new_col in [
        ("TempMin", "Region_Media_7d_TempMin"),
        ("MP2_5", "Region_Media_7d_MP25"),
    ]:
        if col in df.columns:
            df[new_col] = (
                df.groupby("Region")[col]
                .transform(lambda x: x.rolling(window=7, min_periods=1).mean())
            )
            logger.info("  → %s creado", new_col)

    return df


def filter_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra filas con datos suficientes para modelado y limpia nulos.

    - Elimina filas sin TempMin_Lag_4D (necesario para el lag)
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
    1. Lags (TempMin_Lag_4D, MP2_5_Lag_2D)
    2. Flags binarios (Frio_Polar_Flag, Lluvia_Intensa_Flag, Alerta_MP25_Flag)
    3. Discretización de temperatura
    4. Estadísticos regionales (rolling 7d)
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
