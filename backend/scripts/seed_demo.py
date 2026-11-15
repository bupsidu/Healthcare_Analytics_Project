"""Carga DATOS INVENTADOS de demanda (últimos 5 días) en una base LOCAL de desarrollo, para probar el dashboard.

Uso, desde la carpeta backend:
    python scripts/seed_demo.py           # crea la demanda diaria y los casos por grupo etario
    python scripts/seed_demo.py --borrar  # los elimina
Usa los hospitales que creó scripts/seed_dev.py (ejecútelo antes). No pisa lo que ya exista. No es
para producción: las cifras son ficticias, con la escala típica de cada tipo de establecimiento.
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
import app.models.user  # noqa: E402,F401  (se importa para registrar todas las tablas)
from app.models.establishment import Establishment  # noqa: E402
from app.models.intake import DailyIntake  # noqa: E402
from app.models.ml_data import DailyDemand  # noqa: E402
from scripts.seed_dev import HOSPITALS, LOCAL_HOSTS  # noqa: E402

DAYS = 5
BASE_BY_TYPE = {"Hospital": 35, "SAPU": 18, "SAR": 14, "SUR": 10, "CEAR": 8}  # pacientes por día, aprox.
AGE_SHARES = {"Menores de 1": 0.10, "1-4": 0.20, "5-14": 0.15, "15-64": 0.40, "65+": 0.15}


def window(today: date) -> list[date]:
    return [today - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]


def split_by_age(total: int) -> dict[str, int]:
    """Reparte el total por grupo etario; la suma de los grupos es exactamente el total."""
    parts = {group: int(total * share) for group, share in AGE_SHARES.items()}
    for group in sorted(AGE_SHARES, key=lambda g: total * AGE_SHARES[g] - parts[g], reverse=True)[: total - sum(parts.values())]:
        parts[group] += 1
    return parts


def generate(db: Session, today: date | None = None) -> dict[str, int]:
    """Crea lo que falte (por hospital y día). Lo que ya existe no se modifica."""
    created = {"demanda": 0, "ingresos": 0}
    codes = {h["id_establecimiento"] for h in HOSPITALS}
    for hospital in db.query(Establishment).filter(Establishment.id_establecimiento.in_(codes)):
        for day in window(today or date.today()):
            rng = random.Random(f"{hospital.id_establecimiento}-{day}")  # mismas cifras en cada ejecución
            total = round(BASE_BY_TYPE.get(hospital.tipo, 15) * rng.uniform(0.85, 1.15))
            if db.get(DailyDemand, (hospital.id_establecimiento, day)) is None:
                db.add(DailyDemand(id_establecimiento=hospital.id_establecimiento, fecha=day, total=total))
                created["demanda"] += 1
            if db.query(DailyIntake).filter_by(establecimiento_id=hospital.id, fecha=day).first() is None:
                for group, cases in split_by_age(total).items():
                    if cases:
                        db.add(DailyIntake(fecha=day, establecimiento_id=hospital.id, casos_respiratorios=cases, grupo_etario=group))
                        created["ingresos"] += 1
    db.commit()
    return created


def remove(db: Session, today: date | None = None) -> dict[str, int]:
    """Borra la demanda de esos hospitales en esos días y los casos sin usuario autor (los de este script)."""
    days = window(today or date.today())
    hospitals = db.query(Establishment).filter(Establishment.id_establecimiento.in_({h["id_establecimiento"] for h in HOSPITALS})).all()
    deleted = {
        "demanda": db.query(DailyDemand).filter(
            DailyDemand.id_establecimiento.in_([h.id_establecimiento for h in hospitals]), DailyDemand.fecha.in_(days),
        ).delete(synchronize_session=False),
        "ingresos": db.query(DailyIntake).filter(
            DailyIntake.establecimiento_id.in_([h.id for h in hospitals]), DailyIntake.fecha.in_(days),
            DailyIntake.created_by_user_id.is_(None),
        ).delete(synchronize_session=False),
    }
    db.commit()
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--borrar", action="store_true", help="elimina los datos inventados en vez de crearlos")
    parser.add_argument("--force", action="store_true", help="permite ejecutar contra un servidor que no sea local")
    args = parser.parse_args()
    if settings.POSTGRES_SERVER not in LOCAL_HOSTS and not args.force:
        print(f"ERROR: POSTGRES_SERVER={settings.POSTGRES_SERVER} no parece una base local; estos datos son ficticios.")
        return 1
    with SessionLocal() as db:
        if args.borrar:
            print("Eliminados:", remove(db))
        else:
            print("Creados:", generate(db), "(lo existente no se tocó)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
