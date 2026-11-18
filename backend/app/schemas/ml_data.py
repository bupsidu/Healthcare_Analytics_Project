import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EstablishmentType(str, Enum):
    CEAR = "CEAR"
    HOSPITAL = "Hospital"
    SAPU = "SAPU"
    SAR = "SAR"
    SUR = "SUR"


class EstablishmentSummary(BaseModel):
    """Datos mínimos del hospital de un usuario (lo que muestra el front)."""

    id: int
    id_establecimiento: str | None = None  # código DEIS: el que usan demanda y predicciones
    nombre: str
    comuna: str
    region: str
    tipo: EstablishmentType | None = None

    model_config = ConfigDict(from_attributes=True)


class EstablishmentResponse(BaseModel):
    id: int
    nombre: str
    comuna: str
    region: str
    capacidad_camas: int | None
    id_establecimiento: str | None
    tipo: EstablishmentType | None
    activo: bool
    dominio_correo: str | None = None

    model_config = ConfigDict(from_attributes=True)


# Debe tener al menos un punto (ej. "sapuhospital.cl"): es lo que exige la
# validación de correos de la API, así que un dominio sin punto nunca coincidiría.
DOMAIN_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class EstablishmentPatch(BaseModel):
    id_establecimiento: NonEmptyText | None = None
    tipo: EstablishmentType | None = None
    activo: bool = True
    dominio_correo: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("dominio_correo")
    @classmethod
    def normalize_domain(cls, value: str | None) -> str | None:
        """Acepta '@Sapuhospital.cl' o 'sapuhospital.cl' y lo guarda en minúsculas sin '@'."""
        if value is None:
            return None  # permite quitar el dominio enviando null
        domain = value.strip().lstrip("@").lower()
        if len(domain) > 253 or not DOMAIN_PATTERN.match(domain):
            raise ValueError("Dominio inválido: use un formato como sapuhospital.cl")
        return domain

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


class ProjectionDay(BaseModel):
    fecha: date
    temp_min: float | None
    temp_max: float | None
    precipitacion_mm: float | None
    mp2_5: float | None
    mp10: float | None
    total_lag_4: int | None = Field(description="Demanda del hospital 4 días antes; null si no se cargó")
    pacientes_predichos: int | None = Field(default=None, description="Predicción guardada o respaldo provisional; null si ninguno está disponible")
    nivel_alerta: str | None = None
    color_semaforo: str | None = None


class Projection(BaseModel):
    """Proyección diaria con predicciones guardadas y respaldo provisional cuando falten."""

    establecimiento: EstablishmentSummary
    prediccion_disponible: bool = Field(description="true si al menos un día tiene pacientes_predichos")
    prediccion_provisoria: bool = Field(description="true si al menos un resultado procede del respaldo provisional")
    nota: str
    dias: list[ProjectionDay]


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
