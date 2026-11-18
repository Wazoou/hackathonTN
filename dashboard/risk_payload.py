"""Lossless, versioned payload for the persistent risk map (no UI dependencies)."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

from risk_data import CLASSES, LAYERS, combine, color, class_ranges, to_scale


def file_signature(folder):
    files = sorted(Path(folder).glob('risque_statique_*.geojson'))
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size,
                  p.with_suffix('.json').stat().st_mtime_ns if p.with_suffix('.json').exists() else 0)
                 for p in files)


def build_payload(signature):
    features, metadata, departments = [], {}, []
    for filename, *_ in signature:
        path = Path(filename)
        dept = path.stem.removeprefix('risque_statique_')
        part = json.loads(path.read_text())['features']
        if any(f['properties']['dept'] != dept for f in part):
            raise ValueError(f'Département incohérent : {filename}')
        features.extend(part)
        departments.append(dept)
        meta = path.with_suffix('.json')
        metadata[dept] = json.loads(meta.read_text()) if meta.exists() else {}
    ids = [f['properties']['id'] for f in features]
    if len(set(ids)) != len(ids):
        raise ValueError('Mailles dupliquées dans les fichiers de risque')
    # Same Python rounding as the existing model, for every possible slider step.
    # Integers in tenths preserve all published score precision, with no JS rounding drift.
    terms = [(f['properties']['s_combustible'], f['properties']['s_humain']) for f in features]
    scores = {'multiplicatif': [int(round(combine(c, h) * 10)) for c, h in terms]}
    for step in range(21):
        scores[f'additif:{step}'] = [int(round(combine(c, h, 'additif', step / 20) * 10)) for c, h in terms]
    has_proba = bool(features) and all(f['properties'].get('p_feu') is not None for f in features)
    layers = {k: v for k, v in LAYERS.items() if k != 'p_feu' or has_proba}
    data = {'features': features, 'scores': scores, 'departments': departments,
            'department_names': json.loads((Path(__file__).parent / 'risk_component/departments.json').read_text()),
            'metadata': metadata, 'layers': layers,
            'classes': CLASSES, 'colors': [color(i / 10, 255) for i in range(1001)],
            'probability_colors': [color(to_scale(f['properties']['p_feu'], 'p_feu'), 255)
                                   for f in features] if has_proba else [],
            'legends': {k: class_ranges(k) for k in layers}}
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    return {'version': hashlib.sha256(raw).hexdigest(),
            'payload': base64.b64encode(compressed).decode(), 'count': len(features),
            'departments': len(departments), 'raw_bytes': len(raw), 'compressed_bytes': len(compressed),
            'ids': ids}  # ordre des mailles dans le payload (non envoyé au navigateur)
