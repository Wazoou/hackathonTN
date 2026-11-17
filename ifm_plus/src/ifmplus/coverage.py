"""Contrôles de couverture : une table Gironde ne constitue pas une table France."""
from __future__ import annotations

import pandas as pd
import json
from pathlib import Path

from .config import Config, normalize_dept


def valid_bulk_dem(path: Path) -> bool:
    metadata = path.with_suffix(".json")
    try:
        return path.is_file() and path.stat().st_size > 0 and json.loads(metadata.read_text()).get("mosaic_version") == 2
    except (OSError, ValueError):
        return False


def validate_coverage(features: pd.DataFrame, expected_cells: pd.DataFrame, cfg: Config) -> dict:
    """Vérifie les départements et chaque identifiant du maillage attendu."""
    expected = expected_cells[expected_cells["dept"].isin(cfg.departements)]
    wanted = set(cfg.departements)
    present = set(features["departement"].dropna().map(normalize_dept))
    missing, extra = wanted - present, present - wanted
    if missing or extra:
        raise ValueError(f"Couverture départementale incomplète : absents={sorted(missing)}, hors périmètre={sorted(extra)}")
    for column in ("cell_id", "id_carreau_dfci"):
        if features[column].isna().any() or features[column].duplicated().any():
            raise ValueError(f"Identifiants {column} absents ou dupliqués")
        absent = set(expected[column]) - set(features[column])
        unexpected = set(features[column]) - set(expected[column])
        if absent or unexpected:
            raise ValueError(f"Maillage incomplet ({column}) : {len(absent)} absents, {len(unexpected)} inattendus")
    actual = features.set_index("cell_id").sort_index()
    reference = expected.set_index("cell_id").sort_index()
    if (actual["id_carreau_dfci"].to_numpy() != reference["id_carreau_dfci"].to_numpy()).any():
        raise ValueError("Association cell_id / id_carreau_dfci incohérente")
    if (actual["departement"].map(normalize_dept).to_numpy() != reference["dept"].to_numpy()).any():
        raise ValueError("Affectation départementale incohérente avec le maillage")
    return {"complete": True, "n_departements": len(present), "n_cells": len(features),
            "cells_by_department": {str(k): int(v) for k, v in features.groupby("departement").size().items()}}


def missing_bulk_inputs(cfg: Config, resolution: float, skip: set[str]) -> dict[str, list[str]]:
    """Distingue une couche absente d'une couche réellement vide."""
    missing = {}
    for dept in cfg.departements:
        paths = {layer: cfg.bulk_layer(layer, dept) for layer in ("forest", "habitat", "batiment", "roads", "rpg")}
        paths["relief"] = cfg.bulk_raw("dem", f"dem_{dept}_{int(resolution)}m.tif")
        absent = [layer for layer, path in paths.items() if layer not in skip and (not path.exists() or path.stat().st_size == 0)]
        if "relief" not in skip and "relief" not in absent and not valid_bulk_dem(paths["relief"]):
            absent.append("relief")
        if absent:
            missing[dept] = absent
    return missing


def missing_wfs_inputs(cfg: Config, resolution: float, skip: set[str]) -> dict[str, list[str]]:
    missing = {}
    for dept in cfg.departements:
        sub = cfg.for_departement(dept)
        paths = {layer: sub.layer_path(layer) for layer in ("forest", "habitat", "roads", "rpg")}
        paths["relief"] = sub.dem_path(resolution)
        absent = [layer for layer, path in paths.items() if layer not in skip and (not path.exists() or path.stat().st_size == 0)]
        if absent:
            missing[dept] = absent
    return missing
