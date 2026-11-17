"""Acquisition des couches du pack MVP, sur le périmètre métropolitain ou départemental choisi.

Chaque fonction est idempotente : si le fichier de sortie existe et que
``force=False``, elle ne retélécharge rien. Les couches optionnelles
(FIRMS, EWDS, BDIFF) sont marquées ``skipped`` ou ``manual_required``
lorsque les accès ne sont pas configurés, sans faire échouer le pipeline.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import numpy as np
import pandas as pd
import py7zr
import rasterio
from dotenv import load_dotenv
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from rasterio.warp import reproject
from shapely.geometry import LineString

from .config import METRO_DEPARTEMENTS, Config, normalize_dept
from .datagouv import DataGouvClient, make_session, sha256
from .geoutils import (
    read_bbox,
    read_bbox_wgs84,
    read_scope_bbox_wgs84,
    save_bbox,
    save_scope_bbox,
)
from .manifest import Manifest
from .raster import AnalysisGrid
from .wfs import WfsLayer, download_wfs

log = logging.getLogger("ifmplus")

# ----------------------------------------------------------------------
# Couches WFS IGN
# ----------------------------------------------------------------------
WFS_LAYERS: dict[str, WfsLayer] = {
    "departement": WfsLayer(
        "ADMINEXPRESS-COG-CARTO.LATEST:departement",
        geom_field="geometrie",
        page_size=100,
    ),
    "commune": WfsLayer(
        "ADMINEXPRESS-COG-CARTO.LATEST:commune",
        geom_field="geometrie",
        page_size=1000,
    ),
    "forest": WfsLayer(
        "LANDCOVER.FORESTINVENTORY.V2:formation_vegetale",
        geom_field="geom",
        property_name="id,tfv,essence,geom",
        page_size=4000,
        tile_size_m=25_000,
        id_property="id",
    ),
    "habitat": WfsLayer(
        "BDTOPO_V3:zone_d_habitation",
        geom_field="geometrie",
        property_name="cleabs,nature,importance,geometrie",
        page_size=3000,
        tile_size_m=50_000,
        id_property="cleabs",
    ),
    "roads": WfsLayer(
        "BDTOPO_V3:troncon_de_route",
        geom_field="geometrie",
        property_name="cleabs,importance,nature,piste_dfci,etat_de_l_objet,geometrie",
        page_size=3000,
        tile_size_m=30_000,
        id_property="cleabs",
    ),
    "rpg": WfsLayer(
        "RPG.LATEST:parcelles_graphiques",
        geom_field="geom",
        property_name="num_parcel,code_group,code_cultu,surf_parc,geom",
        page_size=4000,
        tile_size_m=25_000,
        id_property="num_parcel",
    ),
}

#: Colonnes minimales d'une couche vide (département sans entité).
EMPTY_COLUMNS: dict[str, list[str]] = {
    "forest": ["id", "tfv", "essence"],
    "habitat": ["cleabs", "nature", "importance"],
    "roads": ["cleabs", "importance", "nature", "piste_dfci", "etat_de_l_objet"],
    "rpg": ["num_parcel", "code_group", "code_cultu", "surf_parc"],
}

WFS_URL = "https://data.geopf.fr/wfs/ows"


def _dept_cql(cfg: Config) -> str:
    return f"code_insee='{cfg.departement}'"


def _communes_cql(cfg: Config) -> str:
    return f"code_insee LIKE '{cfg.departement}%'"


#: France métropolitaine = tout sauf les DOM (97x) et les COM (98x).
METRO_CQL = "code_insee NOT LIKE '97%' AND code_insee NOT LIKE '98%'"


# ----------------------------------------------------------------------
# 1. Carroyage DFCI
# ----------------------------------------------------------------------
def download_dfci(
    cfg: Config,
    client: DataGouvClient,
    manifest: Manifest,
    force: bool = False,
) -> dict[str, Any]:
    log.info("Carroyage DFCI 2 km — API data.gouv.fr")
    dataset = client.dataset(cfg.sources["dfci_slug"])
    snapshot = cfg.raw("dfci", "dataset.json")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(
        json.dumps(
            {
                "id": dataset.get("id"),
                "title": dataset.get("title"),
                "page": dataset.get("page"),
                "license": dataset.get("license"),
                "last_update": dataset.get("last_update"),
                "resources": [
                    {
                        "title": res.get("title"),
                        "format": res.get("format"),
                        "url": res.get("url"),
                        "filesize": res.get("filesize"),
                    }
                    for res in dataset.get("resources", [])
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    resource = client.pick_resource(
        dataset, formats=("7z", "zip", "gpkg", "shp", "geojson")
    )
    url = resource["url"]
    archive = cfg.raw("dfci", Path(url).name)
    client.download(
        url,
        archive,
        force=force,
        expected_size=resource.get("filesize"),
    )

    extracted = cfg.raw("dfci", "extracted")
    if force and extracted.exists():
        shutil.rmtree(extracted)
    extracted.mkdir(parents=True, exist_ok=True)

    if not any(extracted.rglob("*.shp")) and not any(extracted.rglob("*.gpkg")):
        log.info("  extraction de l'archive…")
        if archive.suffix.lower() == ".7z":
            with py7zr.SevenZipFile(archive, mode="r") as bundle:
                bundle.extractall(path=extracted)
        elif archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extracted)

    candidates = sorted(extracted.rglob("*.shp")) + sorted(extracted.rglob("*.gpkg"))
    if not candidates:
        raise RuntimeError(f"Aucun shapefile/GPKG dans {extracted}")

    log.info("  lecture de %s", candidates[0].name)
    gdf = gpd.read_file(candidates[0], engine="pyogrio")
    if gdf.crs is None:
        raise RuntimeError("Le carroyage DFCI n'a pas de CRS déclaré")
    if gdf.crs.to_string() != cfg.crs:
        gdf = gdf.to_crs(cfg.crs)

    id_column = next(
        (col for col in ("id_carreau_dfci", "NOM", "nom", "ID") if col in gdf.columns),
        None,
    )
    if id_column is None:
        raise KeyError(
            f"Colonne identifiant introuvable dans {list(gdf.columns)}"
        )
    gdf = gdf.rename(columns={id_column: "id_carreau_dfci"})
    gdf["id_carreau_dfci"] = gdf["id_carreau_dfci"].astype(str).str.strip()
    if gdf["id_carreau_dfci"].duplicated().any():
        raise RuntimeError("Identifiants DFCI dupliqués dans le carroyage")

    output = cfg.dfci_path
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    gdf[["id_carreau_dfci", "geometry"]].to_file(
        output, layer="carroyage_dfci", driver="GPKG", engine="pyogrio"
    )

    info = {
        "dataset_page": dataset.get("page"),
        "resource_url": url,
        "resource_format": resource.get("format"),
        "n_carreaux": int(len(gdf)),
        "archive_sha256": sha256(archive),
        "output": str(output),
    }
    manifest.record("dfci", "ok", **info)
    log.info("  %s carreaux DFCI -> %s", f"{len(gdf):,}", output.name)
    return info


# ----------------------------------------------------------------------
# 2. Contours administratifs
# ----------------------------------------------------------------------
def download_admin(
    cfg: Config,
    manifest: Manifest,
    force: bool = False,
) -> dict[str, Any]:
    log.info("Contours Admin Express — département %s", cfg.departement)

    dept_layer = replace(WFS_LAYERS["departement"], extra_cql=_dept_cql(cfg))
    dept = download_wfs(
        WFS_URL,
        dept_layer,
        cfg.dept_path,
        bbox=None,
        force=force,
    )
    if dept.empty:
        raise RuntimeError(f"Département {cfg.departement} introuvable")

    bbox = save_bbox(cfg, dept)
    log.info("  bbox Lambert-93 : %s", tuple(round(v) for v in bbox))

    commune_layer = replace(WFS_LAYERS["commune"], extra_cql=_communes_cql(cfg))
    communes = download_wfs(
        WFS_URL,
        commune_layer,
        cfg.communes_path,
        bbox=None,
        force=force,
    )

    info = {
        "departement": cfg.departement,
        "n_communes": int(len(communes)),
        "bbox_2154": [round(v, 3) for v in bbox],
        "bbox_path": str(cfg.dept_bbox_path),
    }
    manifest.record("admin", "ok", **info)
    return info


def download_admin_france(
    cfg: Config,
    manifest: Manifest,
    force: bool = False,
) -> dict[str, Any]:
    """Contours nationaux (départements + communes) et bboxes par département.

    Téléchargés **une seule fois** pour toute la France métropolitaine, puis
    découpés en bbox départementales pour les couches thématiques WFS. Évite
    96 requêtes Admin Express et garde un référentiel unique.
    """
    log.info(
        "Contours Admin Express — France métropolitaine (%s départements)",
        len(cfg.departements),
    )

    dept_layer = replace(
        WFS_LAYERS["departement"],
        extra_cql=METRO_CQL,
        page_size=1000,
    )
    departements = download_wfs(
        WFS_URL,
        dept_layer,
        cfg.departements_france_path,
        bbox=None,
        force=force,
    )
    if departements.empty:
        raise RuntimeError("Contours départementaux métropolitains introuvables")

    commune_cql = METRO_CQL
    if len(cfg.departements) < len(METRO_DEPARTEMENTS):
        commune_cql = "(" + " OR ".join(
            f"code_insee LIKE '{dept}%'" for dept in cfg.departements
        ) + ")"
        log.info(
            "  communes limitées aux %s département(s) demandés",
            len(cfg.departements),
        )
    commune_layer = replace(
        WFS_LAYERS["commune"],
        extra_cql=commune_cql,
        page_size=2000,
    )
    communes = download_wfs(
        WFS_URL,
        commune_layer,
        cfg.communes_france_path,
        bbox=None,
        force=force,
    )

    departements = departements.copy()
    departements["_dept"] = departements["code_insee"].map(normalize_dept)
    by_code = departements.set_index("_dept", drop=False)

    missing: list[str] = []
    for dept in cfg.departements:
        if dept not in by_code.index:
            missing.append(dept)
            continue
        row = by_code.loc[[dept]]
        save_bbox(cfg.for_departement(dept), row)
    if missing:
        raise RuntimeError(
            "Départements absents d'Admin Express : " + ", ".join(missing)
        )

    scope_bbox = save_scope_bbox(cfg, departements, cfg.departements)
    log.info(
        "  %s départements, %s communes, bbox périmètre %s",
        len(departements),
        f"{len(communes):,}",
        tuple(round(v) for v in scope_bbox),
    )

    info = {
        "perimetre": cfg.perimetre,
        "n_departements": int(len(departements)),
        "n_departements_demandes": len(cfg.departements),
        "n_communes": int(len(communes)),
        "scope_bbox_2154": [round(v, 3) for v in scope_bbox],
        "departements_path": str(cfg.departements_france_path),
        "communes_path": str(cfg.communes_france_path),
    }
    manifest.record("admin", "ok", **info)
    return info


# ----------------------------------------------------------------------
# 3. Couches vectorielles thématiques
# ----------------------------------------------------------------------
def download_vectors(
    cfg: Config,
    manifest: Manifest,
    layers: list[str],
    force: bool = False,
    max_features: int | None = None,
    record_name: str | None = None,
) -> dict[str, Any]:
    if not cfg.dept_bbox_path.exists():
        raise RuntimeError(
            "bbox du département absente : lancer d'abord la couche admin"
        )
    bbox = read_bbox(cfg)
    if cfg.roads.get("include_dfci_tracks", True):
        roads_cql = (
            "(importance<={imp} OR piste_dfci=true)".format(
                imp=int(cfg.roads.get("importance_max", 4))
            )
        )
    else:
        roads_cql = "importance<={imp}".format(
            imp=int(cfg.roads.get("importance_max", 4))
        )

    cql_by_layer = {"roads": roads_cql}
    results: dict[str, Any] = {}

    for name in layers:
        if name not in WFS_LAYERS:
            raise KeyError(f"Couche WFS inconnue : {name}")
        layer = WFS_LAYERS[name]
        if name in cql_by_layer:
            layer = replace(layer, extra_cql=cql_by_layer[name])

        destination = cfg.layer_path(name)
        log.info("Couche %s — WFS IGN (département %s)", name, cfg.departement)
        try:
            gdf = download_wfs(
                WFS_URL,
                layer,
                destination,
                bbox=bbox,
                force=force,
                max_features=max_features,
            )
        except RuntimeError as exc:
            if "Aucune entité" not in str(exc):
                raise
            log.warning(
                "  %s : aucune entité sur le département %s, couche vide",
                name,
                cfg.departement,
            )
            gdf = gpd.GeoDataFrame(
                {
                    column: pd.Series(dtype="object")
                    for column in EMPTY_COLUMNS.get(name, [])
                },
                geometry=[],
                crs=cfg.crs,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.unlink()
            gdf.to_file(
                destination, layer=destination.stem, driver="GPKG", engine="pyogrio"
            )
        info = {
            "departement": cfg.departement,
            "wfs_layer": layer.name,
            "cql": layer.extra_cql,
            "n_features": int(len(gdf)),
            "output": str(destination),
            "bbox_2154": [round(v, 3) for v in bbox],
        }
        manifest.record(record_name or name, "ok", **info)
        results[name] = info

    return results


# ----------------------------------------------------------------------
# 4. TMJA (réseau routier national)
# ----------------------------------------------------------------------
def _resource_year(resource: dict[str, Any]) -> int | None:
    """Année d'une ressource TMJA, lue **dans le titre uniquement**.

    L'URL contient l'horodatage de dépôt (ex. ``20200601-111600/tmja2018.csv``)
    qu'il ne faut surtout pas confondre avec l'année de mesure.
    """
    match = re.search(r"(19|20)\d{2}", str(resource.get("title") or ""))
    return int(match.group(0)) if match else None


def _pick_tmja_resources(
    dataset: dict[str, Any],
    years: list[int],
) -> dict[int, dict[str, Any]]:
    resources = [
        res
        for res in dataset.get("resources", [])
        if str(res.get("format", "")).lower() == "csv" and res.get("url")
    ]
    by_year: dict[int, dict[str, Any]] = {}
    for res in resources:
        year = _resource_year(res)
        if year is not None:
            by_year.setdefault(year, res)

    chosen = {year: by_year[year] for year in years if year in by_year}
    if not chosen and by_year:
        # Aucune année exacte : on prend la plus proche disponible.
        nearest = min(by_year, key=lambda year: min(abs(year - y) for y in years))
        chosen = {nearest: by_year[nearest]}
    return chosen


def download_tmja(
    cfg: Config,
    client: DataGouvClient,
    manifest: Manifest,
    force: bool = False,
) -> dict[str, Any]:
    log.info("TMJA réseau routier national — data.gouv.fr")
    dataset = client.dataset(cfg.sources["tmja_slug"])
    start_year = int(cfg.date_debut[:4])
    end_year = int(cfg.date_fin[:4])
    resources = _pick_tmja_resources(dataset, list(range(start_year, end_year + 1)))
    if not resources:
        raise RuntimeError("Aucune ressource CSV TMJA pour la période demandée")

    # En mode France, le TMJA couvre déjà tout le réseau national : on garde
    # toutes les sections et on réutilise le même fichier pour chaque
    # département (le rattachement aux carreaux se fait au moment des features).
    bbox = None if cfg.france else read_bbox(cfg)
    frames: list[gpd.GeoDataFrame] = []

    for year, resource in sorted(resources.items()):
        url = resource["url"]
        csv_path = cfg.raw("tmja", f"tmja_{year}.csv")
        client.download(url, csv_path, force=force, expected_size=resource.get("filesize"))
        header = csv_path.read_text(encoding="utf-8-sig", errors="ignore").split("\n", 1)[0]
        separator = "\t" if header.count("\t") >= header.count(";") else ";"
        try:
            frame = pd.read_csv(
                csv_path,
                sep=separator,
                decimal=",",
                encoding="utf-8-sig",
                low_memory=False,
            )
        except UnicodeDecodeError:
            frame = pd.read_csv(
                csv_path,
                sep=separator,
                decimal=",",
                encoding="latin-1",
                low_memory=False,
            )
        frame.columns = [str(column).strip() for column in frame.columns]

        required = {"xD", "yD", "xF", "yF", "TMJA"}
        if not required.issubset(frame.columns):
            log.warning(
                "  %s : colonnes manquantes %s, ignoré",
                year,
                sorted(required - set(frame.columns)),
            )
            continue

        for column in required:
            frame[column] = pd.to_numeric(
                frame[column].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            )
        frame = frame.dropna(subset=["xD", "yD", "xF", "yF", "TMJA"])
        # On garde toute section dont au moins une extrémité est dans l'emprise
        # (le point médian décidera ensuite du carreau d'appartenance).
        if bbox is not None:
            in_bbox = [
                frame[column].between(bbox[0], bbox[2])
                & frame[other].between(bbox[1], bbox[3])
                for column, other in (("xD", "yD"), ("xF", "yF"))
            ]
            frame = frame[in_bbox[0] | in_bbox[1]]
            if frame.empty:
                log.warning(
                    "  %s : aucune section dans l'emprise du département", year
                )
                continue

        geometry = [
            LineString([(x1, y1), (x2, y2)])
            for x1, y1, x2, y2 in zip(
                frame["xD"], frame["yD"], frame["xF"], frame["yF"]
            )
        ]
        gdf = gpd.GeoDataFrame(
            {
                "annee": int(year),
                "route": frame.get("route", pd.Series(index=frame.index, dtype=str)).astype(str),
                "TMJA": frame["TMJA"].astype(float),
            },
            geometry=geometry,
            crs=cfg.crs,
        )
        frames.append(gdf)
        log.info("  %s : %s sections", year, f"{len(gdf):,}")

    if not frames:
        raise RuntimeError("TMJA vide après filtrage spatial")

    result = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=cfg.crs)
    output = cfg.tmja_path
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    result.to_file(output, layer="tmja", driver="GPKG", engine="pyogrio")

    info = {
        "perimetre": cfg.perimetre,
        "n_sections": int(len(result)),
        "annees": sorted(int(v) for v in result["annee"].unique()),
        "output": str(output),
    }
    manifest.record("tmja", "ok", **info)
    return info


# ----------------------------------------------------------------------
# 5. MNT Copernicus 30 m
# ----------------------------------------------------------------------
def _copernicus_tile(lat: float, lon: float) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return (
        f"Copernicus_DSM_COG_10_{ns}{abs(int(lat)):02d}_00_"
        f"{ew}{abs(int(lon)):03d}_00_DEM"
    )


def download_dem(
    cfg: Config,
    manifest: Manifest,
    force: bool = False,
    resolution: float | None = None,
    record_name: str | None = None,
) -> dict[str, Any]:
    log.info(
        "MNT Copernicus DEM 30 m — département %s, lecture fenêtrée via /vsicurl",
        cfg.departement,
    )
    resolution = float(resolution or cfg.resolution_m)
    output = cfg.dem_path(resolution)
    if output.exists() and not force:
        log.info("  déjà présent : %s", output.name)
        manifest.record(
            record_name or "dem",
            "ok",
            departement=cfg.departement,
            output=str(output),
            cached=True,
            resolution_m=resolution,
        )
        return {"output": str(output), "cached": True}

    bbox = read_bbox(cfg)
    west, south, east, north = read_bbox_wgs84(cfg)
    grid = AnalysisGrid.from_bounds(bbox, resolution, cfg.crs)
    destination = np.full(grid.shape, np.nan, dtype="float32")

    base = cfg.sources["copernicus_dem"].rstrip("/")
    tiles_used: list[str] = []

    for lat in range(math.floor(south), math.floor(north) + 1):
        for lon in range(math.floor(west), math.floor(east) + 1):
            left, right = max(west, lon), min(east, lon + 1)
            bottom, top = max(south, lat), min(north, lat + 1)
            if left >= right or bottom >= top:
                continue
            tile = _copernicus_tile(lat, lon)
            url = f"/vsicurl/{base}/{tile}/{tile}.tif"
            try:
                with rasterio.Env(
                    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                    GDAL_HTTP_MULTIPLEX="YES",
                    GDAL_HTTP_VERSION="2",
                ):
                    with rasterio.open(url) as src:
                        window = from_bounds(left, bottom, right, top, src.transform)
                        data = src.read(1, window=window, masked=True)
                        if data.size == 0:
                            continue
                        source = data.astype("float32").filled(np.nan)
                        temporary = np.full(grid.shape, np.nan, dtype="float32")
                        reproject(
                            source=source,
                            destination=temporary,
                            src_transform=src.window_transform(window),
                            src_crs=src.crs,
                            dst_transform=grid.transform,
                            dst_crs=grid.crs,
                            resampling=Resampling.bilinear,
                            dst_nodata=np.nan,
                        )
                        valid = np.isfinite(temporary)
                        destination[valid] = temporary[valid]
                tiles_used.append(tile)
                log.info("  tuile %s OK", tile)
            except Exception as exc:  # tuile manquante / réseau
                log.warning("  tuile %s ignorée : %s", tile, exc)

    if not np.isfinite(destination).any():
        raise RuntimeError("Aucune donnée MNT récupérée")

    output.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        height=grid.height,
        width=grid.width,
        count=1,
        dtype="float32",
        crs=cfg.crs,
        transform=grid.transform,
        nodata=-9999.0,
        compress="deflate",
        tiled=True,
    ) as dst:
        dst.write(np.where(np.isfinite(destination), destination, -9999.0), 1)

    info = {
        "departement": cfg.departement,
        "output": str(output),
        "resolution_m": resolution,
        "tiles": tiles_used,
        "grid_shape": list(grid.shape),
    }
    manifest.record(record_name or "dem", "ok", **info)
    log.info("  -> %s (%s tuiles)", output.name, len(tiles_used))
    return info


# ----------------------------------------------------------------------
# 6. NASA FIRMS (optionnel)
# ----------------------------------------------------------------------
def download_firms(
    cfg: Config,
    client: DataGouvClient,
    manifest: Manifest,
    force: bool = False,
) -> dict[str, Any]:
    load_dotenv(cfg.root / ".env")
    api_key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if cfg.france:
        output = cfg.raw("firms", f"firms_{cfg.scope_label}.csv")
    else:
        output = cfg.raw("firms", f"firms_{cfg.departement}.csv")
    if not api_key:
        log.warning(
            "FIRMS ignoré : renseigner FIRMS_MAP_KEY dans ifm_plus/.env "
            "(clé gratuite sur firms.modaps.eosdis.nasa.gov/api/map_key)"
        )
        manifest.record(
            "firms", "skipped", reason="FIRMS_MAP_KEY absent", output=str(output)
        )
        return {"status": "skipped", "reason": "FIRMS_MAP_KEY absent"}

    if cfg.france:
        west, south, east, north = read_scope_bbox_wgs84(cfg)
    else:
        west, south, east, north = read_bbox_wgs84(cfg)
    day_range = int(cfg.firms.get("day_range", 5))
    source = str(cfg.firms.get("source", "VIIRS_SNPP_SP"))
    end = datetime.strptime(cfg.date_fin, "%Y-%m-%d")
    start = end - timedelta(days=day_range - 1)
    area = f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}"
    url = (
        f"{cfg.sources['firms_api']}/{api_key}/{source}/{area}/"
        f"{day_range}/{start:%Y-%m-%d}"
    )
    client.download(url, output, force=force)
    head = output.read_text(encoding="utf-8", errors="ignore")[:200]
    if not head.lower().startswith(("country_id", "latitude")):
        raise RuntimeError(f"Réponse FIRMS inattendue : {head[:120]}")

    info = {
        "output": str(output),
        "source": source,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }
    manifest.record("firms", "ok", **info)
    return info


# ----------------------------------------------------------------------
# 7. BDIFF : export manuel encadré
# ----------------------------------------------------------------------
BDIFF_README = """# BDIFF — dépôt manuel

Le portail BDIFF n'expose pas d'API de téléchargement en masse documentée.
La variable cible du projet est donc constituée à partir d'un export manuel :

1. Ouvrir https://bdiff.agriculture.gouv.fr/
2. Filtrer sur le périmètre **{perimetre}** et la période **{debut} → {fin}**.
3. Exporter en CSV (ou GeoJSON) et déposer le fichier dans ce dossier.
4. Vérifier que les colonnes suivantes existent (les noms peuvent varier) :
   - `date` ou `date_incendie` : date de départ ;
   - `x`, `y` (Lambert-93) ou `lon`, `lat` (WGS84) : localisation ;
   - `surface_ha` ou `surface` : surface brûlée ;
   - `commune`, `code_insee`, `cause` : contexte.

Le script `04_build_labels.py` normalisera ces colonnes. Sans export BDIFF,
les modèles peuvent être entraînés sur FIRMS (moins fiable : faux positifs
de détection, feux non détectés) mais le benchmark final doit utiliser BDIFF.

Pour les interventions SDIS, demander une convention d'accès au SDIS
départemental (données non ouvertes) : date/heure, commune, coordonnées,
surface, cause.
"""


def prepare_bdiff(
    cfg: Config,
    manifest: Manifest,
) -> dict[str, Any]:
    if cfg.france:
        folder = cfg.raw("manual", f"bdiff_{cfg.scope_label}")
        perimetre = (
            "France métropolitaine"
            if len(cfg.departements) == 96
            else "départements " + ", ".join(cfg.departements)
        )
    else:
        folder = cfg.raw("manual", "bdiff")
        perimetre = f"département {cfg.departement}"
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.md"
    if not readme.exists():
        readme.write_text(
            BDIFF_README.format(
                perimetre=perimetre,
                debut=cfg.date_debut,
                fin=cfg.date_fin,
            ),
            encoding="utf-8",
        )

    files = [
        path
        for pattern in ("*.csv", "*.geojson", "*.json", "*.gpkg", "*.xlsx")
        for path in folder.glob(pattern)
    ]
    if files:
        log.info("BDIFF : %s fichier(s) déposé(s)", len(files))
        manifest.record(
            "bdiff",
            "ok",
            files=[str(path) for path in files],
            source="export manuel BDIFF",
        )
        return {"status": "ok", "files": [str(path) for path in files]}

    log.warning(
        "BDIFF : aucun fichier dans %s — voir le README pour l'export manuel",
        folder,
    )
    manifest.record(
        "bdiff",
        "manual_required",
        instructions=str(readme),
        portal=cfg.sources.get("bdiff_slug"),
    )
    return {"status": "manual_required", "folder": str(folder)}


# ----------------------------------------------------------------------
# 8. Indices FWI Copernicus EWDS (optionnel)
# ----------------------------------------------------------------------
def download_weather(
    cfg: Config,
    manifest: Manifest,
    force: bool = False,
) -> dict[str, Any]:
    load_dotenv(cfg.root / ".env")
    scope_slug = cfg.scope_label if cfg.france else cfg.departement
    output = cfg.raw("weather", f"cems_fire_historical_{scope_slug}.nc")
    if output.exists() and not force:
        log.info("  déjà présent : %s", output.name)
        manifest.record("weather", "ok", output=str(output), cached=True)
        return {"output": str(output), "cached": True}

    try:
        import cdsapi
    except ImportError:
        log.warning(
            "EWDS ignoré : installer cdsapi (pip install cdsapi) et créer ~/.cdsapirc"
        )
        manifest.record("weather", "skipped", reason="cdsapi non installé")
        return {"status": "skipped", "reason": "cdsapi non installé"}

    if not (Path.home() / ".cdsapirc").exists() and not os.environ.get("CDSAPI_KEY"):
        log.warning(
            "EWDS ignoré : créer un compte sur ewds.climate.copernicus.eu, "
            "accepter la licence, puis configurer ~/.cdsapirc (url + key)"
        )
        manifest.record("weather", "skipped", reason="identifiants CDS absents")
        return {"status": "skipped", "reason": "identifiants CDS absents"}

    if cfg.france:
        west, south, east, north = read_scope_bbox_wgs84(cfg)
    else:
        west, south, east, north = read_bbox_wgs84(cfg)
    years = [str(year) for year in range(
        int(cfg.date_debut[:4]), int(cfg.date_fin[:4]) + 1
    )]
    months = [f"{month:02d}" for month in cfg.mois_saison]
    request = {
        "product_type": "reanalysis",
        "variable": cfg.weather.get("variables", []),
        "dataset_type": "consolidated_dataset",
        "system_version": ["4_1"],
        "year": years,
        "month": months,
        "day": [f"{day:02d}" for day in range(1, 32)],
        "grid": "0.25/0.25",
        "data_format": "netcdf",
        "area": [round(north, 4), round(west, 4), round(south, 4), round(east, 4)],
    }

    cds_url = os.environ.get(
        "CDSAPI_URL", "https://ewds.climate.copernicus.eu/api"
    )
    cds_key = os.environ.get("CDSAPI_KEY")
    client = (
        cdsapi.Client(url=cds_url, key=cds_key)
        if cds_key
        else cdsapi.Client(url=cds_url)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    log.info(
        "EWDS : requête %s (%s → %s, mois %s) — peut prendre plusieurs minutes",
        cfg.weather.get("dataset"),
        years[0],
        years[-1],
        months,
    )
    client.retrieve(
        cfg.weather.get("dataset", "cems-fire-historical-v1"),
        request,
        str(output),
    )

    info = {
        "output": str(output),
        "dataset": cfg.weather.get("dataset"),
        "years": years,
        "months": months,
        "variables": request["variable"],
    }
    manifest.record("weather", "ok", **info)
    return info


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
LayerFunction = Callable[..., dict[str, Any]]
