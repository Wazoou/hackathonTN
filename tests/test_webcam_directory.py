import json
import tempfile
import unittest
from pathlib import Path

from dashboard.webcam_directory import load_camera_directory, selected_camera_url


class WebcamDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.camera = {
            "nom": "Webcam Biarritz",
            "url_youtube": "https://www.youtube.com/watch?v=abc123def45",
            "lat": 43.48,
            "lon": -1.56,
            "id_maille": "cell-1",
        }

    def test_loads_exact_schema_and_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cameras.json"
            path.write_text(json.dumps([self.camera]), encoding="utf-8")

            cameras = load_camera_directory(path)

        self.assertEqual(list(cameras[0]), ["nom", "url_youtube", "lat", "lon", "id_maille"])
        self.assertEqual(cameras[0]["lat"], 43.48)
        self.assertEqual(cameras[0]["lon"], -1.56)

    def test_rejects_non_youtube_urls_and_invalid_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cameras.json"
            for changes in (
                {"url_youtube": "https://example.com/watch?v=abc"},
                {"lat": 91},
            ):
                path.write_text(json.dumps([{**self.camera, **changes}]), encoding="utf-8")
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    load_camera_directory(path)

    def test_reads_selected_map_marker(self):
        state = {
            "selection": {
                "objects": {
                    "youtube_cameras": [{"url_youtube": self.camera["url_youtube"]}]
                }
            }
        }
        self.assertEqual(selected_camera_url(state), self.camera["url_youtube"])
        self.assertIsNone(selected_camera_url({"selection": {"objects": {}}}))


if __name__ == "__main__":
    unittest.main()
