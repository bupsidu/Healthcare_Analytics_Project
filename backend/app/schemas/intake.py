from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GrupoEtario(str, Enum):
    MENORES_DE_1 = "Menores de 1"
    DE_1_A_4 = "1-4"
    DE_5_A_14 = "5-14"
    DE_15_A_64 = "15-64"
    DE_65_Y_MAS = "65+"


class GrupoEtarioAnterior(str, Enum):
    """Categorías antiguas admitidas únicamente al consultar el historial."""

    INFANTIL = "Infantil"
    ADULTO = "Adulto"
    ADULTO_MAYOR = "Adulto Mayor"
    GENERAL = "General"


class CausaRespiratoria(str, Enum):
    """Las mismas opciones del formulario de triage (TriageSection.jsx)."""

    IRA_ALTA = "IRA Alta (Infección Respiratoria Aguda)"
    BRONQUITIS = "Bronquitis / Bronquiolitis aguda"
    NEUMONIA = "Neumonía / Sospecha de Neumonía"
    CRISIS_ASMATICA = "Crisis Asmática / SBO"
    INFLUENZA = "Influenza / Síndrome Gripal"
    OTRAS = "Otras patologías respiratorias"


class IntakeCreate(BaseModel):
    fecha: date
    establecimiento_id: int = Field(gt=0)
    casos_respiratorios: int = Field(ge=0)
    grupo_etario: GrupoEtario
    causa: CausaRespiratoria | None = None

    @field_validator("causa", mode="before")
    @classmethod
    def normalize_causa(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class IntakeResponse(BaseModel):
    id: int
    fecha: date
    establecimiento_id: int
    casos_respiratorios: int
    grupo_etario: GrupoEtario | GrupoEtarioAnterior
    causa: str | None = None
    created_by_user_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeHistoryResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[IntakeResponse]
