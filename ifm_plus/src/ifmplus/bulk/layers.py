"""Lecture des livraisons IGN et normalisation en GeoParquet.

Les archives bulk contiennent des GPKG « tous thèmes » (BD TOPO) ou des
shapefiles (BD Forêt), avec des noms de couches et de champs qui varient
légèrement selon les versions. Ce module isole cette variabilité :

- détection insensible à la casse des couches et des champs ;
- lecture **filtrée par emprise** (``bbox``) et colonnes utiles seulement ;
- reprojection systématique en Lambert-93 (EPSG:2154) ;
- écriture GeoParquet compressée ZSTD, directement relisible par
  ``geopandas.read_parquet`` (métadonnées GeoParquet conservées).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import pyogrio

log = logging.getLogger("ifmplus")

#: Champs utiles par couche logique (les noms réels sont détectés).
WANTED_FIELDS: dict[str, tuple[str, ...]] = {
    "forest": ("id", "code_tfv", "tfv", "tfv_g11", "essence"),
    "roads": ("cleabs", "importance", "nature", "etat_de_l_objet"),
    "habitat": ("cleabs", "nature", "importance"),
    "batiment": ("cleabs", "nature", "usage_1", "nombre_de_logements"),
    "rpg": ("id_parcel", "code_group", "code_cultu", "cat_cult_p", "surf_parc"),
}

#: Schéma minimal des couches vides (département sans entité).
EMPTY_SCHEMAS: dict[str, dict[str, str]] = {
    "forest": {"code_tfv": "string", "tfv": "string", "tfv_g11": "string", "essence": "string"},
    "roads": {
        "cleabs": "string",
        "importance": "float64",
        "nature": "string",
        "etat_de_l_objet": "string",
        "piste_dfci": "bool",
    },
    "habitat": {"cleabs": "string", "nature": "string", "importance": "float64"},
    "batiment": {
        "cleabs": "string",
        "nature": "string",
        "usage_1": "string",
        "nombre_de_logements": "float64",
    },
    "rpg": {
        "id_parcel": "string",
        "code_group": "string",
        "code_cultu": "string",
        "cat_cult_p": "string",
        "surf_parc": "float64",
    },
}


class LayerError(RuntimeError):
    pass


def _field_lookup(fields: Iterable[str]) -> dict[str, str]:
    return {str(field).lower(): str(field) for field in fields}


def _select_columns(available: Iterable[str], wanted: Iterable[str]) -> list[str]:
    lookup = _field_lookup(available)
    return [lookup[name.lower()] for name in wanted if name.lower() in lookup]


def _normalise_columns(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return frame.rename(columns={column: str(column).lower() for column in frame.columns})


def find_layer(gpkg: Path, logical: str) -> str | None:
    """Retrouve une couche par son nom logique (insensible à la casse)."""
    aliases = {
        "roads": ("troncon_de_route",),
        "habitat": ("zone_d_habitation",),
        "batiment": ("batiment",),
        "rpg": ("rpg_parcelles", "parcelles_graphiques", "parcelles"),
        "forest": ("formation_vegetale",),
    }.get(logical, (logical,))
    names = [name for name, _ in pyogrio.list_layers(gpkg)]
    lookup = {name.lower(): name for name in names}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    for name in names:
        if any(alias in name.lower() for alias in aliases):
            return name
    return None


def read_forest(path: Path, bbox, crs: str) -> gpd.GeoDataFrame:
    """Lit la formation végétale (shapefile ou GPKG) et la reprojette."""
    layer = None
    if path.suffix.lower() == ".gpkg":
        layer = find_layer(path, "forest")
    columns = _select_columns(pyogrio.read_info(path, layer=layer)["fields"], WANTED_FIELDS["forest"])
    frame = pyogrio.read_dataframe(path, layer=layer, columns=columns, bbox=bbox)
    frame = _normalise_columns(frame)
    for column, dtype in EMPTY_SCHEMAS["forest"].items():
        if column not in frame.columns:
            frame[column] = pd.Series(index=frame.index, dtype=dtype)
    if frame.crs is None:
        raise LayerError(f"CRS absent dans {path}")
    if frame.crs.to_string() != crs:
        frame = frame.to_crs(crs)
    return frame[["code_tfv", "tfv", "tfv_g11", "essence", "geometry"]]


def read_bdtopo(
    gpkg: Path,
    bbox,
    crs: str,
    *,
    layers: tuple[str, ...] = ("roads", "habitat", "batiment"),
) -> dict[str, gpd.GeoDataFrame]:
    """Lit les couches BD TOPO utiles, une par une, filtrées par emprise."""
    result: dict[str, gpd.GeoDataFrame] = {}
    for logical in layers:
        layer = find_layer(gpkg, logical)
        if layer is None:
            log.warning("  couche BD TOPO %s absente de %s", logical, gpkg.name)
            result[logical] = empty_layer(logical, crs)
            continue
        wanted = WANTED_FIELDS[logical]
        columns = _select_columns(pyogrio.read_info(gpkg, layer=layer)["fields"], wanted)
        log.info("  lecture BD TOPO %s…", layer)
        frame = pyogrio.read_dataframe(gpkg, layer=layer, columns=columns, bbox=bbox)
        frame = _normalise_columns(frame)
        for column, dtype in EMPTY_SCHEMAS[logical].items():
            if column not in frame.columns:
                frame[column] = pd.Series(index=frame.index, dtype=dtype)
        if frame.crs is None:
            raise LayerError(f"CRS absent dans la couche {layer}")
        if frame.crs.to_string() != crs:
            frame = frame.to_crs(crs)
        keep = [column for column in EMPTY_SCHEMAS[logical] if column in frame.columns]
        result[logical] = frame[keep + ["geometry"]]
        del frame
    return result


def read_rpg(path: Path, bbox, crs: str) -> gpd.GeoDataFrame:
    """Lit les parcelles RPG (couche ``RPG_Parcelles`` du GPKG 4.0)."""
    layer = find_layer(path, "rpg")
    columns = _select_columns(pyogrio.read_info(path, layer=layer)["fields"], WANTED_FIELDS["rpg"])
    frame = pyogrio.read_dataframe(path, layer=layer, columns=columns, bbox=bbox)
    frame = _normalise_columns(frame)
    for column, dtype in EMPTY_SCHEMAS["rpg"].items():
        if column not in frame.columns:
            frame[column] = pd.Series(index=frame.index, dtype=dtype)
    if frame.crs is None:
        raise LayerError(f"CRS absent dans {path}")
    if frame.crs.to_string() != crs:
        frame = frame.to_crs(crs)
    return frame[["id_parcel", "code_group", "code_cultu", "cat_cult_p", "surf_parc", "geometry"]]


def empty_layer(logical: str, crs: str) -> gpd.GeoDataFrame:
    """GeoDataFrame vide avec le schéma attendu par les fonctions de features."""
    schema = EMPTY_SCHEMAS[logical]
    return gpd.GeoDataFrame(
        {column: pd.Series(dtype=dtype) for column, dtype in schema.items()},
        geometry=gpd.GeoSeries([], dtype="geometry"),
        crs=crs,
    )


def write_parquet(frame: gpd.GeoDataFrame, path: Path) -> Path:
    """Écrit un GeoParquet ZSTD (métadonnées géographiques incluses)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    frame.to_parquet(path, index=False, compression="zstd")
    return path


def read_parquet(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"GeoParquet absent : {path}")
    return gpd.read_parquet(path)
