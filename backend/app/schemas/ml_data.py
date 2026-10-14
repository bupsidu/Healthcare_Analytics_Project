from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EstablishmentType(str, Enum):
    CEAR = "CEAR"
    HOSPITAL = "Hospital"
    SAPU = "SAPU"
    SAR = "SAR"
    SUR = "SUR"


class EstablishmentResponse(BaseModel):
    id: int
    nombre: str
    comuna: str
    region: str
    capacidad_camas: int | None
    id_establecimiento: str | None
    tipo: EstablishmentType | None
    activo: bool

    model_config = ConfigDict(from_attributes=True)


class EstablishmentPatch(BaseModel):
    id_establecimiento: NonEmptyText | None = None
    tipo: EstablishmentType | None = None
    activo: bool = True

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo para actualizar")
        return self


class DemandInput(BaseModel):
    id_establecimiento: NonEmptyText
    fecha: date
    total: int = Field(ge=0, le=2147483647, strict=True)

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ClimateInput(BaseModel):
    region: NonEmptyText
    fecha: date
    temp_min: float | None = None
    temp_max: float | None = None
    precipitacion_mm: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", from_attributes=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def temperature_bounds(self):
        if self.temp_min is not None and self.temp_max is not None and self.temp_min > self.temp_max:
            raise ValueError("temp_min no puede superar temp_max")
        return self


class StoredPredictionResponse(BaseModel):
    id: int
    id_establecimiento: str
    fecha: date
    pacientes_predichos: int
    modelo_version: str
    fecha_hora_prediccion: datetime

    model_config = ConfigDict(from_attributes=True)


class DemandHistory(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[DemandInput]


class ClimateHistory(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ClimateInput]


class PredictionHistory(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[StoredPredictionResponse]
