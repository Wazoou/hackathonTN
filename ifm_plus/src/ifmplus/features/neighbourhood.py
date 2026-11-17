"""Features de voisinage : continuité du massif et pression à 1-2 km.

Les carreaux DFCI sont jointifs. On calcule, pour chaque maille, la moyenne
des features dans les 8 mailles voisines (fenêtre 3x3, soit environ 2 km).
Cela capture les effets de masse : un petit bois isolé ne se comporte pas
comme le cœur d'un massif forestier.
"""

from __future__ import annotations

import logging
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

log = logging.getLogger("ifmplus")


def add_neighbourhood_features(
    features: pd.DataFrame,
    cells: gpd.GeoDataFrame,
    sources: tuple[str, ...],
) -> pd.DataFrame:
    coords = np.column_stack(
        [cells["x_centroid"].to_numpy(), cells["y_centroid"].to_numpy()]
    )
    n = len(coords)
    k = min(9, n)
    tree = cKDTree(coords)
    _, indices = tree.query(coords, k=k)
    if k == 1:
        indices = indices[:, None]

    result = features.copy()
    for column in sources:
        if column not in result.columns:
            continue
        values = result[column].to_numpy(dtype="float64")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            result[f"{column}_1km"] = np.nanmean(values[indices], axis=1)
    log.info("  voisinage 3x3 calculé pour %s variables", len(sources))
    return result
