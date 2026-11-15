import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.ml_data import DailyClimate
from app.services.open_meteo import REGION_COORDS, OpenMeteoError
from scripts.load_climate import load
from tests.test_roles import forecast_96h


class LoadClimateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_loads_three_full_days_for_every_region_and_is_repeatable(self):
        first = load(self.db, fetch=lambda lat, lon: forecast_96h())
        self.assertEqual(first, {region: 3 for region in REGION_COORDS})
        self.assertEqual(load(self.db, fetch=lambda lat, lon: forecast_96h()), {region: 0 for region in REGION_COORDS})
        self.assertEqual(self.db.query(DailyClimate).count(), 3 * len(REGION_COORDS))

    def test_one_failing_region_does_not_stop_the_others(self):
        def fetch(lat, lon):
            if (lat, lon) == REGION_COORDS["Maule"]:
                raise OpenMeteoError("sin conexión")
            return forecast_96h()

        result = load(self.db, fetch=fetch)
        self.assertTrue(result["Maule"].startswith("FALLÓ"))
        self.assertEqual(result["Atacama"], 3)


if __name__ == "__main__":
    unittest.main()
