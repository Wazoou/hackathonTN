"""Features de relief : altitude et pente (Copernicus DEM 30 m)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from ..raster import AnalysisGrid, ZonalStats

log = logging.getLogger("ifmplus")


def load_dem_on_grid(dem_path: Path, grid: AnalysisGrid) -> np.ndarray:
    """Lit le MNT et le reprojette sur la grille d'analyse (EPSG:2154)."""
    with rasterio.open(dem_path) as src:
        destination = np.full(grid.shape, np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            resampling=Resampling.bilinear,
            dst_nodata=np.nan,
        )
    return destination


def compute_relief_features(
    cells: gpd.GeoDataFrame,
    dem_path: Path,
    grid: AnalysisGrid,
    zonal: ZonalStats,
) -> pd.DataFrame:
    log.info("Calcul du relief (MNT %s)…", dem_path.name)
    dem = load_dem_on_grid(dem_path, grid)
    dem = np.where(np.isfinite(dem), dem, np.nan).astype("float32")
    valid = np.isfinite(dem)

    # Pente (degrés) par gradient centré ; les bords et le nodata restent NaN.
    dy, dx = np.gradient(dem, grid.resolution)
    slope = np.degrees(np.arctan(np.hypot(dx, dy))).astype("float32")
    slope[~valid] = np.nan

    features = pd.DataFrame({"cell_id": cells["cell_id"].to_numpy()})
    features["alt_moy_m"] = zonal.mean(dem, valid)
    features["alt_min_m"] = zonal.minimum(np.where(valid, dem, np.nan))
    features["alt_max_m"] = zonal.maximum(np.where(valid, dem, np.nan))
    mean_square = zonal.mean(
        np.where(valid, dem * dem, np.nan).astype("float32"), valid
    )
    features["alt_std_m"] = np.sqrt(
        np.maximum(mean_square - features["alt_moy_m"] ** 2, 0)
    )

    features["pente_moy_deg"] = zonal.mean(slope, valid)
    features["pente_max_deg"] = zonal.maximum(np.where(valid, slope, np.nan))
    features["frac_pente_sup15"] = zonal.mean(
        (slope > 15).astype("float32"), valid
    )
    features["frac_pente_sup25"] = zonal.mean(
        (slope > 25).astype("float32"), valid
    )

    # ------------------------------------------------------------------
    # Exposition (aspect) : azimut de la pente descendante, 0° = nord.
    # On agrège en moyenne circulaire (sin/cos) et en secteurs de 45°.
    # ------------------------------------------------------------------
    aspect = (np.degrees(np.arctan2(-dx, -dy)) + 360.0) % 360.0
    aspect_valid = valid & np.isfinite(aspect) & (slope >= 0.5)

    sin_mean = zonal.mean(
        np.where(aspect_valid, np.sin(np.radians(aspect)), np.nan).astype("float32"),
        aspect_valid,
    )
    cos_mean = zonal.mean(
        np.where(aspect_valid, np.cos(np.radians(aspect)), np.nan).astype("float32"),
        aspect_valid,
    )
    mean_aspect = (np.degrees(np.arctan2(sin_mean, cos_mean)) + 360.0) % 360.0
    concentration = np.hypot(sin_mean, cos_mean)
    mean_aspect[concentration < 0.05] = np.nan

    features["aspect_moyen_deg"] = mean_aspect
    features["aspect_sin"] = sin_mean
    features["aspect_cos"] = cos_mean
    features["aspect_concentration"] = concentration

    # Secteurs : 1=N, 2=NE, 3=E, 4=SE, 5=S, 6=SO, 7=O, 8=NO.
    sector_names = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")
    sector = np.floor(((aspect + 22.5) % 360.0) / 45.0).astype("int8")
    sector_stack = np.column_stack(
        [
            zonal.mean(
                ((sector == index) & aspect_valid).astype("float32"), aspect_valid
            )
            for index in range(8)
        ]
    )
    filled = np.where(np.isfinite(sector_stack), sector_stack, -1.0)
    best_index = filled.argmax(axis=1)
    best_fraction = filled.max(axis=1)
    codes = np.where(best_fraction >= 0, best_index + 1, 0).astype("int8")
    labels = np.array([""] + list(sector_names), dtype=object)
    features["exposition_dominante_code"] = codes
    features["exposition_dominante"] = labels[codes]
    features["exposition_dominante_frac"] = np.where(
        best_fraction >= 0, best_fraction, np.nan
    )

    log.info(
        "  altitude moyenne : %.0f m | pente moyenne : %.1f°",
        np.nanmean(features["alt_moy_m"]),
        np.nanmean(features["pente_moy_deg"]),
    )
    return features
