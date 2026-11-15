"""Roles (admin/medico), hospital por usuario y acceso cruzado entre hospitales."""

import asyncio
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call as call_, patch
from urllib.parse import urlencode

from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.predictions import get_prediction_service
from app.services.ml_service import build_prediction_response
from app.core.security import create_access_token, get_password_hash
from app.db.session import Base, get_db
from app.main import app
from app.models.establishment import Establishment
from app.models.intake import DailyIntake
from app.models.ml_data import DailyClimate
from app.schemas.climate import ClimateResponse
from app.services.open_meteo import REGION_COORDS
from app.models.user import User
from app.schemas.prediction import PREDICTION_EXAMPLE

def forecast_96h():
    """96 horas desde el 15-nov 02:00: temperatura = hora del día (0 a 23) y 1 mm de lluvia cada hora."""
    start = datetime(2026, 11, 15, 2)
    hours = [{"fecha_hora": start + timedelta(hours=i), "temperatura_c": (start + timedelta(hours=i)).hour,
              "humedad_relativa_pct": 50, "precipitacion_mm": 1, "viento_kmh": 5, "pm10_ug_m3": 1,
              "pm2_5_ug_m3": 1, "ozono_ug_m3": 1, "indice_calidad_aire_us": 1} for i in range(96)]
    return ClimateResponse(latitud=0, longitud=0, zona_horaria="America/Santiago",
                           horas_pronosticadas=96, pronostico_horario=hours)

PASSWORD = "Prueba12345"
PASSWORD_HASH = get_password_hash(PASSWORD)  # un solo hash para todos: bcrypt es lento


async def call(method, path, body=None, token=None, query=None, form=None):
    messages = []
    content_type = b"application/x-www-form-urlencoded" if form is not None else b"application/json"
    headers = [(b"content-type", content_type)]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))

    async def receive():
        raw = urlencode(form).encode() if form is not None else (json.dumps(body).encode() if body is not None else b"")
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
        "query_string": urlencode(query or {}).encode(), "headers": headers,
        "client": ("127.0.0.1", 12345), "server": ("test", 80),
    }, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    raw = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, (json.loads(raw) if raw else None)


def request(*args, **kwargs):
    return asyncio.run(call(*args, **kwargs))


def token_for(email):
    return create_access_token({"sub": email})


class RolesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.hospital_a = Establishment(id=1, nombre="SAPU A", comuna="Santiago", region="Metropolitana",
                                        id_establecimiento="A-1", tipo="SAPU", dominio_correo="sapua.cl")
        self.hospital_b = Establishment(id=2, nombre="Hospital B", comuna="Talca", region="Maule",
                                        id_establecimiento="B-1", tipo="Hospital", dominio_correo="hospitalb.cl")
        self.db.add_all([
            self.hospital_a, self.hospital_b,
            User(email="admin@root.cl", hashed_password=PASSWORD_HASH, role="admin"),
            User(email="doc@sapua.cl", hashed_password=PASSWORD_HASH, role="medico", establecimiento_id=1),
            User(email="doc@hospitalb.cl", hashed_password=PASSWORD_HASH, role="medico", establecimiento_id=2),
            User(email="sinhospital@sapua.cl", hashed_password=PASSWORD_HASH, role="medico"),
            User(email="inactivo@sapua.cl", hashed_password=PASSWORD_HASH, role="medico", establecimiento_id=1, is_active=False),
        ])
        self.db.commit()
        self.admin = token_for("admin@root.cl")
        self.doc_a = token_for("doc@sapua.cl")
        self.previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)
        self.db.close()
        self.engine.dispose()

    # --- Login ----------------------------------------------------------------------------------

    def login(self, email, password=PASSWORD):
        return request("POST", "/api/auth/login", form={"username": email, "password": password})

    def test_login_returns_a_token_that_opens_me(self):
        status, result = self.login("DOC@sapua.cl")  # el correo no distingue mayúsculas
        self.assertEqual((status, result["token_type"]), (200, "bearer"))
        status, me = request("GET", "/api/auth/me", token=result["access_token"])
        self.assertEqual((status, me["email"], me["establecimiento"]["id"]), (200, "doc@sapua.cl", 1))

    def test_login_rejects_wrong_password_unknown_user_and_inactive_user(self):
        self.assertEqual(self.login("doc@sapua.cl", "clave-mala")[0], 401)
        self.assertEqual(self.login("nadie@sapua.cl")[0], 401)
        self.assertEqual(self.login("inactivo@sapua.cl")[0], 403)

    def test_protected_routes_reject_missing_or_invalid_token(self):
        self.assertEqual(request("GET", "/api/auth/me")[0], 401)
        self.assertEqual(request("GET", "/api/auth/me", token="no-es-un-jwt")[0], 401)

    def intake(self, hospital_id):
        return {"fecha": "2026-11-01", "establecimiento_id": hospital_id,
                "casos_respiratorios": 5, "grupo_etario": "15-64"}

    # --- Un médico ve solo su hospital -----------------------------------------------------

    def test_medico_only_sees_own_hospital_data(self):
        self.assertEqual(request("POST", "/api/ingresos", self.intake(1), self.doc_a)[0], 201)
        self.assertEqual(request("POST", "/api/ingresos", self.intake(2), self.admin)[0], 201)
        status, result = request("GET", "/api/ingresos", token=self.doc_a)
        self.assertEqual((status, result["total"], {i["establecimiento_id"] for i in result["items"]}), (200, 1, {1}))
        status, catalog = request("GET", "/api/establecimientos", token=self.doc_a)
        self.assertEqual([h["nombre"] for h in catalog], ["SAPU A"])
        self.assertEqual(len(request("GET", "/api/establecimientos", token=self.admin)[1]), 2)

    def test_me_returns_role_and_hospital(self):
        status, me = request("GET", "/api/auth/me", token=self.doc_a)
        self.assertEqual((status, me["role"], me["establecimiento"]["nombre"]), (200, "medico", "SAPU A"))
        self.assertEqual(me["establecimiento"]["id_establecimiento"], "A-1")  # código DEIS para el front
        self.assertIsNone(request("GET", "/api/auth/me", token=self.admin)[1]["establecimiento"])

    # --- Acceso cruzado ---------------------------------------------------------------------

    def test_cross_hospital_access_is_forbidden(self):
        predict = {**PREDICTION_EXAMPLE, "id_establecimiento": "B-1"}
        cases = [
            ("POST", "/api/ingresos", self.intake(2), None),
            ("GET", "/api/ingresos", None, {"establecimiento_id": 2}),
            ("PUT", "/api/demanda-diaria", {"id_establecimiento": "B-1", "fecha": "2026-11-01", "total": 3}, None),
            ("GET", "/api/demanda-diaria", None, {"id_establecimiento": "B-1"}),
            ("GET", "/api/clima/historial", None, {"region": "Maule"}),
            ("GET", "/api/predicciones/historial", None, {"id_establecimiento": "B-1"}),
            ("POST", "/api/predict", predict, None),
        ]
        for method, path, body, query in cases:
            with self.subTest(method=method, path=path):
                self.assertEqual(request(method, path, body, self.doc_a, query)[0], 403)

    def test_medico_can_load_demand_for_own_hospital(self):
        body = {"id_establecimiento": "A-1", "fecha": "2026-11-01", "total": 20}
        self.assertEqual(request("PUT", "/api/demanda-diaria", body, self.doc_a)[0], 201)
        status, result = request("GET", "/api/demanda-diaria", token=self.doc_a)
        self.assertEqual((status, result["total"]), (200, 1))

    def test_predict_must_match_catalog_region_and_type(self):
        """El hospital A es SAPU de la Metropolitana: otra región u otro tipo no se acepta."""
        ok = {**PREDICTION_EXAMPLE, "id_establecimiento": "A-1", "tipo_establecimiento": "SAPU"}
        service = SimpleNamespace(predict=lambda d: build_prediction_response(20, "test"))
        app.dependency_overrides[get_prediction_service] = lambda: service
        self.assertEqual(request("POST", "/api/predict", ok, self.doc_a)[0], 200)
        for change in ({"region": "Maule"}, {"tipo_establecimiento": "Hospital"}):
            with self.subTest(change=change):
                self.assertEqual(request("POST", "/api/predict", {**ok, **change}, self.doc_a)[0], 422)

    # --- Clima por hospital -------------------------------------------------------------------

    def test_hospital_climate_queries_its_region_and_stores_daily_summary(self):
        with patch("app.api.ml_data.forecast_or_http_error", return_value=forecast_96h()) as forecast:
            self.assertEqual(request("GET", "/api/establecimientos/1/clima", token=self.doc_a)[0], 200)
            self.assertEqual(request("GET", "/api/establecimientos/1/clima", token=self.admin)[0], 200)
        self.assertEqual(forecast.call_args_list, [call_(*REGION_COORDS["Metropolitana"])] * 2)
        rows = self.db.query(DailyClimate).order_by(DailyClimate.fecha).all()
        # 96 horas desde las 02:00: solo 3 días completos; la segunda consulta reemplaza, no duplica.
        self.assertEqual([(r.region, str(r.fecha)) for r in rows],
                         [("Metropolitana", "2026-11-16"), ("Metropolitana", "2026-11-17"), ("Metropolitana", "2026-11-18")])
        self.assertEqual((float(rows[0].temp_min), float(rows[0].temp_max), float(rows[0].precipitacion_mm)), (0.0, 23.0, 24.0))
        self.assertFalse(hasattr(DailyClimate, "mp2_5"))  # la contaminación no se guarda en la base

    def test_projection_predicts_provisionally_only_days_with_demand(self):
        seen = []

        def predict(req):
            seen.append(req)
            return build_prediction_response(21, "test")

        service = SimpleNamespace(predict=predict, artifacts_dir=Path(__file__).resolve().parents[2] / "Modelo" / "artifacts")
        app.dependency_overrides[get_prediction_service] = lambda: service
        request("PUT", "/api/demanda-diaria", {"id_establecimiento": "A-1", "fecha": "2026-11-12", "total": 8}, self.doc_a)
        with patch("app.api.ml_data.forecast_or_http_error", return_value=forecast_96h()):
            status, result = request("GET", "/api/predict/proyeccion-96h", token=self.doc_a)
        self.assertEqual(status, 200)
        self.assertTrue(result["prediccion_disponible"] and result["prediccion_provisoria"])
        # Solo el 16-nov tiene demanda 4 días antes (12-nov).
        self.assertEqual([(d["fecha"], d["pacientes_predichos"], d["color_semaforo"]) for d in result["dias"]],
                         [("2026-11-16", 21, "amarillo"), ("2026-11-17", None, None), ("2026-11-18", None, None)])
        (req,) = seen
        self.assertEqual((req.total_lag_4, req.region.value, req.tipo_establecimiento.value), (8, "Metropolitana", "SAPU"))
        self.assertAlmostEqual(req.share_trailing * req.pred_region, 8)  # Pred_E1 = Total_Lag_4
        self.assertEqual((req.temp_min_lag_4d, req.lluvia_intensa), (req.temp_min, True))  # 24 mm > umbral de reemplazo

    def test_projection_gives_daily_climate_and_demand_lag_even_without_a_model(self):
        # La demanda del 12-nov es el Total_Lag_4 del 16-nov; la del 13-nov, el del 17-nov; el 18-nov queda sin dato.
        for day, total in (("2026-11-12", 7), ("2026-11-13", 9)):
            self.assertEqual(request("PUT", "/api/demanda-diaria", {"id_establecimiento": "A-1", "fecha": day, "total": total}, self.doc_a)[0], 201)
        with patch("app.api.ml_data.forecast_or_http_error", return_value=forecast_96h()):
            status, result = request("GET", "/api/predict/proyeccion-96h", token=self.doc_a)
            self.assertEqual(status, 200)
            self.assertEqual(result["establecimiento"]["id_establecimiento"], "A-1")
            self.assertFalse(result["prediccion_disponible"])
            self.assertEqual([(d["fecha"], d["total_lag_4"], d["pacientes_predichos"]) for d in result["dias"]],
                             [("2026-11-16", 7, None), ("2026-11-17", 9, None), ("2026-11-18", None, None)])
            self.assertEqual({k: result["dias"][0][k] for k in ("temp_min", "temp_max", "precipitacion_mm", "mp2_5", "mp10")},
                             {"temp_min": 0.0, "temp_max": 23.0, "precipitacion_mm": 24.0, "mp2_5": 1.0, "mp10": 1.0})
            # Admin: debe indicar el hospital. Médico: no puede pedir otro.
            self.assertEqual(request("GET", "/api/predict/proyeccion-96h", token=self.admin)[0], 422)
            self.assertEqual(request("GET", "/api/predict/proyeccion-96h", token=self.admin, query={"establecimiento_id": 2})[0], 200)
            self.assertEqual(request("GET", "/api/predict/proyeccion-96h", token=self.doc_a, query={"establecimiento_id": 2})[0], 403)
            self.assertEqual(request("GET", "/api/predict/proyeccion-96h", token=self.admin, query={"establecimiento_id": 99})[0], 404)
        self.assertEqual(request("GET", "/api/predict/proyeccion-96h")[0], 401)

    def test_hospital_climate_permissions_and_unknown_region(self):
        self.db.add(Establishment(id=3, nombre="Otro", comuna="X", region="Valparaíso", id_establecimiento="C-1"))
        self.db.commit()
        with patch("app.api.ml_data.forecast_or_http_error", return_value=forecast_96h()) as forecast:
            self.assertEqual(request("GET", "/api/establecimientos/2/clima", token=self.doc_a)[0], 403)  # ajeno
            self.assertEqual(request("GET", "/api/establecimientos/1/clima")[0], 401)
            self.assertEqual(request("GET", "/api/establecimientos/99/clima", token=self.admin)[0], 404)
            self.assertEqual(request("GET", "/api/establecimientos/3/clima", token=self.admin)[0], 409)  # región sin punto
        forecast.assert_not_called()
        self.assertEqual(self.db.query(DailyClimate).count(), 0)

    def test_free_coordinates_climate_is_admin_only(self):
        query = {"latitud": 0, "longitud": 0}
        with patch("app.api.climate.get_climate_forecast", return_value=forecast_96h()):
            self.assertEqual(request("GET", "/api/clima", token=self.doc_a, query=query)[0], 403)
            self.assertEqual(request("GET", "/api/clima", token=self.admin, query=query)[0], 200)

    # --- Lo que un médico no puede hacer ---------------------------------------------------

    def test_medico_cannot_administer(self):
        new_user = {"email": "otro@sapua.cl", "password": "Abcdef123"}
        climate = {"region": "Metropolitana", "fecha": "2026-11-01", "temp_min": 5, "temp_max": 15}
        self.assertEqual(request("POST", "/api/usuarios", new_user, self.doc_a)[0], 403)
        self.assertEqual(request("GET", "/api/usuarios", token=self.doc_a)[0], 403)
        self.assertEqual(request("PATCH", "/api/establecimientos/1", {"tipo": "SAR"}, self.doc_a)[0], 403)
        self.assertEqual(request("PUT", "/api/clima/diario", climate, self.doc_a)[0], 403)
        self.assertEqual(request("PUT", "/api/clima/diario", climate, self.admin)[0], 201)

    # --- Estados que bloquean al médico ------------------------------------------------------

    def test_inactive_hospital_blocks_medico_but_not_admin(self):
        self.assertEqual(request("GET", "/api/ingresos", token=self.doc_a)[0], 200)
        self.hospital_a.activo = False
        self.db.commit()
        status, result = request("GET", "/api/ingresos", token=self.doc_a)
        self.assertEqual(status, 403)
        self.assertIn("desactivado", result["detail"])
        self.assertEqual(request("GET", "/api/auth/me", token=self.doc_a)[0], 200)
        self.assertEqual(request("GET", "/api/ingresos", token=self.admin)[0], 200)

    def test_medico_without_hospital_is_blocked(self):
        token = token_for("sinhospital@sapua.cl")
        self.assertEqual(request("GET", "/api/ingresos", token=token)[0], 403)
        self.assertEqual(request("GET", "/api/auth/me", token=token)[0], 200)

    def test_unknown_role_is_not_treated_as_medico(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            role="otro", establecimiento=self.hospital_a)
        for path in ("/api/ingresos", "/api/establecimientos", "/api/demanda-diaria"):
            with self.subTest(path=path):
                status, result = request("GET", path)
                self.assertEqual(status, 403)
                self.assertIn("no reconocido", result["detail"])

    def test_database_rejects_unknown_role(self):
        self.db.add(User(email="raro@sapua.cl", hashed_password=PASSWORD_HASH, role="otro"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    # --- Alta de usuarios (solo admin) ------------------------------------------------------

    def test_admin_creates_medico_from_email_domain(self):
        body = {"email": "Nuevo@SAPUA.cl", "password": "Abcdef123", "full_name": "Nuevo"}
        status, user = request("POST", "/api/usuarios", body, self.admin)
        self.assertEqual((status, user["role"], user["establecimiento"]["id"]), (201, "medico", 1))
        self.assertEqual(request("POST", "/api/usuarios", body, self.admin)[0], 409)

    def test_unknown_domain_is_rejected_and_admin_needs_no_hospital(self):
        body = {"email": "x@desconocido.cl", "password": "Abcdef123"}
        self.assertEqual(request("POST", "/api/usuarios", body, self.admin)[0], 422)
        admin_body = {"email": "jefe@otro.cl", "password": "Abcdef123", "role": "admin"}
        status, user = request("POST", "/api/usuarios", admin_body, self.admin)
        self.assertEqual((status, user["role"], user["establecimiento"]), (201, "admin", None))
        self.assertEqual(request("POST", "/api/usuarios", {**admin_body, "email": "z@otro.cl", "role": "root"},
                                 self.admin)[0], 422)

    def test_admin_can_assign_hospital_explicitly_for_shared_domains(self):
        body = {"email": "alguien@municipalidad.cl", "password": "Abcdef123", "establecimiento_id": 2}
        status, user = request("POST", "/api/usuarios", body, self.admin)
        self.assertEqual((status, user["establecimiento"]["id"]), (201, 2))
        self.assertEqual(request("POST", "/api/usuarios", {**body, "email": "b@muni.cl", "establecimiento_id": 99},
                                 self.admin)[0], 422)
        self.hospital_b.activo = False
        self.db.commit()
        self.assertEqual(request("POST", "/api/usuarios", {**body, "email": "c@muni.cl"}, self.admin)[0], 422)
        admin_body = {"email": "d@muni.cl", "password": "Abcdef123", "role": "admin", "establecimiento_id": 1}
        self.assertEqual(request("POST", "/api/usuarios", admin_body, self.admin)[0], 422)

    # --- Filtro por tipo y administración de cuentas ------------------------------------------

    def uid(self, email):
        return self.db.query(User).filter_by(email=email).one().id

    def test_catalog_can_be_filtered_by_type(self):
        names = lambda token, tipo: [h["nombre"] for h in request("GET", "/api/establecimientos", token=token,
                                                                   query={"tipo": tipo})[1]]
        self.assertEqual(names(self.admin, "SAPU"), ["SAPU A"])
        self.assertEqual(names(self.admin, "Hospital"), ["Hospital B"])
        self.assertEqual(names(self.doc_a, "Hospital"), [])  # un médico solo ve su propio hospital
        self.assertEqual(request("GET", "/api/establecimientos", token=self.admin, query={"tipo": "Clinica"})[0], 422)

    def test_admin_deactivates_and_reactivates_a_user(self):
        doc_id = self.uid("doc@sapua.cl")
        status, user = request("PATCH", f"/api/usuarios/{doc_id}", {"is_active": False}, self.admin)
        self.assertEqual((status, user["is_active"]), (200, False))
        self.assertEqual(self.login("doc@sapua.cl")[0], 403)
        self.assertEqual(request("GET", "/api/auth/me", token=self.doc_a)[0], 401)  # el token vigente deja de servir
        self.assertEqual(request("PATCH", f"/api/usuarios/{doc_id}", {"is_active": True}, self.admin)[0], 200)
        self.assertEqual(self.login("doc@sapua.cl")[0], 200)

    def test_admin_cannot_deactivate_own_account(self):
        admin_id = self.uid("admin@root.cl")
        self.assertEqual(request("PATCH", f"/api/usuarios/{admin_id}", {"is_active": False}, self.admin)[0], 422)
        self.assertEqual(request("GET", "/api/auth/me", token=self.admin)[0], 200)

    def test_admin_reassigns_hospital_and_old_medico_regains_access(self):
        orphan_id = self.uid("sinhospital@sapua.cl")
        token = token_for("sinhospital@sapua.cl")
        self.assertEqual(request("GET", "/api/ingresos", token=token)[0], 403)
        status, user = request("PATCH", f"/api/usuarios/{orphan_id}", {"establecimiento_id": 1}, self.admin)
        self.assertEqual((status, user["establecimiento"]["id"]), (200, 1))
        self.assertEqual(request("GET", "/api/ingresos", token=token)[0], 200)

    def test_user_patch_rejects_invalid_changes(self):
        orphan_id = self.uid("sinhospital@sapua.cl")
        admin_id = self.uid("admin@root.cl")
        self.hospital_b.activo = False
        self.db.commit()
        cases = [
            (orphan_id, {}),                                   # sin cambios
            (orphan_id, {"establecimiento_id": None}),         # un médico no puede quedar sin hospital
            (orphan_id, {"establecimiento_id": 99}),           # hospital inexistente
            (orphan_id, {"establecimiento_id": 2}),            # hospital desactivado
            (orphan_id, {"role": "admin"}),                    # el rol no se cambia por aquí
            (admin_id, {"establecimiento_id": 1}),             # un admin no tiene hospital
            (orphan_id, {"password": "corta"}),
        ]
        for user_id, body in cases:
            with self.subTest(body=body):
                self.assertEqual(request("PATCH", f"/api/usuarios/{user_id}", body, self.admin)[0], 422)
        self.assertEqual(request("PATCH", "/api/usuarios/9999", {"is_active": True}, self.admin)[0], 404)

    def test_admin_changes_password(self):
        doc_id = self.uid("doc@sapua.cl")
        self.assertEqual(request("PATCH", f"/api/usuarios/{doc_id}", {"password": "NuevaClave123"}, self.admin)[0], 200)
        self.assertEqual(self.login("doc@sapua.cl", "NuevaClave123")[0], 200)
        self.assertEqual(self.login("doc@sapua.cl")[0], 401)

    def test_medico_cannot_patch_users(self):
        orphan_id = self.uid("sinhospital@sapua.cl")
        self.assertEqual(request("PATCH", f"/api/usuarios/{orphan_id}", {"is_active": False}, self.doc_a)[0], 403)

    def test_open_registration_creates_an_inactive_doctor_until_admin_approves(self):
        body = {"email": "Nuevo@SAPUA.cl", "password": "Abcdef123", "full_name": "Nuevo Médico"}
        status, user = request("POST", "/api/auth/register", body)
        self.assertEqual((status, user["email"], user["role"], user["is_active"]), (201, "nuevo@sapua.cl", "medico", False))
        self.assertEqual(user["establecimiento"]["nombre"], "SAPU A")  # hospital deducido del dominio
        self.assertEqual(self.login("nuevo@sapua.cl", "Abcdef123")[0], 403)  # pendiente de aprobación
        self.assertEqual(request("PATCH", f"/api/usuarios/{user['id']}", {"is_active": True}, self.admin)[0], 200)
        status, session = self.login("nuevo@sapua.cl", "Abcdef123")
        self.assertEqual(status, 200)
        me = request("GET", "/api/auth/me", token=session["access_token"])[1]
        self.assertEqual((me["role"], me["establecimiento"]["id"]), ("medico", 1))

    def test_open_registration_cannot_pick_role_or_hospital_and_validates_input(self):
        ok = {"email": "otro@sapua.cl", "password": "Abcdef123"}
        for extra in ({"role": "admin"}, {"establecimiento_id": 2}, {"is_active": True}):
            with self.subTest(extra=extra):
                self.assertEqual(request("POST", "/api/auth/register", {**ok, **extra})[0], 422)
        self.assertEqual(request("POST", "/api/auth/register", {**ok, "password": "corta"})[0], 422)
        self.assertEqual(request("POST", "/api/auth/register", {**ok, "email": "x@dominio-desconocido.cl"})[0], 422)
        self.assertEqual(request("POST", "/api/auth/register", {**ok, "email": "DOC@sapua.cl"})[0], 409)  # ya existe
        self.assertEqual(self.db.query(User).filter(User.email == "otro@sapua.cl").count(), 0)
        self.assertEqual(request("POST", "/api/usuarios", ok)[0], 401)  # la ruta de admin sigue protegida

    def test_intake_keeps_author_for_traceability(self):
        request("POST", "/api/ingresos", self.intake(1), self.doc_a)
        author = self.db.query(DailyIntake).one().created_by_user_id
        self.assertEqual(author, self.db.query(User).filter_by(email="doc@sapua.cl").one().id)


if __name__ == "__main__":
    unittest.main()
