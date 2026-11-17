#!/usr/bin/env python
"""01 — Acquisition des données du pack MVP IFM+.

Deux périmètres :

- ``--perimetre departement --departement 33`` : un département pilote, bbox locale ;
- ``--perimetre france_metro`` (défaut) : France métropolitaine entière, traitée
  département par département (les couches WFS sont filtrées par bbox).

Le carroyage DFCI, les contours administratifs, le TMJA et la météo sont
téléchargés une seule fois à l'échelle nationale ; les couches thématiques
(BD Forêt, habitat, routes, RPG, MNT) sont téléchargées par département,
ce qui permet de reprendre un lot interrompu et de borner la mémoire.

Exemples
--------
    python scripts/01_download_data.py --layers all
    python scripts/01_download_data.py --perimetre france_metro --layers all
    python scripts/01_download_data.py --departements 33,40 --layers forest,dem
    python scripts/01_download_data.py --perimetre france_metro --layers all --force
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifmplus.config import Config  # noqa: E402
from ifmplus.datagouv import DataGouvClient  # noqa: E402
from ifmplus.log import setup_logging  # noqa: E402
from ifmplus.manifest import Manifest  # noqa: E402
from ifmplus.sources import (  # noqa: E402
    download_admin,
    download_admin_france,
    download_dem,
    download_dfci,
    download_firms,
    download_tmja,
    download_vectors,
    download_weather,
    prepare_bdiff,
)

log = logging.getLogger("ifmplus")

ORDER = [
    "dfci",
    "admin",
    "forest",
    "habitat",
    "roads",
    "rpg",
    "tmja",
    "dem",
    "firms",
    "bdiff",
    "weather",
]
SPATIAL_LAYERS = {"forest", "habitat", "roads", "rpg", "tmja", "dem"}
VECTOR_LAYERS = {"forest", "habitat", "roads", "rpg"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Téléchargement des couches IFM+ (département ou France métro)."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--departement", default=None, help="Code INSEE (ex. 33)")
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
        default="all",
        help="Liste séparée par des virgules, ou 'all'.",
    )
    parser.add_argument("--force", action="store_true", help="Retélécharge tout.")
    parser.add_argument(
        "--max-features",
        type=int,
        default=None,
        help="Plafond par couche WFS et par département (tests uniquement).",
    )
    parser.add_argument(
        "--dem-resolution",
        type=float,
        default=None,
        help="Résolution du MNT de sortie en mètres (défaut : config).",
    )
    parser.add_argument("--list-layers", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _requested_layers(value: str, logger: logging.Logger) -> list[str] | None:
    requested = (
        list(ORDER)
        if value.strip().lower() == "all"
        else [item.strip() for item in value.split(",") if item.strip()]
    )
    unknown = sorted(set(requested) - set(ORDER))
    if unknown:
        logger.error("Couches inconnues : %s", ", ".join(unknown))
        return None
    return requested


def _status(result) -> str:
    return result.get("status", "ok") if isinstance(result, dict) else "ok"


def _detail(result) -> str:
    if not isinstance(result, dict):
        return ""
    return str(
        result.get("reason")
        or result.get("folder")
        or result.get("output")
        or ""
    )


# ----------------------------------------------------------------------
# Mode « un département » (comportement historique)
# ----------------------------------------------------------------------
def run_departement(
    cfg: Config,
    requested: list[str],
    args: argparse.Namespace,
    manifest: Manifest,
    client: DataGouvClient,
    logger: logging.Logger,
) -> int:
    def execute(name: str, function, **kwargs) -> None:
        try:
            result = function(**kwargs)
            status = _status(result)
            if status == "skipped":
                logger.warning("%s : ignoré (%s)", name, result.get("reason"))
            elif status == "manual_required":
                logger.warning(
                    "%s : action manuelle requise (%s)",
                    name,
                    result.get("folder"),
                )
            else:
                logger.info("%s : terminé", name)
        except Exception as exc:  # noqa: BLE001 — on continue les autres couches
            logger.error("%s : ÉCHEC — %s", name, exc)
            if args.verbose:
                logger.exception("Détail de l'échec %s", name)
            manifest.record(name, "failed", error=str(exc))

    for name in requested:
        if name == "dfci":
            execute("dfci", download_dfci, cfg=cfg, client=client,
                    manifest=manifest, force=args.force)
        elif name == "admin":
            execute("admin", download_admin, cfg=cfg, manifest=manifest,
                    force=args.force)
        elif name in VECTOR_LAYERS:
            execute(
                name,
                download_vectors,
                cfg=cfg,
                manifest=manifest,
                layers=[name],
                force=args.force,
                max_features=args.max_features,
            )
        elif name == "tmja":
            execute("tmja", download_tmja, cfg=cfg, client=client,
                    manifest=manifest, force=args.force)
        elif name == "dem":
            execute("dem", download_dem, cfg=cfg, manifest=manifest,
                    force=args.force, resolution=args.dem_resolution)
        elif name == "firms":
            execute("firms", download_firms, cfg=cfg, client=client,
                    manifest=manifest, force=args.force)
        elif name == "bdiff":
            execute("bdiff", prepare_bdiff, cfg=cfg, manifest=manifest)
        elif name == "weather":
            execute("weather", download_weather, cfg=cfg, manifest=manifest,
                    force=args.force)

    # ------------------------------------------------------------------
    # Résumé
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("%-10s %-18s %s", "COUCHE", "STATUT", "DÉTAIL")
    logger.info("-" * 78)
    failures = 0
    for name in requested:
        entry = manifest.get(name) or {}
        status = entry.get("status", "non exécuté")
        if status == "failed":
            failures += 1
        detail = (
            entry.get("error")
            or entry.get("reason")
            or entry.get("output")
            or entry.get("folder")
            or ""
        )
        logger.info("%-10s %-18s %s", name, status, detail)

    logger.info("")
    logger.info("Données brutes : %s", cfg.raw_dir)
    logger.info("Étape suivante : python scripts/02_build_static_features.py")
    return 1 if failures else 0


# ----------------------------------------------------------------------
# Mode France métropolitaine (boucle départementale)
# ----------------------------------------------------------------------
def run_france(
    cfg: Config,
    requested: list[str],
    args: argparse.Namespace,
    manifest: Manifest,
    client: DataGouvClient,
    logger: logging.Logger,
) -> int:
    departements = cfg.departements
    counters: dict[str, dict[str, int]] = {}
    details: dict[str, list[str]] = {}

    def note(layer: str, status: str, detail: str = "") -> None:
        bucket = counters.setdefault(layer, {})
        bucket[status] = bucket.get(status, 0) + 1
        if detail:
            details.setdefault(layer, []).append(detail)

    def run_layer(layer: str, label: str, function, manifest_key: str, **kwargs):
        try:
            result = function(**kwargs)
        except Exception as exc:  # noqa: BLE001 — un département n'arrête pas le lot
            logger.error("%s : ÉCHEC — %s", label, exc)
            if args.verbose:
                logger.exception("Détail de l'échec %s", label)
            manifest.record(manifest_key, "failed", error=str(exc))
            note(layer, "failed", f"{label}: {exc}")
            return None

        status = _status(result)
        if status == "skipped":
            logger.warning("%s : ignoré (%s)", label, result.get("reason"))
        elif status == "manual_required":
            logger.warning(
                "%s : action manuelle requise (%s)", label, result.get("folder")
            )
        else:
            logger.info("%s : terminé", label)
        note(layer, status, "" if status == "ok" else f"{label}: {_detail(result)}")
        return result

    logger.info(
        "Périmètre France métropolitaine — %s département(s) : %s",
        len(departements),
        ", ".join(departements) if len(departements) <= 12 else
        ", ".join(departements[:12]) + ", …",
    )

    # Les couches WFS ont besoin des bboxes départementales (couche admin).
    if "admin" not in requested:
        missing = [
            dept for dept in departements if not cfg.bbox_path(dept).exists()
        ]
        needs_bboxes = bool(SPATIAL_LAYERS.intersection(requested)) and bool(missing)
        needs_referentiel = not cfg.departements_france_path.exists()
        needs_communes = not cfg.communes_scope_path.exists()
        needs_scope_bbox = (
            bool({"firms", "weather"}.intersection(requested))
            and not cfg.scope_bbox_path.exists()
        )
        if needs_bboxes or needs_referentiel or needs_communes or needs_scope_bbox:
            logger.info(
                "Admin Express ajouté automatiquement (référentiel national=%s, "
                "communes=%s, bbox manquantes=%s)",
                "absent" if needs_referentiel else "présent",
                "absentes" if needs_communes else "présentes",
                len(missing),
            )
            requested.insert(0, "admin")

    def bboxes_ready() -> bool:
        missing = [
            dept for dept in departements if not cfg.bbox_path(dept).exists()
        ]
        if missing:
            logger.error(
                "bbox départementales manquantes pour %s département(s) : "
                "lancer d'abord --layers admin",
                len(missing),
            )
            return False
        return True

    for name in requested:
        if name == "dfci":
            run_layer(
                "dfci", "dfci", download_dfci, "dfci",
                cfg=cfg, client=client, manifest=manifest, force=args.force,
            )
        elif name == "admin":
            run_layer(
                "admin", "admin (France)", download_admin_france, "admin",
                cfg=cfg, manifest=manifest, force=args.force,
            )
        elif name in VECTOR_LAYERS:
            if not bboxes_ready():
                note(name, "failed", "bbox départementales manquantes")
                continue
            for dept in departements:
                sub = cfg.for_departement(dept)
                run_layer(
                    name,
                    f"{name} [{dept}]",
                    download_vectors,
                    f"{name}:{dept}",
                    cfg=sub,
                    manifest=manifest,
                    layers=[name],
                    force=args.force,
                    max_features=args.max_features,
                    record_name=f"{name}:{dept}",
                )
        elif name == "tmja":
            run_layer(
                "tmja", "tmja (France)", download_tmja, "tmja",
                cfg=cfg, client=client, manifest=manifest, force=args.force,
            )
        elif name == "dem":
            if not bboxes_ready():
                note(name, "failed", "bbox départementales manquantes")
                continue
            for dept in departements:
                sub = cfg.for_departement(dept)
                run_layer(
                    "dem",
                    f"dem [{dept}]",
                    download_dem,
                    f"dem:{dept}",
                    cfg=sub,
                    manifest=manifest,
                    force=args.force,
                    resolution=args.dem_resolution,
                    record_name=f"dem:{dept}",
                )
        elif name == "firms":
            run_layer(
                "firms", "firms (France)", download_firms, "firms",
                cfg=cfg, client=client, manifest=manifest, force=args.force,
            )
        elif name == "bdiff":
            run_layer(
                "bdiff", "bdiff (France)", prepare_bdiff, "bdiff",
                cfg=cfg, manifest=manifest,
            )
        elif name == "weather":
            run_layer(
                "weather", "weather (France)", download_weather, "weather",
                cfg=cfg, manifest=manifest, force=args.force,
            )

    # ------------------------------------------------------------------
    # Résumé agrégé
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("%-10s %-34s %s", "COUCHE", "STATUT", "DÉTAIL")
    logger.info("-" * 90)
    failures = 0
    for name in requested:
        bucket = counters.get(name, {})
        ok = bucket.get("ok", 0)
        failed = bucket.get("failed", 0)
        skipped = bucket.get("skipped", 0)
        manual = bucket.get("manual_required", 0)
        failures += failed
        parts = []
        if ok:
            parts.append(f"{ok} OK")
        if failed:
            parts.append(f"{failed} échec(s)")
        if skipped:
            parts.append(f"{skipped} ignoré(s)")
        if manual:
            parts.append(f"{manual} manuel")
        detail = " | ".join(details.get(name, [])[:3])
        logger.info(
            "%-10s %-34s %s",
            name,
            ", ".join(parts) or "non exécuté",
            detail[:120],
        )

    logger.info("")
    logger.info("Données brutes : %s", cfg.raw_dir)
    logger.info(
        "Étape suivante : python scripts/02_build_static_features.py "
        "--perimetre france_metro"
    )
    return 1 if failures else 0


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.verbose)

    if args.list_layers:
        print("\n".join(ORDER))
        return 0

    requested = _requested_layers(args.layers, logger)
    if requested is None:
        return 2

    cfg = Config.load(
        args.config,
        departement=args.departement,
        departements=args.departements,
        perimetre=args.perimetre,
    )
    cfg.ensure_dirs()
    manifest = Manifest(cfg.raw_dir / "_manifest.json")
    client = DataGouvClient(cfg.sources["datagouv_api"])

    if cfg.france:
        return run_france(cfg, requested, args, manifest, client, logger)
    return run_departement(cfg, requested, args, manifest, client, logger)


if __name__ == "__main__":
    raise SystemExit(main())
