from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.establishment import Establishment
from app.models.intake import DailyIntake
from app.models.user import User
from app.schemas.intake import GrupoEtario, IntakeCreate, IntakeHistoryResponse, IntakeResponse


router = APIRouter(prefix="/ingresos", tags=["Registro de Pacientes"])


@router.post("", response_model=IntakeResponse, status_code=status.HTTP_201_CREATED)
def registrar_ingreso_diario(
    intake_in: IntakeCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    establecimiento = (
        db.query(Establishment)
        .filter(Establishment.id == intake_in.establecimiento_id)
        .first()
    )
    if establecimiento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El establecimiento indicado no existe",
        )

    nuevo_registro = DailyIntake(
        fecha=intake_in.fecha,
        establecimiento_id=intake_in.establecimiento_id,
        casos_respiratorios=intake_in.casos_respiratorios,
        grupo_etario=intake_in.grupo_etario.value,
        created_by_user_id=usuario_actual.id,
    )
    try:
        db.add(nuevo_registro)
        db.commit()
        db.refresh(nuevo_registro)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No fue posible registrar el ingreso por una restricción de datos",
        )
    return nuevo_registro


@router.get("", response_model=IntakeHistoryResponse)
def listar_historial_ingresos(
    establecimiento_id: int | None = Query(default=None, gt=0),
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    grupo_etario: GrupoEtario | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="fecha_desde no puede ser posterior a fecha_hasta",
        )

    query = db.query(DailyIntake)
    if establecimiento_id is not None:
        query = query.filter(DailyIntake.establecimiento_id == establecimiento_id)
    if fecha_desde is not None:
        query = query.filter(DailyIntake.fecha >= fecha_desde)
    if fecha_hasta is not None:
        query = query.filter(DailyIntake.fecha <= fecha_hasta)
    if grupo_etario is not None:
        query = query.filter(DailyIntake.grupo_etario == grupo_etario.value)

    total = query.count()
    items = (
        query.order_by(DailyIntake.fecha.desc(), DailyIntake.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "skip": skip, "limit": limit, "items": items}
