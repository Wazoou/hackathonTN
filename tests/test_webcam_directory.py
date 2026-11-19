import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from dashboard.webcam_directory import (
    fetch_opencctv_snapshot,
    is_valid_webcam_url,
    load_camera_directory,
    selected_camera_url,
    webcam_display_type,
    webcam_embed_url,
)


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
                {"url_youtube": "ftp://example.com/camera.m3u8"},
                {"url_youtube": "javascript:alert(1)"},
                {"lat": 91},
            ):
                path.write_text(json.dumps([{**self.camera, **changes}]), encoding="utf-8")
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    load_camera_directory(path)

    def test_reads_selected_map_marker(self):
        state = {
            "selection": {
                "objects": {
                    "public-webcams": [{"url_youtube": self.camera["url_youtube"]}]
                }
            }
        }
        self.assertEqual(selected_camera_url(state), self.camera["url_youtube"])
        self.assertIsNone(selected_camera_url({"selection": {"objects": {}}}))

    def test_csv_catalogue_is_usable_without_generated_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cameras.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["ville", "url_youtube", "lat", "lon", "id_maille"], delimiter=";")
                writer.writeheader()
                writer.writerow({"ville": self.camera["nom"], **{k: v for k, v in self.camera.items() if k != "nom"}})
            self.assertEqual(load_camera_directory(path), [self.camera])

    def test_csv_requires_complete_positions_and_cell_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cameras.csv"
            path.write_text("url_youtube;ville;lat;lon\nhttps://example.org/live.jpg;Test;48;2\n")
            with self.assertRaisesRegex(ValueError, "id_maille"):
                load_camera_directory(path)

    def test_csv_reuses_coordinate_and_duplicate_url_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cameras.csv"
            header = "url_youtube;ville;lat;lon;id_maille\n"
            with self.subTest("invalid position"):
                path.write_text(header + "https://example.org/live.jpg;Test;nan;2;cell\n")
                with self.assertRaises(ValueError):
                    load_camera_directory(path)
            with self.subTest("duplicate feed"):
                row = "https://example.org/live.jpg;Test;48;2;cell\n"
                path.write_text(header + row + row)
                with self.assertRaisesRegex(ValueError, "double"):
                    load_camera_directory(path)

    def test_builds_embed_url_from_live_link_and_drops_tracking_query(self):
        self.assertEqual(
            webcam_embed_url("https://www.youtube.com/live/QzDQcYL8NXk?si=tracking"),
            "https://www.youtube.com/embed/QzDQcYL8NXk",
        )
        self.assertEqual(
            webcam_embed_url("https://youtu.be/QzDQcYL8NXk"),
            "https://www.youtube.com/embed/QzDQcYL8NXk",
        )

    def test_classifies_image_stream_and_external_webcam_sources(self):
        image_url = "https://opencctv.org/still/73628.jpg"
        stream_url = "https://example.org/camera/live.m3u8"
        page_url = "https://fr.worldcam.eu/webcams/europe/france/1059-nice"

        self.assertEqual(webcam_display_type(self.camera["url_youtube"]), "youtube")
        self.assertEqual(webcam_display_type(image_url), "image")
        self.assertEqual(webcam_display_type(stream_url), "video")
        self.assertEqual(webcam_display_type(page_url), "external")
        self.assertEqual(webcam_embed_url(image_url), image_url)
        self.assertTrue(is_valid_webcam_url(image_url))
        self.assertTrue(is_valid_webcam_url(page_url))

    @patch("dashboard.webcam_directory.requests.get")
    def test_fetches_opencctv_image_server_side(self, get):
        response = Mock(status_code=200, headers={"Content-Type": "image/jpeg"})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [b"jpeg-data"]
        get.return_value = response

        image = fetch_opencctv_snapshot("https://opencctv.org/still/73628.jpg")

        self.assertEqual(image, b"jpeg-data")
        get.assert_called_once_with(
            "https://opencctv.org/still/73628.jpg",
            timeout=(5, 10),
            allow_redirects=False,
            stream=True,
        )

    @patch("dashboard.webcam_directory.requests.get")
    def test_rejects_non_opencctv_image_hosts(self, get):
        with self.assertRaises(ValueError):
            fetch_opencctv_snapshot("https://example.org/camera.jpg")
        get.assert_not_called()

    @patch("dashboard.webcam_directory.requests.get")
    def test_reports_unavailable_opencctv_snapshot(self, get):
        response = Mock(status_code=404, headers={})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        get.return_value = response

        with self.assertRaisesRegex(ValueError, "HTTP 404"):
            fetch_opencctv_snapshot("https://opencctv.org/still/73628.jpg")


if __name__ == "__main__":
    unittest.main()
