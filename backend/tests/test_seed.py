import csv
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash, verify_password
from app.db.session import Base
from app.models.establishment import Establishment
from app.models.user import User
from app.schemas.prediction import MlRegion
from app.schemas.ml_data import EstablishmentType
from scripts.seed_dev import ADMIN_EMAIL, DOCTOR_PASSWORD, DOCTORS, HOSPITALS, ensure_schema, seed, validate


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        ensure_schema(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_seed_creates_hospitals_admin_and_linked_doctors(self):
        self.assertEqual(seed(self.db, "ClaveAdmin1"), {"hospitales": len(HOSPITALS), "usuarios": len(DOCTORS) + 1})
        admin = self.db.query(User).filter_by(email=ADMIN_EMAIL).one()
        self.assertEqual((admin.role, admin.establecimiento_id), ("admin", None))
        self.assertTrue(verify_password("ClaveAdmin1", admin.hashed_password))
        doctor = self.db.query(User).filter_by(email="medico1@hospitalprueba.cl").one()
        self.assertEqual(doctor.role, "medico")
        self.assertEqual(doctor.establecimiento.dominio_correo, "hospitalprueba.cl")
        self.assertTrue(verify_password(DOCTOR_PASSWORD, doctor.hashed_password))

    def test_seed_can_run_twice_without_duplicates_or_overwriting(self):
        self.db.add(User(email=ADMIN_EMAIL, hashed_password=get_password_hash("MiPropiaClave"), role="admin"))
        self.db.commit()
        seed(self.db, "ClaveAdmin1")
        self.assertEqual(seed(self.db, "OtraClave99"), {"hospitales": 0, "usuarios": 0})
        self.assertEqual(self.db.query(Establishment).count(), len(HOSPITALS))
        self.assertEqual(self.db.query(User).count(), len(DOCTORS) + 1)
        admin = self.db.query(User).filter_by(email=ADMIN_EMAIL).one()
        self.assertTrue(verify_password("MiPropiaClave", admin.hashed_password))

    def test_seeded_hospitals_are_usable_by_the_ml_model(self):
        """Región y tipo deben ser valores que el modelo conoce; los códigos reales, los de su catálogo."""
        shares = Path(__file__).resolve().parents[2] / "Modelo" / "artifacts" / "cuotas_establecimiento_v5.csv"
        known = {}
        if shares.exists():
            with shares.open(encoding="utf-8") as f:
                known = {row["IdEstablecimiento"].strip(): row["Region"] for row in csv.DictReader(f)}
        regions, types = {r.value for r in MlRegion}, {t.value for t in EstablishmentType}
        for h in HOSPITALS:
            with self.subTest(hospital=h["id_establecimiento"]):
                self.assertIn(h["region"], regions)
                self.assertIn(h["tipo"], types)
                if not h["id_establecimiento"].startswith("99-") and known:
                    self.assertEqual(known.get(h["id_establecimiento"]), h["region"])
        self.assertGreaterEqual(len({h["id_establecimiento"] for h in HOSPITALS}), 3)

    def test_only_admin_creates_no_hospitals_or_doctors(self):
        self.assertEqual(seed(self.db, "ClaveAdmin1", only_admin=True), {"hospitales": 0, "usuarios": 1})
        self.assertEqual((self.db.query(Establishment).count(), self.db.query(User).one().role), (0, "admin"))
        # Después se puede completar con el seed normal sin duplicar al admin.
        self.assertEqual(seed(self.db, "ClaveAdmin1"), {"hospitales": len(HOSPITALS), "usuarios": len(DOCTORS)})

    def test_schema_only_needs_no_admin_password_but_still_refuses_remote_servers(self):
        self.assertIsNone(validate("localhost", None, False, needs_admin=False))
        self.assertIn("no parece una base local", validate("prod.example.com", None, False, needs_admin=False))

    def test_seed_refuses_non_local_servers_and_missing_admin_password(self):
        self.assertIsNone(validate("localhost", "ClaveAdmin1", False))
        self.assertIn("no parece una base local", validate("prod.example.com", "ClaveAdmin1", False))
        self.assertIsNone(validate("prod.example.com", "ClaveAdmin1", True))
        for password in (None, "", "corta"):
            self.assertIn("SEED_ADMIN_PASSWORD", validate("localhost", password, False))


if __name__ == "__main__":
    unittest.main()
