"""Calcul des features statiques du score IFM+."""

from .catalog import NEIGHBOURHOOD_SOURCES, STATIC_FEATURES
from .forest import compute_forest_features
from .human import (
    AGRICULTURAL_GROUPS,
    compute_agri_features,
    compute_building_features,
    compute_commune_features,
    compute_habitat_features,
    compute_road_features,
)
from .neighbourhood import add_neighbourhood_features
from .relief import compute_relief_features

__all__ = [
    "STATIC_FEATURES",
    "NEIGHBOURHOOD_SOURCES",
    "AGRICULTURAL_GROUPS",
    "compute_forest_features",
    "compute_relief_features",
    "compute_habitat_features",
    "compute_building_features",
    "compute_road_features",
    "compute_agri_features",
    "compute_commune_features",
    "add_neighbourhood_features",
]
