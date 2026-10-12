import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError

from app.schemas.climate import ClimateResponse


WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEZONE = "America/Santiago"
FORECAST_HOURS = 96
REQUEST_TIMEOUT_SECONDS = 10

WEATHER_FIELDS = {
    "temperature_2m": "temperatura_c",
    "relative_humidity_2m": "humedad_relativa_pct",
    "precipitation": "precipitacion_mm",
    "wind_speed_10m": "viento_kmh",
}
AIR_FIELDS = {
    "pm10": "pm10_ug_m3",
    "pm2_5": "pm2_5_ug_m3",
    "ozone": "ozono_ug_m3",
    "us_aqi": "indice_calidad_aire_us",
}


class OpenMeteoError(Exception):
    """El proveedor no está disponible o devolvió datos inválidos."""


class OpenMeteoTimeoutError(OpenMeteoError):
    """El proveedor excedió el tiempo máximo de espera."""


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={"User-Agent": "Healthcare-Analytics/0.1", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise OpenMeteoError("Open-Meteo respondió con un error HTTP") from exc
    except TimeoutError as exc:
        raise OpenMeteoTimeoutError("Open-Meteo excedió el tiempo de espera") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise OpenMeteoTimeoutError("Open-Meteo excedió el tiempo de espera") from exc
        raise OpenMeteoError("No se pudo conectar con Open-Meteo") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenMeteoError("Open-Meteo devolvió una respuesta inválida") from exc

    if not isinstance(payload, dict):
        raise OpenMeteoError("Open-Meteo devolvió una respuesta inválida")
    return payload


def _hourly_rows(payload: dict[str, Any], fields: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Relaciona cada instante con sus valores; nunca inventa ceros para datos faltantes."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or payload.get("timezone") != TIMEZONE:
        raise OpenMeteoError("Open-Meteo devolvió datos horarios inválidos")
    times = hourly.get("time")
    if (
        not isinstance(times, list)
        or len(times) != FORECAST_HOURS
        or not all(isinstance(time, str) for time in times)
        or len(set(times)) != len(times)
    ):
        raise OpenMeteoError("Open-Meteo no devolvió las 96 horas solicitadas")

    for field in fields:
        series = hourly.get(field)
        if not isinstance(series, list) or len(series) != len(times):
            raise OpenMeteoError("Open-Meteo devolvió una serie incompleta")

    return {
        time: {output_field: hourly[field][index] for field, output_field in fields.items()}
        for index, time in enumerate(times)
    }


def get_climate_forecast(latitude: float, longitude: float) -> ClimateResponse:
    """Consulta ambos proveedores y combina clima y contaminación por fecha/hora."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "forecast_hours": FORECAST_HOURS,
        "timezone": TIMEZONE,
    }
    weather = _get_json(
        WEATHER_URL,
        {**params, "hourly": ",".join(WEATHER_FIELDS), "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"},
    )
    air = _get_json(AIR_QUALITY_URL, {**params, "hourly": ",".join(AIR_FIELDS)})
    weather_rows = _hourly_rows(weather, WEATHER_FIELDS)
    air_rows = _hourly_rows(air, AIR_FIELDS)
    if weather_rows.keys() != air_rows.keys():
        raise OpenMeteoError("Los horarios de clima y contaminación no coinciden")

    try:
        return ClimateResponse(
            latitud=latitude,
            longitud=longitude,
            zona_horaria=TIMEZONE,
            horas_pronosticadas=FORECAST_HOURS,
            pronostico_horario=[
                {"fecha_hora": time, **values, **air_rows[time]}
                for time, values in weather_rows.items()
            ],
        )
    except ValidationError as exc:
        raise OpenMeteoError("Open-Meteo devolvió valores inválidos") from exc
