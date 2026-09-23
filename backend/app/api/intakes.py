from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.intake import DailyIntake
from app.schemas.intake import IntakeCreate, IntakeResponse

router = APIRouter(prefix="/ingresos", tags=["Registro de Pacientes"])

@router.post("", response_model=IntakeResponse, status_code=201)
def registrar_ingreso_diario(intake_in: IntakeCreate, db: Session = Depends(get_db)):
    nuevo_registro = DailyIntake(
        fecha=intake_in.fecha,
        establecimiento_id=intake_in.establecimiento_id,
        casos_respiratorios=intake_in.casos_respiratorios,
        grupo_etario=intake_in.grupo_etario
    )
    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)
    return nuevo_registro

@router.get("", response_model=List[IntakeResponse])
def listar_historial_ingresos(db: Session = Depends(get_db)):
    return db.query(DailyIntake).order_by(DailyIntake.fecha.desc()).all()
