from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.deps import get_current_user
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


@router.post("", response_model=PredictResponse)
def generar_prediccion(
    datos: PredictRequest,
    _: User = Depends(get_current_user),
    service: PredictionService = Depends(get_prediction_service),
):
    """MVP: recibe 20 variables precalculadas; no obtiene datos ni los guarda.

    El horizonte temporal depende de cómo se preparó la entrada. Este endpoint
    no verifica por sí solo una anticipación de 96 horas. La alerta es demostrativa.
    """
    try:
        return service.predict(datos)
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
