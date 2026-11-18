"""Predicciones almacenadas por hospital/fecha y respaldo provisional, en SQLite temporal."""

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import test_roles as role_helpers
from app.models.ml_data import StoredPrediction
from app.services.ml_service import build_prediction_response


class StoredProjectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = role_helpers.RolesTests(methodName="test_me_returns_role_and_hospital")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db

    def store(self, day, patients, version="modelo-v12-ventanas", code="A-1", hour=12):
        self.db.add(StoredPrediction(
            id_establecimiento=code, fecha=date(2026, 11, day),
            pacientes_predichos=patients, modelo_version=version,
            fecha_hora_prediccion=datetime(2026, 11, 15, hour, tzinfo=timezone.utc),
        ))
        self.db.commit()

    def projection(self):
        return role_helpers.request("GET", "/api/predict/proyeccion-96h", token=self.fixture.doc_a)

    def test_stored_values_work_without_demand_or_model_including_zero(self):
        for day, patients in ((16, 0), (17, 17), (18, 36)):
            self.store(day, patients)
        with patch("app.api.ml_data.forecast_or_http_error", return_value=role_helpers.forecast_96h()), \
             patch("app.api.ml_data.provisional_prediction") as fallback:
            status, result = self.projection()
        self.assertEqual(status, 200)
        fallback.assert_not_called()
        self.assertTrue(result["prediccion_disponible"])
        self.assertFalse(result["prediccion_provisoria"])
        self.assertEqual([d["pacientes_predichos"] for d in result["dias"]], [0, 17, 36])
        self.assertEqual([d["color_semaforo"] for d in result["dias"]], ["verde", "amarillo", "rojo"])
        for day in result["dias"]:
            self.assertIsNone(day["total_lag_4"])
        self.assertEqual(self.db.query(StoredPrediction).count(), 3)

    def test_latest_saved_version_is_selected_only_for_own_hospital_and_dates(self):
        self.store(16, 10, version="anterior", hour=8)
        self.store(16, 62, hour=10)
        self.store(16, 999, code="B-1", hour=11)
        self.store(15, 888)
        self.store(19, 777)
        with patch("app.api.ml_data.forecast_or_http_error", return_value=role_helpers.forecast_96h()), \
             patch("app.api.ml_data.provisional_prediction", return_value=None):
            status, result = self.projection()
        self.assertEqual(status, 200)
        self.assertEqual([d["pacientes_predichos"] for d in result["dias"]], [62, None, None])
        self.assertFalse(result["prediccion_provisoria"])
        self.assertEqual(self.db.query(StoredPrediction).count(), 5)

    def test_missing_dates_use_provisional_fallback(self):
        self.store(16, 62)

        def fallback(service, hospital, day, lag):
            return build_prediction_response(18, "test-v6") if day["fecha"].day == 17 else None

        with patch("app.api.ml_data.forecast_or_http_error", return_value=role_helpers.forecast_96h()), \
             patch("app.api.ml_data.provisional_prediction", side_effect=fallback) as provisional:
            status, result = self.projection()
        self.assertEqual(status, 200)
        self.assertTrue(result["prediccion_provisoria"])
        self.assertEqual([d["pacientes_predichos"] for d in result["dias"]], [62, 18, None])
        self.assertEqual([call.args[2]["fecha"].day for call in provisional.call_args_list], [17, 18])


if __name__ == "__main__":
    unittest.main()
