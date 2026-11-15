import unittest
from datetime import date

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.establishment import Establishment
from app.models.intake import DailyIntake
from app.models.ml_data import DailyDemand
from app.models.user import User
from scripts.seed_demo import AGE_SHARES, DAYS, generate, remove, split_by_age
from scripts.seed_dev import HOSPITALS, ensure_schema, seed

TODAY = date(2026, 11, 15)


class SeedDemoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        ensure_schema(self.engine)
        self.db = Session(self.engine)
        seed(self.db, "ClaveAdmin1")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_split_by_age_always_adds_up_to_the_total(self):
        for total in range(0, 200):
            self.assertEqual(sum(split_by_age(total).values()), total, total)
        self.assertEqual(set(split_by_age(30)), set(AGE_SHARES))

    def test_generates_five_days_per_hospital_with_coherent_intakes(self):
        created = generate(self.db, TODAY)
        self.assertEqual(created["demanda"], DAYS * len(HOSPITALS))
        self.assertEqual(self.db.query(DailyDemand).count(), DAYS * len(HOSPITALS))
        # Para cada hospital y día, los casos por edad suman la demanda diaria.
        sums = {(r[0], r[1]): r[2] for r in self.db.query(
            DailyIntake.establecimiento_id, DailyIntake.fecha, func.sum(DailyIntake.casos_respiratorios)).group_by(
            DailyIntake.establecimiento_id, DailyIntake.fecha)}
        self.assertEqual(len(sums), DAYS * len(HOSPITALS))
        ids = {h.id_establecimiento: h.id for h in self.db.query(Establishment)}
        for demand in self.db.query(DailyDemand):
            self.assertEqual(sums[(ids[demand.id_establecimiento], demand.fecha)], demand.total)
        self.assertEqual(min(d.fecha for d in self.db.query(DailyDemand)), date(2026, 11, 11))

    def test_repeating_does_not_duplicate_or_overwrite_and_remove_cleans_up(self):
        generate(self.db, TODAY)
        first = self.db.query(DailyDemand).order_by(DailyDemand.id_establecimiento, DailyDemand.fecha).first()
        first.total = 777
        self.db.commit()
        self.assertEqual(generate(self.db, TODAY), {"demanda": 0, "ingresos": 0})
        self.assertEqual(self.db.get(DailyDemand, (first.id_establecimiento, first.fecha)).total, 777)
        self.assertEqual(remove(self.db, TODAY)["demanda"], DAYS * len(HOSPITALS))
        self.assertEqual((self.db.query(DailyDemand).count(), self.db.query(DailyIntake).count()), (0, 0))

    def test_remove_keeps_intakes_registered_by_a_user(self):
        hospital = self.db.query(Establishment).first()
        user = User(email="doc@x.cl", hashed_password="x", role="medico", establecimiento_id=hospital.id)
        self.db.add(user)
        self.db.flush()
        self.db.add(DailyIntake(fecha=TODAY, establecimiento_id=hospital.id, casos_respiratorios=3,
                                grupo_etario="15-64", created_by_user_id=user.id))
        self.db.commit()
        remove(self.db, TODAY)
        self.assertEqual(self.db.query(DailyIntake).count(), 1)


if __name__ == "__main__":
    unittest.main()
