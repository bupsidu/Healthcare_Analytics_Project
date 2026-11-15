"""Carga explícita y consulta de datos. No ejecuta ni prepara el modelo ML."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import false
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, hospital_scope, require_admin
from app.api.climate import forecast_or_http_error
from app.api.predictions import PredictionRoute, get_prediction_service
from app.db.session import get_db
from app.models.establishment import Establishment
from app.models.ml_data import DailyClimate, DailyDemand, StoredPrediction
from app.schemas.climate import ClimateResponse
from app.services.open_meteo import REGION_COORDS, daily_summaries
from app.services.provisional_inputs import provisional_prediction
from app.schemas.ml_data import (
    ClimateHistory, ClimateInput, DemandHistory, DemandInput,
    EstablishmentPatch, EstablishmentResponse, EstablishmentType, PredictionHistory, Projection,
)


logger = logging.getLogger(__name__)

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


def restrict_to_hospital(query, model, hospital, requested_code):
    """Filtra por código DEIS según el hospital del usuario.

    Admin (hospital=None): usa el código que pida, o ve todo si no pide ninguno.
    Médico: solo su hospital; si pide otro código se responde 403.
    """
    if hospital is None:
        if requested_code is not None:
            return query.filter(model.id_establecimiento == requested_code)
        return query
    if requested_code is not None and requested_code != hospital.id_establecimiento:
        raise HTTPException(403, "Solo puede consultar datos de su propio hospital")
    if hospital.id_establecimiento is None:
        # Su hospital aún no tiene código DEIS: no puede haber datos asociados.
        return query.filter(false())
    return query.filter(model.id_establecimiento == hospital.id_establecimiento)


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
    tipo: EstablishmentType | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    hospital=Depends(hospital_scope),
):
    query = db.query(Establishment)
    if hospital is not None:  # un médico solo ve su propio hospital
        query = query.filter(Establishment.id == hospital.id)
    if activo is not None:
        query = query.filter(Establishment.activo == activo)
    if tipo is not None:
        query = query.filter(Establishment.tipo == tipo.value)
    return query.order_by(Establishment.id).offset(skip).limit(limit).all()


def store_daily_climate(db: Session, region: str, forecast: ClimateResponse) -> None:
    """Guarda en clima_diario el resumen de cada día completo del pronóstico (reemplaza el existente).

    Si la base falla, no se pierde la respuesta al usuario: el pronóstico igual se entrega.
    """
    try:
        for day in daily_summaries(forecast):
            row = db.get(DailyClimate, (region, day["fecha"]))
            if row is None:
                row = DailyClimate(region=region, fecha=day["fecha"])
                db.add(row)
            for key, value in day.items():
                setattr(row, key, value)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("No se pudo guardar el clima diario de %s", region, exc_info=True)


def fetch_hospital_forecast(id: int, db: Session, hospital):
    """Valida el acceso, consulta Open-Meteo para la región del hospital y guarda el resumen diario."""
    if hospital is not None and id != hospital.id:
        raise HTTPException(403, "Solo puede consultar el clima de su propio hospital")
    row = db.get(Establishment, id)
    if row is None:
        raise HTTPException(404, "El establecimiento indicado no existe")
    coords = REGION_COORDS.get(row.region)
    if coords is None:
        raise HTTPException(409, f"No hay punto de consulta de clima para la región {row.region!r}")
    forecast = forecast_or_http_error(*coords)
    store_daily_climate(db, row.region, forecast)
    return row, forecast


@router.get("/establecimientos/{id}/clima", response_model=ClimateResponse)
def hospital_climate(id: int, db: Session = Depends(get_db), hospital=Depends(hospital_scope)):
    """Pronóstico de 96 horas de la región del hospital (el médico solo accede al suyo).

    Además guarda en clima_diario el resumen (mín, máx, lluvia, MP2.5 y MP10) de cada día completo."""
    return fetch_hospital_forecast(id, db, hospital)[1]


@router.get("/predict/proyeccion-96h", response_model=Projection)
def projection_96h(
    establecimiento_id: int | None = None,
    db: Session = Depends(get_db),
    hospital=Depends(hospital_scope),
    service=Depends(get_prediction_service),
):
    """Proyección de 96 h del hospital. El médico no envía nada (se usa su hospital); el admin indica `establecimiento_id`.

    Entrega clima y contaminación por día, la demanda de hace 4 días y pacientes predichos con el modelo v6
    usando entradas PROVISORIAS (ver app/services/provisional_inputs.py). No se guarda en `predicciones`."""
    if establecimiento_id is None:
        if hospital is None:
            raise HTTPException(422, "Indique establecimiento_id")
        establecimiento_id = hospital.id
    row, forecast = fetch_hospital_forecast(establecimiento_id, db, hospital)
    first_day = forecast.pronostico_horario[0].fecha_hora.date()
    days = [day for day in daily_summaries(forecast) if day["fecha"] > first_day]  # de mañana en adelante: días completos
    lags = {}
    if row.id_establecimiento is not None:
        lags = {
            d.fecha: d.total for d in db.query(DailyDemand).filter(
                DailyDemand.id_establecimiento == row.id_establecimiento,
                DailyDemand.fecha.in_([day["fecha"] - timedelta(days=4) for day in days]),
            )
        }
    result_days = []
    for day in days:
        lag = lags.get(day["fecha"] - timedelta(days=4))
        prediction = provisional_prediction(service, row, day, lag)
        result_days.append({
            **day, "total_lag_4": lag,
            "pacientes_predichos": prediction.pacientes_predichos if prediction else None,
            "nivel_alerta": prediction.nivel_alerta.value if prediction else None,
            "color_semaforo": prediction.color_semaforo.value if prediction else None,
        })
    return {
        "establecimiento": row,
        "prediccion_disponible": any(d["pacientes_predichos"] is not None for d in result_days),
        "prediccion_provisoria": True,
        "nota": "Estimación provisoria: usa entradas de reemplazo (cuota fija, sin modelo regional) hasta que ML defina las reales. "
                "Un día sin demanda cargada 4 días antes no tiene predicción.",
        "dias": result_days,
    }


@router.patch("/establecimientos/{id}", response_model=EstablishmentResponse, dependencies=[Depends(require_admin)])
def update_establishment(id: int, data: EstablishmentPatch, db: Session = Depends(get_db)):
    """Solo admin. Completa datos del catálogo existente (código DEIS, tipo, dominio de correo)."""
    row = db.get(Establishment, id)
    if row is None:
        raise HTTPException(404, "El establecimiento indicado no existe")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    return save(db, row)


@router.put("/demanda-diaria", response_model=DemandInput)
def put_demand(
    data: DemandInput, response: Response, db: Session = Depends(get_db),
    hospital=Depends(hospital_scope),
):
    """Crea o reemplaza el total observado del día; nunca lo suma al anterior."""
    if hospital is not None and data.id_establecimiento != hospital.id_establecimiento:
        raise HTTPException(403, "Solo puede cargar datos de su propio hospital")
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
    hospital=Depends(hospital_scope),
):
    query = restrict_to_hospital(db.query(DailyDemand), DailyDemand, hospital, id_establecimiento)
    return history(query, DailyDemand, dates, skip, limit,
                   (DailyDemand.fecha.desc(), DailyDemand.id_establecimiento))


@router.put("/clima/diario", response_model=ClimateInput, dependencies=[Depends(require_admin)])
def put_climate(data: ClimateInput, response: Response, db: Session = Depends(get_db)):
    """Solo admin (el clima regional lo comparten varios hospitales). Carga manual de valores diarios."""
    row = db.get(DailyClimate, (data.region, data.fecha))
    if row is None:
        row = DailyClimate(**data.model_dump())
        response.status_code = 201
    else:
        # PUT reemplaza los valores de la fila; los campos omitidos quedan en NULL.
        for key, value in data.model_dump(exclude={"region", "fecha"}).items():
            setattr(row, key, value)
    return save(db, row)


@router.get("/clima/historial", response_model=ClimateHistory)
def list_climate(
    region: str | None = None,
    dates: tuple = Depends(date_window),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    hospital=Depends(hospital_scope),
):
    if hospital is not None:  # un médico solo ve el clima de la región de su hospital
        if region is not None and region != hospital.region:
            raise HTTPException(403, "Solo puede consultar datos de su propio hospital")
        region = hospital.region
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
    hospital=Depends(hospital_scope),
):
    query = restrict_to_hospital(db.query(StoredPrediction), StoredPrediction, hospital, id_establecimiento)
    if modelo_version is not None:
        query = query.filter(StoredPrediction.modelo_version == modelo_version)
    return history(query, StoredPrediction, dates, skip, limit,
                   (StoredPrediction.fecha.desc(), StoredPrediction.id.desc()))
