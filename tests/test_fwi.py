import importlib.util
import unittest
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("fwi", Path(__file__).resolve().parents[1] / "ml/fwi.py")
fwi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fwi)


class FwiReferenceTests(unittest.TestCase):
    def test_van_wagner_reference_day(self):
        # Exemple de référence du programme de Van Wagner & Pickett (1985) :
        # 17 °C, 42 %, 25 km/h, 0 mm, avril, départ FFMC 85, DMC 6, DC 15.
        state = {k: np.array([v]) for k, v in fwi.START.items()}
        state, out = fwi.step(state, np.array([17.0]), np.array([42.0]), np.array([25.0]), np.array([0.0]), 4)
        expected = {"ffmc": 87.7, "dmc": 8.5, "dc": 19.0, "isi": 10.9, "bui": 8.5, "fwi": 10.1}
        for key, value in expected.items():
            self.assertAlmostEqual(float(out[key][0]), value, delta=0.06, msg=key)

    def test_rain_lowers_codes_and_missing_day_keeps_state(self):
        temp = np.array([[30.0, 30.0], [20.0, np.nan]])
        rh = np.array([[20.0, 20.0], [90.0, 90.0]])
        wind = np.array([[20.0, 20.0], [10.0, 10.0]])
        rain = np.array([[0.0, 0.0], [25.0, 25.0]])
        out = fwi.run(temp, rh, wind, rain, [7, 7])
        self.assertLess(out["ffmc"][1, 0], out["ffmc"][0, 0])     # pluie : litière humidifiée
        self.assertLess(out["dc"][1, 0], out["dc"][0, 0])
        self.assertTrue(np.isnan(out["fwi"][1, 1]))               # donnée manquante : pas d'indice
        self.assertGreater(out["fwi"][0, 0], 15)                  # dès le 1er jour chaud, sec, venté


if __name__ == "__main__":
    unittest.main()
