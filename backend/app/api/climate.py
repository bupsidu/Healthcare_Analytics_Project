from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.climate import ClimateResponse
from app.services.open_meteo import (
    OpenMeteoError,
    OpenMeteoTimeoutError,
    get_climate_forecast,
)


router = APIRouter(prefix="/clima", tags=["Clima y contaminación"])


@router.get("", response_model=ClimateResponse)
def consultar_clima(
    latitud: float = Query(ge=-90, le=90, description="Latitud de la ubicación"),
    longitud: float = Query(ge=-180, le=180, description="Longitud de la ubicación"),
    _: User = Depends(get_current_user),
):
    """Devuelve 96 horas de pronóstico, con horarios locales de America/Santiago."""
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
