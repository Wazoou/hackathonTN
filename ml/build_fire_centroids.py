"""Build display coordinates for all metropolitan communes from the local IGN cache."""
from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    assets = ROOT / 'dashboard/assets'
    source = ROOT / 'ifm_plus/data/raw/admin'
    for kind, filename, key in [('communes', 'fire_commune_centroids.csv', 'Code INSEE'),
                                ('departements', 'fire_department_centroids.csv', 'departement')]:
        frame = gpd.read_file(source / f'{kind}_france_metro.gpkg').to_crs(2154)
        centers = frame.geometry.centroid.to_crs(4326)
        data = pd.DataFrame({key: frame.code_insee, 'latitude': centers.y.round(6),
                             'longitude': centers.x.round(6)})
        if kind == 'communes':
            data['precision'] = 'commune'
            # Keep historical/overseas locations already bundled with the UI.
            previous = pd.read_csv(assets / filename, dtype={key: str})
            data = pd.concat([data, previous]).drop_duplicates(key, keep='first')
        data.sort_values(key).to_csv(assets / filename, index=False)
        print(filename, len(data))


if __name__ == '__main__':
    main()
