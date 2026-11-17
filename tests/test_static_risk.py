import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from risk_data import apply_scores, color, combine, risk_class  # noqa: E402

spec = importlib.util.spec_from_file_location("build_static_risk", ROOT / "ml/build_static_risk.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class SubScoreTests(unittest.TestCase):
    def test_percentile_rank_puts_minimum_and_ties_at_zero(self):
        ranks = build.percentile_rank(pd.Series([0.0, 0.0, 0.0, 5.0, 10.0]))
        self.assertEqual(ranks.tolist(), [0.0, 0.0, 0.0, 0.75, 1.0])

    def test_pure_pine_forest_beats_empty_cell(self):
        table = pd.DataFrame({
            "resineux_frac": [1.0, 0.0], "foret_frac": [1.0, 0.0], "pin_frac": [1.0, 0.0],
            "lisiere_m_ha": [3.0, 0.0], "pente_moy_deg": [1.0, 0.0],
            "wui_frac": [0.1, 0.0], "route_ponderee_km": [2.0, 0.0],
            "tmja_max": [500.0, 0.0], "agri_frac": [0.2, 0.0]})
        scores, info = build.sub_scores(table)
        self.assertEqual(scores["s_combustible"].tolist(), [100.0, 0.0])
        self.assertEqual(scores["s_humain"].tolist(), [100.0, 0.0])
        self.assertEqual(info["colonnes_absentes"], [])

    def test_missing_columns_renormalise_weights(self):
        table = pd.DataFrame({"resineux_frac": [0.5], "foret_frac": [0.5], "wui_frac": [0.0]})
        scores, info = build.sub_scores(table)
        self.assertEqual(scores["s_combustible"].iloc[0], 50.0)
        self.assertIn("tmja_max", info["colonnes_absentes"])


class CombineTests(unittest.TestCase):
    def test_multiplicative_needs_fuel(self):
        self.assertEqual(combine(0, 100), 0)            # centre-ville sans végétation
        self.assertEqual(combine(80, 0), 48.0)          # massif isolé
        self.assertEqual(combine(80, 100), 80.0)        # massif fréquenté

    def test_additive_uses_weight(self):
        self.assertEqual(combine(80, 20, "additif", 0.5), 50.0)

    def test_classes_and_colours(self):
        self.assertEqual(risk_class(0), "Très faible")
        self.assertEqual(risk_class(60), "Élevé")
        self.assertEqual(risk_class(100), "Très élevé")
        self.assertEqual(color(0, 255), [255, 255, 204, 255])
        self.assertEqual(color(100, 255), [128, 0, 38, 255])

    def test_apply_scores_keeps_input_unchanged(self):
        geojson = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": None,
            "properties": {"s_combustible": 50.0, "s_humain": 50.0, "foret_frac": 0.42}}]}
        out = apply_scores(geojson, layer="s_humain")
        props = out["features"][0]["properties"]
        self.assertEqual(props["valeur"], 50.0)
        self.assertEqual(props["score"], 40.0)
        self.assertEqual(props["foret_frac_pct"], "42 %")
        self.assertNotIn("score", geojson["features"][0]["properties"])


if __name__ == "__main__":
    unittest.main()
