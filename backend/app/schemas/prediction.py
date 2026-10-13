from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


PREDICTION_EXAMPLE = {
    "Menores_1": 8,
    "De_1_a_4": 15,
    "De_5_a_14": 12,
    "De_15_a_64": 25,
    "De_65_y_mas": 18,
    "TempMin": 1.5,
    "TempMax": 14.2,
    "Precipitacion_mm": 5.0,
    "MP2_5": 28.5,
    "MP10": 55.0,
    "TempMin_Lag_4D": 0.8,
    "MP2_5_Lag_2D": 32.0,
    "Frio_Polar_Flag": 1,
    "Lluvia_Intensa_Flag": 0,
    "Alerta_MP25_Flag": 1,
    "Cat_TempMin_Encoded": 1,
    "Region_Media_7d_TempMin": 2.1,
    "Region_Media_7d_MP25": 25.4,
    "Region_Encoded": 0,
    "TipoEstablecimiento_Encoded": 0,
}


class PredictRequest(BaseModel):
    """Variables ya calculadas y codificadas como durante el entrenamiento."""

    Menores_1: int = Field(ge=0, strict=True)
    De_1_a_4: int = Field(ge=0, strict=True)
    De_5_a_14: int = Field(ge=0, strict=True)
    De_15_a_64: int = Field(ge=0, strict=True)
    De_65_y_mas: int = Field(ge=0, strict=True)
    TempMin: float
    TempMax: float
    Precipitacion_mm: float = Field(ge=0)
    MP2_5: float = Field(ge=0)
    MP10: float = Field(ge=0)
    TempMin_Lag_4D: float
    MP2_5_Lag_2D: float = Field(ge=0)
    Frio_Polar_Flag: int = Field(ge=0, le=1, strict=True)
    Lluvia_Intensa_Flag: int = Field(ge=0, le=1, strict=True)
    Alerta_MP25_Flag: int = Field(ge=0, le=1, strict=True)
    Cat_TempMin_Encoded: int = Field(ge=0, le=4, strict=True)
    Region_Media_7d_TempMin: float
    Region_Media_7d_MP25: float = Field(ge=0)
    Region_Encoded: int = Field(ge=0, strict=True, description="Código del encoder ML, no código oficial de región")
    TipoEstablecimiento_Encoded: int = Field(ge=0, strict=True)

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        json_schema_extra={"example": PREDICTION_EXAMPLE},
    )

    @model_validator(mode="after")
    def temperature_bounds(self):
        if self.TempMin > self.TempMax:
            raise ValueError("TempMin no puede superar TempMax")
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
