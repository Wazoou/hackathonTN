import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from archive_data import active_sequence, frames_in_window, prepare_frames, sequences


class ArchiveTimeTests(unittest.TestCase):
    def setUp(self):
        self.frames = prepare_frames({"frames": [
            {"camera_id": "a", "timestamp": t}
            for t in ["2025-06-01T12:05:00", "2025-06-01T10:00:00", "2025-06-01T10:03:00"]]})

    def test_gap_does_not_create_fictitious_coverage(self):
        self.assertEqual([len(s) for s in sequences(self.frames)], [2, 1])
        self.assertEqual(active_sequence(self.frames, datetime(2025, 6, 1, 11)), [])

    def test_sequence_includes_exact_boundaries(self):
        self.assertEqual(len(active_sequence(self.frames, datetime(2025, 6, 1, 10))), 2)
        self.assertEqual(len(active_sequence(self.frames, datetime(2025, 6, 1, 10, 3))), 2)
        self.assertEqual(len(active_sequence(self.frames, datetime(2025, 6, 1, 12, 5))), 1)

    def test_source_times_are_preserved_and_sorted(self):
        self.assertEqual(self.frames[0]["time"], datetime(2025, 6, 1, 10))
        self.assertIsNone(self.frames[0]["time"].tzinfo)

    def test_window_does_not_infer_images_between_frames(self):
        self.assertEqual(frames_in_window(self.frames, datetime(2025, 6, 1, 10, 1, 30),
                                          timedelta(seconds=60)), [])

    def test_window_includes_both_boundaries(self):
        selected = frames_in_window(self.frames, datetime(2025, 6, 1, 10, 1, 30), timedelta(minutes=3))
        self.assertEqual(len(selected), 2)

    def test_window_size_changes_availability(self):
        cursor = datetime(2025, 6, 1, 11)
        self.assertEqual(len(frames_in_window(self.frames, cursor, timedelta(minutes=15))), 0)
        self.assertEqual(len(frames_in_window(self.frames, cursor, timedelta(hours=3))), 3)

    def test_curated_episode_replays_sparse_images_without_inventing_coverage(self):
        frames = [{**f, "sequence_id": "episode-a"} for f in self.frames]
        self.assertEqual([len(s) for s in sequences(frames)], [3])
        self.assertEqual(frames_in_window(frames, datetime(2025, 6, 1, 11), timedelta(minutes=5)), [])
        frames[-1]["sequence_id"] = "episode-b"
        self.assertEqual([len(s) for s in sequences(frames)], [2, 1])


if __name__ == "__main__":
    unittest.main()
