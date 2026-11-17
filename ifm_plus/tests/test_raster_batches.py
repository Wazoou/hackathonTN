import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifmplus.raster import AnalysisGrid


class RasterBatchTests(unittest.TestCase):
    def test_batches_preserve_overlap_order_fill_and_touch_rules(self):
        grid = AnalysisGrid.from_bounds((0, 0, 10, 10), 1, "EPSG:2154")
        frame = gpd.GeoDataFrame(
            {"value": [2, 7, 0, 4, 8]},
            geometry=[box(1, 1, 7, 7), box(3, 3, 9, 9), box(4, 4, 6, 6),
                      None, box(0.2, 0.2, 1.2, 1.2)], crs=grid.crs)
        for touched in (False, True):
            for column in (None, "value"):
                with self.subTest(touched=touched, column=column):
                    shapes = [(g, v if column else 1) for g, v in zip(frame.geometry, frame.value)
                              if g is not None]
                    expected = rasterize(shapes, out_shape=grid.shape, transform=grid.transform,
                                         fill=3, dtype="int32", all_touched=touched)
                    with patch("ifmplus.raster.RASTER_BATCH_SIZE", 2), \
                         patch("ifmplus.raster.rio_rasterize", wraps=rasterize) as burn:
                        actual = grid.rasterize(frame, values=column, fill=3, all_touched=touched)
                    np.testing.assert_array_equal(actual, expected)
                    self.assertEqual(burn.call_count, 2)
                    self.assertTrue(all(len(c.args[0]) <= 2 for c in burn.call_args_list))

    def test_empty_input_keeps_background(self):
        grid = AnalysisGrid.from_bounds((0, 0, 2, 2), 1, "EPSG:2154")
        frame = gpd.GeoDataFrame(geometry=[], crs=grid.crs)
        np.testing.assert_array_equal(grid.rasterize(frame, fill=9), np.full((2, 2), 9))


if __name__ == "__main__":
    unittest.main()
