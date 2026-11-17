"""Outils géographiques communs (lecture, écriture, maillage DFCI)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

from .config import METRO_DEPARTEMENTS, Config, normalize_dept

log = logging.getLogger("ifmplus")


def read_layer(
    path: Path,
    layer: str | None = None,
    columns: list[str] | None = None,
) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Couche absente : {path}")
    return gpd.read_file(
        path,
        layer=layer,
        columns=columns,
        engine="pyogrio",
    )


def write_layer(
    gdf: gpd.GeoDataFrame,
    path: Path,
    layer: str | None = None,
    driver: str = "GPKG",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    gdf.to_file(path, layer=layer or path.stem, driver=driver, engine="pyogrio")


def read_bbox(cfg: Config) -> tuple[float, float, float, float]:
    payload = json.loads(cfg.dept_bbox_path.read_text(encoding="utf-8"))
    return tuple(float(v) for v in payload["bbox_2154"])  # type: ignore[return-value]


def read_bbox_wgs84(cfg: Config) -> tuple[float, float, float, float]:
    payload = json.loads(cfg.dept_bbox_path.read_text(encoding="utf-8"))
    return tuple(float(v) for v in payload["bbox_wgs84"])  # type: ignore[return-value]


def read_scope_bbox(cfg: Config) -> tuple[float, float, float, float]:
    """Bbox du périmètre complet (national ou sous-ensemble demandé)."""
    payload = json.loads(cfg.scope_bbox_path.read_text(encoding="utf-8"))
    return tuple(float(v) for v in payload["bbox_2154"])  # type: ignore[return-value]


def read_scope_bbox_wgs84(cfg: Config) -> tuple[float, float, float, float]:
    payload = json.loads(cfg.scope_bbox_path.read_text(encoding="utf-8"))
    return tuple(float(v) for v in payload["bbox_wgs84"])  # type: ignore[return-value]


def _bbox_wgs84(
    cfg: Config,
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    west, south, east, north = (
        gpd.GeoSeries([box(*bbox)], crs=cfg.crs)
        .to_crs(cfg.crs_wgs84)
        .total_bounds.tolist()
    )
    return west, south, east, north


def save_bbox(
    cfg: Config,
    dept: gpd.GeoDataFrame,
    buffer_m: float | None = None,
) -> tuple[float, float, float, float]:
    """Calcule et sauvegarde la bbox du département (2154 + WGS84)."""
    buffer = cfg.buffer_m if buffer_m is None else buffer_m
    minx, miny, maxx, maxy = dept.total_bounds
    bbox = (minx - buffer, miny - buffer, maxx + buffer, maxy + buffer)
    west, south, east, north = _bbox_wgs84(cfg, bbox)

    payload = {
        "departement": cfg.departement,
        "bbox_2154": [round(v, 3) for v in bbox],
        "bbox_wgs84": [round(v, 6) for v in (west, south, east, north)],
        "buffer_m": buffer,
    }
    cfg.dept_bbox_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.dept_bbox_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bbox


def save_scope_bbox(
    cfg: Config,
    departements: gpd.GeoDataFrame,
    codes: tuple[str, ...] | None = None,
    buffer_m: float | None = None,
) -> tuple[float, float, float, float]:
    """Sauvegarde la bbox englobante du périmètre traité.

    Utilisée pour les couches nationales (TMJA, FIRMS, météo) qui n'ont pas
    besoin d'un découpage départemental.
    """
    codes = tuple(codes or cfg.departements)
    buffer = cfg.buffer_m if buffer_m is None else buffer_m
    frame = departements.copy()
    frame["_dept"] = frame["code_insee"].map(normalize_dept)
    selected = frame[frame["_dept"].isin(codes)]
    if selected.empty:
        raise RuntimeError("Aucun département du périmètre dans Admin Express")

    minx, miny, maxx, maxy = selected.total_bounds
    bbox = (minx - buffer, miny - buffer, maxx + buffer, maxy + buffer)
    west, south, east, north = _bbox_wgs84(cfg, bbox)

    payload = {
        "perimetre": cfg.perimetre,
        "scope": cfg.scope_label,
        "departements": list(codes),
        "bbox_2154": [round(v, 3) for v in bbox],
        "bbox_wgs84": [round(v, 6) for v in (west, south, east, north)],
        "buffer_m": buffer,
    }
    cfg.scope_bbox_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.scope_bbox_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bbox


# ----------------------------------------------------------------------
# Index départemental et affectation des carreaux
# ----------------------------------------------------------------------
class DepartmentIndex:
    """Contours départementaux nationaux et affectation des carreaux DFCI.

    Chaque carreau est affecté à **un seul** département, celui qui contient
    son centroïde ; les carreaux côtiers (centroïde en mer) sont rattachés au
    département le plus proche. Cela garantit qu'un carreau n'apparaît qu'une
    fois dans la table nationale, sans doublon aux frontières.
    """

    def __init__(self, departements: gpd.GeoDataFrame, crs: str):
        if "code_insee" not in departements.columns:
            raise KeyError(
                "Admin Express département sans colonne code_insee "
                f"(colonnes : {list(departements.columns)})"
            )
        frame = departements[["code_insee", "geometry"]].copy()
        frame["dept"] = frame["code_insee"].map(normalize_dept)
        self.gdf = gpd.GeoDataFrame(
            frame[["dept", "geometry"]], geometry="geometry", crs=departements.crs
        ).to_crs(crs)
        self.gdf = self.gdf[~self.gdf.geometry.is_empty]
        self.gdf = self.gdf.drop_duplicates("dept").reset_index(drop=True)
        self._by_dept = dict(zip(self.gdf["dept"], self.gdf.geometry))

    @classmethod
    def from_file(cls, path: Path, crs: str) -> "DepartmentIndex":
        if not path.exists():
            raise FileNotFoundError(
                f"Contours départementaux absents : {path}. "
                "Lancer scripts/01_download_data.py --layers admin."
            )
        log.info("Lecture des contours départementaux (%s)…", path.name)
        return cls(gpd.read_file(path, engine="pyogrio"), crs)

    def geometry(self, dept: str):
        code = normalize_dept(dept)
        if code not in self._by_dept:
            raise KeyError(f"Département {code} absent d'Admin Express")
        return self._by_dept[code]

    def assign(
        self,
        cells: gpd.GeoDataFrame,
        label: str = "dept",
    ) -> gpd.GeoDataFrame:
        """Affecte chaque carreau à un département et écarte la mer.

        Règles :

        1. si le centroïde est dans un département, c'est lui ;
        2. sinon, si le carreau intersecte un ou plusieurs départements
           (carreaux côtiers ou frontaliers), on retient le département avec
           la plus grande surface d'intersection ;
        3. un carreau qui n'intersecte aucun département (pleine mer) est
           **ignoré** : le carroyage DFCI national couvre aussi la mer.
        """
        if cells.crs is None or cells.crs.to_string() != self.gdf.crs.to_string():
            cells = cells.to_crs(self.gdf.crs)

        centroids = gpd.GeoDataFrame(
            geometry=cells.geometry.centroid, crs=cells.crs
        )
        joined = gpd.sjoin(
            centroids,
            self.gdf,
            predicate="within",
            how="left",
        )
        joined = joined[~joined.index.duplicated(keep="first")]
        assignment = joined["dept"].reindex(cells.index)
        n_centroid = int(assignment.notna().sum())

        # Carreaux dont le centroïde est hors terre (côte, frontière) :
        # on les rattache au département le plus couvert par le carreau.
        missing = assignment.isna()
        n_ring = 0
        if missing.any():
            candidates = gpd.sjoin(
                cells.loc[missing, ["geometry"]],
                self.gdf,
                predicate="intersects",
                how="inner",
            )
            if len(candidates):
                left_geom = cells.loc[candidates.index, "geometry"].to_numpy()
                right_geom = self.gdf.loc[
                    candidates["index_right"].to_numpy(), "geometry"
                ].to_numpy()
                areas = shapely.area(
                    shapely.intersection(left_geom, right_geom)
                )
                overlaps = pd.DataFrame(
                    {
                        "cell_index": candidates.index.to_numpy(),
                        "dept": candidates["dept"].to_numpy(),
                        "area": areas,
                    }
                )
                best = overlaps.loc[
                    overlaps.groupby("cell_index")["area"].idxmax()
                ]
                assignment.loc[best["cell_index"].to_numpy()] = best[
                    "dept"
                ].to_numpy()
                n_ring = int(len(best))

        assigned = assignment.notna()
        dropped = int((~assigned).sum())
        log.info(
            "  %s carreaux : %s par centroïde, %s côtiers/frontaliers, "
            "%s hors territoire (mer) ignorés",
            f"{len(cells):,}",
            f"{n_centroid:,}",
            f"{n_ring:,}",
            f"{dropped:,}",
        )

        result = cells.loc[assigned].copy()
        result[label] = assignment.loc[assigned].to_numpy()
        return result.reset_index(drop=True)


def assign_dfci_cells(
    cfg: Config,
    force: bool = False,
) -> gpd.GeoDataFrame:
    """Carroyage national + ``cell_id`` global + département d'appartenance.

    Le cache (``data/interim/dfci_cells_assigned_v2.gpkg``) évite de refaire
    l'affectation spatiale des 339 264 carreaux à chaque département. Seuls
    les carreaux terrestres sont conservés (~139 842) ; ``cell_id`` est
    attribué après ce filtrage.
    """
    cache = cfg.dfci_cells_cache_path
    if cache.exists() and not force:
        log.info("Carroyage DFCI affecté déjà présent : %s", cache.name)
        cells = gpd.read_file(cache, engine="pyogrio")
        if not {"cell_id", "id_carreau_dfci", "dept"}.issubset(cells.columns):
            log.warning("  cache incomplet, reconstruction")
        elif (set(cells["dept"].dropna()) == set(METRO_DEPARTEMENTS)
              and not cells["cell_id"].duplicated().any()
              and not cells["id_carreau_dfci"].duplicated().any()
              and all(path.exists() and path.stat().st_mtime_ns <= cache.stat().st_mtime_ns
                      for path in (cfg.dfci_path, cfg.departements_france_path))):
            return cells
        else:
            log.warning("  cache national partiel ou périmé, reconstruction")

    if not cfg.dfci_path.exists():
        raise FileNotFoundError(
            f"Carroyage DFCI absent : {cfg.dfci_path}. "
            "Lancer scripts/01_download_data.py --layers dfci."
        )
    if not cfg.departements_france_path.exists():
        raise FileNotFoundError(
            f"Contours départementaux absents : {cfg.departements_france_path}. "
            "Lancer scripts/01_download_data.py --layers admin."
        )

    log.info("Lecture du carroyage DFCI national…")
    dfci = gpd.read_file(cfg.dfci_path, engine="pyogrio")
    if dfci.crs is None or dfci.crs.to_string() != cfg.crs:
        dfci = dfci.to_crs(cfg.crs)
    if "id_carreau_dfci" not in dfci.columns:
        raise KeyError(
            "Le carroyage doit contenir une colonne id_carreau_dfci "
            f"(colonnes trouvées : {list(dfci.columns)})"
        )

    dfci["id_carreau_dfci"] = dfci["id_carreau_dfci"].astype(str).str.strip()
    dfci = dfci[~dfci.geometry.is_empty]
    dfci = dfci.drop_duplicates("id_carreau_dfci")
    dfci = dfci.sort_values("id_carreau_dfci", kind="mergesort").reset_index(drop=True)

    index = DepartmentIndex.from_file(cfg.departements_france_path, cfg.crs)
    log.info("Affectation des carreaux aux départements…")
    assigned = index.assign(dfci[["id_carreau_dfci", "geometry"]])

    # Identifiant global attribué **après** filtrage de la mer : 1…N sans trou.
    assigned = assigned.sort_values(
        "id_carreau_dfci", kind="mergesort"
    ).reset_index(drop=True)
    assigned.insert(0, "cell_id", np.arange(1, len(assigned) + 1, dtype="int32"))
    if len(assigned) >= np.iinfo("int32").max:
        raise RuntimeError("Trop de carreaux pour un cell_id int32")

    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        cache.unlink()
    assigned.to_file(cache, layer="dfci_cells", driver="GPKG", engine="pyogrio")
    log.info(
        "  %s carreaux terrestres affectés -> %s", f"{len(assigned):,}", cache.name
    )
    return assigned


def build_cells_for_department(
    cfg: Config,
    assigned: gpd.GeoDataFrame,
    index: DepartmentIndex,
) -> gpd.GeoDataFrame:
    """Sous-ensemble départemental des carreaux affectés nationalement.

    ``cell_id`` est conservé tel quel (identifiant global) : l'assemblage
    national n'a donc aucun identifiant à recalculer.
    """
    dept = normalize_dept(cfg.departement)
    cells = assigned.loc[assigned["dept"] == dept].copy()
    if cells.empty:
        raise RuntimeError(
            f"Aucun carreau DFCI affecté au département {dept} "
            "(vérifier le carroyage et Admin Express)"
        )

    dept_geom = index.geometry(dept)
    cells["area_ha"] = cells.geometry.area / 10_000.0
    cells["frac_dans_dept"] = (
        cells.geometry.intersection(dept_geom).area / cells.geometry.area
    ).clip(0, 1)

    centroids = cells.geometry.centroid
    cells["x_centroid"] = centroids.x
    cells["y_centroid"] = centroids.y
    wgs = gpd.GeoSeries(centroids, crs=cfg.crs).to_crs(cfg.crs_wgs84)
    cells["lon"] = wgs.x
    cells["lat"] = wgs.y

    cells = cells.sort_values("id_carreau_dfci", kind="mergesort").reset_index(drop=True)
    return cells[
        [
            "cell_id",
            "id_carreau_dfci",
            "dept",
            "area_ha",
            "frac_dans_dept",
            "x_centroid",
            "y_centroid",
            "lon",
            "lat",
            "geometry",
        ]
    ]


def build_dfci_cells(cfg: Config) -> gpd.GeoDataFrame:
    """Découpe le carroyage national sur le département et prépare la table.

    Mode « un département » uniquement : on garde la règle historique
    (intersection avec le contour), qui conserve les carreaux de bord. Le mode
    France utilise :func:`build_cells_for_department` (affectation exclusive).
    """
    if not cfg.dfci_path.exists():
        raise FileNotFoundError(
            f"Carroyage DFCI absent : {cfg.dfci_path}. "
            "Lancer d'abord scripts/01_download_data.py --layers dfci."
        )
    if not cfg.dept_path.exists():
        raise FileNotFoundError(
            f"Contour du département absent : {cfg.dept_path}. "
            "Lancer d'abord scripts/01_download_data.py --layers admin."
        )

    log.info("Lecture du carroyage DFCI national…")
    dfci = gpd.read_file(cfg.dfci_path, engine="pyogrio")
    if dfci.crs is None or dfci.crs.to_string() != cfg.crs:
        dfci = dfci.to_crs(cfg.crs)
    if "id_carreau_dfci" not in dfci.columns:
        raise KeyError(
            "Le carroyage doit contenir une colonne id_carreau_dfci "
            f"(colonnes trouvées : {list(dfci.columns)})"
        )

    dept = gpd.read_file(cfg.dept_path, engine="pyogrio").to_crs(cfg.crs)
    dept_geom = dept.geometry.union_all()

    log.info("Filtrage des carreaux sur le département %s…", cfg.departement)
    cells = gpd.sjoin(
        dfci[["id_carreau_dfci", "geometry"]],
        dept[["geometry"]],
        predicate="intersects",
        how="inner",
    ).drop(columns=["index_right"])
    cells = cells[~cells.geometry.is_empty].copy()
    cells = cells.drop_duplicates(subset="id_carreau_dfci").reset_index(drop=True)

    cells["cell_id"] = pd.RangeIndex(start=1, stop=len(cells) + 1, dtype="int32")
    cells["area_ha"] = cells.geometry.area / 10_000.0
    cells["frac_dans_dept"] = (
        cells.geometry.intersection(dept_geom).area / cells.geometry.area
    ).clip(0, 1)

    centroids = cells.geometry.centroid
    cells["x_centroid"] = centroids.x
    cells["y_centroid"] = centroids.y
    wgs = gpd.GeoSeries(centroids, crs=cfg.crs).to_crs(cfg.crs_wgs84)
    cells["lon"] = wgs.x
    cells["lat"] = wgs.y

    cells = cells.sort_values("id_carreau_dfci").reset_index(drop=True)
    log.info("  %s carreaux DFCI retenus", len(cells))
    return cells[["cell_id", "id_carreau_dfci", "area_ha", "frac_dans_dept",
                   "x_centroid", "y_centroid", "lon", "lat", "geometry"]]


def clamp_fractions(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].clip(0.0, 1.0)
