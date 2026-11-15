"""Entradas PROVISORIAS del modelo v6 para la proyección de 96 h.

Sirven para que el dashboard tenga una cifra mientras el equipo de ML define cómo calcular las
entradas reales (Share_Trailing, Pred_Region, umbral de lluvia intensa y lags de temperatura).
Ninguna de estas cifras es una predicción validada.
"""

import csv
import logging
from functools import lru_cache
from pathlib import Path
from statistics import median

from pydantic import ValidationError

from app.schemas.prediction import PredictRequest, PredictResponse
from app.services.ml_service import ModelUnavailableError, PredictionInferenceError, PredictionInputError

logger = logging.getLogger(__name__)

# shortcut: el umbral real es el percentil 90 regional (no exportado por ML); 5 mm/día es un valor
# de reemplazo. Cambiarlo cuando ML entregue los 8 umbrales.
LLUVIA_INTENSA_MM = 5.0


@lru_cache
def _shares(artifacts_dir: Path) -> dict[str, tuple[str, float]]:
    with (artifacts_dir / "cuotas_establecimiento_v5.csv").open(encoding="utf-8") as f:
        return {row["IdEstablecimiento"].strip(): (row["Region"], float(row["share"])) for row in csv.DictReader(f)}


def provisional_share(artifacts_dir: Path, code: str | None, region: str) -> float:
    """Cuota fija de v5 del establecimiento; si no figura, la mediana de su región (o la general)."""
    shares = _shares(artifacts_dir)
    if code in shares:
        return shares[code][1]
    return median([s for r, s in shares.values() if r == region] or [s for _, s in shares.values()])


def provisional_prediction(service, hospital, day: dict, total_lag_4: int | None) -> PredictResponse | None:
    """Predice un día con entradas provisorias; None si falta algún dato o el modelo no responde.

    - Share_Trailing: cuota fija de v5 (ver provisional_share).
    - Pred_Region = Total_Lag_4 / Share_Trailing, de modo que Pred_E1 = Total_Lag_4 (equivale a persistencia).
    - TempMin_Lag_4D y Region_Media_7d_TempMin: la temperatura mínima del propio día, que es lo que el
      entrenamiento terminó usando (el lag se calculó sobre filas, no sobre días).
    """
    if total_lag_4 is None or hospital.tipo is None or day["temp_min"] is None or day["temp_max"] is None or day["precipitacion_mm"] is None:
        return None
    try:
        share = provisional_share(service.artifacts_dir, hospital.id_establecimiento, hospital.region)
        request = PredictRequest(
            fecha=day["fecha"], region=hospital.region, tipo_establecimiento=hospital.tipo,
            total_lag_4=total_lag_4, share_trailing=share, pred_region=total_lag_4 / share,
            temp_min=day["temp_min"], temp_max=day["temp_max"], precipitacion_mm=day["precipitacion_mm"],
            temp_min_lag_4d=day["temp_min"], region_media_7d_temp_min=day["temp_min"],
            lluvia_intensa=day["precipitacion_mm"] >= LLUVIA_INTENSA_MM,
        )
        return service.predict(request)
    except (ModelUnavailableError, PredictionInferenceError, PredictionInputError, ValidationError, OSError, ZeroDivisionError):
        logger.warning("Sin predicción provisoria para %s el %s", hospital.id_establecimiento, day["fecha"], exc_info=True)
        return None
