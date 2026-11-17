import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from fire_history import (
    available_months,
    build_leaflet_map_html,
    build_map_points,
    area_radius_px,
    filter_fire_records,
    fire_records_for_map_period,
    fire_records_for_month,
    format_month,
    load_fire_records,
    MAP_PERIOD_ALL,
    MAP_PERIOD_MONTH,
)


class FireHistoryTests(unittest.TestCase):
    def test_records_keep_insee_codes_and_group_red_map_points(self):
        with tempfile.TemporaryDirectory() as directory:
            fire_path = Path(directory) / "fires.csv"
            centroid_path = Path(directory) / "centroids.csv"
            fire_path.write_text(
                "Métadonnées\nCritères\n"
                "Année;Numéro;Département;Code INSEE;Nom de la commune;Date de première alerte;"
                "Surface parcourue (m2);Nature\n"
                "2025;1;01;00123;Commune A;2025-01-02 08:00:00;100;Accidentelle\n"
                "2025;2;01;00123;Commune A;2025-01-04 08:00:00;300;Malveillance\n"
                "2025;3;974;97412;Commune B;2025-03-01 08:00:00;1000;Naturelle\n"
                "2025;4;01;00999;Commune C;2025-04-01 08:00:00;50;\n",
                encoding="utf-8",
            )
            centroid_path.write_text(
                "Code INSEE,latitude,longitude,precision\n"
                "00123,46.0,5.0,commune\n"
                "97412,-21.1,55.5,département\n",
                encoding="utf-8",
            )
            records, total_count = load_fire_records(
                str(fire_path),
                str(centroid_path),
                fire_path.stat().st_mtime_ns,
                centroid_path.stat().st_mtime_ns,
            )

        self.assertEqual(total_count, 4)
        self.assertEqual(records.loc[0, "Code INSEE"], "00123")
        self.assertEqual(records.loc[2, "zone"], "Outre-mer")
        self.assertEqual(records["latitude"].notna().sum(), 3)
        self.assertEqual(
            available_months(records),
            ["2025-01", "2025-02", "2025-03", "2025-04"],
        )
        self.assertEqual(format_month("2025-02"), "Février 2025")
        january = fire_records_for_month(records, "2025-01")
        self.assertEqual(len(january), 2)
        points = build_map_points(
            january[january["zone"] == "France métropolitaine"]
        )
        mainland = points[points["zone"] == "France métropolitaine"].iloc[0]
        self.assertEqual(mainland["incident_count"], 2)
        self.assertEqual(mainland["locations"], "Commune A")
        self.assertEqual(mainland["burned_area_m2"], 400)
        self.assertAlmostEqual(mainland["radius_px"], area_radius_px(400))
        self.assertGreaterEqual(area_radius_px(1), 4)
        self.assertLessEqual(area_radius_px(111_330_000), 20)
        self.assertAlmostEqual(area_radius_px(40_000) ** 2 / area_radius_px(10_000) ** 2, 4)

    def test_filters_by_year_season_and_cause(self):
        records = pd.DataFrame({
            "Date de première alerte": pd.to_datetime([
                "2024-01-15",
                "2025-06-15",
                "2025-08-15",
                "2025-12-15",
            ]),
            "Nature": ["Accidentelle", "Naturelle", "Malveillance", "Naturelle"],
        })

        filtered = filter_fire_records(
            records,
            season="Été",
            cause="Foudre (naturelle)",
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["Date de première alerte"].month, 6)

    def test_map_period_selects_all_records_or_the_slider_month(self):
        records = pd.DataFrame({
            "Date de première alerte": pd.to_datetime([
                "2024-12-15",
                "2025-01-15",
                "2025-02-15",
            ]),
        })

        all_points = fire_records_for_map_period(records, MAP_PERIOD_ALL, "2025-01")
        selected_month = fire_records_for_map_period(
            records,
            MAP_PERIOD_MONTH,
            "2025-01",
        )

        self.assertEqual(len(all_points), 3)
        self.assertEqual(len(selected_month), 1)
        self.assertEqual(selected_month.iloc[0]["Date de première alerte"].month, 1)

    def test_duplicate_centroid_codes_raise_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            fire_path = Path(directory) / "fires.csv"
            centroid_path = Path(directory) / "centroids.csv"
            fire_path.write_text(
                "Metadata\nCriteria\n"
                "Code INSEE;Département;Nom de la commune;Date de première alerte;"
                "Surface parcourue (m2);Nature\n"
                "00123;01;Commune;2025-01-01 00:00:00;100;Accidentelle\n",
                encoding="utf-8",
            )
            centroid_path.write_text(
                "Code INSEE,latitude,longitude,precision\n"
                "00123,46.0,5.0,commune\n"
                "00123,46.1,5.1,commune\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "en double"):
                load_fire_records(
                    str(fire_path),
                    str(centroid_path),
                    fire_path.stat().st_mtime_ns,
                    centroid_path.stat().st_mtime_ns,
                )

    def test_map_uses_the_same_openstreetmap_tiles_as_the_webcam_map(self):
        points = pd.DataFrame([{
            "latitude": 46.0,
            "longitude": 5.0,
            "incident_count": 1,
            "locations": "Commune A",
            "burned_area_m2": 100,
            "radius_px": area_radius_px(100),
        }])

        html = build_leaflet_map_html(points)

        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", html)
        self.assertIn("fillColor:'#cd232d'", html)
        self.assertIn("L.circleMarker([fire.latitude,fire.longitude]", html)
        self.assertIn("Surface brûlée :", html)
        self.assertNotIn("cartocdn", html)


if __name__ == "__main__":
    unittest.main()
