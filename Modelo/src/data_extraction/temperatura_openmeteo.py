"""
Genera archivos de temperatura 2026 en formato SENAMHI a partir de Open-Meteo.

Necesario porque el pipeline de unificación lee temperatura desde
`data/raw/Datos Por Región/<Region>/Temperatura <Region> <año>.csv` con el
esquema SENAMHI, y para 2026 no existen esos archivos.

Usa el endpoint de archivo (datos observados) de Open-Meteo. Genera el mismo
esquema que consumen los CSV de SENAMHI:

    CodigoNacional;Fecha;MediaCli;MediaAri;NumDatos;Ts00;Ts12;Maxima;FechaMax;Minima;FechaMin;FechaPro

Uso:
    python3 src/data_extraction/temperatura_openmeteo.py --start-date 2026-01-01 --end-date 2026-11-15
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw" / "Datos Por Región"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Coordenadas de la capital regional (mismas que usan los scripts de clima).
REGIONES = {
    "Arica y Parinacota": (-18.47, -70.31),
    "Tarapacá": (-20.21, -70.15),
    "Antofagasta": (-23.65, -70.40),
    "Atacama": (-27.37, -70.33),
    "Coquimbo": (-29.95, -71.34),
    "Valparaíso": (-33.05, -71.62),
    "Metropolitana": (-33.45, -70.66),
    "O'Higgins": (-34.17, -70.74),
    "Maule": (-35.43, -71.66),
    "Ñuble": (-36.61, -72.10),
    "Biobío": (-36.82, -73.05),
    "La Araucanía": (-38.74, -72.60),
    "Los Ríos": (-39.81, -73.25),
    "Los Lagos": (-41.47, -72.94),
    "Aysén": (-45.57, -72.07),
    "Magallanes": (-53.16, -70.91),
}

# Carpeta real en disco (los nombres pueden estar en NFD por macOS).
CARPETAS = {
    "Metropolitana": "RM",
    "Biobío": "Bio Bio",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger("temp2026")


def fetch(lat: float, lon: float, start: str, end: str, forecast: bool) -> dict:
    base = FORECAST_URL if forecast else ARCHIVE_URL
    params = (
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_min,temperature_2m_max,temperature_2m_mean"
        f"&timezone=America%2FSantiago"
    )
    if forecast:
        params += "&forecast_days=16"
    else:
        params += f"&start_date={start}&end_date={end}"
    req = urllib.request.Request(base + params, headers={"User-Agent": "MINSAL-tesis/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def to_senamhi(data: dict, region: str) -> pd.DataFrame:
    d = data.get("daily", {})
    fechas = d.get("time", [])
    if not fechas:
        return pd.DataFrame()
    mins = d.get("temperature_2m_min", [None] * len(fechas))
    maxs = d.get("temperature_2m_max", [None] * len(fechas))
    medias = d.get("temperature_2m_mean", [None] * len(fechas))

    filas = []
    for f, mn, mx, md in zip(fechas, mins, maxs, medias):
        if mn is None and mx is None:
            continue
        filas.append({
            "CodigoNacional": f"OM-{region[:6].upper()}",
            "Fecha": pd.Timestamp(f).strftime("%d-%m-%Y"),
            "MediaCli": round(md, 1) if md is not None else "",
            "MediaAri": "",
            "NumDatos": 24,
            "Ts00": "",
            "Ts12": "",
            "Maxima": round(mx, 1) if mx is not None else "",
            "FechaMax": pd.Timestamp(f).strftime("%d-%m-%Y"),
            "Minima": round(mn, 1) if mn is not None else "",
            "FechaMin": pd.Timestamp(f).strftime("%d-%m-%Y"),
            "FechaPro": pd.Timestamp(f).strftime("%d-%m-%Y"),
        })
    return pd.DataFrame(filas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", default="2026-01-01")
    ap.add_argument("--end-date", default="2026-11-15")
    args = ap.parse_args()

    total_ok = 0
    for region, (lat, lon) in REGIONES.items():
        nombre_carpeta = CARPETAS.get(region, region)
        carpeta = RAW_DIR / nombre_carpeta
        if not carpeta.exists():
            log.warning("Sin carpeta para %s (%s)", region, nombre_carpeta)
            continue

        # Histórico observado
        try:
            data = fetch(lat, lon, args.start_date, args.end_date, forecast=False)
            df = to_senamhi(data, region)
            if df.empty:
                log.warning("%s: sin datos", region)
                continue
            dest = carpeta / f"Temperatura {region} 2026.csv"
            df.to_csv(dest, sep=";", index=False, encoding="utf-8")
            log.info("%s: %d días (%s → %s)", region, len(df),
                     df["Fecha"].iloc[0], df["Fecha"].iloc[-1])
            total_ok += 1
        except urllib.error.URLError as exc:
            log.error("%s: error de red %s", region, exc)
        time.sleep(0.4)  # cortesía con la API

        # Pronóstico (16 días) como archivo aparte, para las predicciones futuras
        try:
            data_f = fetch(lat, lon, args.start_date, args.end_date, forecast=True)
            df_f = to_senamhi(data_f, region)
            if not df_f.empty:
                dest_f = carpeta / f"Temperatura {region} 2026 forecast.csv"
                df_f.to_csv(dest_f, sep=";", index=False, encoding="utf-8")
        except urllib.error.URLError:
            pass
        time.sleep(0.4)

    log.info("Completado: %d/16 regiones", total_ok)


if __name__ == "__main__":
    main()
