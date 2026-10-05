from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class GrupoEtario(str, Enum):
    INFANTIL = "Infantil"
    ADULTO = "Adulto"
    ADULTO_MAYOR = "Adulto Mayor"
    GENERAL = "General"


class IntakeCreate(BaseModel):
    fecha: date
    establecimiento_id: int = Field(gt=0)
    casos_respiratorios: int = Field(ge=0)
    grupo_etario: GrupoEtario = GrupoEtario.GENERAL


class IntakeResponse(BaseModel):
    id: int
    fecha: date
    establecimiento_id: int
    casos_respiratorios: int
    grupo_etario: GrupoEtario
    created_by_user_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeHistoryResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[IntakeResponse]
