import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from daily_data import (cell_probability, commune_probabilities, commune_probability, day_class,  # noqa: E402
                        fwi_class, weather_term)

spec = importlib.util.spec_from_file_location("build_daily_risk", ROOT / "ml/build_daily_risk.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

MODEL = {"intercept": -7.0, "coefficients": {"log_terrain": 0.8, "ffmc_100": -3.0, "log_dmc": 0.7,
                                              "log_dc": 0.0, "log_isi": 1.0}}
DAY = {"ffmc": 90.0, "dmc": 40.0, "dc": 400.0, "isi": 12.0, "bui": 60.0, "fwi": 30.0}


class DashboardModelTests(unittest.TestCase):
    def test_vectorised_matches_scalar(self):
        z = weather_term(MODEL, pd.DataFrame([DAY]))
        vector = commune_probabilities(MODEL, z[:, None], np.array([-2.0]))[0, 0]
        self.assertAlmostEqual(vector, commune_probability(MODEL, DAY, -2.0), places=12)

    def test_cells_share_the_commune_probability(self):
        shares = [0.5, 0.3, 0.2]
        total = sum(cell_probability(MODEL, DAY, -2.0, s) for s in shares)
        self.assertAlmostEqual(total, commune_probability(MODEL, DAY, -2.0), places=12)

    def test_drier_day_is_riskier(self):
        wet = {**DAY, "ffmc": 60.0, "dmc": 2.0, "isi": 0.5}
        self.assertGreater(commune_probability(MODEL, DAY, -2.0), commune_probability(MODEL, wet, -2.0))

    def test_classes(self):
        self.assertEqual(day_class(0.1), 0)
        self.assertEqual(day_class(3), 2)
        self.assertEqual(day_class(80), 4)
        self.assertEqual(fwi_class(2), "faible")
        self.assertEqual(fwi_class(40), "extrême")


class BuildTests(unittest.TestCase):
    def test_sample_keeps_every_fire_day_once_and_weights_negatives(self):
        communes = pd.DataFrame(index=["33001", "33002"])
        dates = pd.date_range("2020-01-01", periods=100, freq="D")
        fires = pd.DataFrame({"code_insee": ["33001", "33001"], "date": [dates[3], dates[3]]})
        sample = build.sample_commune_days(communes, fires, dates, rate=1.0)
        self.assertEqual(int(sample["y"].sum()), 1)              # deux feux le même jour = une commune-jour
        self.assertEqual(len(sample), 200)                         # taux 1 : tous les jours, sans doublon
        sparse = build.sample_commune_days(communes, fires, dates, rate=0.1)
        self.assertTrue((sparse.loc[sparse.y == 0, "w"] == 10).all())

    def test_gap_filled_from_nearest_station(self):
        dates = pd.date_range("2020-07-01", periods=3, freq="D")
        rows = []
        for station, lat, temp in (("A", 44.0, 30.0), ("B", 44.1, 25.0), ("C", 46.0, 10.0)):
            for i, d in enumerate(dates):
                missing = station == "A" and i == 1
                rows.append({"station": station, "nom": station, "lat": lat, "lon": 0.0, "dept": "33", "date": d,
                             "temp": np.nan if missing else temp, "rh": 30.0, "wind": 15.0, "rain": 0.0})
        meteo = pd.DataFrame(rows)
        stations = build.select_stations(meteo, min_share=0.6)
        out = build.station_indices(meteo, stations)
        self.assertEqual(set(stations.index), {"A", "B", "C"})
        self.assertFalse(out["fwi"].isna().any())                 # le trou de A est comblé par B (la plus proche)
        a_day2 = out[(out.station == "A") & (out.date == dates[1])]["ffmc"].iloc[0]
        b_day2 = out[(out.station == "B") & (out.date == dates[1])]["ffmc"].iloc[0]
        self.assertLess(abs(a_day2 - b_day2), 1.0)


if __name__ == "__main__":
    unittest.main()
