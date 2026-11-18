import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from dashboard.webcam_directory import load_camera_directory
from ml.build_camera_directory import (
    OUTPUT_FIELDS,
    assign_cameras_to_mesh,
    build_directory,
    geocode_city,
    is_valid_webcam_url,
    read_camera_csv,
)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class GeocodingSession:
    def __init__(self, features=None):
        self.headers = {}
        self.params = []
        self.features = features or [
            {
                "type": "Feature",
                "properties": {"type": "municipality", "city": "Testville", "score": 0.9},
                "geometry": {"type": "Point", "coordinates": [0.5, 0.5]},
            }
        ]

    def get(self, url, *, params, timeout):
        self.params.append(params)
        return Response({"features": self.features})


class CameraDirectoryTests(unittest.TestCase):
    def test_accepts_youtube_and_other_http_webcam_sources(self):
        for url in (
            "https://www.youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://www.youtube.com/live/abc123",
            "https://www.youtube.com/embed/abc123",
            "https://opencctv.org/still/73628.jpg",
            "http://example.org/camera/live.m3u8",
            "https://fr.worldcam.eu/webcams/europe/france/1059-nice",
        ):
            self.assertTrue(is_valid_webcam_url(url))
        self.assertFalse(is_valid_webcam_url("javascript:alert(1)"))
        self.assertFalse(is_valid_webcam_url("ftp://example.org/camera.jpg"))

    def test_geocodes_a_city_without_youtube_api_credentials(self):
        session = GeocodingSession()
        self.assertEqual(geocode_city(session, "Testville"), (0.5, 0.5))
        self.assertEqual(session.params[0]["q"], "Testville")
        self.assertEqual(session.params[0]["type"], "municipality")

    def test_reads_csv_with_semicolons_or_commas(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            semicolon_csv = root / "semicolon.csv"
            semicolon_csv.write_text(
                "url_youtube;ville\nhttps://youtu.be/abc123;Lyon\n",
                encoding="utf-8",
            )
            comma_csv = root / "comma.csv"
            comma_csv.write_text(
                "ville,url_youtube\nBiarritz,https://youtu.be/def456\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_camera_csv(semicolon_csv),
                [{"nom": "Lyon", "url_youtube": "https://youtu.be/abc123"}],
            )
            self.assertEqual(
                read_camera_csv(comma_csv),
                [{"nom": "Biarritz", "url_youtube": "https://youtu.be/def456"}],
            )

    def test_csv_rejects_rows_missing_a_city_or_link(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cameras.csv"
            path.write_text(
                "url_youtube;ville\nhttps://youtu.be/abc123;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "URL de webcam et ville obligatoires"):
                read_camera_csv(path)

    def test_ambiguous_city_requires_a_department(self):
        session = GeocodingSession(
            [
                {
                    "type": "Feature",
                    "properties": {"type": "municipality", "city": "Saint-Denis", "score": 0.9},
                    "geometry": {"type": "Point", "coordinates": [2.35, 48.93]},
                },
                {
                    "type": "Feature",
                    "properties": {"type": "municipality", "city": "Saint-Denis", "score": 0.88},
                    "geometry": {"type": "Point", "coordinates": [55.45, -20.88]},
                },
            ]
        )
        with self.assertRaisesRegex(ValueError, "Ajoutez son département"):
            geocode_city(session, "Saint-Denis")

    def test_spatial_join_assigns_the_city_to_its_risk_cell(self):
        mesh = gpd.GeoDataFrame(
            {"cell_code": ["cell-1"], "geometry": [box(0, 0, 1, 1)]},
            crs="EPSG:4326",
        )
        camera = {
            "nom": "Testville",
            "url_youtube": "https://www.youtube.com/watch?v=abc123",
            "lat": 0.5,
            "lon": 0.5,
        }
        result = assign_cameras_to_mesh([camera], mesh, "cell_code")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id_maille"], "cell-1")
        self.assertEqual(tuple(result[0]), OUTPUT_FIELDS)

    def test_build_directory_matches_csv_and_removes_deleted_cameras(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mesh_path = root / "mesh.geojson"
            gpd.GeoDataFrame(
                {"cell_code": ["cell-1"], "geometry": [box(0, 0, 1, 1)]},
                crs="EPSG:4326",
            ).to_file(mesh_path, driver="GeoJSON")
            output_path = root / "camera.json"
            input_csv = root / "cameras.csv"
            output_path.write_text(
                json.dumps(
                    [
                        {
                            "nom": "Obsolete",
                            "url_youtube": "https://youtu.be/old111",
                            "lat": 0.25,
                            "lon": 0.25,
                            "id_maille": "old-cell",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            input_csv.write_text(
                "url_youtube;ville\n"
                "https://www.youtube.com/watch?v=abc123;Testville\n"
                "https://youtu.be/def456;Testville\n",
                encoding="utf-8",
            )
            session = GeocodingSession()
            result = build_directory(
                mesh_path=mesh_path,
                id_column="cell_code",
                input_csv=input_csv,
                output_json=output_path,
                output_fn=lambda _message: None,
                session=session,
            )
            exported = json.loads(output_path.read_text(encoding="utf-8"))
            expected_urls = {
                "https://www.youtube.com/watch?v=abc123",
                "https://youtu.be/def456",
            }
            self.assertEqual(len(result), 2)
            self.assertEqual({camera["url_youtube"] for camera in exported}, expected_urls)
            self.assertEqual(len(load_camera_directory(output_path)), 2)
            self.assertTrue(all(tuple(camera) == OUTPUT_FIELDS for camera in exported))

            input_csv.write_text(
                "url_youtube;ville\nhttps://youtu.be/def456;Testville\n",
                encoding="utf-8",
            )
            result = build_directory(
                mesh_path=mesh_path,
                id_column="cell_code",
                input_csv=input_csv,
                output_json=output_path,
                output_fn=lambda _message: None,
                session=session,
            )
            self.assertEqual([camera["url_youtube"] for camera in result], ["https://youtu.be/def456"])
            self.assertEqual(len(load_camera_directory(output_path)), 1)

            input_csv.write_text("url_youtube;ville\n", encoding="utf-8")
            result = build_directory(
                mesh_path=mesh_path,
                id_column="cell_code",
                input_csv=input_csv,
                output_json=output_path,
                output_fn=lambda _message: None,
                session=session,
            )
            self.assertEqual(result, [])
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
