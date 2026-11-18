import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from ml.build_camera_directory import (
    OUTPUT_FIELDS,
    assign_cameras_to_mesh,
    geocoding_query,
    is_active_public_live,
    video_to_candidate,
    write_json,
    write_sqlite,
)


class CameraDirectoryTests(unittest.TestCase):
    def test_only_active_public_lives_are_accepted(self):
        video = {
            "snippet": {"liveBroadcastContent": "live"},
            "liveStreamingDetails": {"actualStartTime": "2026-01-01T10:00:00Z"},
            "status": {"privacyStatus": "public"},
        }
        self.assertTrue(is_active_public_live(video))

        ended = {**video, "liveStreamingDetails": {"actualStartTime": "x", "actualEndTime": "y"}}
        upcoming = {**video, "snippet": {"liveBroadcastContent": "upcoming"}}
        private = {**video, "status": {"privacyStatus": "private"}}
        self.assertFalse(is_active_public_live(ended))
        self.assertFalse(is_active_public_live(upcoming))
        self.assertFalse(is_active_public_live(private))

    def test_video_metadata_uses_source_coordinates_and_cleans_geocoding_query(self):
        video = {
            "id": "abc123",
            "snippet": {"title": "Webcam en direct 4K à Biarritz"},
            "recordingDetails": {"location": {"latitude": 43.48, "longitude": -1.56}},
        }
        candidate = video_to_candidate(video)
        self.assertEqual(candidate["lat"], 43.48)
        self.assertEqual(candidate["lon"], -1.56)
        self.assertEqual(candidate["url_youtube"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(geocoding_query("Webcam en direct 4K"), None)

    def test_spatial_join_deduplicates_and_assigns_boundary_points_deterministically(self):
        mesh = gpd.GeoDataFrame(
            {"cell_code": ["Z-cell", "A-cell"], "geometry": [box(0, 0, 1, 1), box(1, 0, 2, 1)]},
            crs="EPSG:4326",
        )
        camera = {
            "nom": "Webcam Biarritz",
            "url_youtube": "https://www.youtube.com/watch?v=abc123",
            "lat": 0.5,
            "lon": 1.0,
        }
        result = assign_cameras_to_mesh([camera, camera], mesh, "cell_code")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id_maille"], "A-cell")
        self.assertEqual(tuple(result[0]), OUTPUT_FIELDS)

    def test_json_and_sqlite_export_only_requested_fields(self):
        camera = {
            "nom": "Caméra",
            "url_youtube": "https://www.youtube.com/watch?v=abc123",
            "lat": 43.48,
            "lon": -1.56,
            "id_maille": "cell-1",
        }
        with tempfile.TemporaryDirectory() as folder:
            json_path = Path(folder) / "cameras.json"
            sqlite_path = Path(folder) / "cameras.sqlite"
            write_json(json_path, [camera])
            write_sqlite(sqlite_path, [camera])

            exported = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(tuple(exported[0]), OUTPUT_FIELDS)
            connection = sqlite3.connect(sqlite_path)
            try:
                columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(cameras)"))
                self.assertEqual(columns, OUTPUT_FIELDS)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM cameras").fetchone()[0], 1)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
