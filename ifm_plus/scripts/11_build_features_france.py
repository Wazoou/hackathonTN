#!/usr/bin/env python
"""11 — Features DFCI à partir des couches bulk, France métropolitaine.

Pendant de ``02_build_static_features.py`` pour le track « bulk » : il lit
les GeoParquet produits par ``10_bulk_download.py`` (BD TOPO, BD Forêt V2,
RPG, MNT Copernicus) et réutilise exactement les mêmes fonctions de calcul
de features (forêt, relief, WUI, bâti, routes/TMJA, agriculture).

Deux modes :

- **un département** (défaut) : grille locale, sortie
  ``dfci_2km_features_<dept>.parquet`` ;
- **France métropolitaine** (``--perimetre france_metro``) : boucle
  département par département (grille 25 m), cache par département, puis
  assemblage national et voisinage 3×3 à l'échelle nationale.

La table finale s'appelle ``dfci_2km_features_france.parquet`` pour le
périmètre complet (96 départements) ; un sous-ensemble garde un suffixe
explicite (``dfci_2km_features_33-40.parquet``) pour ne jamais écraser la
sortie nationale.

Par défaut, les couches bulk manquantes sont téléchargées à la demande
(``--no-fetch`` pour l'interdire) : le script peut donc être relancé après
une interruption sans repasser par une étape manuelle.

Exemples
--------
    python scripts/11_build_features_france.py --departements 33
    python scripts/11_build_features_france.py --departements 33 --skip rpg,dem
    python scripts/11_build_features_france.py --perimetre france_metro --workers 2
    python scripts/11_build_features_france.py --perimetre france_metro --gpkg
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifmplus.bulk import ensure_bulk  # noqa: E402
from ifmplus.bulk.build import (  # noqa: E402
    FRACTION_COLUMNS,
    build_department,
)
from ifmplus.config import Config  # noqa: E402
from ifmplus.features import (  # noqa: E402
    NEIGHBOURHOOD_SOURCES,
    STATIC_FEATURES,
    add_neighbourhood_features,
    compute_commune_features,
)
from ifmplus.geoutils import (  # noqa: E402
    DepartmentIndex,
    assign_dfci_cells,
    build_cells_for_department,
    build_dfci_cells,
    read_bbox,
)
from ifmplus.log import setup_logging  # noqa: E402

log = logging.getLogger("ifmplus")

SKIPPABLE = {"forest", "relief", "habitat", "batiment", "roads", "rpg"}

CONTEXT_COLUMNS = {
    "area_ha",
    "frac_dans_dept",
    "x_centroid",
    "y_centroid",
    "lon",
    "lat",
}

IDENTIFIER_COLUMNS = {
    "cell_id",
    "id_carreau_dfci",
    "code_insee",
    "nom_commune",
    "departement",
}


# ----------------------------------------------------------------------
# Arguments
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Construction de la table analytique DFCI 2 km à partir des "
            "couches bulk (GeoParquet) — France métropolitaine."
        )
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--departement", default=None)
    parser.add_argument(
        "--perimetre",
        choices=("departement", "france_metro"),
        default=None,
        help="Périmètre du traitement (défaut : config.yaml).",
    )
    parser.add_argument(
        "--departements",
        default=None,
        help="Sous-ensemble en mode France : '33,40' ou 'all'.",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=None,
        help="Résolution de la grille raster d'analyse (m). Défaut : config.",
    )
    parser.add_argument(
        "--skip",
        default="",
        help=(
            "Couches à ignorer (features à NaN), séparées par des virgules : "
            "forest, relief (alias dem), habitat, batiment, roads, rpg."
        ),
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="N'effectue aucun téléchargement bulk : utilise l'existant.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Téléchargements simultanés si récupération à la demande.",
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Conserve les archives .7z lors d'une récupération à la demande.",
    )
    parser.add_argument(
        "--no-dfci-wfs",
        action="store_true",
        help="Désactive l'enrichissement WFS des pistes DFCI.",
    )
    parser.add_argument(
        "--no-batiment",
        action="store_true",
        help="N'utilise pas la couche bâti (ajoute 'batiment' aux skips).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalcule aussi les départements déjà présents dans le cache.",
    )
    parser.add_argument(
        "--refresh-cells",
        action="store_true",
        help="Refait l'affectation nationale des carreaux DFCI aux départements.",
    )
    parser.add_argument(
        "--gpkg",
        action="store_true",
        help="Écrit aussi le GPKG (volumineux, géométries DFCI).",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


# ----------------------------------------------------------------------
# Entrées et empreinte
# ----------------------------------------------------------------------
def _required_bulk(skip: set[str]) -> dict[str, tuple[str, ...]]:
    """Couches bulk nécessaires et fichiers attendus par couche."""
    needs: dict[str, tuple[str, ...]] = {}
    if "forest" not in skip:
        needs["bdf"] = ("forest",)
    bdtopo = tuple(
        layer
        for layer in ("roads", "habitat", "batiment")
        if layer not in skip
    )
    if bdtopo:
        needs["bdtopo"] = bdtopo
    if "rpg" not in skip:
        needs["rpg"] = ("rpg",)
    if "relief" not in skip:
        needs["dem"] = ()
    return needs


def _bulk_path(cfg: Config, layer: str, resolution: float) -> Path:
    if layer == "dem":
        return cfg.bulk_raw("dem", f"dem_{cfg.departement}_{int(resolution)}m.tif")
    return cfg.bulk_layer(layer, cfg.departement)


def _missing(cfg: Config, needs: dict[str, tuple[str, ...]], resolution: float) -> dict[str, list[str]]:
    """Départements pour lesquels au moins un fichier bulk manque."""
    missing: dict[str, list[str]] = {}
    for dept in cfg.departements:
        sub = cfg.for_departement(dept)
        for bulk_layer, outputs in needs.items():
            expected = outputs or ("dem",)
            if any(not _bulk_path(sub, layer, resolution).exists() for layer in expected):
                missing.setdefault(bulk_layer, []).append(dept)
    return missing


def _fetch_missing(
    cfg: Config,
    needs: dict[str, tuple[str, ...]],
    resolution: float,
    args: argparse.Namespace,
    include_batiment: bool,
    dfci_wfs: bool,
) -> None:
    missing = _missing(cfg, needs, resolution)
    if not missing:
        return
    workers = args.workers
    if workers is None:
        workers = int((cfg.bulk or {}).get("workers", 2))

    for layer, depts in missing.items():
        log.info(
            "Récupération à la demande — %s : %s département(s)",
            layer,
            len(depts),
        )
        summary = ensure_bulk(
            cfg,
            layers=(layer,),
            departements=tuple(depts),
            force=False,
            keep_raw=args.keep_raw,
            workers=max(1, min(int(workers), 4)),
            include_batiment=include_batiment,
            dfci_wfs=dfci_wfs,
            with_dem=layer == "dem",
        )
        for results in summary.values():
            for result in results:
                if result.status == "failed":
                    log.warning(
                        "  %s / %s non récupéré : %s",
                        result.layer,
                        result.scope,
                        result.detail,
                    )


def _fingerprint(cfg: Config, resolution: float, skip: set[str]) -> str:
    """Empreinte des entrées bulk : invalide le cache si un fichier change."""
    digest = hashlib.sha256()
    digest.update(
        f"v=bulk-1|res={resolution}|skip={','.join(sorted(skip))}".encode("utf-8")
    )
    for layer in ("forest", "roads", "habitat", "batiment", "rpg"):
        path = cfg.bulk_layer(layer, cfg.departement)
        if path.exists():
            stat = path.stat()
            digest.update(f"|{layer}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    dem = cfg.bulk_raw("dem", f"dem_{cfg.departement}_{int(resolution)}m.tif")
    if dem.exists():
        stat = dem.stat()
        digest.update(f"|dem:{stat.st_size}:{stat.st_mtime_ns}".encode())
    if cfg.tmja_path.exists():
        digest.update(f"|tmja:{cfg.tmja_path.stat().st_size}".encode())
    return digest.hexdigest()[:10]


def _check_inputs(cfg: Config) -> list[str]:
    required: list[tuple[str, Path]] = [("carroyage DFCI", cfg.dfci_path)]
    if cfg.france:
        required.append(("contours départementaux", cfg.departements_france_path))
    else:
        required.append(("contour du département", cfg.dept_path))
    required.append(("communes", cfg.communes_scope_path))
    required.append(("TMJA", cfg.tmja_path))

    missing = [(label, path) for label, path in required if not path.exists()]
    if missing:
        log.error("Entrées manquantes :")
        for label, path in missing:
            log.error("  - %s : %s", label, path)
        log.error(
            "Lancer d'abord : python scripts/01_download_data.py --layers admin,dfci,tmja"
        )
    return [label for label, _ in missing]


def _bulk_provenance(cfg: Config) -> dict[str, dict]:
    """Éditions et sources bulk lues dans les métadonnées de téléchargement."""
    provenance: dict[str, dict] = {}
    for layer, key in (
        ("bdf", "bdf"),
        ("bdtopo", "bdtopo"),
        ("rpg", "rpg"),
    ):
        meta = cfg.bulk_raw(key, f"{cfg.departement}.meta.json")
        if meta.exists():
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            provenance[key] = {
                "sub_resource": payload.get("sub_resource"),
                "edition": payload.get("edition"),
                "url": payload.get("url"),
            }
            if payload.get("dfci_source"):
                provenance[key]["dfci_source"] = payload["dfci_source"]
    dem = cfg.bulk_raw("dem", f"dem_{cfg.departement}_{int(cfg.resolution_m)}m.tif")
    if dem.exists():
        provenance["dem"] = {
            "source": "Copernicus DEM 30 m (COG ZSTD 25 m)",
            "file": str(dem),
        }
    return provenance


# ----------------------------------------------------------------------
# Contrôles qualité et métadonnées
# ----------------------------------------------------------------------
def _quality_report(features: pd.DataFrame, france: bool) -> dict:
    if features["id_carreau_dfci"].duplicated().any():
        raise RuntimeError("Identifiants DFCI dupliqués dans la table finale")
    if features["cell_id"].duplicated().any():
        raise RuntimeError("cell_id dupliqué dans la table finale")

    attribute_columns = [
        column for column in features.columns if column not in IDENTIFIER_COLUMNS
    ]
    missing = (
        features[attribute_columns]
        .isna()
        .mean()
        .sort_values(ascending=False)
    )
    qa = {
        "n_cells": int(len(features)),
        "n_features": len(attribute_columns),
        "n_features_hors_contexte": len(
            [column for column in attribute_columns if column not in CONTEXT_COLUMNS]
        ),
        "missing_rate": {
            key: round(float(value), 4)
            for key, value in missing.items()
            if value > 0
        },
        "foret_frac_moyenne": round(float(features["foret_frac"].mean()), 4)
        if "foret_frac" in features
        else None,
        "wui_frac_moyenne": round(float(features["wui_frac"].mean()), 4)
        if "wui_frac" in features
        else None,
        "pente_moyenne_deg": round(float(features["pente_moy_deg"].mean()), 2)
        if "pente_moy_deg" in features
        else None,
    }
    if france and "departement" in features.columns:
        counts = features.groupby("departement").size()
        qa["n_cells_par_departement"] = {
            "min": int(counts.min()),
            "max": int(counts.max()),
            "moyenne": round(float(counts.mean()), 1),
        }
    return qa


def _metadata(
    cfg: Config,
    features: pd.DataFrame,
    resolution: float,
    qa: dict,
    bbox,
    provenance: dict,
    skip: set[str],
    neighbourhood: str,
) -> dict:
    feature_columns = [
        column for column in features.columns if column not in IDENTIFIER_COLUMNS
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "track": "bulk",
        "perimetre": cfg.perimetre,
        "scope": cfg.scope_label,
        "departements": list(cfg.departements),
        "n_departements": len(cfg.departements),
        "nom_departement": cfg.nom_departement if not cfg.france else "",
        "crs": cfg.crs,
        "resolution_m": resolution,
        "bbox_2154": [round(v, 3) for v in bbox],
        "neighbourhood": neighbourhood,
        "skipped_layers": sorted(skip),
        "bulk_sources": provenance,
        "inputs": {
            "dfci": str(cfg.dfci_path),
            "admin": str(
                cfg.departements_france_path if cfg.france else cfg.dept_path
            ),
            "communes": str(cfg.communes_scope_path),
            "tmja": str(cfg.tmja_path),
            "bulk_dir": str(cfg.bulk_dir),
        },
        "qa": qa,
        "feature_catalog": {
            column: STATIC_FEATURES.get(
                column,
                {"famille": "autre", "source": "", "unite": "", "description": ""},
            )
            for column in feature_columns
        },
    }


def _write_outputs(
    cfg: Config,
    features: pd.DataFrame,
    resolution: float,
    qa: dict,
    bbox,
    provenance: dict,
    skip: set[str],
    *,
    neighbourhood: str,
    write_gpkg: bool,
    cells: gpd.GeoDataFrame | None,
) -> None:
    output = cfg.bulk_features_path
    output.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output, index=False, compression="zstd")
    log.info("-> %s (%s lignes, %s colonnes)", output, f"{len(features):,}", len(features.columns))

    if write_gpkg and cells is not None:
        gpkg = cfg.bulk_features_gpkg_path
        merged = cells.merge(features, on="cell_id", how="left", suffixes=("", "_f"))
        if gpkg.exists():
            gpkg.unlink()
        merged[["cell_id", "id_carreau_dfci", "geometry"] + [
            column for column in features.columns
            if column not in {"cell_id", "id_carreau_dfci"}
        ]].to_file(gpkg, layer="dfci_2km_features", driver="GPKG", engine="pyogrio")
        log.info("-> %s", gpkg)

    metadata = _metadata(
        cfg,
        features,
        resolution,
        qa,
        bbox,
        provenance,
        skip,
        neighbourhood,
    )
    metadata_path = cfg.bulk_features_metadata_path
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("-> %s", metadata_path)


# ----------------------------------------------------------------------
# Périmètre France
# ----------------------------------------------------------------------
def run_france(
    cfg: Config,
    args: argparse.Namespace,
    resolution: float,
    skip: set[str],
) -> int:
    departements = cfg.departements
    log.info(
        "Features bulk — France métropolitaine : %s département(s), grille %.0f m",
        len(departements),
        resolution,
    )

    assigned = assign_dfci_cells(cfg, force=args.refresh_cells)
    index = DepartmentIndex.from_file(cfg.departements_france_path, cfg.crs)

    commune_all = None
    if cfg.communes_scope_path.exists():
        communes = gpd.read_file(cfg.communes_scope_path, engine="pyogrio")
        scope_cells = assigned[assigned["dept"].isin(departements)]
        log.info(
            "Rattachement des %s carreaux du périmètre aux communes…",
            f"{len(scope_cells):,}",
        )
        commune_all = compute_commune_features(scope_cells, communes)
        del communes

    frames: list[pd.DataFrame] = []
    cells_parts: list[gpd.GeoDataFrame] = []
    built = resumed = failed = 0
    started = time.monotonic()

    for position, dept in enumerate(departements, start=1):
        sub = cfg.for_departement(dept)
        cache = sub.bulk_dept_cache_path(
            resolution,
            tuple(sorted(skip)),
            _fingerprint(sub, resolution, skip),
        )
        prefix = f"[{position}/{len(departements)}] {dept}"

        cells: gpd.GeoDataFrame | None = None
        if cache.exists() and not args.force:
            log.info("%s — cache : %s", prefix, cache.name)
            features = pd.read_parquet(cache)
            resumed += 1
        else:
            log.info("%s — construction", prefix)
            try:
                cells = build_cells_for_department(sub, assigned, index)
                commune_part = (
                    commune_all.loc[commune_all["cell_id"].isin(cells["cell_id"])]
                    if commune_all is not None
                    else None
                )
                features = build_department(
                    sub,
                    cells,
                    resolution,
                    skip,
                    commune_features=commune_part,
                    neighbourhood=False,
                )
            except Exception as exc:  # noqa: BLE001 — un département n'arrête pas le lot
                log.error("%s — ÉCHEC : %s", prefix, exc)
                failed += 1
                continue

            cache.parent.mkdir(parents=True, exist_ok=True)
            features.to_parquet(cache, index=False, compression="zstd")
            built += 1

        if args.gpkg and cells is None:
            cells = build_cells_for_department(sub, assigned, index)
        if cells is not None:
            cells_parts.append(cells[["cell_id", "id_carreau_dfci", "geometry"]])
        frames.append(features)

        elapsed = time.monotonic() - started
        log.info(
            "%s — %s carreaux (%.1f min écoulées)",
            prefix,
            f"{len(features):,}",
            elapsed / 60.0,
        )

    if not frames:
        log.error("Aucun département construit : rien à assembler.")
        return 1

    log.info(
        "Départements : %s construits, %s repris du cache, %s en échec",
        built,
        resumed,
        failed,
    )

    features = pd.concat(frames, ignore_index=True)
    features = features.drop_duplicates(subset="cell_id", keep="first")

    coords = features[["x_centroid", "y_centroid"]]
    log.info("Voisinage 3×3 national sur %s carreaux…", f"{len(features):,}")
    features = add_neighbourhood_features(
        features, coords, tuple(NEIGHBOURHOOD_SOURCES)
    )

    counts = features.groupby("departement").size()
    log.info(
        "Table nationale : %s carreaux, %s départements (%s à %s carreaux/dept)",
        f"{len(features):,}",
        len(counts),
        int(counts.min()),
        int(counts.max()),
    )

    qa = _quality_report(features, france=True)
    log.info(
        "Contrôles : %s carreaux, %s features, forêt moyenne %.1f %%",
        qa["n_cells"],
        qa["n_features"],
        100 * (qa["foret_frac_moyenne"] or 0.0),
    )
    if qa["missing_rate"]:
        log.warning(
            "Taux de valeurs manquantes les plus élevés : %s",
            list(qa["missing_rate"].items())[:5],
        )

    cells_all = None
    if args.gpkg:
        cells_all = gpd.GeoDataFrame(
            pd.concat(cells_parts, ignore_index=True),
            geometry="geometry",
            crs=cfg.crs,
        )
    bbox = read_bbox(cfg.for_departement(departements[0]))
    scope_bbox = (
        json.loads(cfg.scope_bbox_path.read_text(encoding="utf-8"))["bbox_2154"]
        if cfg.scope_bbox_path.exists()
        else bbox
    )
    _write_outputs(
        cfg,
        features,
        resolution,
        qa,
        scope_bbox,
        _bulk_provenance(cfg),
        skip,
        neighbourhood="3×3 national",
        write_gpkg=args.gpkg,
        cells=cells_all,
    )
    if failed:
        log.warning("%s département(s) en échec : relancer le script pour reprendre.", failed)
        return 1
    return 0


# ----------------------------------------------------------------------
# Périmètre départemental
# ----------------------------------------------------------------------
def run_departement(
    cfg: Config,
    args: argparse.Namespace,
    resolution: float,
    skip: set[str],
) -> int:
    log.info(
        "Features bulk — département %s, grille %.0f m",
        cfg.departement,
        resolution,
    )
    cells = build_dfci_cells(cfg)
    features = build_department(
        cfg,
        cells,
        resolution,
        skip,
        commune_features=None,
        neighbourhood=True,
    )
    qa = _quality_report(features, france=False)
    log.info(
        "Contrôles : %s carreaux, %s features, forêt moyenne %.1f %%",
        qa["n_cells"],
        qa["n_features"],
        100 * (qa["foret_frac_moyenne"] or 0.0),
    )
    if qa["missing_rate"]:
        log.warning(
            "Taux de valeurs manquantes les plus élevés : %s",
            list(qa["missing_rate"].items())[:5],
        )

    _write_outputs(
        cfg,
        features,
        resolution,
        qa,
        read_bbox(cfg),
        _bulk_provenance(cfg),
        skip,
        neighbourhood="3×3 départemental",
        write_gpkg=True,
        cells=cells,
    )
    return 0


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    cfg = Config.load(
        args.config,
        departement=args.departement,
        departements=args.departements,
        perimetre=args.perimetre,
    )
    cfg.ensure_dirs()

    resolution = float(args.resolution or cfg.resolution_m)
    skip = {
        item.strip().lower()
        for item in str(args.skip or "").split(",")
        if item.strip()
    }
    unknown = sorted(skip - SKIPPABLE - {"dem"})
    if unknown:
        log.error("Couches inconnues dans --skip : %s", ", ".join(unknown))
        return 2
    if "dem" in skip:
        skip.discard("dem")
        skip.add("relief")
    if args.no_batiment:
        skip.add("batiment")

    if _check_inputs(cfg):
        return 2

    if not args.no_fetch:
        needs = _required_bulk(skip)
        bdtopo_cfg = (cfg.bulk or {}).get("bdtopo", {}) or {}
        include_batiment = (
            bool(bdtopo_cfg.get("include_batiment", True))
            and "batiment" not in skip
        )
        dfci_wfs = bool((cfg.bulk or {}).get("dfci_wfs", True)) and not args.no_dfci_wfs
        _fetch_missing(
            cfg,
            needs,
            resolution,
            args,
            include_batiment=include_batiment,
            dfci_wfs=dfci_wfs,
        )

    if cfg.france:
        return run_france(cfg, args, resolution, skip)
    return run_departement(cfg, args, resolution, skip)


if __name__ == "__main__":
    raise SystemExit(main())
