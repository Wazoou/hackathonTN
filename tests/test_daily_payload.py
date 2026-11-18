import gzip
import base64
import json
import struct
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from daily_payload import build_daily_payload


class DailyPayloadTests(unittest.TestCase):
    def test_lossless_arrays_missing_weather_and_full_date_range(self):
        d = {'dates': pd.date_range('2005-12-31', periods=3),
             'z': np.array([[1, 2], [np.nan, 0], [2, 3]], dtype=np.float32),
             'fwi': np.array([[3, 4], [np.nan, 7], [9, 10]], dtype=np.float32),
             'commune_station': np.array([1, 0]), 'commune_terrain': np.array([.123456789123, 0]),
             'cell_commune': np.array([1, -1, 0]), 'cell_share': np.array([.3, 0, .7000000123]),
             'model': {'coefficients': {'log_terrain': .9}},
             'bdiff_end': pd.Timestamp('2006-01-01'), 'meta': {},
             'fires': pd.DataFrame([{'date': pd.Timestamp('2006-01-01'), 'lon': 1.234567, 'lat': 45., 'dept': '2A'}])}
        packed = build_daily_payload(d)
        raw = gzip.decompress(base64.b64decode(packed['payload']))
        size = struct.unpack('<I', raw[:4])[0]
        header = json.loads(raw[4:4 + size])
        self.assertEqual((size + 4) % 8, 0)
        self.assertEqual(header['dates'], ['2006-01-01', '2006-01-02'])
        for name in ['z', 'fwi', 'commune_station', 'commune_terrain', 'cell_commune', 'cell_share']:
            spec = header['arrays'][name]
            actual = np.frombuffer(raw, dtype=spec['dtype'], count=spec['length'], offset=4 + size + spec['offset'])
            expected = d[name][1:] if name in ['z', 'fwi'] else d[name]
            np.testing.assert_array_equal(actual, expected.ravel())
        spec = header['arrays']['expected']
        actual = np.frombuffer(raw, dtype=spec['dtype'], count=spec['length'], offset=4 + size + spec['offset'])
        self.assertAlmostEqual(actual[0], 1 / (1 + np.exp(-.9 * .123456789123)))
        self.assertEqual(header['fires']['2006-01-01'], [[1.2346, 45., '2A']])
        self.assertEqual(packed['version'], build_daily_payload(d)['version'])


if __name__ == '__main__':
    unittest.main()
