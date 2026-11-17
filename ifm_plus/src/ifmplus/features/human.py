"""Features de pression humaine : WUI, routes/TMJA, agriculture, communes."""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from ..raster import AnalysisGrid, ZonalStats, dilate, edge_length_m
from .typo import strip_accents

log = logging.getLogger("ifmplus")


# ----------------------------------------------------------------------
# Habitat et interface habitat-forêt (WUI)
# ----------------------------------------------------------------------
def compute_habitat_features(
    cells: gpd.GeoDataFrame,
    habitat: gpd.GeoDataFrame,
    forest_mask: np.ndarray,
    grid: AnalysisGrid,
    zonal: ZonalStats,
) -> tuple[pd.DataFrame, np.ndarray]:
    log.info("Rasterisation des zones d'habitation (%s polygones)…", f"{len(habitat):,}")
    habitat = habitat.to_crs(grid.crs)
    habitat_mask = grid.rasterize(habitat, dtype="uint8", fill=0) > 0

    # Interface : habitat situé à moins de 200 m de la forêt.
    forest_200m = dilate(forest_mask, distance_m=200, resolution=grid.resolution)
    wui_mask = habitat_mask & forest_200m

    features = pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})
    features["habitat_frac"] = zonal.frac(habitat_mask)
    features["wui_frac"] = zonal.frac(wui_mask)

    habitat_px = zonal.sum(habitat_mask.astype("float32"))
    wui_px = zonal.sum(wui_mask.astype("float32"))
    # Sans habitat, il n'y a pas d'interface : 0 (et non NaN, qui serait lu
    # comme « information manquante » par le modèle).
    features["part_habitat_wui"] = np.divide(
        wui_px,
        habitat_px,
        out=np.zeros(len(cells), dtype="float64"),
        where=habitat_px > 0,
    )
    # Linéaire de contact habitat-forêt (périmètre de la zone WUI) par hectare.
    contact = edge_length_m(
        labels=zonal.labels,
        mask=wui_mask,
        resolution=grid.resolution,
        n_cells=len(cells),
    )
    features["contact_habitat_foret_m_ha"] = contact / cells["area_ha"].to_numpy()
    log.info(
        "  habitat : %.1f %% | WUI : %.1f %% du département",
        100 * np.nanmean(features["habitat_frac"]),
        100 * np.nanmean(features["wui_frac"]),
    )
    return features, habitat_mask


# ----------------------------------------------------------------------
# Bâti : densité et interface bâtiment-forêt
# ----------------------------------------------------------------------
def compute_building_features(
    cells: gpd.GeoDataFrame,
    batiment: gpd.GeoDataFrame,
    forest_mask: np.ndarray,
    grid: AnalysisGrid,
    zonal: ZonalStats,
) -> pd.DataFrame:
    """Densité de bâtiments et contact bâti-forêt à 50 m.

    La densité est comptée au **point représentatif** de chaque bâtiment
    (un bâtiment = un point), tandis que l'emprise au sol et le contact sont
    rasterisés à 25 m. Les deux mesures sont complémentaires : la première
    reflète le nombre de foyers potentiels, la seconde l'interface combustible.
    """
    log.info("Rasterisation des bâtiments (%s polygones)…", f"{len(batiment):,}")
    ids = cells["cell_id"].to_numpy()
    features = pd.DataFrame({"cell_id": ids})

    if batiment is None or len(batiment) == 0:
        for column in (
            "batiment_frac",
            "batiment_n",
            "batiment_n_km2",
            "batiment_residentiel_frac",
            "contact_bati_foret_m_ha",
        ):
            features[column] = 0.0
        return features

    batiment = batiment.to_crs(grid.crs)
    bati_mask = grid.rasterize(batiment, dtype="uint8", fill=0) > 0
    features["batiment_frac"] = zonal.frac(bati_mask)

    usage = strip_accents(
        batiment.get("usage_1", pd.Series("", index=batiment.index))
    )
    residential = usage.str.contains("residentiel", na=False)
    if residential.any():
        res_mask = grid.rasterize(
            batiment.loc[residential], dtype="uint8", fill=0
        ) > 0
        features["batiment_residentiel_frac"] = zonal.frac(res_mask)
    else:
        features["batiment_residentiel_frac"] = 0.0

    # Comptage au point représentatif (évite les doubles comptages de
    # bâtiments à cheval sur deux carreaux).
    points = gpd.GeoDataFrame(
        geometry=batiment.geometry.representative_point(),
        crs=grid.crs,
    )
    joined = gpd.sjoin(points, cells[["cell_id", "geometry"]], predicate="within", how="inner")
    counts = joined.groupby("cell_id").size()
    features["batiment_n"] = (
        counts.reindex(ids, fill_value=0).to_numpy().astype("float32")
    )
    area_km2 = cells["area_ha"].to_numpy() / 100.0
    features["batiment_n_km2"] = features["batiment_n"] / area_km2

    forest_50m = dilate(forest_mask, distance_m=50, resolution=grid.resolution)
    contact_mask = bati_mask & forest_50m
    contact = edge_length_m(
        labels=zonal.labels,
        mask=contact_mask,
        resolution=grid.resolution,
        n_cells=len(cells),
    )
    features["contact_bati_foret_m_ha"] = (
        contact / cells["area_ha"].to_numpy()
    )
    log.info(
        "  bâti : %.1f %% du département, %s bâtiments, contact %.1f m/ha",
        100 * np.nanmean(features["batiment_frac"]),
        f"{len(batiment):,}",
        np.nanmean(features["contact_bati_foret_m_ha"]),
    )
    return features


# ----------------------------------------------------------------------
# Routes, trafic et distance aux axes
# ----------------------------------------------------------------------
def _line_midpoints(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    points = gdf.copy()
    points["geometry"] = gdf.geometry.interpolate(0.5, normalized=True)
    return points


def _join_midpoints(
    lines: gpd.GeoDataFrame,
    cells: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    points = _line_midpoints(lines)
    joined = gpd.sjoin(
        points,
        cells[["cell_id", "geometry"]],
        predicate="within",
        how="inner",
    )
    return joined[~joined.index.duplicated(keep="first")]


def compute_road_features(
    cells: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    tmja: gpd.GeoDataFrame | None,
    tmja_year: int,
) -> pd.DataFrame:
    log.info("Calcul de la pression routière (%s tronçons)…", f"{len(roads):,}")
    roads = roads.to_crs(cells.crs).copy()
    roads["length_m"] = roads.geometry.length

    if "importance" in roads.columns:
        importance = pd.to_numeric(roads["importance"], errors="coerce").fillna(99)
    else:
        importance = pd.Series(99, index=roads.index, dtype="float64")
    piste = (
        roads.get("piste_dfci", pd.Series(False, index=roads.index))
        .astype(str)
        .str.lower()
        .isin({"true", "1", "oui"})
    )

    roads["_importance"] = importance.to_numpy()
    roads["_piste"] = piste.to_numpy()
    roads["_weight"] = np.select(
        [
            roads["_importance"] <= 1,
            roads["_importance"] == 2,
            roads["_importance"] == 3,
            roads["_piste"],
        ],
        [1.0, 0.8, 0.5, 0.1],
        # Poids nul pour les chemins non DFCI : ``route_ponderee_km`` reste
        # comparable au track WFS, qui ne chargeait que le réseau classé et
        # les pistes DFCI. Le trafic total est disponible via
        # ``route_totale_km``.
        default=0.0,
    )

    joined = _join_midpoints(roads, cells)
    joined["length_km"] = joined["length_m"] / 1000.0
    joined["length_ponderee_km"] = joined["length_km"] * joined["_weight"]

    # Réseau classé (importance ≤ 4) + pistes DFCI : même définition que le
    # track WFS historique. Les chemins/sentiers non DFCI sont comptés à part.
    joined["_length_classe"] = joined["length_km"] * (
        (joined["_importance"] <= 4) | joined["_piste"]
    )
    joined["_length_chemin"] = joined["length_km"] * (
        (joined["_importance"] >= 5) & ~joined["_piste"]
    )

    grouped = joined.groupby("cell_id").agg(
        route_km=("_length_classe", "sum"),
        route_ponderee_km=("length_ponderee_km", "sum"),
        route_totale_km=("length_km", "sum"),
        route_chemin_km=("_length_chemin", "sum"),
    )
    principale = (
        joined.loc[joined["_importance"] <= 2]
        .groupby("cell_id")["length_km"]
        .sum()
        .rename("route_principale_km")
    )
    dfci = (
        joined.loc[joined["_piste"]]
        .groupby("cell_id")["length_km"]
        .sum()
        .rename("route_dfci_km")
    )

    features = (
        pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})
        .set_index("cell_id")
        .join(grouped)
        .join(principale)
        .join(dfci)
        .reset_index()
    )
    for column in (
        "route_km",
        "route_ponderee_km",
        "route_totale_km",
        "route_chemin_km",
        "route_principale_km",
        "route_dfci_km",
    ):
        features[column] = features[column].fillna(0.0)

    area_km2 = cells["area_ha"].to_numpy() / 100.0
    features["route_km_km2"] = features["route_km"] / area_km2
    features["route_totale_km_km2"] = features["route_totale_km"] / area_km2
    features["route_chemin_km_km2"] = features["route_chemin_km"] / area_km2

    # Distance au réseau principal (autoroutes + nationales).
    major = roads.loc[roads["_importance"] <= 2]
    centroids = gpd.GeoDataFrame(
        cells[["cell_id"]].copy(),
        geometry=cells.geometry.centroid,
        crs=cells.crs,
    )
    if len(major):
        nearest = gpd.sjoin_nearest(
            centroids,
            major[["geometry"]],
            how="left",
            distance_col="distance_route_principale_m",
        )
        nearest = nearest.sort_values("distance_route_principale_m").drop_duplicates(
            "cell_id"
        )
        features = features.merge(
            nearest[["cell_id", "distance_route_principale_m"]],
            on="cell_id",
            how="left",
        )
    else:
        features["distance_route_principale_m"] = np.nan

    # ------------------------------------------------------------------
    # TMJA : moyenne pondérée par la longueur + exposition
    # ------------------------------------------------------------------
    features["tmja_max"] = np.nan
    features["tmja_moyen_pondere"] = np.nan
    features["exposition_tmja"] = np.nan

    if tmja is not None and len(tmja):
        tmja = tmja.to_crs(cells.crs).copy()
        if "annee" in tmja.columns and tmja["annee"].notna().any():
            years = pd.to_numeric(tmja["annee"], errors="coerce")
            target = years.iloc[(years - tmja_year).abs().argmin()]
            tmja = tmja.loc[years == target].copy()
        tmja["TMJA"] = pd.to_numeric(tmja.get("TMJA"), errors="coerce")
        tmja = tmja.dropna(subset=["TMJA"])
        if len(tmja):
            tmja["length_m"] = tmja.geometry.length
            joined_tmja = _join_midpoints(tmja, cells)
            joined_tmja["length_km"] = joined_tmja["length_m"] / 1000.0
            joined_tmja["tmja_km"] = joined_tmja["TMJA"] * joined_tmja["length_km"]

            grouped_tmja = joined_tmja.groupby("cell_id").agg(
                tmja_max=("TMJA", "max"),
                tmja_km=("tmja_km", "sum"),
                length_km=("length_km", "sum"),
            )
            grouped_tmja["tmja_moyen_pondere"] = (
                grouped_tmja["tmja_km"] / grouped_tmja["length_km"]
            )
            grouped_tmja["exposition_tmja"] = grouped_tmja["tmja_km"] / 1000.0
            features = features.drop(
                columns=["tmja_max", "tmja_moyen_pondere", "exposition_tmja"]
            ).merge(
                grouped_tmja[
                    ["tmja_max", "tmja_moyen_pondere", "exposition_tmja"]
                ].reset_index(),
                on="cell_id",
                how="left",
            )

    return features


# ----------------------------------------------------------------------
# Agriculture (RPG) et commune
# ----------------------------------------------------------------------
#: Nomenclature RPG en 28 groupes de cultures, agrégée en grandes familles.
#: (Les codes sont stables entre RPG 2.x et 4.0.)
AGRICULTURAL_GROUPS: dict[str, tuple[int, ...]] = {
    "cereales_frac": (1, 2, 3, 4, 14),
    "oleagineux_frac": (5, 6, 7),
    "proteagineux_frac": (8, 15),
    "fourrage_frac": (16,),
    "estives_landes_frac": (17,),
    "prairies_frac": (18, 19),
    "vergers_frac": (20, 22, 23, 27),
    "vigne_frac": (21,),
    "cultures_industrielles_frac": (9, 10, 24, 26),
    "legumes_fleurs_frac": (25,),
    "gels_frac": (11, 12, 13),
    "divers_frac": (28,),
}

#: Catégories RPG 4.0 : PP = prairies permanentes, CP = cultures permanentes,
#: TA = terres arables, SB = surfaces boisées.
CATEGORY_CODES = {"PP": 1, "CP": 2, "TA": 3, "SB": 4}


def compute_agri_features(
    cells: gpd.GeoDataFrame,
    rpg: gpd.GeoDataFrame,
    grid: AnalysisGrid,
    zonal: ZonalStats,
) -> pd.DataFrame:
    """Part agricole et grands groupes de cultures par carreau DFCI."""
    log.info("Rasterisation du RPG (%s parcelles)…", f"{len(rpg):,}")
    ids = cells["cell_id"].to_numpy()
    features = pd.DataFrame({"cell_id": ids})
    if rpg is None or len(rpg) == 0:
        features["agri_frac"] = 0.0
        for column in AGRICULTURAL_GROUPS:
            features[column] = 0.0
        for column in (
            "prairie_permanente_frac",
            "culture_permanente_frac",
            "terre_arable_frac",
        ):
            features[column] = 0.0
        return features

    rpg = rpg.to_crs(grid.crs)
    agri_mask = grid.rasterize(rpg, dtype="uint8", fill=0) > 0
    features["agri_frac"] = zonal.frac(agri_mask)

    group = pd.to_numeric(
        rpg.get("code_group", pd.Series(index=rpg.index, dtype="float64")),
        errors="coerce",
    ).fillna(0)
    group_frame = rpg.assign(_group=group.to_numpy().astype("int16"))
    group_raster = grid.rasterize(
        group_frame, values="_group", dtype="int16", fill=0
    )
    for column, codes in AGRICULTURAL_GROUPS.items():
        features[column] = zonal.frac(np.isin(group_raster, codes))

    category = (
        rpg.get("cat_cult_p", pd.Series("", index=rpg.index))
        .astype(str)
        .str.upper()
        .str.strip()
        .map(CATEGORY_CODES)
        .fillna(0)
        .astype("int8")
    )
    category_raster = grid.rasterize(
        rpg.assign(_cat=category.to_numpy()), values="_cat", dtype="int8", fill=0
    )
    features["prairie_permanente_frac"] = zonal.frac(category_raster == 1)
    features["culture_permanente_frac"] = zonal.frac(category_raster == 2)
    features["terre_arable_frac"] = zonal.frac(category_raster == 3)

    log.info(
        "  RPG : %.1f %% du département, prairies %.1f %%, céréales %.1f %%, "
        "vignes %.1f %%",
        100 * np.nanmean(features["agri_frac"]),
        100 * np.nanmean(features["prairies_frac"]),
        100 * np.nanmean(features["cereales_frac"]),
        100 * np.nanmean(features["vigne_frac"]),
    )
    return features


def compute_commune_features(
    cells: gpd.GeoDataFrame,
    communes: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Commune du centroïde de chaque carreau (utile pour l'agrégation SDIS).

    Les carreaux de bord (centroïde en mer ou hors département) sont rattachés
    à la commune la plus proche plutôt que laissés vides : un carreau côtier
    reste rattaché à une commune pour l'agrégation opérationnelle.
    """
    communes = communes.to_crs(cells.crs)
    name_column = "nom" if "nom" in communes.columns else (
        "nom_officiel" if "nom_officiel" in communes.columns else None
    )
    keep = [
        column
        for column in ("code_insee", name_column, "geometry")
        if column is not None and column in communes.columns
    ]

    centroids = gpd.GeoDataFrame(
        cells[["cell_id"]].copy(),
        geometry=cells.geometry.centroid,
        crs=cells.crs,
    )
    joined = gpd.sjoin(
        centroids, communes[keep], predicate="within", how="left"
    ).drop_duplicates("cell_id")

    code = joined.set_index("cell_id")["code_insee"]
    name = (
        joined.set_index("cell_id")[name_column]
        if name_column
        else pd.Series(index=code.index, dtype="object")
    )

    missing = joined.loc[joined["code_insee"].isna(), ["cell_id", "geometry"]]
    if len(missing):
        nearest = (
            gpd.sjoin_nearest(missing, communes[keep], how="left")
            .drop_duplicates("cell_id")
            .set_index("cell_id")
        )
        code = code.fillna(nearest["code_insee"])
        if name_column:
            name = name.fillna(nearest[name_column])
        log.info(
            "  %s carreaux de bord rattachés à la commune la plus proche",
            len(missing),
        )

    result = pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})
    result["code_insee"] = code.reindex(result["cell_id"]).to_numpy()
    if name_column:
        result["nom_commune"] = name.reindex(result["cell_id"]).to_numpy()
    return result
