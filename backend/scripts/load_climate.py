"""Llena clima_diario con el pronóstico de Open-Meteo de las 8 regiones del modelo.

Uso, desde la carpeta backend:  python scripts/load_climate.py
Guarda el resumen (mínima, máxima, lluvia) de los días completos del pronóstico y reemplaza lo que
hubiera para esos días. Es la misma carga que hace GET /establecimientos/{id}/clima, pero sin
esperar a que alguien abra la pantalla. Se puede repetir cuando se quiera (idealmente una vez al día).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.api.ml_data import store_daily_climate  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
import app.models.establishment  # noqa: E402,F401  (se importan para registrar todas las tablas)
import app.models.intake  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
from app.models.ml_data import DailyClimate  # noqa: E402
from app.services.open_meteo import REGION_COORDS, OpenMeteoError, get_climate_forecast  # noqa: E402


def load(db: Session, fetch=get_climate_forecast) -> dict[str, int | str]:
    """Devuelve, por región, cuántos días quedaron guardados o el motivo del fallo."""
    result: dict[str, int | str] = {}
    for region, (lat, lon) in REGION_COORDS.items():
        try:
            forecast = fetch(lat, lon)
        except OpenMeteoError as exc:
            result[region] = f"FALLÓ: {exc}"
            continue
        before = db.query(DailyClimate).filter_by(region=region).count()
        store_daily_climate(db, region, forecast)
        result[region] = db.query(DailyClimate).filter_by(region=region).count() - before  # días nuevos
    return result


def main() -> int:
    with SessionLocal() as db:
        result = load(db)
        for region, outcome in result.items():
            print(f"{region}: {outcome if isinstance(outcome, str) else f'{outcome} días nuevos'}")
        total = db.query(DailyClimate).count()
    print(f"Filas en clima_diario: {total}")
    return 1 if any(isinstance(v, str) for v in result.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
