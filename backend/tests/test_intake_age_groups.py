import asyncio
import json
import unittest
from datetime import date
from urllib.parse import urlencode

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.session import Base, get_db
from app.main import app
from app.models.establishment import Establishment
from app.models.intake import DailyIntake
from app.models.user import User
from app.schemas.intake import GrupoEtario


async def request_intakes(method, body=None, query=None):
    messages = []
    payload = json.dumps(body).encode() if body is not None else b""

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": "/api/ingresos",
            "raw_path": b"/api/ingresos", "root_path": "",
            "query_string": urlencode(query or {}).encode(),
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345), "server": ("test", 80),
        },
        receive,
        send,
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    response = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(response)


class IntakeAgeGroupTests(unittest.TestCase):
    def setUp(self):
        # Base temporal en memoria: no se modifica el PostgreSQL del usuario.
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(id=1, email="test@example.invalid", hashed_password="test-hash")
        self.db.add_all([
            self.user,
            Establishment(id=1, nombre="Prueba", comuna="Santiago", region="Metropolitana"),
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

    def test_each_new_group_is_saved_with_user_trace(self):
        for group in GrupoEtario:
            with self.subTest(group=group.value):
                status, result = asyncio.run(request_intakes("POST", {
                    "fecha": "2026-10-12", "establecimiento_id": 1,
                    "casos_respiratorios": 12, "grupo_etario": group.value,
                }))
                self.assertEqual(status, 201)
                self.assertEqual(result["grupo_etario"], group.value)
                self.assertEqual(result["created_by_user_id"], 1)
                self.assertEqual(result["casos_respiratorios"], 12)
        self.assertEqual(self.db.query(DailyIntake).count(), 5)

    def test_new_records_reject_legacy_missing_and_numeric_groups(self):
        for group in ("Infantil", "Adulto", "Adulto Mayor", "General", 4, "0-4", None):
            with self.subTest(group=group):
                body = {"fecha": "2026-10-12", "establecimiento_id": 1, "casos_respiratorios": 12}
                if group is not None:
                    body["grupo_etario"] = group
                status, _ = asyncio.run(request_intakes("POST", body))
                self.assertEqual(status, 422)
        self.assertEqual(self.db.query(DailyIntake).count(), 0)

    def test_history_preserves_and_filters_old_and_new_groups(self):
        self.db.add_all([
            DailyIntake(fecha=date(2026, 10, 7), establecimiento_id=1,
                        casos_respiratorios=12, grupo_etario="Infantil"),
            DailyIntake(fecha=date(2026, 10, 12), establecimiento_id=1,
                        casos_respiratorios=3, grupo_etario="1-4"),
        ])
        self.db.commit()
        status, history = asyncio.run(request_intakes("GET"))
        self.assertEqual(status, 200)
        self.assertEqual(history["total"], 2)
        self.assertEqual({item["grupo_etario"] for item in history["items"]}, {"Infantil", "1-4"})
        for group, cases in (("Infantil", 12), ("1-4", 3)):
            with self.subTest(group=group):
                status, history = asyncio.run(request_intakes("GET", query={"grupo_etario": group}))
                self.assertEqual(status, 200)
                self.assertEqual(history["total"], 1)
                self.assertEqual(history["items"][0]["casos_respiratorios"], cases)

    def test_database_rejects_unknown_groups(self):
        self.db.add(DailyIntake(fecha=date(2026, 10, 12), establecimiento_id=1,
                                casos_respiratorios=1, grupo_etario="Desconocido"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
