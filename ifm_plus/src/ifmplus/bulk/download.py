"""Acquisition bulk streaming des couches lourdes, département par département.

Chaque fonction ``ensure_*`` est **idempotente** : si les GeoParquet de sortie
existent et que ``force=False``, rien n'est retéléchargé. Sinon elle applique
le cycle demandé :

    sélection de l'archive → téléchargement reprenable → extraction ciblée
    → lecture filtrée par emprise → GeoParquet → purge du brut

Les archives ne sont conservées que si ``keep_raw=True`` (option
``--keep-raw``). Le brut est placé dans ``data/raw/bulk/_tmp/`` puis supprimé ;
les GeoParquet normalisés restent dans ``data/raw/bulk/<couche>/``.
"""

from __future__ import annotations

import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from ..geoutils import read_bbox
from . import catalog
from .archive import SHAPEFILE_SUFFIXES, extract_members, find_one, purge
from .dfci import approximate_dfci, fetch_dfci_cleabs
from .geopf import GeoPlateformeClient, GeoPlateformeError, SubResource
from .layers import (
    LayerError,
    empty_layer,
    read_bdtopo,
    read_forest,
    read_rpg,
    write_parquet,
)
from .regions import REGION_NAMES, departments_of_region, region_zone, regions_for

log = logging.getLogger("ifmplus")

BULK_LAYERS = ("bdtopo", "bdf", "rpg", "dem")


@dataclass
class BulkResult:
    layer: str
    scope: str
    status: str
    detail: str = ""
    outputs: tuple[str, ...] = ()


def _meta_path(cfg, layer: str, scope: str) -> Path:
    return cfg.bulk_raw(layer, f"{scope}.meta.json")


def _write_meta(cfg, layer: str, scope: str, payload: dict) -> None:
    path = _meta_path(cfg, layer, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _keep_archive(cfg, layer: str, archive: Path) -> Path:
    destination = cfg.bulk_raw("_archives", layer, archive.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    shutil.move(str(archive), str(destination))
    return destination


def _tmp_dir(cfg, layer: str, scope: str) -> Path:
    return cfg.bulk_raw("_tmp", f"{layer}_{scope}")


def _download(
    client: GeoPlateformeClient,
    sub: SubResource,
    cfg,
    layer: str,
    scope: str,
    *,
    force: bool,
) -> tuple[SubResource, Path, Path]:
    resolved = client.resolve(sub)
    tmp = _tmp_dir(cfg, layer, scope)
    tmp.mkdir(parents=True, exist_ok=True)
    archive = tmp / (resolved.name + resolved.suffix)
    client.download(resolved, archive, force=force)
    return resolved, archive, tmp


def _dfci_cleabs(
    cfg,
    dept: str,
    bbox,
    *,
    force: bool,
    enabled: bool,
) -> tuple[set[str], str]:
    """Identifiants DFCI, avec cache parquet et repli heuristique."""
    cache = cfg.bulk_raw("dfci", f"dfci_{dept}.parquet")
    if cache.exists() and not force:
        try:
            frame = pd.read_parquet(cache)
            return set(frame["cleabs"].astype(str)), "wfs:piste_dfci (cache)"
        except (OSError, KeyError, ValueError):
            log.warning("  cache DFCI illisible pour %s, rechargement", dept)
    if not enabled:
        return set(), "heuristique (WFS désactivé)"
    try:
        cleabs = fetch_dfci_cleabs(bbox)
        cache.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"cleabs": sorted(cleabs)}).to_parquet(cache, index=False)
        return cleabs, "wfs:piste_dfci"
    except Exception as exc:  # noqa: BLE001 — repli explicite
        log.warning("  enrichissement DFCI indisponible (%s) : repli heuristique", exc)
        return set(), f"heuristique (WFS indisponible : {exc})"


# ----------------------------------------------------------------------
# BD Forêt V2
# ----------------------------------------------------------------------
def ensure_forest(
    cfg,
    dept: str,
    client: GeoPlateformeClient,
    *,
    force: bool = False,
    keep_raw: bool = False,
    version: str = "2-0",
) -> BulkResult:
    output = cfg.bulk_layer("forest", dept)
    if output.exists() and not force:
        return BulkResult("bdf", dept, "cached", str(output), (str(output),))

    sub = catalog.select_bdforet(client, dept, version=version)
    resolved, archive, tmp = _download(
        client, sub, cfg, "bdf", dept, force=force
    )
    extract_dir = tmp / "extract"
    try:
        members = extract_members(
            archive,
            extract_dir,
            suffixes=SHAPEFILE_SUFFIXES,
            substrings=("FORMATION_VEGETALE",),
        )
        shapefile = find_one(members, ".shp")
        frame = read_forest(shapefile, read_bbox(cfg.for_departement(dept)), cfg.crs)
        write_parquet(frame, output)
        payload = {
            "layer": "bdf",
            "departement": dept,
            "sub_resource": resolved.name,
            "edition": resolved.edition,
            "url": resolved.download_url,
            "archive_size": resolved.size,
            "n_features": int(len(frame)),
            "output": str(output),
            "crs": cfg.crs,
        }
        _write_meta(cfg, "bdf", dept, payload)
        log.info("  BD Forêt %s : %s polygones -> %s", dept, f"{len(frame):,}", output.name)
    finally:
        kept = None
        if keep_raw and archive.exists():
            kept = _keep_archive(cfg, "bdf", archive)
        purge(tmp)
    return BulkResult(
        "bdf",
        dept,
        "ok",
        str(kept) if keep_raw else str(output),
        (str(output),),
    )


# ----------------------------------------------------------------------
# BD TOPO (routes, habitat, bâti)
# ----------------------------------------------------------------------
def ensure_bdtopo(
    cfg,
    dept: str,
    client: GeoPlateformeClient,
    *,
    force: bool = False,
    keep_raw: bool = False,
    include_batiment: bool = True,
    dfci_wfs: bool = True,
    edition: str | None = None,
) -> BulkResult:
    logical_layers = ("roads", "habitat") + (("batiment",) if include_batiment else ())
    outputs = [cfg.bulk_layer(layer, dept) for layer in logical_layers]
    if all(path.exists() for path in outputs) and not force:
        return BulkResult(
            "bdtopo", dept, "cached", str(outputs[0]), tuple(str(p) for p in outputs)
        )

    sub = catalog.select_bdtopo(client, dept, edition=edition)
    resolved, archive, tmp = _download(
        client, sub, cfg, "bdtopo", dept, force=force
    )
    extract_dir = tmp / "extract"
    kept = None
    try:
        members = extract_members(
            archive,
            extract_dir,
            suffixes=(".gpkg",),
            substrings=("TOUSTHEMES",),
        )
        gpkg = find_one(members, ".gpkg")
        bbox = read_bbox(cfg.for_departement(dept))
        frames = read_bdtopo(gpkg, bbox, cfg.crs, layers=logical_layers)

        cleabs, dfci_source = _dfci_cleabs(
            cfg, dept, bbox, force=force, enabled=dfci_wfs
        )
        roads = frames["roads"]
        if cleabs:
            roads["piste_dfci"] = roads["cleabs"].isin(cleabs)
        else:
            roads["piste_dfci"] = approximate_dfci(roads)
        roads["importance"] = pd.to_numeric(roads["importance"], errors="coerce")
        frames["roads"] = roads

        for layer, frame in frames.items():
            write_parquet(frame, cfg.bulk_layer(layer, dept))
            log.info(
                "  BD TOPO %s / %s : %s entités", dept, layer, f"{len(frame):,}"
            )

        _write_meta(
            cfg,
            "bdtopo",
            dept,
            {
                "layer": "bdtopo",
                "departement": dept,
                "sub_resource": resolved.name,
                "edition": resolved.edition,
                "url": resolved.download_url,
                "archive_size": resolved.size,
                "layers": {key: int(len(value)) for key, value in frames.items()},
                "dfci_source": dfci_source,
                "dfci_troncons": int(roads["piste_dfci"].sum()),
                "outputs": [str(path) for path in outputs],
                "crs": cfg.crs,
            },
        )
    finally:
        if keep_raw and archive.exists():
            kept = _keep_archive(cfg, "bdtopo", archive)
        purge(tmp)
    return BulkResult(
        "bdtopo",
        dept,
        "ok",
        " | ".join(f"{path.name}" for path in outputs),
        tuple(str(path) for path in outputs),
    )


# ----------------------------------------------------------------------
# RPG (une archive régionale → un GeoParquet par département)
# ----------------------------------------------------------------------
def ensure_rpg_region(
    cfg,
    region: str,
    departements: Iterable[str],
    client: GeoPlateformeClient,
    *,
    force: bool = False,
    keep_raw: bool = False,
    year: int | None = 2025,
    allow_national_fallback: bool = False,
) -> list[BulkResult]:
    depts = tuple(departements)
    outputs = [cfg.bulk_layer("rpg", dept) for dept in depts]
    if all(path.exists() for path in outputs) and not force:
        return [
            BulkResult("rpg", dept, "cached", str(path), (str(path),))
            for dept, path in zip(depts, outputs)
        ]

    sub = catalog.select_rpg(
        client,
        region,
        year=year,
        allow_national_fallback=allow_national_fallback,
    )
    resolved, archive, tmp = _download(
        client, sub, cfg, "rpg", region, force=force
    )
    extract_dir = tmp / "extract"
    kept = None
    results: list[BulkResult] = []
    try:
        members = extract_members(
            archive,
            extract_dir,
            suffixes=(".gpkg",),
            substrings=("RPG_Parcelles",),
        )
        gpkg = find_one(members, "RPG_Parcelles")
        for dept in depts:
            output = cfg.bulk_layer("rpg", dept)
            try:
                frame = read_rpg(
                    gpkg, read_bbox(cfg.for_departement(dept)), cfg.crs
                )
                write_parquet(frame, output)
                _write_meta(
                    cfg,
                    "rpg",
                    dept,
                    {
                        "layer": "rpg",
                        "departement": dept,
                        "region": region,
                        "region_name": REGION_NAMES.get(region),
                        "sub_resource": resolved.name,
                        "edition": resolved.edition,
                        "annee": catalog.rpg_year(resolved),
                        "url": resolved.download_url,
                        "archive_size": resolved.size,
                        "n_parcelles": int(len(frame)),
                        "output": str(output),
                        "crs": cfg.crs,
                    },
                )
                log.info(
                    "  RPG %s / %s : %s parcelles -> %s",
                    region,
                    dept,
                    f"{len(frame):,}",
                    output.name,
                )
                results.append(BulkResult("rpg", dept, "ok", str(output), (str(output),)))
            except Exception as exc:  # noqa: BLE001 — un département n'arrête pas la région
                log.error("  RPG %s : ÉCHEC — %s", dept, exc)
                results.append(BulkResult("rpg", dept, "failed", str(exc)))
    finally:
        if keep_raw and archive.exists():
            kept = _keep_archive(cfg, "rpg", archive)
        purge(tmp)
    return results


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
def _run_parallel(
    cfg,
    departements: tuple[str, ...],
    worker: Callable[[str, GeoPlateformeClient], BulkResult],
    *,
    workers: int,
    client_factory: Callable[[], GeoPlateformeClient],
) -> list[BulkResult]:
    workers = max(1, min(int(workers), 4))
    if workers == 1 or len(departements) == 1:
        client = client_factory()
        results: list[BulkResult] = []
        for dept in departements:
            try:
                results.append(worker(dept, client))
            except Exception as exc:  # noqa: BLE001
                log.error("  [%s] ÉCHEC — %s", dept, exc)
                results.append(BulkResult("?", dept, "failed", str(exc)))
        return results

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(worker, dept, client_factory()): dept for dept in departements
        }
        for future in as_completed(futures):
            dept = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                log.error("  [%s] ÉCHEC — %s", dept, exc)
                results.append(BulkResult("?", dept, "failed", str(exc)))
    return results


def ensure_bulk(
    cfg,
    *,
    layers: Iterable[str] = BULK_LAYERS,
    departements: Iterable[str] | None = None,
    force: bool = False,
    keep_raw: bool = False,
    workers: int = 1,
    include_batiment: bool = True,
    dfci_wfs: bool = True,
    with_dem: bool = True,
    client_factory: Callable[[], GeoPlateformeClient] | None = None,
) -> dict[str, list[BulkResult]]:
    """Télécharge et normalise les couches bulk demandées.

    ``rpg`` est traité **région par région** (une archive couvre plusieurs
    départements), les autres couches département par département.
    """
    requested = tuple(dict.fromkeys(layer.strip().lower() for layer in layers))
    unknown = sorted(set(requested) - set(BULK_LAYERS))
    if unknown:
        raise ValueError("Couches bulk inconnues : " + ", ".join(unknown))

    depts = tuple(departements or cfg.departements)
    factory = client_factory or (lambda: GeoPlateformeClient(
        cfg.bulk.get("geopf_base", "https://data.geopf.fr/telechargement")
    ))
    summary: dict[str, list[BulkResult]] = {}

    bdtopo_cfg = cfg.bulk.get("bdtopo", {}) if isinstance(cfg.bulk, dict) else {}
    bdf_cfg = cfg.bulk.get("bdforet", {}) if isinstance(cfg.bulk, dict) else {}
    rpg_cfg = cfg.bulk.get("rpg", {}) if isinstance(cfg.bulk, dict) else {}

    if "bdtopo" in requested:
        log.info("BD TOPO — %s département(s), %s worker(s)", len(depts), workers)
        summary["bdtopo"] = _run_parallel(
            cfg,
            depts,
            lambda dept, client: ensure_bdtopo(
                cfg,
                dept,
                client,
                force=force,
                keep_raw=keep_raw,
                include_batiment=include_batiment,
                dfci_wfs=dfci_wfs,
                edition=bdtopo_cfg.get("edition", "latest"),
            ),
            workers=workers,
            client_factory=factory,
        )

    if "bdf" in requested:
        log.info("BD Forêt V2 — %s département(s), %s worker(s)", len(depts), workers)
        summary["bdf"] = _run_parallel(
            cfg,
            depts,
            lambda dept, client: ensure_forest(
                cfg,
                dept,
                client,
                force=force,
                keep_raw=keep_raw,
                version=bdf_cfg.get("version", "2-0"),
            ),
            workers=workers,
            client_factory=factory,
        )

    if "rpg" in requested:
        grouped = regions_for(depts)
        log.info(
            "RPG — %s région(s) pour %s département(s)",
            len(grouped),
            len(depts),
        )
        results: list[BulkResult] = []
        client = factory()
        for region, region_depts in grouped.items():
            try:
                results.extend(
                    ensure_rpg_region(
                        cfg,
                        region,
                        region_depts,
                        client,
                        force=force,
                        keep_raw=keep_raw,
                        year=rpg_cfg.get("year", 2025),
                        allow_national_fallback=bool(
                            rpg_cfg.get("allow_national_fallback", False)
                        ),
                    )
                )
            except Exception as exc:  # noqa: BLE001 — une région n'arrête pas le lot
                log.error("RPG %s : ÉCHEC — %s", region, exc)
                results.extend(
                    BulkResult("rpg", dept, "failed", str(exc)) for dept in region_depts
                )
        summary["rpg"] = results

    if "dem" in requested and with_dem:
        from .dem import ensure_department_dem, ensure_vrt

        log.info("MNT Copernicus — VRT distant puis COG par département")
        try:
            vrt = ensure_vrt(cfg)
            dem_results: list[BulkResult] = []
            for dept in depts:
                try:
                    path = ensure_department_dem(cfg, dept, vrt, force=force)
                    dem_results.append(BulkResult("dem", dept, "ok", str(path), (str(path),)))
                except Exception as exc:  # noqa: BLE001
                    log.error("  MNT %s : ÉCHEC — %s", dept, exc)
                    dem_results.append(BulkResult("dem", dept, "failed", str(exc)))
            summary["dem"] = dem_results
        except Exception as exc:  # noqa: BLE001
            log.error("MNT : ÉCHEC — %s", exc)
            summary["dem"] = [BulkResult("dem", "-", "failed", str(exc))]

    return summary
