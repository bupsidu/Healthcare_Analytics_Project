"""
Script de Extracción de Datos de Contaminación del Aire
========================================================

Este módulo extrae datos históricos y pronósticos de calidad del aire,
específicamente concentraciones de MP2.5 y MP10, para todas las regiones
administrativas de Chile, utilizando la API pública de Open-Meteo Air Quality.

Autor: Ignacio Fernández (Nafery) - ML Lead
Proyecto: Sistema de Alerta Temprana MINSAL - Modelo Predictivo de Demanda Respiratoria

API Utilizada:
- Base: https://air-quality-api.open-meteo.com/v1/air-quality
- Parámetros: pm2_5, pm10 (en μg/m³)

Notas Metodológicas:
- Los valores horarios se promedian para obtener valores diarios
- MP2.5 representa partículas finas (< 2.5 μm)
- MP10 representa partículas gruesas (< 10 μm)
"""

import urllib.request
import urllib.error
import json
import csv
import os
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('contaminacion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('contaminacion_extraction')

# Coordenadas de las 16 regiones de Chile
REGIONES_COORDS = {
    'Arica y Parinacota': {'lat': -18.47, 'lon': -70.31},
    'Tarapacá': {'lat': -20.21, 'lon': -70.15},
    'Antofagasta': {'lat': -23.65, 'lon': -70.40},
    'Atacama': {'lat': -27.36, 'lon': -70.33},
    'Coquimbo': {'lat': -29.90, 'lon': -71.25},
    'Valparaíso': {'lat': -33.04, 'lon': -71.61},
    'Metropolitana': {'lat': -33.45, 'lon': -70.66},
    "O'Higgins": {'lat': -34.17, 'lon': -70.74},
    'Maule': {'lat': -35.42, 'lon': -71.65},
    'Ñuble': {'lat': -36.60, 'lon': -72.10},
    'Biobío': {'lat': -36.82, 'lon': -73.04},
    'La Araucanía': {'lat': -38.73, 'lon': -72.59},
    'Los Ríos': {'lat': -39.81, 'lon': -73.24},
    'Los Lagos': {'lat': -41.47, 'lon': -72.94},
    'Aysén': {'lat': -45.57, 'lon': -72.06},
    'Magallanes': {'lat': -53.16, 'lon': -70.91}
}

# Mapeo de normalización de regiones
REGION_NAMING_MAPPING = {
    'Tarapaca': 'Tarapacá',
    'Nuble': 'Ñuble',
    'Araucania': 'La Araucanía',
    'Aysen': 'Aysén',
    'Biobio': 'Biobío',
    "O'higgins": "O'Higgins",
}


def normalize_region_name(region: str) -> str:
    """Normaliza el nombre de una región al formato DEIS/MINSAL."""
    return REGION_NAMING_MAPPING.get(region, region)


def fetch_air_quality_data(
    lat: float, lon: float,
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
    forecast_days: int = 1,
    is_forecast: bool = False,
    max_retries: int = 3,
    retry_delay: float = 2.0
) -> Optional[Dict]:
    """
    Obtiene datos de calidad del aire desde la API de Open-Meteo.
    """
    if is_forecast:
        url = (f"https://air-quality-api.open-meteo.com/v1/air-quality"
               f"?latitude={lat}&longitude={lon}"
               f"&hourly=pm2_5,pm10&forecast_days={forecast_days}&timezone=auto")
    else:
        url = (f"https://air-quality-api.open-meteo.com/v1/air-quality"
               f"?latitude={lat}&longitude={lon}"
               f"&start_date={start_date}&end_date={end_date}"
               f"&hourly=pm2_5,pm10&timezone=auto")

    logger.debug(f"Solicitando datos para ({lat}, {lon})")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'MINSAL-AirQualityExtractor/1.0')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

                if 'hourly' not in data:
                    logger.warning("Respuesta: no contiene datos horarios")
                    return None
                if 'pm2_5' not in data['hourly'] or 'pm10' not in data['hourly']:
                    logger.warning("Respuesta: faltan parámetros pm2_5 o pm10")
                    return None

                return data

        except urllib.error.HTTPError as e:
            logger.error(f"Error HTTP {e.code}: {e.reason}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))
        except urllib.error.URLError as e:
            logger.error(f"Error de conexión: {e.reason}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))
            else:
                return None

    return None


def process_hourly_to_daily(data: Dict) -> List[Dict]:
    """
    Convierte datos horarios a promedios diarios.
    """
    hourly_data = data['hourly']
    times = hourly_data['time']
    pm25_list = hourly_data['pm2_5']
    pm10_list = hourly_data['pm10']

    diarios = {}

    for i, t in enumerate(times):
        fecha = t.split('T')[0] if 'T' in t else t.split(' ')[0]

        if fecha not in diarios:
            diarios[fecha] = {'pm25': [], 'pm10': []}

        if i < len(pm25_list) and pm25_list[i] is not None:
            diarios[fecha]['pm25'].append(pm25_list[i])
        if i < len(pm10_list) and pm10_list[i] is not None:
            diarios[fecha]['pm10'].append(pm10_list[i])

    daily_records = []
    for fecha, valores in diarios.items():
        avg_pm25 = round(sum(valores['pm25']) / len(valores['pm25']), 2) if valores['pm25'] else 0.0
        avg_pm10 = round(sum(valores['pm10']) / len(valores['pm10']), 2) if valores['pm10'] else 0.0
        daily_records.append({'fecha': fecha, 'pm2_5': avg_pm25, 'pm10': avg_pm10})

    return daily_records


def save_air_quality_csv(daily_records: List[Dict], region: str, output_file: str, forecast_timestamp: str = "") -> bool:
    """Guarda datos de calidad del aire en CSV."""
    try:
        normalized_region = normalize_region_name(region)
        with open(output_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            for record in daily_records:
                if forecast_timestamp:
                    writer.writerow([record['fecha'], record['pm2_5'], record['pm10'], normalized_region, forecast_timestamp])
                else:
                    writer.writerow([record['fecha'], record['pm2_5'], record['pm10'], normalized_region])
        return True
    except Exception as e:
        logger.error(f"Error al guardar CSV para {region}: {str(e)}")
        return False


def download_historical_air_quality(start_date: str = "2024-01-01", end_date: str = "2025-12-31", output_dir: str = "./data/contaminacion") -> str:
    """Descarga datos históricos de calidad del aire para todas las regiones."""
    logger.info(f"Iniciando descarga histórica ({start_date} a {end_date})")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = os.path.join(output_dir, "calidad_aire_historica.csv")

    with open(output_file, mode='w', newline='', encoding='utf-8') as master_file:
        csv.writer(master_file).writerow(['Fecha', 'MP2_5', 'MP10', 'Region'])

    success_count = 0
    error_count = 0

    for region, coords in REGIONES_COORDS.items():
        logger.info(f"Descargando: {region}...")
        data = fetch_air_quality_data(lat=coords['lat'], lon=coords['lon'], start_date=start_date, end_date=end_date, is_forecast=False)
        if data:
            daily_records = process_hourly_to_daily(data)
            if save_air_quality_csv(daily_records, region, output_file):
                success_count += 1
            else:
                error_count += 1
        else:
            error_count += 1
        time.sleep(1.0)

    logger.info(f"Completado. Éxitos: {success_count}, Errores: {error_count}")
    return output_file


def download_forecast_air_quality(forecast_days: int = 4, output_dir: str = "./data/forecast") -> str:
    """Descarga pronósticos de calidad del aire."""
    logger.info(f"Iniciando pronóstico ({forecast_days} días)")
    if forecast_days < 1 or forecast_days > 3:
        logger.warning("forecast_days ajustado al rango válido (1-3)")
        forecast_days = max(1, min(forecast_days, 3))

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(output_dir, f"calidad_aire_forecast_{timestamp_str}.csv")

    with open(output_file, mode='w', newline='', encoding='utf-8') as master_file:
        csv.writer(master_file).writerow(['Fecha', 'MP2_5', 'MP10', 'Region', 'Forecast_Timestamp'])

    success_count = 0
    error_count = 0
    forecast_timestamp = datetime.now().isoformat()

    for region, coords in REGIONES_COORDS.items():
        logger.info(f"Pronóstico para: {region}...")
        data = fetch_air_quality_data(lat=coords['lat'], lon=coords['lon'], forecast_days=forecast_days, is_forecast=True)
        if data:
            daily_records = process_hourly_to_daily(data)
            if save_air_quality_csv(daily_records, region, output_file, forecast_timestamp):
                success_count += 1
            else:
                error_count += 1
        else:
            error_count += 1
        time.sleep(1.0)

    logger.info(f"Pronóstico completado. Éxitos: {success_count}, Errores: {error_count}")
    return output_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Extractor de calidad del aire para MINSAL')
    parser.add_argument('--mode', choices=['historical', 'forecast'], default='historical')
    parser.add_argument('--start-date', type=str, default='2024-01-01')
    parser.add_argument('--end-date', type=str, default='2025-12-31')
    parser.add_argument('--forecast-days', type=int, default=4)
    parser.add_argument('--output-dir', type=str, default='./data/contaminacion')
    args = parser.parse_args()

    try:
        if args.mode == 'historical':
            output = download_historical_air_quality(args.start_date, args.end_date, args.output_dir)
        else:
            output = download_forecast_air_quality(args.forecast_days, args.output_dir)
        logger.info(f"✅ Extracción completada: {output}")
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise