import asyncio
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import joblib
import pandas
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.predictions import get_prediction_service
from app.db.session import Base, get_db
from app.main import app
from app.models.establishment import Establishment
from app.models.ml_data import StoredPrediction
from app.schemas.prediction import PREDICTION_EXAMPLE, PredictRequest
from app.services.ml_service import (
    EXPECTED_FEATURES,
    ModelSpec,
    PredictionInferenceError,
    PredictionService,
    build_features,
    build_prediction_response,
)

TEST_RELEASE = "test-model-v6"
MODEL_FILENAME = "model_test.joblib"
METADATA_FILENAME = "metadata_test.json"


async def request_prediction(body=None, path="/api/predict", method="POST"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345), "server": ("test", 80),
        },
        receive,
        send,
    )
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    response = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(response)


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_dir.name)
        self.features = list(EXPECTED_FEATURES)
        frame = pandas.DataFrame([build_features(PredictRequest(**PREDICTION_EXAMPLE))] * 2, columns=self.features)
        model = RandomForestRegressor(n_estimators=1, random_state=42)
        model.fit(frame, [17.2, 17.2])
        model_path = self.directory / MODEL_FILENAME
        joblib.dump(model, model_path)
        self.spec = ModelSpec(
            release=TEST_RELEASE, model_filename=MODEL_FILENAME, metadata_filename=METADATA_FILENAME,
            model_bytes=model_path.stat().st_size,
            model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        )
        self.metadata = {"release": TEST_RELEASE, "features": self.features}
        self.write_metadata()
        self.service = PredictionService(self.directory, self.spec)
        self.assertTrue(self.service.load(), self.service.load_error)

        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Establishment(id=1, nombre="Prueba", comuna="Santiago", region="Metropolitana",
                                  id_establecimiento="99-001", tipo="Hospital"))
        self.db.commit()
        self.previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_current_user] = lambda: object()
        app.dependency_overrides[get_prediction_service] = lambda: self.service
        app.dependency_overrides[get_db] = lambda: self.db

    def write_metadata(self):
        (self.directory / METADATA_FILENAME).write_text(json.dumps(self.metadata), encoding="utf-8")

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)
        self.db.close()
        self.engine.dispose()
        self.temporary_dir.cleanup()

    # --- Construcción de las 27 variables -------------------------------------------------

    def test_features_cover_exactly_the_27_model_inputs(self):
        features = build_features(PredictRequest(**PREDICTION_EXAMPLE))
        self.assertEqual(len(EXPECTED_FEATURES), 27)
        self.assertEqual(set(features), set(EXPECTED_FEATURES))

    def test_derived_features_follow_training_logic(self):
        features = build_features(PredictRequest(**PREDICTION_EXAMPLE))
        self.assertAlmostEqual(features["Pred_E1"], 0.05 * 800)
        self.assertEqual(features["Doy"], date(2025, 7, 15).timetuple().tm_yday)
        self.assertEqual(features["Tipo_Hospital"], 1)
        self.assertEqual(sum(features[f"Tipo_{kind}"] for kind in ("CEAR", "Hospital", "SAPU", "SAR", "SUR")), 1)
        self.assertEqual(features["Region_Metropolitana"], 1)
        self.assertEqual(sum(value for name, value in features.items() if name.startswith("Region_") and name != "Region_Media_7d_TempMin"), 1)
        self.assertEqual(features["Lluvia_Intensa_Flag"], 0)

    def test_cold_flag_uses_two_degree_threshold(self):
        for temp_min, expected in ((2.0, 1), (2.1, 0), (-3.0, 1)):
            with self.subTest(temp_min=temp_min):
                body = {**PREDICTION_EXAMPLE, "temp_min": temp_min, "temp_max": 20}
                self.assertEqual(build_features(PredictRequest(**body))["Frio_Polar_Flag"], expected)

    def test_region_names_with_spaces_and_apostrophes_are_supported(self):
        for region in ("Arica y Parinacota", "O'Higgins"):
            with self.subTest(region=region):
                features = build_features(PredictRequest(**{**PREDICTION_EXAMPLE, "region": region}))
                self.assertEqual(features[f"Region_{region}"], 1)

    # --- Endpoint --------------------------------------------------------------------------

    def test_authenticated_endpoint_predicts_and_orders_columns_like_the_model(self):
        with patch.object(self.service._model, "predict", wraps=self.service._model.predict) as predict:
            status, response = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 200)
        self.assertEqual(response["pacientes_predichos"], 17)
        self.assertEqual(response["nivel_alerta"], "Alerta Moderada")
        self.assertEqual(response["color_semaforo"], "amarillo")
        self.assertEqual(response["version_modelo"], TEST_RELEASE)
        self.assertEqual(response["fecha"], "2025-07-15")
        self.assertTrue(response["alerta_demostracion"])
        self.assertEqual(list(predict.call_args.args[0].columns), self.features)

    def test_prediction_is_saved_and_replaced_for_an_existing_establishment(self):
        status, response = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 200)
        self.assertTrue(response["guardada"])
        with patch.object(self.service._model, "predict", return_value=[41.4]):
            status, response = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 200)
        rows = self.db.query(StoredPrediction).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].id_establecimiento, rows[0].modelo_version), ("99-001", TEST_RELEASE))
        self.assertEqual(rows[0].pacientes_predichos, 41)

    def test_prediction_without_establishment_code_is_not_saved(self):
        body = {key: value for key, value in PREDICTION_EXAMPLE.items() if key != "id_establecimiento"}
        status, response = asyncio.run(request_prediction(body))
        self.assertEqual(status, 200)
        self.assertFalse(response["guardada"])
        self.assertEqual(self.db.query(StoredPrediction).count(), 0)

    def test_unknown_establishment_code_returns_404_without_running_the_model(self):
        body = {**PREDICTION_EXAMPLE, "id_establecimiento": "NO-EXISTE"}
        with patch.object(self.service, "predict") as predict:
            status, _ = asyncio.run(request_prediction(body))
        self.assertEqual(status, 404)
        predict.assert_not_called()

    def test_lifespan_loads_model_once_for_multiple_requests(self):
        previous_service = app.state.prediction_service
        app.state.prediction_service = self.service

        async def exercise_lifespan():
            async with app.router.lifespan_context(app):
                for _ in range(2):
                    status, _ = await request_prediction(PREDICTION_EXAMPLE)
                    self.assertEqual(status, 200)

        try:
            with patch("app.main.Base.metadata.create_all"):
                with patch.object(self.service, "load", wraps=self.service.load) as load:
                    asyncio.run(exercise_lifespan())
                    load.assert_called_once()
        finally:
            app.state.prediction_service = previous_service

    def test_missing_extra_invalid_and_nonfinite_inputs_are_rejected(self):
        cases = [
            ("missing", None), ("extra", 1), ("total_lag_4", -1), ("share_trailing", 1.5),
            ("lluvia_intensa", 1), ("region", "Narnia"), ("tipo_establecimiento", "Clinica"),
            ("fecha", "no-es-fecha"), ("temp_min", float("nan")), ("pred_region", float("inf")),
            ("temp_min", 100), ("temp_min", 30),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                body = PREDICTION_EXAMPLE.copy()
                if field == "missing":
                    del body["total_lag_4"]
                elif field == "extra":
                    body["campo_inventado"] = value
                else:
                    body[field] = value
                with patch.object(self.service, "predict") as predict:
                    status, response = asyncio.run(request_prediction(body))
                self.assertEqual(status, 422)
                self.assertIn("detail", response)
                predict.assert_not_called()

    def test_authentication_is_required(self):
        app.dependency_overrides.pop(get_current_user)
        with patch.object(self.service, "predict") as predict:
            status, _ = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 401)
        predict.assert_not_called()

    def test_missing_artifacts_return_503_and_health_still_works(self):
        service = PredictionService(self.directory / "missing", self.spec)
        with patch("app.services.ml_service.logger"):
            self.assertFalse(service.load())
        app.dependency_overrides[get_prediction_service] = lambda: service
        status, _ = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 503)
        status, _ = asyncio.run(request_prediction(path="/api/healthcheck", method="GET"))
        self.assertEqual(status, 200)

    def test_inference_failure_is_controlled(self):
        with patch.object(self.service, "predict", side_effect=PredictionInferenceError()):
            status, response = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 500)
        self.assertEqual(response["detail"], "No fue posible calcular la predicción")

    # --- Carga segura del modelo -----------------------------------------------------------

    def test_hash_mismatch_prevents_deserialization(self):
        model_path = self.directory / MODEL_FILENAME
        with model_path.open("ab") as model_file:
            model_file.write(b"tampered")
        service = PredictionService(self.directory, ModelSpec(
            release=TEST_RELEASE, model_filename=MODEL_FILENAME, metadata_filename=METADATA_FILENAME,
            model_bytes=model_path.stat().st_size, model_sha256=self.spec.model_sha256,
        ))
        with patch("joblib.load") as deserialize, patch("app.services.ml_service.logger"):
            self.assertFalse(service.load())
        deserialize.assert_not_called()
        self.assertIn("SHA-256", service.load_error)

    def test_wrong_size_prevents_deserialization(self):
        service = PredictionService(self.directory, ModelSpec(
            release=TEST_RELEASE, model_filename=MODEL_FILENAME, metadata_filename=METADATA_FILENAME,
            model_bytes=self.spec.model_bytes + 1, model_sha256=self.spec.model_sha256,
        ))
        with patch("joblib.load") as deserialize, patch("app.services.ml_service.logger"):
            self.assertFalse(service.load())
        deserialize.assert_not_called()
        self.assertIn("tamaño", service.load_error)

    def test_changed_feature_order_is_rejected(self):
        self.metadata["features"] = list(reversed(self.features))
        self.write_metadata()
        with patch("app.services.ml_service.logger"):
            self.assertFalse(self.service.load())
        self.assertIn("orden", self.service.load_error)

    def test_metadata_with_different_features_is_rejected(self):
        self.metadata["features"] = self.features[:-1]
        self.write_metadata()
        with patch("app.services.ml_service.logger"):
            self.assertFalse(self.service.load())
        self.assertIn("contrato", self.service.load_error)

    def test_metadata_of_another_release_is_rejected(self):
        self.metadata["release"] = "modelo-v1"
        self.write_metadata()
        with patch("app.services.ml_service.logger"):
            self.assertFalse(self.service.load())
        self.assertIn("release", self.service.load_error)

    # --- Salida ----------------------------------------------------------------------------

    def test_nonfinite_model_output_is_not_returned(self):
        with patch.object(self.service._model, "predict", return_value=[float("nan")]):
            with patch("app.services.ml_service.logger"), self.assertRaises(PredictionInferenceError):
                self.service.predict(PredictRequest(**PREDICTION_EXAMPLE))

    def test_predictions_are_rounded_and_clipped_at_zero(self):
        for raw, expected in ((-1.5, 0), (14.4, 14), (14.6, 15), (29.6, 30)):
            with self.subTest(raw=raw):
                with patch.object(self.service._model, "predict", return_value=[raw]):
                    result = self.service.predict(PredictRequest(**PREDICTION_EXAMPLE))
                self.assertEqual(result.pacientes_predichos, expected)

    def test_demonstration_alert_boundaries(self):
        for patients, color in ((0, "verde"), (14, "verde"), (15, "amarillo"), (29, "amarillo"), (30, "rojo")):
            with self.subTest(patients=patients):
                result = build_prediction_response(patients, "test-model")
                self.assertEqual(result.color_semaforo.value, color)
                self.assertTrue(result.alerta_demostracion)


if __name__ == "__main__":
    unittest.main()
