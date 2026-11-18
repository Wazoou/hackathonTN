"""Export lightweight display boundaries from the national IGN cache.

Run with ifm_plus/.venv/bin/python ml/build_department_boundaries.py.
Only this display overlay is simplified; analytical grid geometry is untouched.
"""
import json
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]


def round_coordinates(coords):
    if isinstance(coords, (int, float)):
        return round(coords, 5)
    return [round_coordinates(c) for c in coords]


def main():
    source = ROOT / 'ifm_plus/data/raw/admin/departements_france_metro.gpkg'
    frame = gpd.read_file(source)[['code_insee', 'nom_officiel', 'geometry']]
    frame = frame.rename(columns={'code_insee': 'code', 'nom_officiel': 'name'}).sort_values('code')
    assert len(frame) == 96 and frame.code.nunique() == 96
    frame = frame.to_crs(2154)
    frame.geometry = frame.geometry.simplify(50, preserve_topology=True)
    data = json.loads(frame.to_crs(4326).to_json(drop_id=True))
    for feature in data['features']:
        geometry = feature['geometry']
        geometry['coordinates'] = round_coordinates(geometry['coordinates'])
    data['source'] = {
        'name': 'IGN ADMIN EXPRESS COG CARTO', 'url': 'https://data.geopf.fr/wfs/ows',
        'layer': 'ADMINEXPRESS-COG-CARTO.LATEST:departement', 'license': 'Licence Ouverte 2.0',
        'simplification_m': 50, 'coordinate_decimals': 5,
        'purpose': 'Contours d’affichage uniquement ; mailles et indicateurs de risque inchangés.',
    }
    target = ROOT / 'dashboard/risk_component/department_boundaries.geojson'
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(frame)} départements : {target.stat().st_size / 1e6:.2f} Mo')


if __name__ == '__main__':
    main()
