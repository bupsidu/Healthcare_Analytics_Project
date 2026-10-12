"""
Script de Extracción de Datos Climáticos - Precipitaciones
============================================================

Este módulo extrae datos históricos y futuros de precipitaciones diarias
para todas las regiones administrativas de Chile, utilizando la API pública de Open-Meteo.

Autor: Ignacio Fernández (Nafery) - ML Lead
Proyecto: Sistema de Alerta Temprana MINSAL - Modelo Predictivo de Demanda Respiratoria

Funcionalidades:
- Descarga de datos históricos desde la API de archivo de Open-Meteo
- Descarga de pronósticos desde la API estándar de Open-Meteo
- Normalización de nombres de regiones a formato DEIS/MINSAL
- Manejo robusto de errores con reintentos y backoff exponencial
- Logging estructurado para trazabilidad completa
- Consolidación de datos en archivos CSV unificados

API Utilizada:
- Histórico: https://archive-api.open-meteo.com/v1/archive
- Pronóstico: https://api.open-meteo.com/v1/forecast
- Parámetro: precipitation_sum (precipitación diaria en mm)
"""

import urllib.request
import urllib.error
import json
import csv
import os
import logging
import time
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

# Configuración del sistema de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('precipitaciones.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('precipitaciones_extraction')

# Coordenadas geográficas de las 16 regiones de Chile
REGIONES_COORDS: Dict[str, Dict[str, float]] = {
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

# Mapeo de normalización de regiones (compatibilidad con datos DEIS)
REGION_NAMING_MAPPING: Dict[str, str] = {
    'Tarapaca': 'Tarapacá',
    'Nuble': 'Ñuble',
    'Araucania': 'La Araucanía',
    'Aysen': 'Aysén',
    'Biobio': 'Biobío',
    "O'higgins": "O'Higgins",
    "ohiggins": "O'Higgins"
}


def normalize_region_name(region: str) -> str:
    """Normaliza el nombre de una región al formato DEIS/MINSAL."""
    return REGION_NAMING_MAPPING.get(region, region)


def fetch_precipitation_data(
    lat: float,
    lon: float,
    start_date: str = "",
    end_date: str = "",
    is_forecast: bool = False,
    forecast_days: int = 4,
    max_retries: int = 3,
    retry_delay: float = 2.0
) -> Optional[Dict]:
    """
    Obtiene datos de precipitación diaria desde la API de Open-Meteo.
    
    Args:
        lat: Latitud de la ubicación
        lon: Longitud de la ubicación
        start_date: Fecha de inicio (YYYY-MM-DD) - para modo histórico
        end_date: Fecha de fin (YYYY-MM-DD) - para modo histórico
        is_forecast: Si True, usa API de pronóstico; si False, usa API de archivo
        forecast_days: Días de pronóstico (1-7)
        max_retries: Número máximo de reintentos
        retry_delay: Segundos de espera inicial (backoff exponencial)
        
    Returns:
        Dict con datos de precipitación, o None si falla
    """
    if is_forecast:
        url = (f"https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               f"&daily=precipitation_sum&timezone=auto&forecast_days={forecast_days}")
    else:
        url = (f"https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={lat}&longitude={lon}"
               f"&start_date={start_date}&end_date={end_date}"
               f"&daily=precipitation_sum&timezone=auto")
    
    logger.debug(f"Solicitando datos para coordenadas ({lat}, {lon})")
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"Intento {attempt + 1}/{max_retries} para ({lat}, {lon})")
            
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'MINSAL-PrecipitationExtractor/1.0')
            
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                if 'daily' not in data or 'time' not in data['daily']:
                    logger.warning("Estructura inesperada en respuesta de API")
                    return None
                    
                logger.debug("Datos recibidos exitosamente")
                return data
                
        except urllib.error.HTTPError as e:
            logger.error(f"Error HTTP {e.code}: {e.reason}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.info(f"Reintentando en {wait_time}s...")
                time.sleep(wait_time)
                
        except urllib.error.URLError as e:
            logger.error(f"Error de conexión: {e.reason}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.info(f"Reintentando en {wait_time}s...")
                time.sleep(wait_time)
                
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON: {e}")
            return None
            
        except Exception as e:
            logger.error(f"Error inesperado: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                logger.info(f"Reintentando en {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error("Agotados reintentos")
                return None
    
    return None


def save_precipitation_csv(
    data: Dict,
    region: str,
    output_file: str,
    forecast_timestamp: str = ""
) -> bool:
    """
    Guarda los datos de precipitación en un archivo CSV consolidado.
    
    Args:
        data: Datos de precipitación obtenidos de la API
        region: Nombre de la región
        output_file: Ruta del archivo CSV de salida
        forecast_timestamp: Timestamp del pronóstico
        
    Returns:
        bool: True si se guardó correctamente
    """
    try:
        fechas = data['daily']['time']
        precipitaciones = data['daily']['precipitation_sum']
        normalized_region = normalize_region_name(region)
        
        with open(output_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            for fecha, precipitacion in zip(fechas, precipitaciones):
                precip_value = precipitacion if precipitacion is not None else 0.0
                if forecast_timestamp:
                    writer.writerow([fecha, precip_value, normalized_region, forecast_timestamp])
                else:
                    writer.writerow([fecha, precip_value, normalized_region])
                    
        logger.debug(f"Registros guardados para {normalized_region}")
        return True
        
    except Exception as e:
        logger.error(f"Error al guardar CSV para {region}: {str(e)}")
        return False


def download_historical_precipitations(
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
    output_dir: str = "./data/clima"
) -> str:
    """
    Descarga datos históricos de precipitaciones para todas las regiones de Chile.
    
    Args:
        start_date: Fecha de inicio (YYYY-MM-DD)
        end_date: Fecha de fin (YYYY-MM-DD)
        output_dir: Directorio de salida
        
    Returns:
        str: Ruta del archivo CSV consolidado
    """
    logger.info(f"Iniciando descarga histórica ({start_date} a {end_date})")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = os.path.join(output_dir, "precipitaciones_historicas.csv")
    
    with open(output_file, mode='w', newline='', encoding='utf-8') as master_file:
        master_writer = csv.writer(master_file)
        master_writer.writerow(['Fecha', 'Precipitacion_mm', 'Region'])
    
    success_count = 0
    error_count = 0
    
    for region, coords in REGIONES_COORDS.items():
        logger.info(f"Descargando: {region}...")
        
        data = fetch_precipitation_data(
            lat=coords['lat'],
            lon=coords['lon'],
            start_date=start_date,
            end_date=end_date,
            is_forecast=False
        )
        
        if data:
            if save_precipitation_csv(data, region, output_file):
                success_count += 1
            else:
                error_count += 1
        else:
            error_count += 1
            logger.error(f"Falló descarga para: {region}")
        
        time.sleep(1.0)  # Respetar rate limits
    
    logger.info(f"Completado. Éxitos: {success_count}, Errores: {error_count}")
    logger.info(f"Archivo generado: {output_file}")
    
    return output_file


def download_forecast_precipitations(
    forecast_days: int = 4,
    output_dir: str = "./data/forecast"
) -> str:
    """
    Descarga pronósticos de precipitaciones para los próximos días.
    
    Args:
        forecast_days: Días de pronóstico (1-7)
        output_dir: Directorio de salida
        
    Returns:
        str: Ruta del archivo CSV consolidado de pronósticos
    """
    logger.info(f"Iniciando pronóstico de precipitaciones ({forecast_days} días)")
    
    if forecast_days < 1 or forecast_days > 7:
        logger.warning("forecast_days ajustado al rango válido (1-7)")
        forecast_days = max(1, min(forecast_days, 7))
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(output_dir, f"precipitaciones_forecast_{timestamp_str}.csv")
    
    with open(output_file, mode='w', newline='', encoding='utf-8') as master_file:
        master_writer = csv.writer(master_file)
        master_writer.writerow(['Fecha', 'Precipitacion_mm', 'Region', 'Forecast_Timestamp'])
    
    success_count = 0
    error_count = 0
    forecast_timestamp = datetime.now().isoformat()
    
    for region, coords in REGIONES_COORDS.items():
        logger.info(f"Obteniendo pronóstico para: {region}...")
        
        data = fetch_precipitation_data(
            lat=coords['lat'],
            lon=coords['lon'],
            is_forecast=True,
            forecast_days=forecast_days
        )
        
        if data:
            if save_precipitation_csv(data, region, output_file, forecast_timestamp):
                success_count += 1
            else:
                error_count += 1
        else:
            error_count += 1
            logger.error(f"Falló pronóstico para: {region}")
        
        time.sleep(1.0)
    
    logger.info(f"Pronóstico completado. Éxitos: {success_count}, Errores: {error_count}")
    logger.info(f"Archivo generado: {output_file}")
    
    return output_file


if __name__ == "__main__":
    """Punto de entrada principal del script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extractor de precipitaciones para MINSAL',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--mode', choices=['historical', 'forecast'], default='historical',
                       help='Modo de descarga: histórico o pronóstico')
    parser.add_argument('--start-date', type=str, default='2024-01-01',
                       help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2025-12-31',
                       help='Fecha de fin (YYYY-MM-DD)')
    parser.add_argument('--forecast-days', type=int, default=4,
                       help='Días de pronóstico (1-7)')
    parser.add_argument('--output-dir', type=str, default='./data/clima',
                       help='Directorio de salida')
    
    args = parser.parse_args()
    
    try:
        if args.mode == 'historical':
            output = download_historical_precipitations(
                start_date=args.start_date,
                end_date=args.end_date,
                output_dir=args.output_dir
            )
        else:
            output = download_forecast_precipitations(
                forecast_days=args.forecast_days,
                output_dir=args.output_dir
            )
        logger.info(f"✅ Extracción completada: {output}")
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise