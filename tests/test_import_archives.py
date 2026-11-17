import importlib.util
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

spec = importlib.util.spec_from_file_location("import_archives", Path(__file__).resolve().parents[1] / "ml/import_archives.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImportArchiveTests(unittest.TestCase):
    def test_all_shards_keep_split_and_report_exclusions(self):
        def row(partner, camera, name):
            return {"partner": partner, "camera": camera, "image_name": name,
                    "date": "2025-06-01T12-00-00", "annotations": "0 0.5 0.5 0.2 0.4",
                    "image": {"bytes": b"fixture"}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            train1, train2, val = [root / name for name in ["train-0.parquet", "train-1.parquet", "val.parquet"]]
            pq.write_table(pa.Table.from_pylist([row("sdis-07", "brison-110", "same.jpg")]), train1)
            pq.write_table(pa.Table.from_pylist([row("engie", "salaunes-1-0", "engie.jpg"),
                                                row("biobio", "florida-180", "foreign.jpg")]), train2)
            pq.write_table(pa.Table.from_pylist([row("sdis-07", "brison-110", "same.jpg")]), val)
            manifest = module.import_archives([("train", train1), ("train", train2), ("val", val)],
                                             root / "out", {"07": {}, "33": {}}, "pinned-revision")
            self.assertEqual(manifest["source_rows"], 4)
            self.assertEqual(manifest["splits"], {"train": 2, "val": 1})
            self.assertEqual(manifest["excluded_by_partner"], {"biobio": 1})
            self.assertEqual(len({f["image"] for f in manifest["frames"]}), 3)
            self.assertTrue(all((root / "out" / f["image"]).exists() for f in manifest["frames"]))
            self.assertEqual(manifest["frames"][0]["boxes"], [[0.4, 0.3, 0.6, 0.7]])
            self.assertEqual(len(manifest["parquets"]), 3)

    def test_unknown_camera_is_not_assigned_to_france(self):
        self.assertIsNone(module.department_for("engie", "unknown"))
        self.assertIsNone(module.department_for("ohiggins", "mostazal-1"))
        self.assertEqual(module.department_for("sdis-2a", "camera"), "2A")


if __name__ == "__main__":
    unittest.main()
