import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from archive_data import merge_archives


class MergeArchivesTests(unittest.TestCase):
    def test_namespaces_preserve_sources_locations_and_annotations(self):
        manifests = {
            "pyro": {"departments": {"33": {"lat": 44, "lon": -1}}, "frames": [
                {"camera_id": "same", "department": "33", "timestamp": "2025-07-07T10:00:00",
                 "image": "images/pyro.jpg", "boxes": [[0.1, 0.2, 0.3, 0.4]], "split": "train"}]},
            "webcams": {"departments": {"33": {"lat": 44.5, "lon": -0.5, "name": "Webcam"}}, "frames": [
                {"camera_id": "same", "department": "33", "timestamp": "2025-07-07T10:00:00",
                 "image": "webcam-demo/web.jpg", "boxes": [], "annotated": False, "sequence_id": "same"}]},
        }
        before = copy.deepcopy(manifests)
        merged = merge_archives(manifests)
        self.assertEqual(manifests, before)
        self.assertEqual(set(merged["cameras"]), {"pyro:same", "webcams:same"})
        self.assertEqual(set(merged["points"]), {"pyro:33", "webcams:33"})
        self.assertEqual(merged["points"]["webcams:33"]["lat"], 44.5)
        for frame in merged["frames"]:
            original = manifests[frame["source_key"]]["frames"][0]
            for key in ("timestamp", "image", "boxes"):
                self.assertEqual(frame[key], original[key])
        self.assertEqual(merged["frames"][0]["split"], "train")
        self.assertFalse(merged["frames"][1]["annotated"])
        self.assertEqual(merged["frames"][1]["sequence_id"], "webcams:same")

    def test_single_available_source_still_loads(self):
        self.assertEqual(merge_archives({"pyro": {"departments": {}, "frames": []}})["frames"], [])

    def test_unmapped_frame_is_reported_instead_of_silently_dropped(self):
        with self.assertRaises(ValueError):
            merge_archives({"pyro": {"departments": {}, "frames": [{"camera_id": "x", "department": "33"}]}})
