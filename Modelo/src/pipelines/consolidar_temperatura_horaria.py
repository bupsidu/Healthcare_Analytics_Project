"""
Convierte datos horarios de temperatura SENAMHI (CodigoNacional;Instante;Ts)
a resumen diario con el esquema que consume unificar_datos.load_climate_data().

Uso:
    python3 src/pipelines/consolidar_temperatura_horaria.py

Lee los CSV horarios indicados en SOURCES, agrega min/max/mean por día y
escribe `data/raw/Datos Por Región/<Region>/Temperatura <Region> <year>.csv`.
Los originales horarios se copian a data/raw/_hourly_sources/ para trazabilidad.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
RAW = BASE / "data" / "raw"
REGION_DIR = RAW / "Datos Por Región"
HOURLY_DIR = RAW / "_hourly_sources"
REPLACED_DIR = RAW / "_replaced_invalid"

DOWNLOADS = Path.home() / "Downloads"

# (región, año, archivo horario, código de estación)
SOURCES = [
    ("Antofagasta", 2024, "220002_2024_Temperatura_Antofagasta.csv", "220002"),
    ("Atacama", 2024, "270008_2024_Temperatura_Atacama.csv", "270008"),
    ("Los Lagos", 2024, "400009_2024_Temperatura_LosLagos.csv", "400009"),
    ("Los Lagos", 2025, "400009_2025_Temperatura_LosLagos.csv", "400009"),
    ("Tarapacá", 2024, "200006_2024_Temperatura_Tarapaca.csv", "200006"),
]

DAILY_COLUMNS = [
    "CodigoNacional", "Fecha", "MediaCli", "MediaAri", "NumDatos",
    "Ts00", "Ts12", "Maxima", "FechaMax", "Minima", "FechaMin", "FechaPro",
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("consolidar")


def resolve_region_dir(region: str) -> Path:
    """Encuentra la carpeta de región real (los nombres en disco pueden estar en NFD)."""
    import unicodedata

    target = unicodedata.normalize("NFC", region)
    for p in REGION_DIR.iterdir():
        if p.is_dir() and unicodedata.normalize("NFC", p.name) == target:
            return p
    raise FileNotFoundError(f"No existe carpeta de región para: {region}")


def build_daily(path: Path, year: int, station: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str)
    df["f"] = pd.to_datetime(df["Instante"], errors="coerce")
    df["Ts"] = pd.to_numeric(df["Ts"].str.replace(",", ".", regex=False), errors="coerce")
    df = df.dropna(subset=["f", "Ts"])

    # Recortar al año solicitado (los archivos traen una fila del 01-01 del año siguiente)
    df = df[df["f"].dt.year == year].copy()
    df["dia"] = df["f"].dt.normalize()

    rows = []
    for dia, g in df.groupby("dia"):
        g = g.sort_values("f")
        n = len(g)
        rows.append({
            "CodigoNacional": station,
            "Fecha": dia.strftime("%d-%m-%Y"),
            "MediaCli": round(g["Ts"].mean(), 1),
            "MediaAri": round(g["Ts"].mean(), 1),
            "NumDatos": n,
            "Ts00": g.iloc[0]["Ts"],
            "Ts12": (g[g["f"].dt.hour == 12].iloc[0]["Ts"]
                     if (g["f"].dt.hour == 12).any() else ""),
            "Maxima": round(g["Ts"].max(), 1),
            "FechaMax": dia.strftime("%d-%m-%Y"),
            "Minima": round(g["Ts"].min(), 1),
            "FechaMin": dia.strftime("%d-%m-%Y"),
            "FechaPro": dia.strftime("%d-%m-%Y"),
        })

    daily = pd.DataFrame(rows, columns=DAILY_COLUMNS)
    return daily.sort_values("Fecha", key=lambda s: pd.to_datetime(s, format="%d-%m-%Y"))


def main() -> None:
    HOURLY_DIR.mkdir(parents=True, exist_ok=True)
    REPLACED_DIR.mkdir(parents=True, exist_ok=True)

    for region, year, filename, station in SOURCES:
        src = DOWNLOADS / filename
        if not src.exists():
            raise FileNotFoundError(f"No se encontró el archivo descargado: {src}")

        daily = build_daily(src, year, station)
        expected = 366 if year % 4 == 0 else 365
        log.info("%s %s: %d días diarios (esperado %d)", region, year, len(daily), expected)
        if len(daily) < expected - 5:
            log.warning("  ⚠ %s %s tiene %d días de %d", region, year, len(daily), expected)

        region_dir = resolve_region_dir(region)
        dest = region_dir / f"Temperatura {region} {year}.csv"

        # Apartar el archivo inválido previo (vacío o de precipitación)
        if dest.exists():
            backup = REPLACED_DIR / f"{dest.name}.invalid"
            shutil.move(str(dest), str(backup))
            log.info("  Archivo previo movido a: %s", backup.relative_to(BASE))

        daily.to_csv(dest, sep=";", index=False, encoding="utf-8")
        log.info("  Escrito: %s (%d filas)", dest.relative_to(BASE), len(daily))

        # Preservar el original horario
        shutil.copy2(src, HOURLY_DIR / src.name)
        log.info("  Original horario preservado en: %s", (HOURLY_DIR / src.name).relative_to(BASE))


if __name__ == "__main__":
    main()
