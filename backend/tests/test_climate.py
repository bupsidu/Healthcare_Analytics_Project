import asyncio
import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from app.api.deps import get_current_user
from app.main import app
from app.services.open_meteo import (
    AIR_FIELDS,
    FORECAST_HOURS,
    TIMEZONE,
    WEATHER_FIELDS,
    OpenMeteoError,
    OpenMeteoTimeoutError,
    _get_json,
    get_climate_forecast,
)


def forecast_payloads():
    start = datetime(2026, 10, 12, 12)
    times = [(start + timedelta(hours=index)).isoformat() for index in range(FORECAST_HOURS)]
    weather = {
        "timezone": TIMEZONE,
        "hourly": {
            "time": times,
            **{field: [10.0] * FORECAST_HOURS for field in WEATHER_FIELDS},
        },
    }
    air = {
        "timezone": TIMEZONE,
        "hourly": {
            "time": list(times),
            **{field: list(range(FORECAST_HOURS)) for field in AIR_FIELDS},
        },
    }
    return weather, air


async def request_climate(query):
    """Llama a ASGI directamente: no abre sockets ni ejecuta el lifespan de PostgreSQL."""
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": "/api/clima",
            "raw_path": b"/api/clima", "root_path": "", "query_string": query.encode(),
            "headers": [], "client": ("127.0.0.1", 12345), "server": ("test", 80),
        },
        receive,
        send,
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(body)


class OpenMeteoTests(unittest.TestCase):
    def test_combines_by_time_even_when_air_is_reordered(self):
        weather, air = forecast_payloads()
        for field in air["hourly"]:
            air["hourly"][field].reverse()
        weather["hourly"]["temperature_2m"][0] = None
        with patch("app.services.open_meteo._get_json", side_effect=[weather, air]) as fetch:
            result = get_climate_forecast(-33.4489, -70.6693)
        self.assertEqual(result.horas_pronosticadas, 96)
        self.assertEqual(len(result.pronostico_horario), 96)
        self.assertEqual(result.pronostico_horario[0].pm2_5_ug_m3, 0)
        self.assertEqual(result.pronostico_horario[-1].pm2_5_ug_m3, 95)
        self.assertIsNone(result.pronostico_horario[0].temperatura_c)
        self.assertEqual(result.latitud, -33.4489)
        self.assertEqual(fetch.call_args_list[0].args[1]["forecast_hours"], 96)

    def test_rejects_incomplete_misaligned_or_invalid_forecasts(self):
        weather, air = forecast_payloads()
        for case in ("missing_field", "short_series", "wrong_time", "invalid_value", "wrong_timezone"):
            with self.subTest(case=case):
                bad_weather, bad_air = copy.deepcopy(weather), copy.deepcopy(air)
                if case == "missing_field":
                    del bad_air["hourly"]["pm10"]
                elif case == "short_series":
                    bad_air["hourly"]["pm10"].pop()
                elif case == "wrong_time":
                    bad_air["hourly"]["time"][0] = "2026-11-01T12:00:00"
                elif case == "invalid_value":
                    bad_weather["hourly"]["relative_humidity_2m"][0] = 101
                else:
                    bad_air["timezone"] = "UTC"
                with patch("app.services.open_meteo._get_json", side_effect=[bad_weather, bad_air]):
                    with self.assertRaises(OpenMeteoError):
                        get_climate_forecast(-33.4489, -70.6693)

    def test_network_and_http_errors_are_controlled(self):
        errors = (
            (HTTPError("https://example.test", 503, "Unavailable", {}, None), OpenMeteoError),
            (URLError("Offline"), OpenMeteoError),
            (TimeoutError("Timeout"), OpenMeteoTimeoutError),
            (URLError(TimeoutError("Timeout")), OpenMeteoTimeoutError),
        )
        for error, expected in errors:
            with self.subTest(error=type(error).__name__):
                with patch("app.services.open_meteo.urlopen", side_effect=error):
                    with self.assertRaises(expected):
                        _get_json("https://example.test", {})

    def test_invalid_json_is_controlled(self):
        for body in (b"not-json", b"[]", b"\xff"):
            with self.subTest(body=body):
                response = MagicMock()
                response.__enter__.return_value.read.return_value = body
                with patch("app.services.open_meteo.urlopen", return_value=response):
                    with self.assertRaises(OpenMeteoError):
                        _get_json("https://example.test", {})


class ClimateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_current_user] = lambda: object()

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)

    def test_valid_request_returns_96_hours(self):
        weather, air = forecast_payloads()
        with patch("app.services.open_meteo._get_json", side_effect=[weather, air]):
            status, body = asyncio.run(request_climate("latitud=-33.4489&longitud=-70.6693"))
        self.assertEqual(status, 200)
        self.assertEqual(len(body["pronostico_horario"]), 96)
        self.assertEqual(body["zona_horaria"], TIMEZONE)

    def test_invalid_or_missing_coordinates_do_not_call_provider(self):
        for query in ("latitud=91&longitud=0", "latitud=0&longitud=-181", "latitud=nan&longitud=0", "longitud=0"):
            with self.subTest(query=query):
                with patch("app.api.climate.get_climate_forecast") as service:
                    status, _ = asyncio.run(request_climate(query))
                self.assertEqual(status, 422)
                service.assert_not_called()

    def test_request_without_token_is_rejected(self):
        app.dependency_overrides.pop(get_current_user)
        with patch("app.api.climate.get_climate_forecast") as service:
            status, _ = asyncio.run(request_climate("latitud=0&longitud=0"))
        self.assertEqual(status, 401)
        service.assert_not_called()

    def test_provider_errors_become_502_or_504(self):
        for error, expected in ((OpenMeteoError(), 502), (OpenMeteoTimeoutError(), 504)):
            with self.subTest(status=expected):
                with patch("app.api.climate.get_climate_forecast", side_effect=error):
                    status, _ = asyncio.run(request_climate("latitud=0&longitud=0"))
                self.assertEqual(status, expected)


if __name__ == "__main__":
    unittest.main()
