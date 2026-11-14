import hashlib
import json
import logging
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.schemas.ml_data import EstablishmentType
from app.schemas.prediction import AlertColor, AlertLevel, MlRegion, PredictRequest, PredictResponse


logger = logging.getLogger(__name__)

# Umbral de Frio_Polar_Flag del pipeline de entrenamiento (TempMin <= 2 °C).
FRIO_POLAR_THRESHOLD = 2.0
# Periodo usado en el entrenamiento para Doy_Sin / Doy_Cos.
DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class ModelSpec:
    """Identifica el modelo exacto que se acepta cargar (nombre, tamaño y huella)."""

    release: str
    model_filename: str
    metadata_filename: str
    model_bytes: int
    model_sha256: str


# Modelo v6 E2 (RandomForest directo por establecimiento), release "modelo-v6-e2".
# El .joblib no está en Git: se descarga con scripts/download_model.py.
MODEL_V6 = ModelSpec(
    release="modelo-v6-e2",
    model_filename="model_rf_directo_v6e2.joblib",
    metadata_filename="model_metadata_v6e2.json",
    model_bytes=45_596_481,
    model_sha256="b1a8882eb381ebb3f24f4fa5899765bffd1612f04a324e949045a0dbb711683a",
)

# Las 27 variables, en el orden exacto con que se entrenó el modelo.
EXPECTED_FEATURES = [
    "Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1",
    *(f"Tipo_{kind.value}" for kind in EstablishmentType),
    *(f"Region_{region.value}" for region in sorted(MlRegion, key=lambda item: item.value)),
    "Doy", "Doy_Sin", "Doy_Cos",
    "TempMin", "TempMax", "Precipitacion_mm", "TempMin_Lag_4D",
    "Region_Media_7d_TempMin", "Frio_Polar_Flag", "Lluvia_Intensa_Flag",
]


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


def build_features(request: PredictRequest) -> dict[str, float]:
    """Arma las 27 variables de v6 a partir de la solicitud (misma lógica del entrenamiento)."""
    day_of_year = request.fecha.timetuple().tm_yday
    angle = 2 * np.pi * day_of_year / DAYS_PER_YEAR
    features: dict[str, float] = {
        "Total_Lag_4": request.total_lag_4,
        "Share_Trailing": request.share_trailing,
        "Pred_Region": request.pred_region,
        "Pred_E1": request.share_trailing * request.pred_region,
        "Doy": day_of_year,
        "Doy_Sin": float(np.sin(angle)),
        "Doy_Cos": float(np.cos(angle)),
        "TempMin": request.temp_min,
        "TempMax": request.temp_max,
        "Precipitacion_mm": request.precipitacion_mm,
        "TempMin_Lag_4D": request.temp_min_lag_4d,
        "Region_Media_7d_TempMin": request.region_media_7d_temp_min,
        "Frio_Polar_Flag": int(request.temp_min <= FRIO_POLAR_THRESHOLD),
        "Lluvia_Intensa_Flag": int(request.lluvia_intensa),
    }
    for kind in EstablishmentType:
        features[f"Tipo_{kind.value}"] = int(request.tipo_establecimiento == kind)
    for region in MlRegion:
        features[f"Region_{region.value}"] = int(request.region == region)
    return features


class PredictionService:
    def __init__(self, artifacts_dir: Path, spec: ModelSpec = MODEL_V6):
        self.artifacts_dir = artifacts_dir
        self.spec = spec
        self._model: Any = None
        self._pandas: Any = None
        self._features: list[str] = []
        self._metadata: dict[str, Any] = {}
        self.load_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def release(self) -> str:
        return self.spec.release

    def load(self) -> bool:
        """Se llama una vez al iniciar cada proceso. Un fallo solo deshabilita inferencia."""
        self._model = None
        self._pandas = None
        self._features = []
        self._metadata = {}
        self.load_error = None
        try:
            metadata = json.loads((self.artifacts_dir / self.spec.metadata_filename).read_text(encoding="utf-8"))
            model_path = self.artifacts_dir / self.spec.model_filename
            if not isinstance(metadata, dict) or metadata.get("release") != self.spec.release:
                raise ValueError("El metadata no corresponde al release esperado")
            features = metadata.get("features")
            if not isinstance(features, list) or not all(isinstance(name, str) for name in features):
                raise ValueError("El metadata debe contener la lista de features")
            if len(features) != len(EXPECTED_FEATURES) or set(features) != set(EXPECTED_FEATURES):
                raise ValueError("Las features del metadata no coinciden con el contrato de la API")
            if model_path.stat().st_size != self.spec.model_bytes:
                raise ValueError("El tamaño del modelo no coincide con el release esperado")
            checksum = hashlib.sha256()
            with model_path.open("rb") as model_file:
                for block in iter(lambda: model_file.read(1024 * 1024), b""):
                    checksum.update(block)
            if checksum.hexdigest() != self.spec.model_sha256:
                raise ValueError("El SHA-256 del modelo no coincide; no se cargará")

            # Imports locales: las demás rutas pueden arrancar sin dependencias ML.
            import joblib
            import pandas
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.exceptions import InconsistentVersionWarning

            with warnings.catch_warnings():
                # Una versión de scikit-learn distinta a la del entrenamiento invalida el modelo.
                warnings.simplefilter("error", InconsistentVersionWarning)
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
            logger.info("Modelo %s cargado con %s variables", self.spec.release, len(features))
            return True
        except Exception as exc:
            self.load_error = str(exc)
            logger.warning("Inferencia ML no disponible: %s", exc)
            return False

    def predict(self, request: PredictRequest) -> PredictResponse:
        if not self.ready:
            raise ModelUnavailableError("Modelo no disponible")
        try:
            frame = self._pandas.DataFrame([build_features(request)], columns=self._features)
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
        response = build_prediction_response(patients, self.spec.release)
        response.fecha = request.fecha
        response.id_establecimiento = request.id_establecimiento
        return response
