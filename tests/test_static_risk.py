import importlib.util
import sys
import unittest
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from risk_data import apply_scores, color, combine, risk_class, to_scale  # noqa: E402

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

    def test_national_table_joins_by_id_and_rejects_mismatched_grid(self):
        import geopandas as gpd
        from shapely.geometry import box

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            grid = gpd.GeoDataFrame({"cell_id": [1, 2], "id_carreau_dfci": ["A", "B"],
                                    "departement": ["01", "2A"]},
                                   geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:2154")
            table = pd.DataFrame({"cell_id": [2, 1], "id_carreau_dfci": ["B", "A"],
                                  "departement": ["2A", "01"], "foret_frac": [0.8, 0.2]})
            gp, tp = folder / "grid.parquet", folder / "features.parquet"
            grid.to_parquet(gp); table.to_parquet(tp)
            cells = build.load_cells([tp], gp).set_index("cell_id")
            self.assertEqual(cells.loc[1, "foret_frac"], 0.2)
            self.assertEqual(cells.loc[2, "dept"], "2A")
            self.assertTrue(cells.loc[2, "geometry"].equals(grid.geometry.iloc[1]))
            table.loc[0, "departement"] = "33"
            table.to_parquet(tp)
            with self.assertRaisesRegex(ValueError, "mêmes cellules"):
                build.load_cells([tp], gp)
            with self.assertRaisesRegex(ValueError, "--grid"):
                build.load_cells([tp])


    def test_border_cell_kept_once_in_main_department(self):
        table = pd.DataFrame({"id_carreau_dfci": ["A", "A", "B"], "dept": ["33", "40", "40"],
                              "frac_dans_dept": [0.3, 0.7, 1.0]})
        kept = build.dedupe_border_cells(table)
        self.assertEqual(sorted(zip(kept.id_carreau_dfci, kept.dept)), [("A", "40"), ("B", "40")])


class BdiffModelTests(unittest.TestCase):
    def setUp(self):
        self.cells = pd.DataFrame({"code_insee": ["A", "A", "B", "C"], "dept": ["33", "33", "33", "40"]})
        self.X = pd.DataFrame({"foret_frac": [1.0, 0.5, 0.0, 0.2]})

    def test_commune_table_counts_fire_years_not_fires(self):
        fires = pd.DataFrame({"code_insee": ["A", "A", "A", "B", "Z"], "annee": [2010, 2010, 2011, 1999, 2010]})
        table = build.commune_table(self.X, self.cells, fires, range(2010, 2013))
        self.assertEqual(table.loc["A", "annees_feu"], 2)       # deux feux en 2010 = une année
        self.assertEqual(table.loc["A", "feux"], 3)
        self.assertEqual(table.loc["B", "annees_feu"], 0)       # 1999 hors période
        self.assertAlmostEqual(table.loc["A", "foret_frac"], 0.75)
        self.assertAlmostEqual(table.loc["A", "log_surface"], 0.6931, places=3)
        self.assertEqual(table.loc["B", "log_surface"], 0)
        self.assertNotIn("Z", table.index)                       # commune sans carreau ignorée

    def test_expand_weights_sum_to_commune_years(self):
        fires = pd.DataFrame({"code_insee": ["A"], "annee": [2010]})
        table = build.commune_table(self.X, self.cells, fires, range(2010, 2014))
        _, y, w, _ = build._expand(table, ["foret_frac"])
        self.assertEqual(w.sum(), 3 * 4)
        self.assertEqual(w[y == 1].sum(), 1)


class CombineTests(unittest.TestCase):
    def test_probability_scale_matches_legend_bounds(self):
        self.assertEqual(to_scale(0, "p_feu"), 0)
        self.assertEqual(to_scale(2, "p_feu"), 20)
        self.assertEqual(to_scale(7.5, "p_feu"), 50)
        self.assertEqual(to_scale(90, "p_feu"), 100)
        self.assertEqual(to_scale(42, "score"), 42)
        self.assertEqual(risk_class(to_scale(12, "p_feu")), "Élevé")

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
