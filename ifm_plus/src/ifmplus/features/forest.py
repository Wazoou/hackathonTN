"""Features de combustible issues de la BD Forêt V2.

La BD Forêt V2 décrit les formations végétales (tfv) et l'essence dominante.
On agrège ces informations en classes d'inflammabilité utiles pour le risque :

- résineux (dont pins, très inflammables) ;
- feuillus ;
- mélange ;
- peupleraie ;
- lande / formation herbacée (combustible fin) ;
- forêt sans couvert arboré (contexte).

Le calcul se fait sur une grille raster de 25 m, puis agrégation par carreau
DFCI : plus rapide et homogène avec les autres couches.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from ..raster import AnalysisGrid, ZonalStats, edge_length_m
from .typo import strip_accents

log = logging.getLogger("ifmplus")

# Codes de base (unités) ; les dizaines codent "forêt fermée" et les
# centaines le flag "pin".
TYPE_RESINEUX = 1
TYPE_FEUILLU = 2
TYPE_MIXTE = 3
TYPE_PEUPLERAIE = 4
TYPE_LANDE = 5
TYPE_AUTRE_FORET = 6
TYPE_SANS_COUVERT = 7

FOREST_TYPES = {TYPE_RESINEUX, TYPE_FEUILLU, TYPE_MIXTE, TYPE_PEUPLERAIE,
                TYPE_AUTRE_FORET, TYPE_SANS_COUVERT}


def _classify(forest: gpd.GeoDataFrame) -> np.ndarray:
    tfv = strip_accents(forest["tfv"])
    essence = strip_accents(forest["essence"])

    is_lande = tfv.str.contains("lande|formation herbacee", regex=True)
    is_sans_couvert = tfv.str.contains("sans couvert")
    is_peupleraie = tfv.str.contains("peupleraie") | essence.eq("peuplier")
    is_mixte = tfv.str.contains("melange") | essence.eq("mixte")
    is_conif = tfv.str.contains("conifere|pin") | essence.str.contains("conifere|pin")
    is_feuillu = (
        tfv.str.contains("feuillu|chene|robinier|chataignier")
        | essence.str.contains("feuillu|chene|robinier|chataignier")
    )
    is_forest = tfv.str.startswith("foret") | tfv.str.contains("peupleraie")

    base = np.select(
        [is_lande, is_sans_couvert, is_peupleraie, is_mixte, is_conif,
         is_feuillu, is_forest],
        [TYPE_LANDE, TYPE_SANS_COUVERT, TYPE_PEUPLERAIE, TYPE_MIXTE,
         TYPE_RESINEUX, TYPE_FEUILLU, TYPE_AUTRE_FORET],
        default=0,
    ).astype("int16")

    closed = tfv.str.contains("fermee").to_numpy()
    pin = (tfv.str.contains("pin") | essence.str.contains("pin")).to_numpy()
    forest_flag = np.isin(base, list(FOREST_TYPES))

    # Encodage compact : unités = type, dizaines = fermé, centaines = pin.
    codes = base + 10 * (closed & forest_flag).astype("int16") + 100 * (
        pin & forest_flag
    ).astype("int16")
    return codes


def compute_forest_features(
    cells: gpd.GeoDataFrame,
    forest: gpd.GeoDataFrame,
    grid: AnalysisGrid,
    zonal: ZonalStats,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Calcule les fractions de combustible et renvoie aussi les masques.

    Returns:
        (DataFrame indexé par cell_id, masques utiles au WUI)
    """
    log.info("Rasterisation BD Forêt V2 (%s polygones)…", f"{len(forest):,}")
    forest = forest.to_crs(grid.crs)
    codes = _classify(forest)
    forest_codes = grid.rasterize(
        forest.assign(_code=codes), values="_code", dtype="int16", fill=0
    )

    type_code = forest_codes % 10
    is_closed = (forest_codes // 10) % 10 == 1
    is_pin = (forest_codes // 100) >= 1
    forest_mask = np.isin(type_code, list(FOREST_TYPES))

    n = len(cells)
    features = pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})

    features["foret_frac"] = zonal.frac(forest_mask)
    features["resineux_frac"] = zonal.frac(type_code == TYPE_RESINEUX)
    features["feuillus_frac"] = zonal.frac(type_code == TYPE_FEUILLU)
    features["mixte_frac"] = zonal.frac(type_code == TYPE_MIXTE)
    features["peupleraie_frac"] = zonal.frac(type_code == TYPE_PEUPLERAIE)
    features["lande_frac"] = zonal.frac(type_code == TYPE_LANDE)
    features["foret_fermee_frac"] = zonal.frac(forest_mask & is_closed)
    features["foret_ouverte_frac"] = zonal.frac(forest_mask & ~is_closed)
    features["foret_sans_couvert_frac"] = zonal.frac(
        type_code == TYPE_SANS_COUVERT
    )
    features["pin_frac"] = zonal.frac(forest_mask & is_pin)

    lisiere = edge_length_m(
        labels=zonal.labels,
        mask=forest_mask,
        resolution=grid.resolution,
        n_cells=n,
    )
    features["lisiere_m_ha"] = lisiere / cells["area_ha"].to_numpy()

    masks = {
        "forest": forest_mask,
        "fuel": np.isin(type_code, [TYPE_RESINEUX, TYPE_FEUILLU, TYPE_MIXTE,
                                    TYPE_PEUPLERAIE, TYPE_LANDE]),
    }
    log.info(
        "  forêt moyenne : %.1f %% du département",
        100 * np.nanmean(features["foret_frac"]),
    )
    return features, masks
