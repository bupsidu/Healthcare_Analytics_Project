import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy
import pandas
import sklearn
from sklearn.ensemble import RandomForestRegressor

from app.api.deps import get_current_user
from app.api.predictions import get_prediction_service
from app.main import app
from app.schemas.prediction import PREDICTION_EXAMPLE, PredictRequest
from app.services.ml_service import (
    MODEL_FILENAME,
    PredictionInferenceError,
    PredictionInputError,
    PredictionService,
    build_prediction_response,
)


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
        self.features = list(PredictRequest.model_fields)
        frame = pandas.DataFrame([PREDICTION_EXAMPLE, PREDICTION_EXAMPLE], columns=self.features)
        model = RandomForestRegressor(n_estimators=1, random_state=42)
        model.fit(frame, [17.2, 17.2])
        model_path = self.directory / MODEL_FILENAME
        joblib.dump(model, model_path)
        self.metadata = {
            "model_name": MODEL_FILENAME, "release": "test-model", "target": "Total",
            "features": self.features, "regions": 8,
            "model_bytes": model_path.stat().st_size,
            "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "environment": {
                "sklearn": sklearn.__version__, "numpy": numpy.__version__,
                "pandas": pandas.__version__,
            },
        }
        (self.directory / "features.json").write_text(json.dumps(self.features), encoding="utf-8")
        self.write_metadata()
        self.service = PredictionService(self.directory)
        self.assertTrue(self.service.load(), self.service.load_error)
        self.previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_current_user] = lambda: object()
        app.dependency_overrides[get_prediction_service] = lambda: self.service

    def write_metadata(self):
        (self.directory / "model_metadata.json").write_text(json.dumps(self.metadata), encoding="utf-8")

    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)
        self.temporary_dir.cleanup()

    def test_authenticated_endpoint_predicts_without_request_key_order_dependency(self):
        body = dict(reversed(list(PREDICTION_EXAMPLE.items())))
        with patch.object(self.service._model, "predict", wraps=self.service._model.predict) as predict:
            status, response = asyncio.run(request_prediction(body))
        self.assertEqual(status, 200)
        self.assertEqual(response["pacientes_predichos"], 17)
        self.assertEqual(response["nivel_alerta"], "Alerta Moderada")
        self.assertEqual(response["color_semaforo"], "amarillo")
        self.assertTrue(response["alerta_demostracion"])
        self.assertEqual(list(predict.call_args.args[0].columns), self.features)

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

    def test_missing_extra_negative_boolean_and_nonfinite_inputs_are_rejected(self):
        cases = [
            ("missing", None), ("extra", 1), ("Menores_1", -1), ("Menores_1", True),
            ("Frio_Polar_Flag", 2), ("Cat_TempMin_Encoded", 5),
            ("MP2_5", float("nan")), ("MP2_5", float("inf")), ("TempMin", 100),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                body = PREDICTION_EXAMPLE.copy()
                if field == "missing":
                    del body["Menores_1"]
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
        service = PredictionService(self.directory / "missing")
        with patch("app.services.ml_service.logger"):
            self.assertFalse(service.load())
        app.dependency_overrides[get_prediction_service] = lambda: service
        status, _ = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 503)
        status, _ = asyncio.run(request_prediction(path="/api/healthcheck", method="GET"))
        self.assertEqual(status, 200)

    def test_hash_mismatch_prevents_deserialization(self):
        model_path = self.directory / MODEL_FILENAME
        with model_path.open("ab") as model_file:
            model_file.write(b"tampered")
        self.metadata["model_bytes"] = model_path.stat().st_size
        self.write_metadata()
        with patch("joblib.load") as deserialize, patch("app.services.ml_service.logger"):
            self.assertFalse(self.service.load())
        deserialize.assert_not_called()
        self.assertIn("SHA-256", self.service.load_error)

    def test_changed_feature_order_is_rejected(self):
        self.features.reverse()
        (self.directory / "features.json").write_text(json.dumps(self.features), encoding="utf-8")
        self.write_metadata()
        with patch("app.services.ml_service.logger"):
            self.assertFalse(self.service.load())
        self.assertIn("orden", self.service.load_error)

    def test_mismatched_training_versions_are_rejected(self):
        self.metadata["environment"]["sklearn"] = "0.0.0"
        self.write_metadata()
        with patch("joblib.load") as deserialize, patch("app.services.ml_service.logger"):
            self.assertFalse(self.service.load())
        deserialize.assert_not_called()

    def test_invalid_encoded_region_is_rejected(self):
        body = {**PREDICTION_EXAMPLE, "Region_Encoded": 13}
        status, response = asyncio.run(request_prediction(body))
        self.assertEqual(status, 422)
        self.assertIn("0 y 7", response["detail"])

    def test_inference_failure_is_controlled(self):
        with patch.object(self.service, "predict", side_effect=PredictionInferenceError()):
            status, response = asyncio.run(request_prediction(PREDICTION_EXAMPLE))
        self.assertEqual(status, 500)
        self.assertEqual(response["detail"], "No fue posible calcular la predicción")

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
