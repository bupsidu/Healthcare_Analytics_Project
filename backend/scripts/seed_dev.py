"""Prepara una base LOCAL de desarrollo: actualiza el esquema y carga hospitales y usuarios de prueba.

Uso, desde la carpeta backend:
    python scripts/seed_dev.py                 # esquema + hospitales, admin y médicos de prueba
    python scripts/seed_dev.py --solo-admin    # esquema + solo el administrador
    python scripts/seed_dev.py --solo-esquema  # solo las tablas y columnas que falten, sin datos
Salvo --solo-esquema, requiere SEED_ADMIN_PASSWORD en backend/.env (la clave del admin; no va en el código).
Se puede ejecutar varias veces: no duplica ni pisa lo que ya existe. Solo para desarrollo.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
import app.models.intake  # noqa: E402,F401  (los modelos se importan para registrar todas las tablas)
import app.models.ml_data  # noqa: E402,F401
from app.models.establishment import Establishment  # noqa: E402
from app.models.user import User  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}
ADMIN_EMAIL = "adminbot@adminhospitalario.cl"
DOCTOR_PASSWORD = "123456789"  # solo desarrollo; los médicos de prueba no tienen poder de admin

# Un establecimiento REAL por región de las 8 que conoce el modelo v6 (código DEIS, región y tipo
# tal como salen de Modelo/artifacts/cuotas_establecimiento_v5.csv y Modelo/data/sample; el nombre
# es EXACTO al de la base del modelo, incluido el "(comuna)" final, a pedido de ML). Los
# dominios de correo son de prueba. La capacidad de camas se deja vacía porque no la tenemos:
# completarla con el catálogo oficial. Antofagasta y Atacama no figuran en el CSV de cuotas
# (no tenían datos de 2024); el modelo las trata con una cuota de reemplazo.
HOSPITALS = [
    {"nombre": "Hospital Padre Alberto Hurtado (San Ramón)", "comuna": "San Ramón", "region": "Metropolitana",
     "capacidad_camas": None, "id_establecimiento": "14-103", "tipo": "Hospital",
     "dominio_correo": "hospitalhurtado.cl"},
    {"nombre": "Hospital de Pichilemu", "comuna": "Pichilemu", "region": "O'Higgins",
     "capacidad_camas": None, "id_establecimiento": "15-112", "tipo": "Hospital",
     "dominio_correo": "hospitalpichilemu.cl"},
    {"nombre": "Hospital Regional Dr. Juan Noé Crevani (Arica)", "comuna": "Arica", "region": "Arica y Parinacota",
     "capacidad_camas": None, "id_establecimiento": "01-100", "tipo": "Hospital",
     "dominio_correo": "hospitalarica.cl"},
    {"nombre": "Hospital Dr. Carlos Cisternas (Calama)", "comuna": "Calama", "region": "Antofagasta",
     "capacidad_camas": None, "id_establecimiento": "03-101", "tipo": "Hospital",
     "dominio_correo": "hospitalcalama.cl"},
    {"nombre": "Hospital Dr. Jerónimo Méndez Arancibia (Chañaral)", "comuna": "Chañaral", "region": "Atacama",
     "capacidad_camas": None, "id_establecimiento": "04-101", "tipo": "Hospital",
     "dominio_correo": "hospitalchanaral.cl"},
    {"nombre": "Hospital San Pablo (Coquimbo)", "comuna": "Coquimbo", "region": "Coquimbo",
     "capacidad_camas": None, "id_establecimiento": "05-101", "tipo": "Hospital",
     "dominio_correo": "hospitalcoquimbo.cl"},
    {"nombre": "Hospital Clínico de Magallanes Dr. Lautaro Navarro Avaria", "comuna": "Punta Arenas",
     "region": "Magallanes", "capacidad_camas": None, "id_establecimiento": "26-100", "tipo": "Hospital",
     "dominio_correo": "hospitalmagallanes.cl"},
    {"nombre": "Hospital de Molina", "comuna": "Molina", "region": "Maule",
     "capacidad_camas": None, "id_establecimiento": "16-102", "tipo": "Hospital",
     "dominio_correo": "hospitalmolina.cl"},
]
DOCTORS = [
    ("medico3@hospitalhurtado.cl", "Medico Tres", "14-103"),
    ("medico4@hospitalpichilemu.cl", "Medico Cuatro", "15-112"),
    ("medico6@hospitalarica.cl", "Medico Seis", "01-100"),
    ("medico7@hospitalcalama.cl", "Medico Siete", "03-101"),
    ("medico8@hospitalchanaral.cl", "Medico Ocho", "04-101"),
    ("medico9@hospitalcoquimbo.cl", "Medico Nueve", "05-101"),
    ("medico10@hospitalmagallanes.cl", "Medico Diez", "26-100"),
    ("medico11@hospitalmolina.cl", "Medico Once", "16-102"),
]


def ensure_schema(eng) -> list[str]:
    """Crea tablas que falten y, en PostgreSQL, agrega las columnas y restricciones nuevas.

    create_all() no modifica tablas existentes, por eso este paso. Devuelve lo que aplicó.
    """
    Base.metadata.create_all(eng)
    if eng.dialect.name != "postgresql":
        return []
    insp = inspect(eng)
    columns = {t: {c["name"] for c in insp.get_columns(t)} for t in ("usuarios", "establecimientos")}
    with eng.begin() as conn:
        constraints = {row[0] for row in conn.execute(text("SELECT conname FROM pg_constraint"))}
        steps = []
        if "dominio_correo" not in columns["establecimientos"]:
            steps.append("ALTER TABLE establecimientos ADD COLUMN dominio_correo VARCHAR(255)")
        if "uq_establecimientos_dominio_correo" not in constraints:
            steps.append("ALTER TABLE establecimientos ADD CONSTRAINT uq_establecimientos_dominio_correo UNIQUE (dominio_correo)")
        if "establecimiento_id" not in columns["usuarios"]:
            steps.append("ALTER TABLE usuarios ADD COLUMN establecimiento_id INTEGER "
                         "REFERENCES establecimientos(id) ON DELETE RESTRICT")
        if "ix_usuarios_establecimiento_id" not in {i["name"] for i in insp.get_indexes("usuarios")}:
            steps.append("CREATE INDEX ix_usuarios_establecimiento_id ON usuarios (establecimiento_id)")
        if "ck_usuarios_rol" not in constraints:
            steps.append("ALTER TABLE usuarios ADD CONSTRAINT ck_usuarios_rol CHECK (role IN ('admin', 'medico'))")
        for step in steps:
            conn.execute(text(step))
    return steps


def seed(db: Session, admin_password: str, only_admin: bool = False) -> dict[str, int]:
    """Crea lo que falte. Lo que ya existe (por código DEIS o por correo) no se modifica.

    Con only_admin=True solo crea el administrador (sin hospitales ni médicos de prueba)."""
    created = {"hospitales": 0, "usuarios": 0}
    by_code = {}
    for data in [] if only_admin else HOSPITALS:
        hospital = db.query(Establishment).filter(Establishment.id_establecimiento == data["id_establecimiento"]).first()
        if hospital is None:
            hospital = Establishment(**data)
            db.add(hospital)
            created["hospitales"] += 1
        by_code[data["id_establecimiento"]] = hospital
    db.flush()  # asigna los ids antes de vincular a los usuarios

    def add_user(email, name, password, role, hospital):
        if db.query(User).filter(User.email == email).first() is None:
            db.add(User(email=email, full_name=name, hashed_password=get_password_hash(password), role=role,
                        establecimiento_id=hospital.id if hospital else None))
            created["usuarios"] += 1

    add_user(ADMIN_EMAIL, "Admin Bot", admin_password, "admin", None)
    for email, name, code in [] if only_admin else DOCTORS:
        add_user(email, name, DOCTOR_PASSWORD, "medico", by_code[code])
    db.commit()
    return created


def validate(host: str, admin_password: str | None, force: bool, needs_admin: bool = True) -> str | None:
    """Devuelve un mensaje de error si no se debe ejecutar el seed, o None si todo está bien."""
    if host not in LOCAL_HOSTS and not force:
        return f"POSTGRES_SERVER={host} no parece una base local; el seed modifica la base. Use --force solo si está seguro."
    if needs_admin and (not admin_password or len(admin_password) < 8):
        return "Defina SEED_ADMIN_PASSWORD (mínimo 8 caracteres) en backend/.env."
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="permite ejecutar contra un servidor que no sea local")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--solo-esquema", action="store_true", help="solo crea las tablas y columnas que falten (sin datos)")
    mode.add_argument("--solo-admin", action="store_true", help="esquema + solo el administrador (sin hospitales ni médicos de prueba)")
    args = parser.parse_args()
    error = validate(settings.POSTGRES_SERVER, settings.SEED_ADMIN_PASSWORD, args.force, needs_admin=not args.solo_esquema)
    if error:
        print(f"ERROR: {error}")
        return 1
    applied = ensure_schema(engine)
    print("Esquema actualizado:" if applied else "Esquema al día.")
    for step in applied:
        print("  ", step)
    if args.solo_esquema:
        return 0
    with SessionLocal() as db:
        created = seed(db, settings.SEED_ADMIN_PASSWORD, only_admin=args.solo_admin)
    print(f"Creados: {created['hospitales']} hospitales, {created['usuarios']} usuarios (lo existente no se tocó).")
    print(f"Admin: {ADMIN_EMAIL} (clave: SEED_ADMIN_PASSWORD)." + ("" if args.solo_admin else f" Médicos de prueba: clave {DOCTOR_PASSWORD}."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
