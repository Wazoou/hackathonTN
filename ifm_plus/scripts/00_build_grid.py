#!/usr/bin/env python
"""Exporte le maillage métropolitain sans inventer de score de risque.

Prérequis : python scripts/01_download_data.py --layers dfci,admin
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifmplus.config import Config
from ifmplus.coverage import validate_coverage
from ifmplus.geoutils import assign_dfci_cells
from ifmplus.log import setup_logging


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--departements", default="all")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    setup_logging(False)
    cfg = Config.load(args.config, departements=args.departements)
    cfg.ensure_dirs()
    assigned = assign_dfci_cells(cfg, force=args.force)
    cells = assigned[assigned["dept"].isin(cfg.departements)].copy()
    cells = cells.rename(columns={"dept": "departement"})
    centres = cells.geometry.centroid
    cells["x_centroid"], cells["y_centroid"] = centres.x, centres.y
    wgs84 = centres.to_crs(cfg.crs_wgs84)
    cells["lon"], cells["lat"] = wgs84.x, wgs84.y
    cells["area_ha"] = cells.geometry.area / 10_000
    report = validate_coverage(cells, assigned, cfg)
    output = cfg.processed_dir / f"dfci_2km_grid_{cfg.scope_label}.parquet"
    temporary = output.with_suffix(".part.parquet")
    cells.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(output)
    report.update({"scope": cfg.scope_label, "crs": cfg.crs, "output": str(output),
                   "kind": "grid_only", "risk_score_available": False,
                   "sources": [str(cfg.dfci_path), str(cfg.departements_france_path)]})
    output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(cells):,} carreaux · {report['n_departements']} départements → {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
