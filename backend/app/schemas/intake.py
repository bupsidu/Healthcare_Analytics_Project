from pydantic import BaseModel
from typing import Optional

class IntakeCreate(BaseModel):
    fecha: str # YYYY-MM-DD
    establecimiento_id: int
    casos_respiratorios: int
    grupo_etario: Optional[str] = "General"

class IntakeResponse(BaseModel):
    id: int
    fecha: str
    establecimiento_id: int
    casos_respiratorios: int
    grupo_etario: str

    class Config:
        from_attributes = True
