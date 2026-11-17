#!/usr/bin/env python
"""10 — Acquisition bulk des couches lourdes depuis la Géoplateforme.

Ce script remplace, pour les couches lourdes, les requêtes WFS de
``01_download_data.py`` par les archives officielles de l'IGN
(``https://data.geopf.fr/telechargement``) :

===============  ==========================================================
Couche           Archive Géoplateforme
===============  ==========================================================
BD Forêt V2      ``BDFORET_2-0__SHP_LAMB93_D<dept>_<date>`` (~43 Mo/dept)
BD TOPO          ``BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_D<dept>_<date>``
                 (~600 Mo/dept, routes + habitat + bâti)
RPG 4.0          ``RPG_4-0__GPKG_LAMB93_R<region>_<année>``
                 (~90 Mo à 1,8 Go par région)
MNT Copernicus   tuiles COG 1°×1° lues via un VRT ``/vsicurl`` puis
                 reprojetées en COG ZSTD 25 m par département
===============  ==========================================================

Cycle appliqué pour chaque archive :

    sélection de la dernière édition → téléchargement reprenable
    → extraction ciblée → lecture filtrée par emprise → GeoParquet
    → purge du brut (sauf ``--keep-raw``)

Les sorties sont des GeoParquet normalisés dans ``data/raw/bulk/<couche>/`` ;
ils sont la seule entrée de ``11_build_features_france.py``.

Prérequis : le carroyage et les contours doivent déjà être présents
(``01_download_data.py --layers admin,dfci``) : ce script lit les bbox
départementales ``data/interim/dept_<dept>_bbox.json``.

Exemples
--------
    python scripts/10_bulk_download.py --departements 33 --layers bdf,bdtopo
    python scripts/10_bulk_download.py --perimetre france_metro --layers all
    python scripts/10_bulk_download.py --departements 33,40 --layers rpg --workers 2
    python scripts/10_bulk_download.py --departements 2A --layers all --keep-raw
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifmplus.bulk import BULK_LAYERS, BulkResult, ensure_bulk  # noqa: E402
from ifmplus.config import Config  # noqa: E402
from ifmplus.log import setup_logging  # noqa: E402

log = logging.getLogger("ifmplus")

ALL_LAYERS = "all"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Téléchargement bulk Géoplateforme et normalisation en GeoParquet "
            "(BD TOPO, BD Forêt V2, RPG, MNT Copernicus)."
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
        "--layers",
        default=ALL_LAYERS,
        help=(
            "Couches à acquérir, séparées par des virgules : "
            f"{', '.join(BULK_LAYERS)} ou '{ALL_LAYERS}' (défaut)."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Téléchargements simultanés (1–4). Défaut : config bulk.workers.",
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Conserve les archives .7z (sinon purge après extraction).",
    )
    parser.add_argument(
        "--no-dfci-wfs",
        action="store_true",
        help="Désactive l'enrichissement WFS des pistes DFCI (repli heuristique).",
    )
    parser.add_argument(
        "--no-batiment",
        action="store_true",
        help="Ignore la couche bâti de la BD TOPO (features de bâti absentes).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retélécharge et recalcule les couches déjà présentes.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _parse_layers(value: str) -> tuple[str, ...]:
    tokens = [token.strip().lower() for token in str(value).split(",") if token.strip()]
    if not tokens or ALL_LAYERS in tokens:
        return tuple(BULK_LAYERS)
    unknown = sorted(set(tokens) - set(BULK_LAYERS))
    if unknown:
        raise ValueError(
            "Couches inconnues : "
            + ", ".join(unknown)
            + f" (attendu : {', '.join(BULK_LAYERS)})"
        )
    return tuple(dict.fromkeys(tokens))


def _check_prerequisites(cfg: Config) -> list[str]:
    """Bbox départementales requises par le filtrage des archives."""
    missing = [
        dept for dept in cfg.departements if not cfg.bbox_path(dept).exists()
    ]
    if missing:
        log.error(
            "Bbox manquante(s) pour : %s\n"
            "Lancer d'abord : python scripts/01_download_data.py "
            "--layers admin%s",
            ", ".join(missing),
            " --perimetre france_metro" if cfg.france else "",
        )
    return missing


def _summarise(summary: dict[str, list[BulkResult]]) -> int:
    log.info("")
    log.info("Résumé")
    log.info("-------")
    failures: list[BulkResult] = []
    for layer, results in summary.items():
        ok = sum(1 for item in results if item.status == "ok")
        cached = sum(1 for item in results if item.status == "cached")
        failed = sum(1 for item in results if item.status == "failed")
        log.info(
            "  %-7s : %3d ok, %3d en cache, %3d échec(s)",
            layer,
            ok,
            cached,
            failed,
        )
        for item in results:
            if item.status == "failed":
                log.error("    [%s] %s", item.scope, item.detail)
                failures.append(item)

    if failures:
        log.error("")
        log.error("%s échec(s) : relancer la commande pour reprendre.", len(failures))
    return len(failures)


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

    try:
        layers = _parse_layers(args.layers)
    except ValueError as exc:
        log.error("%s", exc)
        return 2

    missing = _check_prerequisites(cfg)
    if missing:
        return 2

    bulk_cfg = cfg.bulk or {}
    workers = args.workers
    if workers is None:
        workers = int(bulk_cfg.get("workers", 2))
    workers = max(1, min(int(workers), 4))

    bdtopo_cfg = bulk_cfg.get("bdtopo", {}) or {}
    include_batiment = (
        bool(bdtopo_cfg.get("include_batiment", True)) and not args.no_batiment
    )
    dfci_wfs = bool(bulk_cfg.get("dfci_wfs", True)) and not args.no_dfci_wfs
    keep_raw = bool(bulk_cfg.get("keep_raw", False)) or args.keep_raw

    log.info("IFM+ — acquisition bulk Géoplateforme")
    log.info(
        "Périmètre : %s (%s département(s)) | couches : %s",
        cfg.scope_label,
        len(cfg.departements),
        ", ".join(layers),
    )
    if "bdtopo" in layers:
        log.info(
            "BD TOPO : édition %s | bâti %s | pistes DFCI via WFS %s",
            bdtopo_cfg.get("edition", "latest"),
            "oui" if include_batiment else "non",
            "oui" if dfci_wfs else "non (repli heuristique)",
        )
    if "rpg" in layers:
        rpg_cfg = bulk_cfg.get("rpg", {}) or {}
        log.info(
            "RPG : millésime %s | repli national %s",
            rpg_cfg.get("year", 2025),
            "oui" if rpg_cfg.get("allow_national_fallback", False) else "non",
        )

    started = time.monotonic()
    summary = ensure_bulk(
        cfg,
        layers=layers,
        departements=cfg.departements,
        force=args.force,
        keep_raw=keep_raw,
        workers=workers,
        include_batiment=include_batiment,
        dfci_wfs=dfci_wfs,
        with_dem="dem" in layers,
    )
    elapsed = time.monotonic() - started

    failures = _summarise(summary)
    log.info("")
    log.info("Terminé en %.1f min — sorties : %s", elapsed / 60.0, cfg.bulk_dir)
    if failures:
        return 1
    log.info(
        "Étape suivante : python scripts/11_build_features_france.py"
        + (" --perimetre france_metro" if cfg.france else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
