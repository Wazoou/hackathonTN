"""Alert persistence, demo isolation, stale uploads and input boundaries.

Run inside the API image with tests mounted; uses a temporary database only.
"""
import asyncio
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException, UploadFile

spec = importlib.util.spec_from_file_location("smoke_api", str(Path("/app/app/main.py") if Path("/app/app/main.py").exists() else Path(__file__).resolve().parents[1] / "api/app/main.py"))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        api.DATA_DIR = Path(self.directory.name)
        api.DB_PATH = api.DATA_DIR / "pyro.db"
        api.FRAMES_DIR = api.DATA_DIR / "frames"
        api.ALERTS_DIR = api.DATA_DIR / "alerts"
        api._consecutive.clear()
        self.frame_number = 0
        api.init()
        for cam_id, demo in [("public-test", False), ("demo-fire", True)]:
            api.upsert_camera(cam_id, api.CameraIn(name=cam_id, lat=44, lon=-1, is_demo=demo,
                                                   detector="yolo", source_url="https://example.org/cam.jpg"))

    def tearDown(self):
        self.directory.cleanup()

    def frame(self, cam="public-test", confidence=0.8, generation=None, content=None):
        self.frame_number += 1
        if content is None:
            content = f"test image {self.frame_number}".encode()
        return asyncio.run(api.post_frame(cam, UploadFile(filename="test.jpg", file=io.BytesIO(content)),
                         json.dumps([{"confidence": confidence, "bbox": [0.1, 0.2, 0.7, 0.8]}]), generation))

    def test_persistence_and_deduplication(self):
        self.assertIsNone(self.frame()["alert_id"])
        first = self.frame()["alert_id"]
        self.assertIsNotNone(first)
        api.ALERT_COOLDOWN_S = -1  # even after cooldown, an open incident stays unique
        self.assertIsNone(self.frame(confidence=0.9)["alert_id"])
        alerts = api.list_alerts(None, 50)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["confidence"], 0.9)
        self.assertEqual(alerts[0]["camera_name"], "public-test")
        self.assertEqual(alerts[0]["detector"], "yolo")
        api.ALERT_COOLDOWN_S = 300

    def test_negative_frame_and_error_break_streak(self):
        self.frame()
        self.frame(confidence=0.1)
        self.assertIsNone(self.frame()["alert_id"])
        api.camera_failure("public-test", api.CameraFailure(error="Offline"))
        self.assertIsNone(self.frame()["alert_id"])
        self.assertIsNone(api.list_cameras()[1]["last_error"])

    def test_demo_reset_isolated_and_rejects_stale_upload(self):
        self.frame(); self.frame()
        state = api.control_demo("start")
        self.frame("demo-fire", generation=state["generation"])
        self.frame("demo-fire", generation=state["generation"])
        self.assertEqual(len(api.list_alerts(None, 50)), 2)
        api.control_demo("reset")
        self.assertEqual(len(api.list_alerts(None, 50)), 1)
        with self.assertRaises(HTTPException) as error:
            self.frame("demo-fire", generation=state["generation"])
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse((api.FRAMES_DIR / "demo-fire" / "latest.jpg").exists())

    def test_human_review_persisted(self):
        self.frame(); alert_id = self.frame()["alert_id"]
        self.assertEqual(api.stats()["open_yolo_alerts"], 1)
        api.update_alert(alert_id, api.AlertUpdate(status="false_positive"))
        self.assertEqual(api.stats()["open_yolo_alerts"], 0)
        self.assertEqual(api.list_alerts("false_positive", 50)[0]["id"], alert_id)
        self.frame(confidence=0.95)
        self.assertEqual(api.list_alerts("false_positive", 50)[0]["confidence"], 0.8)

    def test_frozen_public_snapshot_cannot_confirm_an_alert(self):
        self.frame(content=b"same snapshot")
        result = self.frame(content=b"same snapshot")
        self.assertTrue(result["unchanged"])
        self.assertEqual(api.list_alerts(None, 50), [])

    def test_invalid_detections_rejected(self):
        with self.assertRaises(HTTPException) as error:
            self.frame(confidence=5)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(api.list_alerts(None, 50), [])

    def test_additive_migration_is_idempotent(self):
        api.init()
        self.assertEqual(len(api.list_cameras()), 2)

    def test_latest_per_camera_before_filter_and_limit(self):
        with api.db() as c:
            for camera, timestamp, status in [
                ("public-test", "2026-11-19T10:00:00+00:00", "open"),
                ("public-test", "2026-11-19T12:00:00+00:00", "confirmed"),
                # Imported later, but older: insertion order must not win.
                ("public-test", "2026-11-19T11:00:00+00:00", "open"),
                ("demo-fire", "2026-11-19T09:00:00+00:00", "open"),
                ("demo-fire", "2026-11-19T09:00:00+00:00", "false_positive"),
            ]:
                c.execute("""INSERT INTO alerts(camera_id, created_at, status, confidence, bbox)
                    VALUES (?, ?, ?, 0.8, '[0,0,1,1]')""", (camera, timestamp, status))
        latest = api.list_alerts(None, 50)
        self.assertEqual(len(latest), 2)
        self.assertEqual(latest[0]["status"], "confirmed")
        self.assertEqual(latest[1]["status"], "false_positive")
        self.assertEqual(api.list_alerts("open", 50), [])
        self.assertEqual(api.stats()["open_yolo_alerts"], 0)
        self.assertEqual(api.list_alerts(None, 1)[0]["id"], latest[0]["id"])
