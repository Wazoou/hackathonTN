"""Régressions du passage Gironde → métropole, sans réseau."""
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ifmplus.config import Config, METRO_DEPARTEMENTS
from ifmplus.coverage import missing_bulk_inputs, missing_wfs_inputs, valid_bulk_dem, validate_coverage
from ifmplus.geoutils import DepartmentIndex
from ifmplus.bulk.regions import DEPT_REGION, regions_for
from ifmplus.bulk.layers import LayerError, read_bdtopo


class NationalScopeTests(unittest.TestCase):
    def test_default_covers_metropole_including_corsica(self):
        cfg = Config.load()
        self.assertEqual(cfg.departements, METRO_DEPARTEMENTS)
        self.assertEqual(len(set(cfg.departements)), 96)
        self.assertTrue({'2A', '2B', '33', '59', '75'} <= set(cfg.departements))
        self.assertNotIn('971', cfg.departements)
        self.assertEqual(cfg.scope_label, 'france_metro')
        self.assertEqual(cfg.nom_departement, '')
        self.assertEqual(cfg.bulk_features_path.name, 'dfci_2km_features_france.parquet')
        self.assertEqual(set(DEPT_REGION), set(cfg.departements))
        self.assertEqual(len(regions_for(cfg.departements)), 13)

    def test_explicit_local_scope_overrides_national_default(self):
        cfg = Config.load(departement='2a')
        self.assertFalse(cfg.france)
        self.assertEqual(cfg.departements, ('2A',))
        self.assertEqual(cfg.layer_path('forest').name, 'forest_2A.gpkg')
        self.assertEqual(cfg.tmja_path.name, 'tmja_2A.gpkg')

    def test_explicit_national_overrides_old_yaml_subset(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.yaml'
            path.write_text(yaml.safe_dump({'project': {'departements': ['33'], 'departement': '33', 'nom_departement': 'Gironde'}}))
            cfg = Config.load(path, perimetre='france_metro')
            self.assertEqual(cfg.departements, METRO_DEPARTEMENTS)
            self.assertEqual(cfg.nom_departement, '')
            self.assertEqual(Config.load(path, departement='59').departements, ('59',))

    def test_canonical_order_deduplicates_and_preserves_national_names(self):
        cfg = Config.load(departements=tuple(reversed(METRO_DEPARTEMENTS)) + ('33',))
        self.assertEqual(cfg.scope_label, 'france_metro')
        cfg = Config.load(departements='40,2b,33,2A,33')
        self.assertEqual(cfg.departements, ('2A', '2B', '33', '40'))
        self.assertNotEqual(cfg.bulk_features_path.name, 'dfci_2km_features_france.parquet')
        self.assertEqual(cfg.for_departement('2B').tmja_path, cfg.tmja_path)
        self.assertEqual(cfg.for_departement('2B').communes_scope_path, cfg.communes_scope_path)

    def test_invalid_and_conflicting_scopes_are_rejected(self):
        for kwargs in [{'departements': []}, {'departements': '971'}, {'departement': '20'},
                       {'departement': '33', 'departements': '40'},
                       {'departement': '33', 'perimetre': 'france_metro'},
                       {'departements': '33,40', 'perimetre': 'departement'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Config.load(**kwargs)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.load(departements='33,40,2A')
        self.assigned = pd.DataFrame({'cell_id': [1, 2, 3, 4], 'id_carreau_dfci': ['A','B','C','D'], 'dept': ['33','40','2A','33']})
        self.features = self.assigned.rename(columns={'dept': 'departement'})

    def test_complete_and_subset_coverage(self):
        self.assertTrue(validate_coverage(self.features, self.assigned, self.cfg)['complete'])
        cfg = Config.load(departements='33')
        self.assertEqual(validate_coverage(self.features[self.features.departement == '33'], self.assigned, cfg)['n_cells'], 2)

    def test_gironde_only_and_missing_corsica_rejected(self):
        for bad in [self.features.iloc[[0,3]], self.features.iloc[[0,1,3]]]:
            with self.assertRaisesRegex(ValueError, 'départementale'):
                validate_coverage(bad, self.assigned, self.cfg)

    def test_missing_cell_duplicate_and_wrong_assignment_rejected(self):
        wrong = self.features.copy()
        wrong.loc[[0,1], 'departement'] = ['40','33']
        for bad in [self.features.iloc[:3], pd.concat([self.features,self.features.iloc[:1]]), wrong]:
            with self.assertRaises(ValueError):
                validate_coverage(bad, self.assigned, self.cfg)

    def test_missing_layers_require_explicit_skip(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = replace(self.cfg, raw_dir=Path(d))
            missing = missing_bulk_inputs(cfg, 25, set())
            self.assertEqual(set(missing), set(cfg.departements))
            self.assertIn('forest', missing['2A'])
            self.assertEqual(missing_bulk_inputs(cfg, 25, {'forest','habitat','roads','rpg','relief','batiment'}), {})
            self.assertEqual(missing_wfs_inputs(cfg, 25, {'forest','habitat','roads','rpg','relief'}), {})
            path = cfg.bulk_layer('forest', '33')
            path.parent.mkdir(parents=True)
            path.write_bytes(b'')
            self.assertIn('forest', missing_bulk_inputs(cfg,25,set())['33'])

    def test_old_dem_cache_requires_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'dem_2A_25m.tif'
            path.write_bytes(b'old-raster')
            self.assertFalse(valid_bulk_dem(path))
            path.with_suffix('.json').write_text('{"mosaic_version": 1}')
            self.assertFalse(valid_bulk_dem(path))
            path.with_suffix('.json').write_text('{"mosaic_version": 2}')
            self.assertTrue(valid_bulk_dem(path))

    def test_coastal_and_border_cells_have_one_owner_sea_is_excluded(self):
        departments = gpd.GeoDataFrame({'code_insee':['33','40','2A']}, geometry=[box(0,0,2000,2000),box(2000,0,4000,2000),box(6000,0,8000,2000)],crs=2154)
        cells = gpd.GeoDataFrame({'id_carreau_dfci':['border','coast','corse','sea']},geometry=[box(1500,0,2500,1000),box(-1500,0,500,1000),box(6000,0,7000,1000),box(-5000,0,-4000,1000)],crs=2154)
        result = DepartmentIndex(departments, 'EPSG:2154').assign(cells)
        self.assertEqual(set(result.id_carreau_dfci), {'border','coast','corse'})
        self.assertFalse(result.id_carreau_dfci.duplicated().any())
        self.assertEqual(result.set_index('id_carreau_dfci').loc['corse','dept'], '2A')

    def test_missing_bdtopo_layer_is_not_assumed_empty(self):
        with patch('ifmplus.bulk.layers.find_layer', return_value=None):
            with self.assertRaises(LayerError):
                read_bdtopo(Path('missing.gpkg'), (0,0,1,1), 'EPSG:2154')


if __name__ == '__main__':
    unittest.main()
