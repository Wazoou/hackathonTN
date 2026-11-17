"""Téléchargement WFS 2.0 depuis la Géoplateforme IGN.

Le service WFS de ``data.geopf.fr`` permet de filtrer spatialement côté
serveur (BBOX) et attributairement (CQL), ce qui évite de télécharger la
France entière. On pagine avec ``STARTINDEX`` / ``COUNT`` et on demande
directement la projection Lambert-93.

Deux précautions sont indispensables en pratique :

1. **Découpage en tuiles** : la pagination profonde (``STARTINDEX`` élevé)
   est lente et le serveur coupe parfois la connexion. On découpe donc
   l'emprise en tuiles de ``tile_size_m`` et on pagine indépendamment dans
   chaque tuile (puis on déduplique les entités à cheval).
2. **Retries par tuile** : une tuile qui échoue est retentée ; un échec
   isolé n'invalide pas tout le téléchargement, mais on refuse de produire
   une couche trouée si trop de tuiles échouent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from time import sleep
from typing import Any

import geopandas as gpd
import requests
from shapely.geometry import shape

from .datagouv import make_session

log = logging.getLogger("ifmplus")


@dataclass(frozen=True)
class WfsLayer:
    """Description d'une couche WFS et de ses particularités."""

    name: str
    geom_field: str = "geometrie"
    property_name: str | None = None
    page_size: int = 5000
    extra_cql: str | None = None
    #: Taille des tuiles de téléchargement (mètres). ``None`` = emprise entière.
    tile_size_m: float | None = None
    #: Propriété servant à dédupliquer les entités à cheval sur deux tuiles.
    id_property: str | None = None


def _dedupe_key(
    properties: dict[str, Any],
    layer: WfsLayer,
    geometry: Any,
) -> str:
    """Clé de déduplication d'une entité (tuiles adjacentes).

    On privilégie l'identifiant métier ; s'il n'est pas exposé par la requête
    (``PROPERTYNAME`` trop restrictif), on retombe sur l'empreinte de la
    géométrie pour ne **jamais** fusionner deux entités distinctes.
    """
    if layer.id_property:
        value = properties.get(layer.id_property)
        if value not in (None, ""):
            return f"id:{value}"
    return f"geom:{hashlib.sha1(geometry.wkb).hexdigest()}"


def bbox_cql(bbox: tuple[float, float, float, float], geom_field: str) -> str:
    xmin, ymin, xmax, ymax = bbox
    return (
        f"BBOX({geom_field},{xmin:.3f},{ymin:.3f},"
        f"{xmax:.3f},{ymax:.3f},'EPSG:2154')"
    )


def split_bbox(
    bbox: tuple[float, float, float, float],
    tile_size: float,
) -> list[tuple[float, float, float, float]]:
    """Découpe une bbox Lambert-93 en tuiles carrées de ``tile_size`` m."""
    xmin, ymin, xmax, ymax = bbox
    ncols = max(1, int(-(-(xmax - xmin) // tile_size)))
    nrows = max(1, int(-(-(ymax - ymin) // tile_size)))
    tiles: list[tuple[float, float, float, float]] = []
    for row in range(nrows):
        for col in range(ncols):
            x0 = xmin + col * tile_size
            y0 = ymin + row * tile_size
            tiles.append(
                (
                    x0,
                    y0,
                    min(x0 + tile_size, xmax),
                    min(y0 + tile_size, ymax),
                )
            )
    return tiles


def _get_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    attempts: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, params=params, timeout=(30, 240))
            if response.status_code == 400:
                raise ValueError(
                    "Requête WFS invalide : "
                    + response.text.replace("\n", " ")[:800]
                )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == attempts or isinstance(exc, ValueError):
                break
            wait = 2**attempt
            log.warning(
                "  WFS tentative %s/%s échouée (%s), nouvel essai dans %ss",
                attempt,
                attempts,
                type(exc).__name__,
                wait,
            )
            sleep(wait)
    raise RuntimeError(f"Échec WFS après {attempts} tentatives : {last_error}")


def _fetch_extent(
    session: requests.Session,
    wfs_url: str,
    layer: WfsLayer,
    bbox: tuple[float, float, float, float] | None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Récupère une emprise complète, page par page."""
    clauses: list[str] = []
    if bbox is not None:
        clauses.append(bbox_cql(bbox, layer.geom_field))
    if layer.extra_cql:
        clauses.append(f"({layer.extra_cql})")

    params: dict[str, Any] = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": layer.name,
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:2154",
        "COUNT": layer.page_size,
    }
    if clauses:
        params["CQL_FILTER"] = " AND ".join(clauses)
    if layer.property_name:
        params["PROPERTYNAME"] = layer.property_name

    records: list[dict[str, Any]] = []
    geometries: list[Any] = []
    start = 0
    matched: int | None = None
    pages = 0

    while True:
        params["STARTINDEX"] = start
        payload = _get_json(session, wfs_url, params)

        if matched is None:
            raw = payload.get("numberMatched")
            matched = int(raw) if raw is not None else None

        features = payload.get("features") or []
        if not features:
            break

        for feature in features:
            geometry = feature.get("geometry")
            if geometry is None:
                continue
            geometries.append(shape(geometry))
            records.append(feature.get("properties") or {})

        pages += 1
        start += len(features)
        if matched is not None and start >= matched:
            break
        if matched is None and len(features) < layer.page_size:
            break
        if pages > 5_000:
            raise RuntimeError("Boucle WFS suspecte (> 5 000 pages)")

    return records, geometries


def download_wfs(
    wfs_url: str,
    layer: WfsLayer,
    destination,
    bbox: tuple[float, float, float, float] | None = None,
    force: bool = False,
    max_features: int | None = None,
) -> gpd.GeoDataFrame:
    """Télécharge une couche WFS filtrée sur une bbox Lambert-93.

    Args:
        wfs_url: endpoint WFS (ex. https://data.geopf.fr/wfs/ows).
        layer: description de la couche.
        destination: chemin GPKG de sortie.
        bbox: (xmin, ymin, xmax, ymax) en EPSG:2154. ``None`` = pas de filtre
            spatial (utile pour les contours administratifs).
        force: retélécharge même si le fichier existe.
        max_features: plafond de sécurité pour les tests.

    Returns:
        GeoDataFrame téléchargé (même s'il était déjà sur disque).
    """
    if destination.exists() and not force:
        log.info("  déjà présent : %s", destination.name)
        return gpd.read_file(destination, engine="pyogrio")

    session = make_session()
    if bbox is not None and layer.tile_size_m:
        tiles = split_bbox(bbox, layer.tile_size_m)
    else:
        tiles = [bbox]

    log.info(
        "  %s : %s tuile(s) de %.0f km",
        layer.name,
        len(tiles),
        (layer.tile_size_m or 0) / 1000,
    )

    all_records: list[dict[str, Any]] = []
    all_geometries: list[Any] = []
    seen: set[str] = set()
    failed_tiles: list[tuple[float, float, float, float]] = []

    for index, tile in enumerate(tiles, start=1):
        records: list[dict[str, Any]] = []
        geometries: list[Any] = []
        for attempt in (1, 2):
            try:
                records, geometries = _fetch_extent(session, wfs_url, layer, tile)
                break
            except Exception as exc:  # noqa: BLE001 — retry tuile
                if attempt == 2:
                    log.error(
                        "  tuile %s/%s échouée (%s)", index, len(tiles), exc
                    )
                    failed_tiles.append(tile)  # type: ignore[arg-type]
                else:
                    log.warning(
                        "  tuile %s/%s : reprise après %s",
                        index,
                        len(tiles),
                        type(exc).__name__,
                    )
                    sleep(3)

        if index == 1 or index % 5 == 0 or index == len(tiles):
            log.info(
                "    tuile %s/%s : %s entités reçues",
                index,
                len(tiles),
                f"{len(records):,}",
            )

        for properties, geometry in zip(records, geometries):
            key = _dedupe_key(properties, layer, geometry)
            if key in seen:
                continue
            seen.add(key)
            all_records.append(properties)
            all_geometries.append(geometry)

        if index == 1 or index % 5 == 0 or index == len(tiles):
            log.info(
                "    tuile %s/%s terminée : %s entités cumulées",
                index,
                len(tiles),
                f"{len(all_records):,}",
            )

        if max_features and len(all_records) >= max_features:
            all_records = all_records[:max_features]
            all_geometries = all_geometries[:max_features]
            break

        time.sleep(0.2)  # politesse envers le service

    if failed_tiles:
        ratio = len(failed_tiles) / len(tiles)
        log.error(
            "  %s : %s/%s tuiles en échec (%.0f %%)",
            layer.name,
            len(failed_tiles),
            len(tiles),
            100 * ratio,
        )
        if ratio > 0.1:
            raise RuntimeError(
                f"{len(failed_tiles)} tuiles WFS sur {len(tiles)} ont échoué "
                f"pour {layer.name} : couche incomplète, relancer la commande."
            )

    if not all_records:
        raise RuntimeError(
            f"Aucune entité téléchargée pour {layer.name} "
            f"(bbox={bbox}, cql={layer.extra_cql})"
        )

    gdf = gpd.GeoDataFrame(
        all_records, geometry=all_geometries, crs="EPSG:2154"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    gdf.to_file(
        destination, layer=destination.stem, driver="GPKG", engine="pyogrio"
    )
    log.info("  -> %s : %s entités", destination.name, f"{len(gdf):,}")
    return gdf


def read_bbox(path) -> tuple[float, float, float, float]:
    """Relit une bbox Lambert-93 depuis le JSON intermédiaire."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(float(v) for v in payload["bbox_2154"])  # type: ignore[return-value]
