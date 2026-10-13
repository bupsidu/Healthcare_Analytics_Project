import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

from app.schemas.prediction import AlertColor, AlertLevel, PredictRequest, PredictResponse


logger = logging.getLogger(__name__)
MODEL_FILENAME = "model_rf_respiratorio.joblib"


class ModelUnavailableError(Exception):
    """No se cargó un modelo compatible."""


class PredictionInputError(Exception):
    """La entrada no corresponde al contrato del modelo cargado."""


class PredictionInferenceError(Exception):
    """El modelo no pudo producir un resultado válido."""


def build_prediction_response(patients: int, version: str) -> PredictResponse:
    """Semáforo de demostración: no calcula saturación ni indica tratamientos."""
    if patients >= 30:
        level, color = AlertLevel.CRITICAL, AlertColor.RED
        recommendation = "Estimación alta según umbrales de demostración. Revisar capacidad y dotación con el equipo responsable."
    elif patients >= 15:
        level, color = AlertLevel.MODERATE, AlertColor.YELLOW
        recommendation = "Estimación moderada según umbrales de demostración. Revisar la planificación de recursos con el equipo responsable."
    else:
        level, color = AlertLevel.NORMAL, AlertColor.GREEN
        recommendation = "Estimación bajo el umbral de demostración. Mantener seguimiento; este resultado no verifica la capacidad del centro."
    return PredictResponse(
        pacientes_predichos=patients,
        nivel_alerta=level,
        color_semaforo=color,
        recomendacion=recommendation,
        version_modelo=version,
    )


class PredictionService:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self._model: Any = None
        self._pandas: Any = None
        self._features: list[str] = []
        self._metadata: dict[str, Any] = {}
        self.load_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> bool:
        """Se llama una vez al iniciar cada proceso. Un fallo solo deshabilita inferencia."""
        self._model = None
        self._pandas = None
        self._features = []
        self._metadata = {}
        self.load_error = None
        try:
            features = json.loads((self.artifacts_dir / "features.json").read_text(encoding="utf-8"))
            metadata = json.loads((self.artifacts_dir / "model_metadata.json").read_text(encoding="utf-8"))
            model_path = self.artifacts_dir / MODEL_FILENAME
            if not isinstance(features, list) or not all(isinstance(name, str) for name in features):
                raise ValueError("features.json debe contener una lista de nombres")
            if len(features) != 20 or len(set(features)) != 20 or set(features) != set(PredictRequest.model_fields):
                raise ValueError("Las features no coinciden con los 20 campos de la API")
            if not isinstance(metadata, dict) or metadata.get("features") != features:
                raise ValueError("El metadata y features.json no coinciden")
            if metadata.get("model_name") != MODEL_FILENAME or metadata.get("target") != "Total":
                raise ValueError("El metadata no corresponde al modelo respiratorio esperado")
            if not isinstance(metadata.get("release"), str) or not metadata["release"]:
                raise ValueError("Falta la versión del modelo")
            if type(metadata.get("regions")) is not int or metadata["regions"] <= 0:
                raise ValueError("El metadata no indica un número válido de regiones")
            if model_path.stat().st_size != metadata.get("model_bytes"):
                raise ValueError("El tamaño del modelo no coincide con el metadata")
            checksum = hashlib.sha256()
            with model_path.open("rb") as model_file:
                for block in iter(lambda: model_file.read(1024 * 1024), b""):
                    checksum.update(block)
            if checksum.hexdigest() != metadata.get("model_sha256"):
                raise ValueError("El SHA-256 del modelo no coincide; no se cargará")

            # Imports locales: las demás rutas pueden arrancar sin dependencias ML.
            import joblib
            import numpy
            import pandas
            import sklearn
            from sklearn.ensemble import RandomForestRegressor

            versions = {"sklearn": sklearn.__version__, "numpy": numpy.__version__, "pandas": pandas.__version__}
            if any(metadata.get("environment", {}).get(name) != version for name, version in versions.items()):
                raise ValueError("Las versiones ML difieren del entrenamiento; instale backend/requirements.txt")

            model = joblib.load(model_path)
            if not isinstance(model, RandomForestRegressor) or model.n_outputs_ != 1:
                raise ValueError("El artefacto no es un RandomForest de regresión con una salida")
            if model.n_features_in_ != len(features):
                raise ValueError("El número de features no coincide con el modelo")
            if list(getattr(model, "feature_names_in_", [])) != features:
                raise ValueError("Los nombres/orden de features difieren del modelo entrenado")
            self._model = model
            self._pandas = pandas
            self._features = features
            self._metadata = metadata
            logger.info("Modelo %s cargado con %s variables", metadata["release"], len(features))
            return True
        except Exception as exc:
            self.load_error = str(exc)
            logger.warning("Inferencia ML no disponible: %s", exc)
            return False

    def predict(self, request: PredictRequest) -> PredictResponse:
        if not self.ready:
            raise ModelUnavailableError("Modelo no disponible")
        if request.Region_Encoded >= self._metadata["regions"]:
            raise PredictionInputError(
                f"Region_Encoded debe estar entre 0 y {self._metadata['regions'] - 1}, según el encoder del entrenamiento"
            )
        try:
            frame = self._pandas.DataFrame([request.model_dump()], columns=self._features)
            result = self._model.predict(frame)
            if len(result) != 1:
                raise ValueError("El modelo devolvió más de una predicción")
            raw_prediction = float(result[0])
            if not math.isfinite(raw_prediction):
                raise ValueError("El modelo devolvió una predicción no finita")
            patients = max(0, round(raw_prediction))
        except Exception as exc:
            logger.exception("Error al ejecutar el modelo respiratorio")
            raise PredictionInferenceError("No se pudo calcular la predicción") from exc
        return build_prediction_response(patients, self._metadata["release"])
