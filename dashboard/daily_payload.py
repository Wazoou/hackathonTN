"""Compact lossless weather bundle: one load, identical daily calculations in the browser."""
import base64
import gzip
import hashlib
import json
import struct

import numpy as np

from daily_data import DAY_BOUNDS, DAY_COLORS, DAY_LABELS


def build_daily_payload(d):
    dates = d['dates']
    start = int(dates.searchsorted('2006-01-01'))
    weather = np.asarray(d['z'][start:], dtype='<f4')
    terrain = np.asarray(d['commune_terrain'], dtype='<f8')
    coefficient = d['model']['coefficients']['log_terrain']
    expected = np.empty(len(weather), dtype='<f8')
    # This small precomputed series keeps the comparison chart instant while dragging.
    for first in range(0, len(weather), 32):
        z = weather[first:first + 32, d['commune_station']] + coefficient * terrain
        expected[first:first + 32] = np.nansum(1 / (1 + np.exp(-z)), axis=1)
    fires = {}
    for day, frame in d['fires'].groupby('date', sort=False):
        fires[day.strftime('%Y-%m-%d')] = [
            [round(float(row.lon), 4), round(float(row.lat), 4), str(row.dept)]
            for row in frame.itertuples()]
    header = {'format': 1, 'dates': dates[start:].strftime('%Y-%m-%d').tolist(),
              'stations': weather.shape[1], 'coefficient': coefficient,
              'bdiff_end': d['bdiff_end'].strftime('%Y-%m-%d'), 'fires': fires,
              'legend': [[name, str(DAY_BOUNDS[i]).replace('.', ','),
                          str(DAY_BOUNDS[i + 1]).replace('.', ',') if i < 4 else None, list(rgb)]
                         for i, (name, rgb) in enumerate(zip(DAY_LABELS, DAY_COLORS))],
              'arrays': {}, 'meta': d['meta']}
    arrays = {'z': weather, 'fwi': np.asarray(d['fwi'][start:], dtype='<f4'),
              'commune_station': np.asarray(d['commune_station'], dtype='<i4'),
              'commune_terrain': terrain, 'cell_commune': np.asarray(d['cell_commune'], dtype='<i4'),
              'cell_share': np.asarray(d['cell_share'], dtype='<f8'), 'expected': expected}
    body = bytearray()
    for name, array in arrays.items():
        body.extend(b'\0' * (-len(body) % 8))
        header['arrays'][name] = {'offset': len(body), 'length': array.size, 'dtype': array.dtype.str}
        body.extend(array.tobytes())
    text = json.dumps(header, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    text += b' ' * (-(4 + len(text)) % 8)
    raw = struct.pack('<I', len(text)) + text + body
    packed = gzip.compress(raw, compresslevel=6, mtime=0)
    return {'version': hashlib.sha256(raw).hexdigest(),
            'payload': base64.b64encode(packed).decode(), 'compressed_bytes': len(packed)}
