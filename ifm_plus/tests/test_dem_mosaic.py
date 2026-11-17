"""La mosaïque nationale doit lire toutes les tuiles, y compris au nord de 50°."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ifmplus.bulk.dem import build_vrt, probe_tiles


class DemMosaicTests(unittest.TestCase):
    def test_two_tiles_different_widths_are_in_the_same_band(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {}
            for index, (width, value) in enumerate([(8, 100), (4, 200)]):
                path = root / f'{index}.tif'
                # Deux tuiles de même emprise, avec des pas longitudinaux différents.
                transform = from_origin(2 + index * 8 / 3600, 51, (8 / 3600) / width, 1 / 3600)
                with rasterio.open(path, 'w', driver='GTiff', width=width, height=8, count=1,
                                   dtype='float32', crs=4326, transform=transform, nodata=-9999) as target:
                    target.write(np.full((8,width),value,dtype='float32'), 1)
                sources[(50,index)] = path
            vrt = build_vrt(list(sources), root / 'mosaic.vrt', source_paths=sources)
            with rasterio.open(vrt) as src:
                self.assertEqual(src.count, 1)
                data = src.read(1)
                self.assertEqual(data.shape, (8,16))
                np.testing.assert_allclose(data[:,:8], 100)
                np.testing.assert_allclose(data[:,8:], 200)

    def test_network_error_is_not_cached_as_missing_tile(self):
        import requests
        with tempfile.TemporaryDirectory() as directory, patch('ifmplus.bulk.dem.requests.Session') as session:
            session.return_value.head.side_effect = requests.Timeout('network')
            path = Path(directory) / 'tiles.json'
            with self.assertRaises(RuntimeError):
                probe_tiles([(50,2)],path)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
