from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import require_admin
from app.models.user import User
from app.schemas.climate import ClimateResponse
from app.services.open_meteo import (
    OpenMeteoError,
    OpenMeteoTimeoutError,
    get_climate_forecast,
)


router = APIRouter(prefix="/clima", tags=["Clima y contaminación"])


def forecast_or_http_error(latitud: float, longitud: float) -> ClimateResponse:
    """Pide el pronóstico a Open-Meteo y traduce sus fallos a 502/504."""
    try:
        return get_climate_forecast(latitud, longitud)
    except OpenMeteoTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Open-Meteo excedió el tiempo de espera",
        ) from exc
    except OpenMeteoError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible obtener un pronóstico completo desde Open-Meteo",
        ) from exc


@router.get("", response_model=ClimateResponse)
def consultar_clima(
    latitud: float = Query(ge=-90, le=90, description="Latitud de la ubicación"),
    longitud: float = Query(ge=-180, le=180, description="Longitud de la ubicación"),
    _: User = Depends(require_admin),
):
    """Solo admin: pronóstico de 96 horas para cualquier punto (horarios de America/Santiago).

    Los médicos usan GET /establecimientos/{id}/clima, que solo sirve la zona de su hospital.
    """
    return forecast_or_http_error(latitud, longitud)
