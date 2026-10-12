"""
Pipeline de Unificación de Datos - Sistema MINSAL
===================================================

Integra 3 fuentes de datos a nivel establecimiento + fecha:
  1. Salud (DEIS/MINSAL) — atenciones respiratorias por establecimiento
  2. Clima (CR2/SENAMHI/DMC) — temperaturas mínimas/máximas diarias
  3. Contaminación (Open-Meteo) — MP2.5 y MP10 por región

Output: data/interim/df_unificado.parquet
- Una fila por (IdEstablecimiento, Fecha)
- Variables climáticas unidas por Region + Fecha
- Variables de rango etario preservadas originalmente

Autor: Ignacio Fernández (Nafery) - ML Lead
Proyecto: Sistema de Alerta Temprana MINSAL
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("unificar_datos.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("unificar_datos")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path("/Users/naferyh/Desktop/Proyectos/Proyecto de título")
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
YEARS = ["2024", "2025"]
REGIONS_COORDS = {
    "Arica y Parinacota": {"lat": -18.47, "lon": -70.31},
    "Tarapacá": {"lat": -20.21, "lon": -70.15},
    "Antofagasta": {"lat": -23.65, "lon": -70.40},
    "Atacama": {"lat": -27.36, "lon": -70.33},
    "Coquimbo": {"lat": -29.90, "lon": -71.25},
    "Valparaíso": {"lat": -33.04, "lon": -71.61},
    "Metropolitana": {"lat": -33.45, "lon": -70.66},
    "O'Higgins": {"lat": -34.17, "lon": -70.74},
    "Maule": {"lat": -35.42, "lon": -71.65},
    "Ñuble": {"lat": -36.60, "lon": -72.10},
    "Biobío": {"lat": -36.82, "lon": -73.04},
    "La Araucanía": {"lat": -38.73, "lon": -72.59},
    "Los Ríos": {"lat": -39.81, "lon": -73.24},
    "Los Lagos": {"lat": -41.47, "lon": -72.94},
    "Aysén": {"lat": -45.57, "lon": -72.06},
    "Magallanes": {"lat": -53.16, "lon": -70.91},
}

# Mapeo de nombres de regiones DEIS ↔ Open-Meteo
REGION_DEIS_TO_OM = {
    "Arica y Parinacota": "Arica y Parinacota",
    "Tarapacá": "Tarapacá",
    "Antofagasta": "Antofagasta",
    "Atacama": "Atacama",
    "Coquimbo": "Coquimbo",
    "Valparaíso": "Valparaíso",
    "Metropolitana": "Metropolitana",
    "O'Higgins": "O'Higgins",
    "Maule": "Maule",
    "Ñuble": "Ñuble",
    "Biobío": "Biobío",
    "La Araucanía": "La Araucanía",
    "Los Ríos": "Los Ríos",
    "Los Lagos": "Los Lagos",
    "Aysén": "Aysén",
    "Magallanes": "Magallanes",
}

# CIE-10 respiratorias (J00–J99) + keywords
RESPIRATORY_KEYWORDS = [
    "RESPIRATORIO", "NEUMONIA", "BRONQUITIS", "ASMA", "EPOC", "GRIPE",
    "INFLUENZA", "INFECCIÓN RESPIRATORIA", "BRONQUITE", "RALEOS",
]
RESPIRATORY_CIE_PREFIXES = ["J0", "J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_date(date_str: str) -> str:
    """Normaliza fechas al formato YYYY-MM-DD."""
    if not date_str or not date_str.strip():
        return ""
    date_str = str(date_str).strip()
    # Ya ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
    # DD/MM/YYYY → YYYY-MM-DD
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    # DD-MM-YYYY → YYYY-MM-DD (formato SENAMHI/DEGAMMA)
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", date_str)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return date_str


def normalize_region_name(raw) -> str:
    """Normaliza nombre de región a formato DEIS/MINSAL canónico.

    Maneja:
    - Prefijos del notebook: "De X", "Del X" → "X"
    - Variaciones de acentuación y casing
    - Nombres alternativos (ej: "Magallanes y de La Antártica Chilena" → "Magallanes")
    """
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    cleaned = str(raw).strip()

    # Mapeo de alias → nombre canónico (lowercase para matching)
    alias_map = {
        # Folder names → canónico
        "rm": "Metropolitana",
        # Con prefijo "De"/"Del"
        "de arica y parinacota": "Arica y Parinacota",
        "de tarapacá": "Tarapacá",
        "de antofagasta": "Antofagasta",
        "de atacama": "Atacama",
        "de coquimbo": "Coquimbo",
        "de valparaíso": "Valparaíso",
        "del libertador b. o'higgins": "O'Higgins",
        "del maule": "Maule",
        "de ñuble": "Ñuble",
        "del biobío": "Biobío", "del biobio": "Biobío",
        "de la araucanía": "La Araucanía", "de la araucania": "La Araucanía",
        "de los ríos": "Los Ríos", "de los rios": "Los Ríos",
        "de los lagos": "Los Lagos",
        "de aysén": "Aysén", "de aysen": "Aysén",
        "de magallanes y de la antártica chilena": "Magallanes",
        "metropolitana de santiago": "Metropolitana",
        # Sin prefijo
        "arica y parinacota": "Arica y Parinacota",
        "tarapacá": "Tarapacá", "tarapaca": "Tarapacá",
        "antofagasta": "Antofagasta",
        "atacama": "Atacama",
        "coquimbo": "Coquimbo",
        "valparaíso": "Valparaíso", "valparaiso": "Valparaíso",
        "metropolitana": "Metropolitana",
        "o'higgins": "O'Higgins", "ohiggins": "O'Higgins",
        "maule": "Maule",
        "ñuble": "Ñuble", "nuble": "Ñuble",
        "biobío": "Biobío", "biobio": "Biobío",
        "la araucanía": "La Araucanía", "araucania": "La Araucanía",
        "los ríos": "Los Ríos", "los rios": "Los Ríos",
        "los lagos": "Los Lagos",
        "aysén": "Aysén", "aysen": "Aysén",
        "magallanes": "Magallanes",
    }
    lookup = cleaned.lower().strip()
    return alias_map.get(lookup, cleaned)


def is_respiratory_cause(cause_name: str, cause_code: str = "") -> bool:
    """
    Determina si una causa médica es respiratoria (CIE-10 J00-J99 + keywords).
    """
    text = str(cause_name).upper()
    code = str(cause_code).strip().upper()
    # Check CIE-10 prefixes
    for prefix in RESPIRATORY_CIE_PREFIXES:
        if text.startswith(prefix) or code.startswith(prefix):
            return True
    # Keyword fallback
    return any(kw in text for kw in RESPIRATORY_KEYWORDS)


# ---------------------------------------------------------------------------
# Loader 1: Salud (DEIS)
# ---------------------------------------------------------------------------
def load_health_data(year: str) -> pd.DataFrame:
    """
    Carga datos de atenciones de urgencia respiratorias de DEIS.

    - Filtra causas respiratorias (CIE-10 J00-J99 + keywords)
    - Normaliza fechas y regiones
    - Preserva estructura por establecimiento + fecha + rango etario

    Args:
        year: Año del archivo ('2024' o '2025')

    Returns:
        DataFrame con columnas:
        [IdEstablecimiento, NEstablecimiento, Fecha, Region, CodigoRegion,
         TipoEstablecimiento, Total, Menores_1, De_1_a_4, De_5_a_14,
         De_15_a_64, De_65_y_mas, es_respiratoria]
    """
    file_path = RAW_DIR / f"AtencionesUrgencia{year}.csv"
    if not file_path.exists():
        raise FileNotFoundError(f"No se encontró: {file_path}")

    logger.info("Cargando datos de salud %s...", year)

    # Detectar encoding
    encoding = "utf-8"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            f.read(8192)
    except UnicodeDecodeError:
        encoding = "latin-1"
        logger.info("Usando latin-1 para %s", file_path.name)

    # Leer en chunks para manejar archivos grandes
    chunk_size = 500_000
    chunks = []

    for chunk in pd.read_csv(
        file_path,
        sep=";",
        encoding=encoding,
        chunksize=chunk_size,
        dtype=str,
    ):
        # Normalizar nombres de columna
        chunk.columns = [c.strip() if c else f"Col{i}" for i, c in enumerate(chunk.columns)]

        # Filtrar respiratorias
        if "GlosaCausa" in chunk.columns and "IdCausa" in chunk.columns:
            mask = chunk.apply(
                lambda r: is_respiratory_cause(
                    str(r.get("GlosaCausa", "")), str(r.get("IdCausa", ""))
                ),
                axis=1,
            )
            chunk = chunk[mask].copy()

        if len(chunk) == 0:
            continue

        # Normalizar columnas
        chunk["Fecha"] = chunk.get("fecha", "").apply(normalize_date)

        # Normalizar región
        if "NombreRegion" in chunk.columns:
            chunk["Region"] = chunk["NombreRegion"].apply(normalize_region_name)
        else:
            chunk["Region"] = ""

        # Renombrar columnas para consistencia
        rename_map = {
            "IdEstablecimiento": "IdEstablecimiento",
            "NEstablecimiento": "NEstablecimiento",
            "CodigoRegion": "CodigoRegion",
            "GLOSATIPOESTABLECIMIENTO": "TipoEstablecimiento",
            "Total": "Total",
            "Menores_1": "Menores_1",
            "De_1_a_4": "De_1_a_4",
            "De_5_a_14": "De_5_a_14",
            "De_15_a_64": "De_15_a_64",
            "De_65_y_mas": "De_65_y_mas",
        }
        chunk = chunk.rename(columns=rename_map)

        # Convertir numéricos
        for col in ["Total", "Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas"]:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce").fillna(0).astype(int)

        chunk["es_respiratoria"] = 1  # Ya filtramos, siempre es 1
        chunks.append(chunk)

    if not chunks:
        logger.warning("No se obtuvieron datos respiratorios para %s", year)
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
    logger.info("Datos salud %s: %d filas respiratorias", year, len(df))
    return df


# ---------------------------------------------------------------------------
# Loader 2: Clima (temperatura)
# ---------------------------------------------------------------------------
def load_climate_data() -> pd.DataFrame:
    """
    Integra datos climáticos (temperatura mínima y máxima) para todas las regiones.

    Fuentes:
    - data/raw/Datos Por Región/ → CSVs por región (formato DEGAMMA/SENAMHI)
    - Fallback: API Open-Meteo Archive (si falta alguna región)

    Returns:
        DataFrame con columnas:
        [Region, Fecha, TempMin, TempMax, Precipitacion_mm]
    """
    logger.info("Integrando datos climáticos...")
    region_folder = RAW_DIR / "Datos Por Región"

    all_climate = []

    # Listar regiones
    for region_dir in sorted(region_folder.iterdir()):
        if not region_dir.is_dir() or region_dir.name.startswith("."):
            continue

        region_name = normalize_region_name(region_dir.name)
        temp_files = sorted(region_dir.glob("*Temperatura*"))

        if not temp_files:
            logger.warning("No hay archivos de temperatura para: %s", region_name)
            continue

        for temp_file in temp_files:
            logger.info("Procesando: %s/%s", region_name, temp_file.name)
            try:
                df = pd.read_csv(temp_file, sep=";", encoding="utf-8")
            except Exception as e:
                # Try latin-1
                df = pd.read_csv(temp_file, sep=";", encoding="latin-1")

            temp_df = pd.DataFrame()
            # Normalizar fecha
            if "Fecha" in df.columns:
                temp_df["Fecha"] = df["Fecha"].apply(normalize_date)
            else:
                # Buscar columna de fecha
                date_col = [c for c in df.columns if "fecha" in c.lower()]
                if date_col:
                    temp_df["Fecha"] = df[date_col[0]].apply(normalize_date)
                else:
                    logger.warning("Sin columna de fecha en %s: %s", temp_file.name, df.columns.tolist())
                    continue

            # Temperatura mínima
            if "Minima" in df.columns:
                temp_df["TempMin"] = pd.to_numeric(df["Minima"], errors="coerce")
            else:
                temp_df["TempMin"] = None

            # Temperatura máxima
            if "Maxima" in df.columns:
                temp_df["TempMax"] = pd.to_numeric(df["Maxima"], errors="coerce")
            else:
                temp_df["TempMax"] = None

            # Asignar región después de crear las otras columnas
            temp_df["Region"] = region_name

            all_climate.append(temp_df)

    if not all_climate:
        logger.warning("No se obtuvieron datos climáticos")
        return pd.DataFrame()

    climate_df = pd.concat(all_climate, ignore_index=True)
    climate_df = climate_df.drop_duplicates(subset=["Region", "Fecha"])

    logger.info("Datos climáticos: %d filas", len(climate_df))
    return climate_df


# ---------------------------------------------------------------------------
# Loader 3: Contaminación
# ---------------------------------------------------------------------------
def load_pollution_data() -> pd.DataFrame:
    """
    Carga datos de contaminación atmosférica (MP2.5, MP10) consolidados.

    Returns:
        DataFrame con columnas: [Fecha, MP2_5, MP10, Region]
    """
    file_path = RAW_DIR / "Contaminacion 2024 y 2025.csv"
    if not file_path.exists():
        logger.warning("No se encontró archivo de contaminación")
        return pd.DataFrame()

    logger.info("Cargando datos de contaminación...")
    df = pd.read_csv(file_path, encoding="utf-8")
    df["Fecha"] = df["Fecha"].apply(normalize_date)
    df["Region"] = df["Region"].apply(normalize_region_name)

    logger.info("Datos contaminación: %d filas", len(df))
    return df


# ---------------------------------------------------------------------------
# Loader 4: Precipitaciones (fallback desde consolidated CSV)
# ---------------------------------------------------------------------------
def load_precipitation_data() -> pd.DataFrame:
    """Carga datos de precipitación consolidados por región."""
    file_path = RAW_DIR / "Precipitaciones 2024 y 2025.csv"
    if not file_path.exists():
        logger.info("No se encontró archivo de precipitaciones consolidado")
        return pd.DataFrame()

    logger.info("Cargando datos de precipitación...")
    df = pd.read_csv(file_path, encoding="utf-8")
    df["Fecha"] = df["Fecha"].apply(normalize_date)
    df["Region"] = df["Region"].apply(normalize_region_name)

    return df[["Fecha", "Precipitacion_mm", "Region"]] if "Precipitacion_mm" in df.columns else df


# ---------------------------------------------------------------------------
# Pipeline principal: unificar todo
# ---------------------------------------------------------------------------
def unify_all_data() -> pd.DataFrame:
    """
    Integra las 4 fuentes de datos a nivel establecimiento + fecha.

    Estrategia:
    1. Cargar salud (filtrado respiratorio) — nivel establecimiento + fecha
    2. Unir clima (temp + precipitaciones) — nivel región + fecha → broadcast a establecimiento
    3. Unir contaminación — nivel región + fecha → broadcast a establecimiento

    Returns:
        DataFrame unificado con todas las variables integradas.
    """
    logger.info("=" * 60)
    logger.info("INICIANDO PIPELINE DE UNIFICACIÓN DE DATOS")
    logger.info("=" * 60)

    # 1. Salud
    health_2024 = load_health_data("2024")
    health_2025 = load_health_data("2025")
    health_df = pd.concat([health_2024, health_2025], ignore_index=True)
    logger.info("Datos salud integrados: %d filas", len(health_df))

    # 2. Clima (temp + precipitaciones)
    climate_df = load_climate_data()
    precip_df = load_precipitation_data()

    # Unir clima y precipitaciones
    if not climate_df.empty and not precip_df.empty:
        climate_df = climate_df.merge(
            precip_df,
            on=["Region", "Fecha"],
            how="left",
        )
    elif not precip_df.empty:
        climate_df = precip_df.rename(columns={"Precipitacion_mm": "Precipitacion_mm"})
        climate_df["TempMin"] = None
        climate_df["TempMax"] = None

    if climate_df.empty:
        logger.error("No se obtuvieron datos climáticos. Abortando.")
        return pd.DataFrame()

    # 3. Contaminación
    pollution_df = load_pollution_data()
    if not pollution_df.empty:
        climate_df = climate_df.merge(
            pollution_df,
            on=["Region", "Fecha"],
            how="left",
        )

    logger.info("Datos climáticos + contaminación: %d filas", len(climate_df))

    # 4. Unir salud con clima/contaminación por región + fecha
    #   → cada establecimiento hereda el clima de su región
    logger.info("Uniendo salud con clima/contaminación...")

    # Renombrar columnas del clima para evitar colisiones
    climate_cols = ["Region", "Fecha", "TempMin", "TempMax", "Precipitacion_mm", "MP2_5", "MP10"]
    existing_climate_cols = [c for c in climate_cols if c in climate_df.columns]
    climate_uniq = climate_df[existing_climate_cols].drop_duplicates(subset=["Region", "Fecha"])

    unified = health_df.merge(
        climate_uniq,
        left_on=["Region", "Fecha"],
        right_on=["Region", "Fecha"],
        how="left",
    )

    logger.info("DataFrame unificado: %d filas, %d columnas", len(unified), len(unified.columns))

    # Columnas finales ordenadas
    final_cols = [
        "IdEstablecimiento", "NEstablecimiento", "TipoEstablecimiento",
        "CodigoRegion", "Region", "CodigoComuna",
        "Fecha",
        # Target
        "Total", "Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas",
        # Clima
        "TempMin", "TempMax", "Precipitacion_mm",
        # Contaminación
        "MP2_5", "MP10",
        # Flag
        "es_respiratoria",
    ]

    # Seleccionar solo columnas que existen
    available_cols = [c for c in final_cols if c in unified.columns]
    unified = unified[available_cols]

    # Guardar
    output_file = INTERIM_DIR / "df_unificado.parquet"
    unified.to_parquet(output_file, index=False)
    logger.info("Datos unificados guardados en: %s", output_file)

    logger.info("=" * 60)
    logger.info("PIPELINE DE UNIFICACIÓN COMPLETADO")
    logger.info("=" * 60)

    return unified


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = unify_all_data()
    print(f"\n✅ Datos unificados: {len(df)} filas")
    print(f"Columnas: {list(df.columns)}")
    print(f"\nRegiones: {df['Region'].nunique() if 'Region' in df.columns else 0}")
    print(f"Establecimientos: {df['IdEstablecimiento'].nunique() if 'IdEstablecimiento' in df.columns else 0}")
