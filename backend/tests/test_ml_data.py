import asyncio
import json
import unittest
from datetime import date, datetime, timezone
from urllib.parse import urlencode

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.session import Base, get_db
from app.main import app
from app.models.establishment import Establishment
from app.models.ml_data import DailyClimate, DailyDemand, StoredPrediction
from app.models.user import User


async def request(path, method="GET", body=None, query=None):
    messages = []

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "root_path": "", "query_string": urlencode(query or {}).encode(),
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345), "server": ("test", 80),
    }, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    return status, json.loads(b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body"))


class MLDataTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(email="test@example.invalid", hashed_password="test")
        self.db.add_all([
            self.user,
            Establishment(id=1, nombre="Prueba", comuna="Santiago", region="Metropolitana"),
            Establishment(id=2, nombre="Catálogo sintético", comuna="Santiago", region="Metropolitana",
                          id_establecimiento="TEST-02", tipo="Hospital"),
        ])
        self.db.commit()
        self.previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)
        self.db.close()
        self.engine.dispose()

    def call(self, *args, **kwargs):
        return asyncio.run(request(*args, **kwargs))

    def test_catalog_keeps_legacy_numeric_id_and_nullable_code(self):
        status, data = self.call("/api/establecimientos")
        self.assertEqual(status, 200)
        self.assertEqual(data[0]["id"], 1)
        self.assertIsNone(data[0]["id_establecimiento"])
        self.assertIsNone(data[0]["tipo"])
        self.assertTrue(data[0]["activo"])

    def test_patch_catalog_and_filter_active(self):
        status, data = self.call("/api/establecimientos/1", "PATCH",
                                 {"id_establecimiento": " TEST-01 ", "tipo": "SAR", "activo": False})
        self.assertEqual(status, 200)
        self.assertEqual(data["id_establecimiento"], "TEST-01")
        self.assertEqual(data["tipo"], "SAR")
        status, data = self.call("/api/establecimientos", query={"activo": "true"})
        self.assertEqual([row["id"] for row in data], [2])

    def test_patch_does_not_reset_fields_omitted(self):
        status, _ = self.call("/api/establecimientos/2", "PATCH", {"activo": False})
        self.assertEqual(status, 200)
        status, data = self.call("/api/establecimientos/2", "PATCH", {"tipo": "SAPU"})
        self.assertFalse(data["activo"])
        self.assertEqual(data["id_establecimiento"], "TEST-02")

    def test_patch_validation_not_found_and_duplicate(self):
        for body in ({}, {"tipo": "Otro"}, {"id_establecimiento": " "}, {"activo": None}, {"nombre": "Otro"}):
            self.assertEqual(self.call("/api/establecimientos/1", "PATCH", body)[0], 422)
        self.assertEqual(self.call("/api/establecimientos/99", "PATCH", {"tipo": "Hospital"})[0], 404)
        self.assertEqual(self.call("/api/establecimientos/1", "PATCH", {"id_establecimiento": "TEST-02"})[0], 409)
        self.assertIsNone(self.db.get(Establishment, 1).id_establecimiento)

    def test_demand_put_replaces_without_duplicate_or_addition(self):
        body = {"id_establecimiento": "TEST-02", "fecha": "2026-10-13", "total": 12}
        self.assertEqual(self.call("/api/demanda-diaria", "PUT", body)[0], 201)
        body["total"] = 8
        status, data = self.call("/api/demanda-diaria", "PUT", body)
        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 8)
        self.assertEqual(self.db.query(DailyDemand).count(), 1)
        status, data = self.call("/api/demanda-diaria", query={"id_establecimiento": "TEST-02"})
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["total"], 8)

    def test_demand_requires_existing_code_and_valid_total(self):
        body = {"id_establecimiento": "MISSING", "fecha": "2026-10-13", "total": 12}
        self.assertEqual(self.call("/api/demanda-diaria", "PUT", body)[0], 404)
        for total in (-1, 1.5, 2147483648):
            body["total"] = total
            self.assertEqual(self.call("/api/demanda-diaria", "PUT", body)[0], 422)
        self.assertEqual(self.db.query(DailyDemand).count(), 0)

    def test_code_in_use_cannot_be_reassigned(self):
        self.call("/api/demanda-diaria", "PUT", {"id_establecimiento": "TEST-02", "fecha": "2026-10-13", "total": 1})
        status, _ = self.call("/api/establecimientos/2", "PATCH", {"id_establecimiento": "TEST-NEW"})
        self.assertEqual(status, 409)
        self.assertEqual(self.db.get(Establishment, 2).id_establecimiento, "TEST-02")

    def test_climate_put_preserves_nulls_and_replaces(self):
        body = {"region": " Metropolitana ", "fecha": "2026-10-13", "temp_min": 1.5,
                "temp_max": 14.2, "precipitacion_mm": None}
        status, data = self.call("/api/clima/diario", "PUT", body)
        self.assertEqual(status, 201)
        self.assertEqual(data["region"], "Metropolitana")
        self.assertIsNone(data["precipitacion_mm"])
        status, data = self.call("/api/clima/diario", "PUT", {"region": "Metropolitana", "fecha": "2026-10-13"})
        self.assertEqual(status, 200)
        self.assertIsNone(data["temp_min"])
        self.assertEqual(self.db.query(DailyClimate).count(), 1)
        status, data = self.call("/api/clima/historial", query={"region": "Metropolitana"})
        self.assertEqual(data["total"], 1)

    def test_climate_validation(self):
        base = {"region": "Metropolitana", "fecha": "2026-10-13"}
        for fields in ({"temp_min": 20, "temp_max": 1}, {"precipitacion_mm": -1}, {"region": " "}, {"mp2_5": 10},
                       {"temp_min": float("nan")}, {"temp_max": float("inf")}):
            self.assertEqual(self.call("/api/clima/diario", "PUT", {**base, **fields})[0], 422)

    def test_prediction_history_only_reads_stored_results(self):
        self.assertEqual(self.call("/api/predicciones/historial")[1]["items"], [])
        self.db.add(StoredPrediction(id_establecimiento="TEST-02", fecha=date(2026, 10, 17),
                                    pacientes_predichos=8, modelo_version="test-only",
                                    fecha_hora_prediccion=datetime.now(timezone.utc)))
        self.db.commit()
        status, data = self.call("/api/predicciones/historial", query={"modelo_version": "test-only"})
        self.assertEqual(status, 200)
        self.assertEqual(data["items"][0]["pacientes_predichos"], 8)
        self.assertEqual(self.call("/api/predicciones/historial", query={"modelo_version": "other"})[1]["total"], 0)

    def test_history_dates_and_pagination(self):
        for path in ("/api/demanda-diaria", "/api/clima/historial", "/api/predicciones/historial"):
            for query in ({"fecha_desde": "2026-10-14", "fecha_hasta": "2026-10-13"}, {"limit": 101}, {"skip": -1}):
                self.assertEqual(self.call(path, query=query)[0], 422)

    def test_all_new_routes_require_authentication(self):
        del app.dependency_overrides[get_current_user]
        for path, method, body in (
            ("/api/establecimientos", "GET", None),
            ("/api/establecimientos/1", "PATCH", {"tipo": "Hospital"}),
            ("/api/demanda-diaria", "GET", None),
            ("/api/demanda-diaria", "PUT", {"id_establecimiento": "TEST-02", "fecha": "2026-10-13", "total": 1}),
            ("/api/clima/historial", "GET", None),
            ("/api/clima/diario", "PUT", {"region": "Metropolitana", "fecha": "2026-10-13"}),
            ("/api/predicciones/historial", "GET", None),
        ):
            self.assertEqual(self.call(path, method, body)[0], 401)


if __name__ == "__main__":
    unittest.main()
