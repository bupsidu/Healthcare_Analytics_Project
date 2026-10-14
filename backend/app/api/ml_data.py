"""Carga explícita y consulta de datos. No ejecuta ni prepara el modelo ML."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.predictions import PredictionRoute
from app.db.session import get_db
from app.models.establishment import Establishment
from app.models.ml_data import DailyClimate, DailyDemand, StoredPrediction
from app.schemas.ml_data import (
    ClimateHistory, ClimateInput, DemandHistory, DemandInput,
    EstablishmentPatch, EstablishmentResponse, PredictionHistory,
)


# Reutiliza la serialización segura de errores para entradas NaN/Infinity.
router = APIRouter(tags=["Catálogo y datos para ML"], dependencies=[Depends(get_current_user)], route_class=PredictionRoute)


def date_window(fecha_desde: date | None = None, fecha_hasta: date | None = None):
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(422, "fecha_desde no puede ser posterior a fecha_hasta")
    return fecha_desde, fecha_hasta


def history(query, model, dates, skip, limit, order):
    start, end = dates
    if start is not None:
        query = query.filter(model.fecha >= start)
    if end is not None:
        query = query.filter(model.fecha <= end)
    return {
        "total": query.count(), "skip": skip, "limit": limit,
        "items": query.order_by(*order).offset(skip).limit(limit).all(),
    }


def save(db, row):
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Conflicto con una clave o restricción de la base de datos") from exc
    return row


@router.get("/establecimientos", response_model=list[EstablishmentResponse])
def list_establishments(
    activo: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Establishment)
    if activo is not None:
        query = query.filter(Establishment.activo == activo)
    return query.order_by(Establishment.id).offset(skip).limit(limit).all()


@router.patch("/establecimientos/{id}", response_model=EstablishmentResponse)
def update_establishment(id: int, data: EstablishmentPatch, db: Session = Depends(get_db)):
    """Completa datos del catálogo existente. No inventa ni descarga códigos DEIS."""
    row = db.get(Establishment, id)
    if row is None:
        raise HTTPException(404, "El establecimiento indicado no existe")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    return save(db, row)


@router.put("/demanda-diaria", response_model=DemandInput)
def put_demand(data: DemandInput, response: Response, db: Session = Depends(get_db)):
    """Crea o reemplaza el total observado del día; nunca lo suma al anterior."""
    establishment = db.query(Establishment).filter(
        Establishment.id_establecimiento == data.id_establecimiento,
    ).first()
    if establishment is None:
        raise HTTPException(404, "No existe un establecimiento con ese código DEIS")
    row = db.get(DailyDemand, (data.id_establecimiento, data.fecha))
    if row is None:
        row = DailyDemand(**data.model_dump())
        response.status_code = 201
    else:
        row.total = data.total
    return save(db, row)


@router.get("/demanda-diaria", response_model=DemandHistory)
def list_demand(
    id_establecimiento: str | None = None,
    dates: tuple = Depends(date_window),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(DailyDemand)
    if id_establecimiento is not None:
        query = query.filter(DailyDemand.id_establecimiento == id_establecimiento)
    return history(query, DailyDemand, dates, skip, limit,
                   (DailyDemand.fecha.desc(), DailyDemand.id_establecimiento))


@router.put("/clima/diario", response_model=ClimateInput)
def put_climate(data: ClimateInput, response: Response, db: Session = Depends(get_db)):
    """Carga manual de valores diarios; no agrega el pronóstico horario de Open-Meteo."""
    row = db.get(DailyClimate, (data.region, data.fecha))
    if row is None:
        row = DailyClimate(**data.model_dump())
        response.status_code = 201
    else:
        # PUT reemplaza los valores de la fila; los campos omitidos quedan en NULL.
        row.temp_min = data.temp_min
        row.temp_max = data.temp_max
        row.precipitacion_mm = data.precipitacion_mm
    return save(db, row)


@router.get("/clima/historial", response_model=ClimateHistory)
def list_climate(
    region: str | None = None,
    dates: tuple = Depends(date_window),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(DailyClimate)
    if region is not None:
        query = query.filter(DailyClimate.region == region)
    return history(query, DailyClimate, dates, skip, limit,
                   (DailyClimate.fecha.desc(), DailyClimate.region))


@router.get("/predicciones/historial", response_model=PredictionHistory)
def list_predictions(
    id_establecimiento: str | None = None,
    modelo_version: str | None = None,
    dates: tuple = Depends(date_window),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(StoredPrediction)
    if id_establecimiento is not None:
        query = query.filter(StoredPrediction.id_establecimiento == id_establecimiento)
    if modelo_version is not None:
        query = query.filter(StoredPrediction.modelo_version == modelo_version)
    return history(query, StoredPrediction, dates, skip, limit,
                   (StoredPrediction.fecha.desc(), StoredPrediction.id.desc()))
