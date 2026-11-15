from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ml_data import EstablishmentType, NonEmptyText


class MlRegion(str, Enum):
    """Regiones con las que se entrenó el modelo v6 (los nombres deben ser idénticos)."""

    ANTOFAGASTA = "Antofagasta"
    ARICA = "Arica y Parinacota"
    ATACAMA = "Atacama"
    COQUIMBO = "Coquimbo"
    MAGALLANES = "Magallanes"
    MAULE = "Maule"
    METROPOLITANA = "Metropolitana"
    OHIGGINS = "O'Higgins"


PREDICTION_EXAMPLE = {
    "fecha": "2025-07-15",
    "region": "Metropolitana",
    "tipo_establecimiento": "Hospital",
    "id_establecimiento": "14-103",
    "total_lag_4": 40,
    "share_trailing": 0.05,
    "pred_region": 800,
    "temp_min": 3.0,
    "temp_max": 14.0,
    "precipitacion_mm": 5.0,
    "temp_min_lag_4d": 4.0,
    "region_media_7d_temp_min": 4.5,
    "lluvia_intensa": False,
}


class PredictRequest(BaseModel):
    """Entradas del modelo v6 que dependen de historial o del modelo regional.

    El backend deriva el resto de las 27 variables (Pred_E1, estacionalidad,
    one-hot de región y tipo, Frio_Polar_Flag). Mientras no exista carga
    automática de historial, quien consulta aporta estos valores.
    """

    fecha: date = Field(description="Fecha objetivo de la predicción (día T)")
    region: MlRegion
    tipo_establecimiento: EstablishmentType
    id_establecimiento: NonEmptyText | None = Field(
        default=None,
        description="Código DEIS. Si se indica y existe en el catálogo, la predicción se guarda.",
    )
    total_lag_4: float = Field(ge=0, description="Total de pacientes del establecimiento hace 4 días (Total_Lag_4)")
    share_trailing: float = Field(ge=0, le=1, description="Cuota trailing del establecimiento en su región (Share_Trailing)")
    pred_region: float = Field(ge=0, description="Total regional predicho por la etapa 1 de v5 (Pred_Region)")
    temp_min: float = Field(ge=-60, le=60)
    temp_max: float = Field(ge=-60, le=60)
    precipitacion_mm: float = Field(ge=0)
    temp_min_lag_4d: float = Field(ge=-60, le=60)
    region_media_7d_temp_min: float = Field(ge=-60, le=60)
    lluvia_intensa: bool = Field(
        strict=True,
        description="1 si la precipitación supera el percentil 90 regional (Lluvia_Intensa_Flag)",
    )

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        json_schema_extra={"example": PREDICTION_EXAMPLE},
    )

    @model_validator(mode="after")
    def temperature_bounds(self):
        if self.temp_min > self.temp_max:
            raise ValueError("temp_min no puede superar temp_max")
        return self


class AlertLevel(str, Enum):
    NORMAL = "Estado Normal"
    MODERATE = "Alerta Moderada"
    CRITICAL = "Alerta Crítica"


class AlertColor(str, Enum):
    GREEN = "verde"
    YELLOW = "amarillo"
    RED = "rojo"


class PredictResponse(BaseModel):
    pacientes_predichos: int = Field(ge=0)
    nivel_alerta: AlertLevel
    color_semaforo: AlertColor
    recomendacion: str
    alerta_demostracion: bool = True
    version_modelo: str
    fecha: date | None = None
    id_establecimiento: str | None = None
    guardada: bool = False
