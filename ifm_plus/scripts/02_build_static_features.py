#!/usr/bin/env python
"""02 — Construction des features statiques à la maille DFCI 2 km.

Deux modes :

- **un département** (défaut) : grille locale, sorties
  ``static_features_<dept>.{parquet,gpkg}`` ;
- **France métropolitaine** (``--perimetre france_metro``) : boucle
  département par département (25 m), puis assemblage national et calcul du
  voisinage 3×3 **à l'échelle nationale** (pas de couture aux frontières).

Entrées (produites par 01_download_data.py) :
    data/raw/dfci/dfci_2km.gpkg
    data/raw/admin/departements_france_metro.gpkg   (mode France)
    data/raw/admin/dept_<dept>.gpkg                 (mode département)
    data/raw/admin/communes_france_metro.gpkg       (mode France)
    data/raw/admin/communes_<dept>.gpkg             (mode département)
    data/raw/forest/forest_<dept>.gpkg
    data/raw/habitat/habitat_<dept>.gpkg
    data/raw/roads/roads_<dept>.gpkg
    data/raw/rpg/rpg_<dept>.gpkg
    data/raw/tmja/tmja_france_metro.gpkg            (mode France)
    data/raw/tmja/tmja_<dept>.gpkg                  (mode département)
    data/raw/dem/dem_<dept>_25m.tif

Sorties :
    data/processed/static_features_<dept>.parquet
    data/processed/static_features_<dept>.gpkg
    data/processed/static_features_<dept>_metadata.json

    mode France :
    data/processed/dept/static_features_<dept>_25m.parquet  (cache)
    data/processed/static_features_<perimetre>.parquet
    data/processed/static_features_<perimetre>_metadata.json
    (+ GPKG avec --gpkg)

Exemples :
    python scripts/02_build_static_features.py
    python scripts/02_build_static_features.py --perimetre france_metro
    python scripts/02_build_static_features.py --departements 33,40
    python scripts/02_build_static_features.py --perimetre france_metro --skip roads,rpg
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifmplus.config import Config  # noqa: E402
from ifmplus.features import (  # noqa: E402
    NEIGHBOURHOOD_SOURCES,
    STATIC_FEATURES,
    add_neighbourhood_features,
    compute_agri_features,
    compute_commune_features,
    compute_forest_features,
    compute_habitat_features,
    compute_relief_features,
    compute_road_features,
)
from ifmplus.geoutils import (  # noqa: E402
    DepartmentIndex,
    assign_dfci_cells,
    build_cells_for_department,
    build_dfci_cells,
    clamp_fractions,
    read_bbox,
    read_layer,
)
from ifmplus.log import setup_logging  # noqa: E402
from ifmplus.raster import AnalysisGrid  # noqa: E402

log = logging.getLogger("ifmplus")

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
    "agri_frac",
    "agri_frac_1km",
    "habitat_frac_1km",
    "wui_frac_1km",
]

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
]

HABITAT_COLUMNS = ["habitat_frac", "wui_frac", "part_habitat_wui"]

ROAD_COLUMNS = [
    "route_km",
    "route_km_km2",
    "route_principale_km",
    "route_dfci_km",
    "route_ponderee_km",
    "distance_route_principale_m",
    "tmja_max",
    "tmja_moyen_pondere",
    "exposition_tmja",
]

SKIPPABLE = {"forest", "habitat", "roads", "rpg", "relief"}

CONTEXT_COLUMNS = {
    "area_ha",
    "frac_dans_dept",
    "x_centroid",
    "y_centroid",
    "lon",
    "lat",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calcul des features statiques IFM+ par carreau DFCI."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--departement", default=None)
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
        "--resolution",
        type=float,
        default=None,
        help="Résolution de la grille raster d'analyse (m). Défaut : config.",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="Couches à ignorer, séparées par des virgules : "
        "forest, habitat, roads, rpg, relief.",
    )
    parser.add_argument(
        "--skip-relief",
        action="store_true",
        help="Alias de --skip relief (compatibilité).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalcule aussi les départements déjà présents dans le cache.",
    )
    parser.add_argument(
        "--refresh-cells",
        action="store_true",
        help="Refait l'affectation nationale des carreaux DFCI aux départements.",
    )
    parser.add_argument(
        "--gpkg",
        action="store_true",
        help="Écrit aussi le GPKG (volumineux) en mode France.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


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


def _load_optional(path: Path, label: str, columns: list[str] | None = None):
    if not path.exists():
        log.warning("%s absent (%s) — features à NaN", label, path)
        return None
    log.info("Lecture %s…", path.name)
    return read_layer(path, columns=columns)


def _input_fingerprint(cfg: Config, resolution: float) -> str:
    """Empreinte courte des fichiers d'entrée (taille), pour invalider un cache.

    Ajouter une couche manquante ou retélécharger une couche change
    l'empreinte et force le recalcul du département.
    """
    parts: list[str] = []
    for layer in ("forest", "habitat", "roads", "rpg"):
        path = cfg.layer_path(layer)
        parts.append(f"{layer}:{path.stat().st_size if path.exists() else 0}")
    tmja = cfg.tmja_path
    parts.append(f"tmja:{tmja.stat().st_size if tmja.exists() else 0}")
    dem = cfg.dem_path(resolution)
    parts.append(f"dem:{dem.stat().st_size if dem.exists() else 0}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8]


def _build_department(
    cfg: Config,
    cells: gpd.GeoDataFrame,
    resolution: float,
    skip: set[str],
    commune_features: pd.DataFrame | None = None,
    neighbourhood: bool = True,
) -> pd.DataFrame:
    """Features statiques d'un département sur sa grille 25 m.

    Les ``cell_id`` du mode France sont globaux (1…N national) alors que la
    rasterisation zonale indexe les pixels par des identifiants locaux
    contigus. On travaille donc en ids locaux (1…n) et on restaure les ids
    globaux à la fin.
    """
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
    # Combustible / relief
    # ------------------------------------------------------------------
    forest = (
        None
        if "forest" in skip
        else _load_optional(
            cfg.layer_path("forest"),
            "BD Forêt V2",
            columns=["tfv", "tfv_g11", "essence"],
        )
    )
    forest_mask = np.zeros(grid.shape, dtype=bool)
    if forest is not None and len(forest):
        forest_features, masks = compute_forest_features(
            local, forest, grid, zonal
        )
        forest_mask = masks["forest"]
    elif forest is not None:
        forest_features = _zeros(local, FOREST_COLUMNS)
    else:
        forest_features = _empty(local, FOREST_COLUMNS)

    dem_path = cfg.dem_path(resolution)
    if "relief" in skip or not dem_path.exists():
        if "relief" not in skip:
            log.warning("MNT absent (%s) — relief à NaN", dem_path)
        relief_features = _empty(local, RELIEF_COLUMNS)
    else:
        relief_features = compute_relief_features(local, dem_path, grid, zonal)

    # ------------------------------------------------------------------
    # Pression humaine
    # ------------------------------------------------------------------
    habitat = (
        None
        if "habitat" in skip
        else _load_optional(cfg.layer_path("habitat"), "zones d'habitation")
    )
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

    roads = (
        None
        if "roads" in skip
        else _load_optional(cfg.layer_path("roads"), "réseau routier")
    )
    tmja = (
        None
        if "roads" in skip
        else _load_optional(cfg.tmja_path, "TMJA")
    )
    if roads is not None and len(roads):
        road_features = compute_road_features(
            local,
            roads,
            tmja,
            tmja_year=cfg.tmja_annee,
        )
    elif roads is not None:
        road_features = _zeros(local, ROAD_COLUMNS)
        road_features["distance_route_principale_m"] = np.nan
        road_features["tmja_max"] = np.nan
        road_features["tmja_moyen_pondere"] = np.nan
        road_features["exposition_tmja"] = np.nan
    else:
        road_features = _empty(local, ROAD_COLUMNS)

    rpg = (
        None
        if "rpg" in skip
        else _load_optional(cfg.layer_path("rpg"), "RPG")
    )
    if rpg is not None and len(rpg):
        agri_features = compute_agri_features(local, rpg, grid, zonal)
        agri_features["agri_frac_1km"] = np.nan  # calculé au voisinage
    elif rpg is not None:
        agri_features = _zeros(local, ["agri_frac"])
        agri_features["agri_frac_1km"] = np.nan
    else:
        agri_features = _empty(local, ["agri_frac"])

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
        communes = _load_optional(cfg.communes_scope_path, "communes")
        if communes is not None:
            commune_part = compute_commune_features(local, communes)
        else:
            commune_part = _empty(local, ["code_insee", "nom_commune"])

    # ------------------------------------------------------------------
    # Assemblage
    # ------------------------------------------------------------------
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
        road_features,
        agri_features,
        commune_part,
    ):
        features = features.merge(part, on="cell_id", how="left", validate="one_to_one")

    if neighbourhood:
        features = add_neighbourhood_features(
            features, local, tuple(NEIGHBOURHOOD_SOURCES)
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


def _quality_report(
    features: pd.DataFrame,
    perimetre: str,
) -> dict:
    if features["id_carreau_dfci"].duplicated().any():
        raise RuntimeError("Identifiants DFCI dupliqués dans la table finale")
    if features["cell_id"].duplicated().any():
        raise RuntimeError("cell_id dupliqué dans la table finale")

    key_columns = {"cell_id", "id_carreau_dfci", "code_insee", "nom_commune"}
    if perimetre == "france_metro":
        key_columns.add("departement")

    missing = (
        features.drop(
            columns=[
                column
                for column in ("cell_id", "id_carreau_dfci", "code_insee",
                               "nom_commune", "departement")
                if column in features.columns
            ]
        )
        .isna()
        .mean()
        .sort_values(ascending=False)
    )
    attribute_columns = [
        column for column in features.columns if column not in key_columns
    ]
    qa = {
        "n_cells": int(len(features)),
        "n_features": len(attribute_columns),
        "n_features_hors_contexte": len(
            [column for column in attribute_columns if column not in CONTEXT_COLUMNS]
        ),
        "missing_rate": {
            key: round(float(value), 4)
            for key, value in missing.items()
            if value > 0
        },
        "foret_frac_moyenne": round(float(features["foret_frac"].mean()), 4),
        "wui_frac_moyenne": round(float(features["wui_frac"].mean()), 4),
        "pente_moyenne_deg": round(float(features["pente_moy_deg"].mean()), 2),
    }
    if "departement" in features.columns:
        counts = features.groupby("departement").size()
        qa["n_cells_par_departement"] = {
            "min": int(counts.min()),
            "max": int(counts.max()),
            "moyenne": round(float(counts.mean()), 1),
        }
    return qa


def _metadata(
    cfg: Config,
    features: pd.DataFrame,
    resolution: float,
    qa: dict,
    bbox,
    inputs: dict,
    neighbourhood: str,
) -> dict:
    feature_columns = [
        column
        for column in features.columns
        if column not in ("cell_id", "id_carreau_dfci", "code_insee",
                          "nom_commune", "departement")
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "perimetre": cfg.perimetre,
        "scope": cfg.scope_label,
        "departements": list(cfg.departements),
        "n_departements": len(cfg.departements),
        "nom_departement": cfg.nom_departement if not cfg.france else "",
        "crs": cfg.crs,
        "resolution_m": resolution,
        "bbox_2154": [round(v, 3) for v in bbox],
        "neighbourhood": neighbourhood,
        "inputs": inputs,
        "qa": qa,
        "feature_catalog": {
            column: STATIC_FEATURES.get(
                column,
                {"famille": "autre", "source": "", "unite": "", "description": ""},
            )
            for column in feature_columns
        },
    }


def _inputs(cfg: Config, resolution: float) -> dict:
    if cfg.france:
        return {
            "dfci": str(cfg.dfci_path),
            "admin_departements": str(cfg.departements_france_path),
            "communes": str(cfg.communes_scope_path),
            "forest": str(cfg.raw("forest", "forest_<dept>.gpkg")),
            "habitat": str(cfg.raw("habitat", "habitat_<dept>.gpkg")),
            "roads": str(cfg.raw("roads", "roads_<dept>.gpkg")),
            "rpg": str(cfg.raw("rpg", "rpg_<dept>.gpkg")),
            "tmja": str(cfg.tmja_path),
            "dem": str(cfg.raw("dem", f"dem_<dept>_{int(resolution)}m.tif")),
        }
    return {
        "dfci": str(cfg.dfci_path),
        "forest": str(cfg.layer_path("forest")),
        "habitat": str(cfg.layer_path("habitat")),
        "roads": str(cfg.layer_path("roads")),
        "rpg": str(cfg.layer_path("rpg")),
        "tmja": str(cfg.tmja_path),
        "dem": str(cfg.dem_path(resolution)),
    }


def _write_outputs(
    cfg: Config,
    features: pd.DataFrame,
    resolution: float,
    qa: dict,
    bbox,
    neighbourhood: str,
    write_gpkg: bool,
    cells: gpd.GeoDataFrame | None = None,
) -> None:
    output_parquet = cfg.static_features_path
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_parquet, index=False)
    log.info("-> %s", output_parquet)

    if write_gpkg:
        if cells is None:
            raise RuntimeError("GPKG demandé mais géométries des carreaux absentes")
        gdf = cells[["cell_id", "geometry"]].merge(
            features, on="cell_id", how="left"
        )
        ordered = ["id_carreau_dfci", "cell_id"]
        if "departement" in gdf.columns:
            ordered.append("departement")
        ordered += [
            column
            for column in gdf.columns
            if column not in (*ordered, "geometry")
        ]
        gdf = gdf[ordered + ["geometry"]]
        output_gpkg = cfg.static_features_gpkg_path
        if output_gpkg.exists():
            output_gpkg.unlink()
        gdf.to_file(
            output_gpkg,
            layer="static_features",
            driver="GPKG",
            engine="pyogrio",
        )
        log.info("-> %s", output_gpkg)

    metadata = _metadata(
        cfg,
        features,
        resolution,
        qa,
        bbox,
        _inputs(cfg, resolution),
        neighbourhood,
    )
    metadata_path = cfg.static_features_metadata_path
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("-> %s", metadata_path)


# ----------------------------------------------------------------------
# Mode France métropolitaine
# ----------------------------------------------------------------------
def run_france(
    cfg: Config,
    args: argparse.Namespace,
    resolution: float,
    skip: set[str],
) -> int:
    departements = cfg.departements
    log.info(
        "Features statiques — France métropolitaine : %s département(s), "
        "grille %.0f m",
        len(departements),
        resolution,
    )

    assigned = assign_dfci_cells(cfg, force=args.refresh_cells)
    index = DepartmentIndex.from_file(cfg.departements_france_path, cfg.crs)

    # Communes : calcul unique sur les carreaux du périmètre, puis découpage
    # par département (évite de charger les communes 96 fois).
    commune_all = None
    communes = _load_optional(cfg.communes_scope_path, "communes")
    if communes is not None:
        scope_cells = assigned[assigned["dept"].isin(departements)]
        log.info(
            "Rattachement des %s carreaux du périmètre aux communes…",
            f"{len(scope_cells):,}",
        )
        commune_all = compute_commune_features(scope_cells, communes)

    frames: list[pd.DataFrame] = []
    cells_parts: list[gpd.GeoDataFrame] = []
    built = 0
    resumed = 0

    for position, dept in enumerate(departements, start=1):
        sub = cfg.for_departement(dept)
        cache = sub.dept_cache_path(
            resolution,
            tuple(sorted(skip)),
            _input_fingerprint(sub, resolution),
        )
        prefix = f"[{position}/{len(departements)}] {dept}"

        cells: gpd.GeoDataFrame | None = None
        if cache.exists() and not args.force:
            log.info("%s — cache : %s", prefix, cache.name)
            features = pd.read_parquet(cache)
            resumed += 1
        else:
            log.info("%s — construction", prefix)
            cells = build_cells_for_department(sub, assigned, index)
            commune_part = (
                commune_all.loc[commune_all["cell_id"].isin(cells["cell_id"])]
                if commune_all is not None
                else None
            )
            features = _build_department(
                sub,
                cells,
                resolution,
                skip,
                commune_features=commune_part,
                neighbourhood=False,
            )
            cache.parent.mkdir(parents=True, exist_ok=True)
            features.to_parquet(cache, index=False)
            built += 1

        if args.gpkg and cells is None:
            cells = build_cells_for_department(sub, assigned, index)
        if cells is not None:
            cells_parts.append(cells[["cell_id", "id_carreau_dfci", "geometry"]])
        frames.append(features)

    log.info(
        "Départements : %s construits, %s repris du cache",
        built,
        resumed,
    )

    features = pd.concat(frames, ignore_index=True)
    coords = features[["x_centroid", "y_centroid"]]
    log.info("Voisinage 3×3 national sur %s carreaux…", f"{len(features):,}")
    features = add_neighbourhood_features(
        features, coords, tuple(NEIGHBOURHOOD_SOURCES)
    )

    counts = features.groupby("departement").size()
    log.info(
        "Table nationale : %s carreaux, %s départements (%s à %s carreaux/dept)",
        f"{len(features):,}",
        len(counts),
        int(counts.min()),
        int(counts.max()),
    )

    qa = _quality_report(features, cfg.perimetre)
    log.info(
        "Contrôles : %s carreaux, %s features, forêt moyenne %.1f %%",
        qa["n_cells"],
        qa["n_features"],
        100 * qa["foret_frac_moyenne"],
    )
    if qa["missing_rate"]:
        worst = list(qa["missing_rate"].items())[:5]
        log.warning("Taux de valeurs manquantes les plus élevés : %s", worst)

    cells_all = None
    if args.gpkg:
        cells_all = gpd.GeoDataFrame(
            pd.concat(cells_parts, ignore_index=True), geometry="geometry", crs=cfg.crs
        )
    bbox = read_bbox(cfg.for_departement(departements[0]))
    scope_bbox = (
        json.loads(cfg.scope_bbox_path.read_text(encoding="utf-8"))["bbox_2154"]
        if cfg.scope_bbox_path.exists()
        else bbox
    )
    _write_outputs(
        cfg,
        features,
        resolution,
        qa,
        scope_bbox,
        "3×3 national",
        write_gpkg=args.gpkg,
        cells=cells_all,
    )
    log.info(
        "Étape suivante : python scripts/03_build_dynamic_features.py "
        "--perimetre france_metro"
    )
    return 0


# ----------------------------------------------------------------------
# Mode « un département »
# ----------------------------------------------------------------------
def run_departement(
    cfg: Config,
    args: argparse.Namespace,
    resolution: float,
    skip: set[str],
) -> int:
    log.info(
        "Features statiques — département %s, grille %.0f m",
        cfg.departement,
        resolution,
    )
    cells = build_dfci_cells(cfg)
    features = _build_department(
        cfg,
        cells,
        resolution,
        skip,
        commune_features=None,
        neighbourhood=True,
    )
    qa = _quality_report(features, cfg.perimetre)
    log.info(
        "Contrôles : %s carreaux, %s features, forêt moyenne %.1f %%",
        qa["n_cells"],
        qa["n_features"],
        100 * qa["foret_frac_moyenne"],
    )
    if qa["missing_rate"]:
        worst = list(qa["missing_rate"].items())[:5]
        log.warning("Taux de valeurs manquantes les plus élevés : %s", worst)

    _write_outputs(
        cfg,
        features,
        resolution,
        qa,
        read_bbox(cfg),
        "3×3 départemental",
        write_gpkg=True,
        cells=cells,
    )
    log.info(
        "Étape suivante : python scripts/03_build_dynamic_features.py "
        "(météo, lags, table analytique)"
    )
    return 0


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    cfg = Config.load(
        args.config,
        departement=args.departement,
        departements=args.departements,
        perimetre=args.perimetre,
    )
    cfg.ensure_dirs()

    resolution = float(args.resolution or cfg.resolution_m)
    skip = {
        item.strip().lower()
        for item in str(args.skip or "").split(",")
        if item.strip()
    }
    unknown = sorted(skip - SKIPPABLE)
    if unknown:
        log.error("Couches inconnues dans --skip : %s", ", ".join(unknown))
        return 2
    if args.skip_relief:
        skip.add("relief")

    if cfg.france:
        return run_france(cfg, args, resolution, skip)
    return run_departement(cfg, args, resolution, skip)


if __name__ == "__main__":
    raise SystemExit(main())
