from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.establishment import Establishment
from app.models.ml_data import StoredPrediction
from app.models.user import User
from app.schemas.prediction import PredictRequest, PredictResponse
from app.services.ml_service import (
    ModelUnavailableError,
    PredictionInferenceError,
    PredictionInputError,
    PredictionService,
)


class PredictionRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                # No devolver NaN/Infinity del input dentro del propio JSON de error.
                errors = [
                    {key: value for key, value in error.items() if key not in {"input", "ctx"}}
                    for error in exc.errors()
                ]
                return JSONResponse(status_code=422, content={"detail": errors})

        return handler


router = APIRouter(
    prefix="/predict", tags=["Predicción de demanda (ML)"], route_class=PredictionRoute
)


def get_prediction_service(request: Request) -> PredictionService:
    return request.app.state.prediction_service


def guardar_prediccion(db: Session, datos: PredictRequest, resultado: PredictResponse) -> None:
    """Guarda o reemplaza la predicción del mismo establecimiento, fecha y versión."""
    fila = db.query(StoredPrediction).filter(
        StoredPrediction.id_establecimiento == datos.id_establecimiento,
        StoredPrediction.fecha == datos.fecha,
        StoredPrediction.modelo_version == resultado.version_modelo,
    ).first()
    if fila is None:
        fila = StoredPrediction(
            id_establecimiento=datos.id_establecimiento,
            fecha=datos.fecha,
            modelo_version=resultado.version_modelo,
        )
        db.add(fila)
    fila.pacientes_predichos = resultado.pacientes_predichos
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto al guardar la predicción") from exc


@router.post("", response_model=PredictResponse)
def generar_prediccion(
    datos: PredictRequest,
    _: User = Depends(get_current_user),
    service: PredictionService = Depends(get_prediction_service),
    db: Session = Depends(get_db),
):
    """Predice la demanda diaria de un establecimiento con el modelo v6.

    El backend deriva estacionalidad, one-hot y flags; quien consulta aporta los
    valores que dependen de historial (Total_Lag_4, Share_Trailing, Pred_Region)
    y del clima. Si se indica `id_establecimiento` (código DEIS existente), la
    predicción se guarda (una por establecimiento, fecha y versión del modelo).
    El endpoint no verifica por sí solo una anticipación de 96 horas y la alerta
    es demostrativa.
    """
    if datos.id_establecimiento is not None:
        existe = db.query(Establishment.id).filter(
            Establishment.id_establecimiento == datos.id_establecimiento
        ).first()
        if existe is None:
            raise HTTPException(status_code=404, detail="No existe un establecimiento con ese código DEIS")
    try:
        resultado = service.predict(datos)
        if datos.id_establecimiento is not None:
            guardar_prediccion(db, datos, resultado)
            resultado.guardada = True
        return resultado
    except ModelUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Modelo ML no disponible. Revise artefactos y dependencias, y reinicie la API.",
        ) from exc
    except PredictionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PredictionInferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible calcular la predicción",
        ) from exc
