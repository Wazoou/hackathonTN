import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from risk_map import build_risk_map_html


class RiskMapTests(unittest.TestCase):
    def test_map_uses_openstreetmap_and_clickable_department_boundaries(self):
        html = build_risk_map_html()

        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", html)
        self.assertIn("https://raw.githubusercontent.com/gregoiredavid/france-geojson/", html)
        self.assertIn("L.geoJSON(features", html)
        self.assertIn("click:()=>{", html)
        self.assertIn("Données à venir", html)


if __name__ == "__main__":
    unittest.main()
