#!/usr/bin/env python
"""Rapport de couverture locale et, sur demande, audit du catalogue national IGN."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ifmplus.config import Config
from ifmplus.coverage import missing_bulk_inputs, missing_wfs_inputs, validate_coverage


def catalog_report(cfg):
    from ifmplus.bulk.geopf import GeoPlateformeClient
    from ifmplus.bulk.catalog import select_bdforet, select_bdtopo, select_rpg
    from ifmplus.bulk.regions import regions_for
    client = GeoPlateformeClient()
    snapshots = {product: client.subresources(product, fmt=fmt)
                 for product, fmt in [('BDFORET','SHP'), ('BDTOPO','GPKG'), ('RPG','GPKG')]}

    class CatalogSnapshot:
        def subresources(self, resource, zone=None, fmt=None):
            return [s for s in snapshots[resource] if (zone is None or s.zone == zone)
                    and (fmt is None or s.format == fmt)]

    snapshot = CatalogSnapshot()
    selectors = {
        'forest': (cfg.departements, lambda code: select_bdforet(snapshot, code, version=cfg.bulk.get('bdforet', {}).get('version','2-0'))),
        'bdtopo': (cfg.departements, lambda code: select_bdtopo(snapshot, code, edition=cfg.bulk.get('bdtopo', {}).get('edition','latest'))),
        'rpg': (regions_for(cfg.departements), lambda code: select_rpg(snapshot, code,
            year=cfg.bulk.get('rpg', {}).get('year',2025),
            allow_national_fallback=cfg.bulk.get('rpg', {}).get('allow_national_fallback',False))),
    }
    result = {}
    for layer, (codes, select) in selectors.items():
        available, absent = {}, {}
        for code in codes:
            try:
                selected = select(code)
                available[code] = {'archive': selected.name, 'catalog_url': selected.resource_url}
            except Exception as exc:
                absent[code] = str(exc)
        result[layer] = {'available': available, 'missing': absent, 'expected': len(codes)}
    folder = cfg.raw('catalog')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'national_catalog.json').write_text(json.dumps({k:[asdict(s) for s in v] for k,v in snapshots.items()},indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--catalog', action='store_true', help='Vérifier les catalogues IGN en ligne, sans télécharger les archives.')
    parser.add_argument('--require-complete', action='store_true', help='Code retour non nul si les données statiques bulk ne sont pas complètes.')
    args = parser.parse_args()
    cfg = Config.load(args.config)
    cfg.ensure_dirs()
    base = {'dfci': cfg.dfci_path, 'departements': cfg.departements_france_path if cfg.france else cfg.dept_path,
            'communes': cfg.communes_scope_path, 'tmja': cfg.tmja_path}
    missing = missing_bulk_inputs(cfg, cfg.resolution_m, set())
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'scope': cfg.scope_label,
              'expected_departments': list(cfg.departements),
              'base_files_present': {k: p.is_file() and p.stat().st_size > 0 for k,p in base.items()},
              'missing_bulk_by_department': missing,
              'missing_wfs_by_department': missing_wfs_inputs(cfg, cfg.resolution_m, set()),
              'bulk_layer_files_present': {k: sum(k not in missing.get(d,[]) for d in cfg.departements)
                                          for k in ('forest','habitat','roads','batiment','rpg','relief')},
              'weather_file_present': cfg.raw('weather', f'cems_fire_historical_{cfg.scope_label}.nc').exists(),
              'firms_file_present': cfg.raw('firms', f'firms_{cfg.scope_label}.csv').exists(),
              'notes': ['La présence des fichiers ne valide pas leur couverture spatiale ou temporelle.',
                        'TMJA : réseau routier national uniquement, sans comptages sur toutes les routes.',
                        'FIRMS : le fetcher existant ne télécharge que la dernière fenêtre day_range de la période.',
                        'BDIFF : export manuel requis. La météo EWDS requiert un accès utilisateur.',
                        'Les scripts de score quotidien ne sont pas encore implémentés.']}
    grid = cfg.processed_dir / f'dfci_2km_grid_{cfg.scope_label}.parquet'
    report['grid_file'] = str(grid) if grid.exists() else None
    report['features_file'] = str(cfg.bulk_features_path) if cfg.bulk_features_path.exists() else None
    report['features_coverage'] = None
    if cfg.bulk_features_path.exists() and cfg.dfci_cells_cache_path.exists():
        import geopandas as gpd
        import pandas as pd
        try:
            report['features_coverage'] = validate_coverage(pd.read_parquet(cfg.bulk_features_path),
                gpd.read_file(cfg.dfci_cells_cache_path, engine='pyogrio'), cfg)
        except ValueError as exc:
            report['features_coverage'] = {'complete': False, 'error': str(exc)}
    if args.catalog:
        report['catalog'] = catalog_report(cfg)
    report['features_metadata'] = None
    if cfg.bulk_features_metadata_path.exists():
        report['features_metadata'] = json.loads(cfg.bulk_features_metadata_path.read_text(encoding='utf-8'))
    report['static_complete'] = (all(report['base_files_present'].values()) and not missing
                                and bool(report['features_coverage'] and report['features_coverage']['complete'])
                                and bool(report['features_metadata'])
                                and not report['features_metadata'].get('skipped_layers'))
    output = cfg.processed_dir / f'coverage_{cfg.scope_label}.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Périmètre : {cfg.scope_label}, {len(cfg.departements)} départements")
    print('Fichiers bulk présents :', report['bulk_layer_files_present'])
    print('Table statique complète :', report['static_complete'])
    if args.catalog:
        for layer, state in report['catalog'].items():
            print(f"Catalogue {layer} : {len(state['available'])}/{state['expected']} zones disponibles")
    print('Rapport :', output)
    return int(args.require_complete and not report['static_complete'])


if __name__ == '__main__':
    raise SystemExit(main())
