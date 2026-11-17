"""Construction des features DFCI à partir des couches bulk normalisées.

Ce module est le pendant « bulk » de ``scripts/02_build_static_features.py``.
Il réutilise les mêmes fonctions de calcul (``compute_forest_features``,
``compute_relief_features``, ``compute_road_features``, etc.) mais lit des
GeoParquet produits par :mod:`ifmplus.bulk.download` au lieu des couches WFS.

Le calcul reste **département par département** : une grille raster à 25 m et
les masques associés tiennent largement en mémoire, puis sont libérés avant le
département suivant. Le voisinage 3×3 est calculé après assemblage national
pour éviter toute couture aux frontières.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from ..config import Config
from ..features import (
    AGRICULTURAL_GROUPS,
    compute_agri_features,
    compute_building_features,
    compute_commune_features,
    compute_forest_features,
    compute_habitat_features,
    compute_relief_features,
    compute_road_features,
)
from ..geoutils import clamp_fractions, read_bbox
from ..raster import AnalysisGrid
from .layers import empty_layer, read_parquet

log = logging.getLogger("ifmplus")

FOREST_COLUMNS = [
    "foret_frac",
    "resineux_frac",
    "feuillus_frac",
    "mixte_frac",
    "peupleraie_frac",
    "lande_frac",
    "foret_fermee_frac",
    "foret_ouverte_frac",
    "foret_sans_couvert_frac",
    "pin_frac",
    "lisiere_m_ha",
]

RELIEF_COLUMNS = [
    "alt_moy_m",
    "alt_min_m",
    "alt_max_m",
    "alt_std_m",
    "pente_moy_deg",
    "pente_max_deg",
    "frac_pente_sup15",
    "frac_pente_sup25",
    "aspect_moyen_deg",
    "aspect_sin",
    "aspect_cos",
    "aspect_concentration",
    "exposition_dominante",
    "exposition_dominante_code",
    "exposition_dominante_frac",
]

HABITAT_COLUMNS = [
    "habitat_frac",
    "wui_frac",
    "part_habitat_wui",
    "contact_habitat_foret_m_ha",
]

BUILDING_COLUMNS = [
    "batiment_frac",
    "batiment_n",
    "batiment_n_km2",
    "batiment_residentiel_frac",
    "contact_bati_foret_m_ha",
]

ROAD_COLUMNS = [
    "route_km",
    "route_km_km2",
    "route_principale_km",
    "route_dfci_km",
    "route_ponderee_km",
    "route_totale_km",
    "route_totale_km_km2",
    "route_chemin_km",
    "route_chemin_km_km2",
    "distance_route_principale_m",
    "tmja_max",
    "tmja_moyen_pondere",
    "exposition_tmja",
]

AGRI_COLUMNS = [
    "agri_frac",
    *AGRICULTURAL_GROUPS.keys(),
    "prairie_permanente_frac",
    "culture_permanente_frac",
    "terre_arable_frac",
]

FRACTION_COLUMNS = [
    "frac_dans_dept",
    "foret_frac",
    "resineux_frac",
    "feuillus_frac",
    "mixte_frac",
    "peupleraie_frac",
    "lande_frac",
    "foret_fermee_frac",
    "foret_ouverte_frac",
    "foret_sans_couvert_frac",
    "pin_frac",
    "foret_frac_1km",
    "frac_pente_sup15",
    "frac_pente_sup25",
    "habitat_frac",
    "wui_frac",
    "part_habitat_wui",
    "batiment_frac",
    "batiment_residentiel_frac",
    "agri_frac",
    "agri_frac_1km",
    "habitat_frac_1km",
    "wui_frac_1km",
    *AGRICULTURAL_GROUPS.keys(),
    "prairie_permanente_frac",
    "culture_permanente_frac",
    "terre_arable_frac",
]

BULK_SKIPPABLE = {"forest", "relief", "habitat", "batiment", "roads", "rpg"}


def _empty(cells: gpd.GeoDataFrame, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})
    for column in columns:
        frame[column] = np.nan
    return frame


def _zeros(cells: gpd.GeoDataFrame, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})
    for column in columns:
        frame[column] = 0.0
    return frame


def _load(cfg: Config, layer: str, dept: str) -> gpd.GeoDataFrame | None:
    path = cfg.bulk_layer(layer, dept)
    if not path.exists():
        log.warning(
            "%s absent (%s) — features à NaN (lancer 10_bulk_download.py)",
            layer,
            path,
        )
        return None
    log.info("Lecture bulk %s…", path.name)
    return read_parquet(path)


def _read_tmja(cfg: Config, bbox) -> gpd.GeoDataFrame | None:
    path = cfg.tmja_path
    if not path.exists():
        log.warning("TMJA absent (%s) — trafic à NaN", path)
        return None
    try:
        return gpd.read_file(path, bbox=bbox, engine="pyogrio")
    except Exception as exc:  # noqa: BLE001 — GPKG sans index spatial
        log.warning("TMJA : lecture par emprise impossible (%s), lecture complète", exc)
        return gpd.read_file(path, engine="pyogrio")


def build_department(
    cfg: Config,
    cells: gpd.GeoDataFrame,
    resolution: float,
    skip: set[str] | None = None,
    *,
    commune_features: pd.DataFrame | None = None,
    neighbourhood: bool = False,
) -> pd.DataFrame:
    """Features statiques d'un département à partir des GeoParquet bulk."""
    skip = skip or set()
    dept = cfg.departement
    global_ids = cells["cell_id"].to_numpy()
    local = cells.copy()
    local["cell_id"] = np.arange(1, len(cells) + 1, dtype="int32")

    bbox = read_bbox(cfg)
    grid = AnalysisGrid.from_bounds(bbox, resolution, cfg.crs)
    labels = grid.rasterize(
        local.assign(_cell_id=local["cell_id"]),
        values="_cell_id",
        dtype="int32",
        fill=0,
        all_touched=True,
    )
    zonal = grid.zonal(labels, len(local))
    log.info("  grille d'analyse : %s × %s pixels", grid.width, grid.height)

    # ------------------------------------------------------------------
    # Combustible
    # ------------------------------------------------------------------
    forest = None if "forest" in skip else _load(cfg, "forest", dept)
    forest_mask = np.zeros(grid.shape, dtype=bool)
    if forest is not None and len(forest):
        forest_features, masks = compute_forest_features(local, forest, grid, zonal)
        forest_mask = masks["forest"]
    elif forest is not None:
        forest_features = _zeros(local, FOREST_COLUMNS)
    else:
        forest_features = _empty(local, FOREST_COLUMNS)

    # ------------------------------------------------------------------
    # Relief
    # ------------------------------------------------------------------
    dem_path = cfg.bulk_raw("dem", f"dem_{dept}_{int(resolution)}m.tif")
    if "relief" in skip or not dem_path.exists():
        if "relief" not in skip:
            log.warning("MNT bulk absent (%s) — relief à NaN", dem_path)
        relief_features = _empty(local, RELIEF_COLUMNS)
    else:
        relief_features = compute_relief_features(local, dem_path, grid, zonal)

    # ------------------------------------------------------------------
    # Habitat, bâti et interface
    # ------------------------------------------------------------------
    habitat = None if "habitat" in skip else _load(cfg, "habitat", dept)
    if habitat is not None and len(habitat) and forest is not None and len(forest):
        habitat_features, _ = compute_habitat_features(
            local, habitat, forest_mask, grid, zonal
        )
    elif habitat is not None and len(habitat):
        habitat_mask = grid.rasterize(habitat, dtype="uint8", fill=0) > 0
        habitat_features = _zeros(local, HABITAT_COLUMNS)
        habitat_features["habitat_frac"] = zonal.frac(habitat_mask)
    elif habitat is not None:
        habitat_features = _zeros(local, HABITAT_COLUMNS)
    else:
        habitat_features = _empty(local, HABITAT_COLUMNS)

    batiment = None if "batiment" in skip else _load(cfg, "batiment", dept)
    if batiment is not None and len(batiment):
        building_features = compute_building_features(
            local, batiment, forest_mask, grid, zonal
        )
    elif batiment is not None:
        building_features = _zeros(local, BUILDING_COLUMNS)
    else:
        building_features = _empty(local, BUILDING_COLUMNS)

    # ------------------------------------------------------------------
    # Routes et trafic
    # ------------------------------------------------------------------
    roads = None if "roads" in skip else _load(cfg, "roads", dept)
    tmja = None if "roads" in skip else _read_tmja(cfg, bbox)
    if roads is not None and len(roads):
        road_features = compute_road_features(
            local, roads, tmja, tmja_year=cfg.tmja_annee
        )
    elif roads is not None:
        road_features = _zeros(local, ROAD_COLUMNS)
        for column in (
            "distance_route_principale_m",
            "tmja_max",
            "tmja_moyen_pondere",
            "exposition_tmja",
        ):
            road_features[column] = np.nan
    else:
        road_features = _empty(local, ROAD_COLUMNS)

    # ------------------------------------------------------------------
    # Agriculture
    # ------------------------------------------------------------------
    rpg = None if "rpg" in skip else _load(cfg, "rpg", dept)
    if rpg is not None and len(rpg):
        agri_features = compute_agri_features(local, rpg, grid, zonal)
    elif rpg is not None:
        agri_features = _zeros(local, AGRI_COLUMNS)
    else:
        agri_features = _empty(local, AGRI_COLUMNS)

    # ------------------------------------------------------------------
    # Commune et assemblage
    # ------------------------------------------------------------------
    if commune_features is not None:
        commune_part = (
            commune_features.set_index("cell_id")
            .reindex(global_ids)
            .reset_index(drop=True)
        )
        commune_part.insert(0, "cell_id", local["cell_id"].to_numpy())
        if "nom_commune" not in commune_part.columns:
            commune_part["nom_commune"] = pd.NA
    else:
        communes_path = cfg.communes_scope_path
        if communes_path.exists():
            communes = gpd.read_file(communes_path, engine="pyogrio")
            commune_part = compute_commune_features(local, communes)
        else:
            commune_part = _empty(local, ["code_insee", "nom_commune"])

    context = [
        "cell_id",
        "id_carreau_dfci",
        "area_ha",
        "frac_dans_dept",
        "x_centroid",
        "y_centroid",
        "lon",
        "lat",
    ]
    if "dept" in local.columns:
        context.insert(2, "dept")
    features = local[context].copy()
    if "dept" in features.columns:
        features = features.rename(columns={"dept": "departement"})

    for part in (
        forest_features,
        relief_features,
        habitat_features,
        building_features,
        road_features,
        agri_features,
        commune_part,
    ):
        features = features.merge(part, on="cell_id", how="left", validate="one_to_one")

    if neighbourhood:
        from ..features import NEIGHBOURHOOD_SOURCES, add_neighbourhood_features

        features = add_neighbourhood_features(
            features,
            features[["x_centroid", "y_centroid"]],
            tuple(NEIGHBOURHOOD_SOURCES),
        )

    features["code_insee"] = features["code_insee"].astype("string")
    features["nom_commune"] = features["nom_commune"].astype("string")

    # Retour aux identifiants globaux (mode France).
    lookup = pd.Series(
        global_ids, index=np.arange(1, len(global_ids) + 1, dtype="int32")
    )
    features["cell_id"] = features["cell_id"].map(lookup).astype("int32")

    clamp_fractions(features, FRACTION_COLUMNS)
    return features
