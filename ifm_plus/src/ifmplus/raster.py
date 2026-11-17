"""Grille raster d'analyse et statistiques zonales rapides.

Plutôt que de faire des milliers d'intersections vectorielles, on rasterise
les couches à 25 m sur l'emprise du département, puis on agrège les pixels
par ``cell_id`` DFCI. Les formules restent exactes à la résolution près et
le calcul est vectorisé (numpy / scipy.ndimage).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from affine import Affine
from rasterio.features import rasterize as rio_rasterize
from scipy import ndimage


@dataclass(frozen=True)
class AnalysisGrid:
    transform: Affine
    width: int
    height: int
    crs: str
    resolution: float

    @classmethod
    def from_bounds(
        cls,
        bounds: tuple[float, float, float, float],
        resolution: float,
        crs: str,
    ) -> "AnalysisGrid":
        minx, miny, maxx, maxy = bounds
        width = int(math.ceil((maxx - minx) / resolution))
        height = int(math.ceil((maxy - miny) / resolution))
        return cls(
            transform=Affine(resolution, 0.0, minx, 0.0, -resolution, maxy),
            width=width,
            height=height,
            crs=crs,
            resolution=resolution,
        )

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def rasterize(
        self,
        gdf: gpd.GeoDataFrame,
        values: str | None = None,
        default: int = 1,
        all_touched: bool = False,
        dtype: str = "int32",
        fill: int = 0,
    ) -> np.ndarray:
        if gdf.empty:
            return np.full(self.shape, fill, dtype=dtype)
        if values is None:
            shapes = ((geom, default) for geom in gdf.geometry if geom is not None)
        else:
            shapes = (
                (geom, value)
                for geom, value in zip(gdf.geometry, gdf[values])
                if geom is not None and value is not None
            )
        return rio_rasterize(
            shapes,
            out_shape=self.shape,
            transform=self.transform,
            fill=fill,
            all_touched=all_touched,
            dtype=dtype,
        )

    def zonal(self, labels: np.ndarray, n_cells: int) -> "ZonalStats":
        return ZonalStats(labels=labels, n_cells=n_cells)


class ZonalStats:
    """Agrégations par maille DFCI sur un tableau de labels.

    ``labels`` contient 0 hors maille et ``cell_id`` (1..n) dans les mailles.
    """

    def __init__(self, labels: np.ndarray, n_cells: int):
        self.labels = labels
        self.n_cells = n_cells
        flat = labels.ravel()
        self._flat = flat
        self._inside = flat > 0
        self._counts = np.bincount(
            flat[self._inside], minlength=n_cells + 1
        ).astype("float64")

    # ------------------------------------------------------------------
    @property
    def counts(self) -> np.ndarray:
        """Nombre de pixels par maille (index = cell_id)."""
        return self._counts

    def _result(self, values: np.ndarray) -> np.ndarray:
        out = np.asarray(values, dtype="float64")[1:]
        out[self._counts[1:] == 0] = np.nan
        return out

    def mean(self, values: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        flat_values = values.ravel()
        mask = self._inside & np.isfinite(flat_values)
        if valid is not None:
            mask &= valid.ravel()
        weights = np.where(mask, flat_values, 0.0)
        sums = np.bincount(
            self._flat[mask], weights=weights[mask], minlength=self.n_cells + 1
        )
        counts = np.bincount(self._flat[mask], minlength=self.n_cells + 1)
        out = np.divide(
            sums,
            counts,
            out=np.full(self.n_cells + 1, np.nan),
            where=counts > 0,
        )
        return self._result(out)

    def sum(self, values: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        flat_values = values.ravel()
        mask = self._inside & np.isfinite(flat_values)
        if valid is not None:
            mask &= valid.ravel()
        sums = np.bincount(
            self._flat[mask],
            weights=np.where(mask, flat_values, 0.0)[mask],
            minlength=self.n_cells + 1,
        )
        return self._result(sums)

    def frac(self, mask_values: np.ndarray) -> np.ndarray:
        sums = np.bincount(
            self._flat[self._inside],
            weights=mask_values.ravel()[self._inside].astype("float64"),
            minlength=self.n_cells + 1,
        )
        out = np.divide(
            sums,
            self._counts,
            out=np.full(self.n_cells + 1, np.nan),
            where=self._counts > 0,
        )
        return self._result(out)

    def maximum(self, values: np.ndarray) -> np.ndarray:
        prepared = np.where(np.isfinite(values), values, -np.inf).astype("float32")
        result = ndimage.maximum(
            prepared, labels=self.labels, index=np.arange(1, self.n_cells + 1)
        )
        result = np.asarray(result, dtype="float64")
        result[~np.isfinite(result)] = np.nan
        return result

    def minimum(self, values: np.ndarray) -> np.ndarray:
        prepared = np.where(np.isfinite(values), values, np.inf).astype("float32")
        result = ndimage.minimum(
            prepared, labels=self.labels, index=np.arange(1, self.n_cells + 1)
        )
        result = np.asarray(result, dtype="float64")
        result[~np.isfinite(result)] = np.nan
        return result


def dilate(mask: np.ndarray, distance_m: float, resolution: float) -> np.ndarray:
    """Dilatation approximative par un disque de rayon ``distance_m``.

    On utilise des itérations d'un élément structurant en croix : le résultat
    est un losange de rayon ``distance_m``, suffisant pour un indicateur WUI.
    """
    steps = max(1, int(round(distance_m / resolution)))
    return ndimage.binary_dilation(mask, iterations=steps)


def edge_length_m(
    labels: np.ndarray,
    mask: np.ndarray,
    resolution: float,
    n_cells: int,
) -> np.ndarray:
    """Longueur de lisière (périmètre de ``mask``) par maille, en mètres.

    Chaque transition entre un pixel ``mask`` et un pixel hors ``mask`` est
    comptée une fois, puis attribuée à la maille du pixel ``mask``.
    """
    total = np.zeros(n_cells + 1, dtype="float64")

    # Frontières verticales
    transitions = mask[:, 1:] != mask[:, :-1]
    if transitions.any():
        left_labels = labels[:, :-1][transitions]
        right_labels = labels[:, 1:][transitions]
        # On attribue à la maille du côté "mask" quand elle existe.
        left_is_mask = mask[:, :-1][transitions]
        chosen = np.where(left_is_mask, left_labels, right_labels)
        total += np.bincount(chosen, minlength=n_cells + 1) * resolution

    # Frontières horizontales
    transitions = mask[1:, :] != mask[:-1, :]
    if transitions.any():
        top_labels = labels[:-1, :][transitions]
        bottom_labels = labels[1:, :][transitions]
        top_is_mask = mask[:-1, :][transitions]
        chosen = np.where(top_is_mask, top_labels, bottom_labels)
        total += np.bincount(chosen, minlength=n_cells + 1) * resolution

    return total[1:]
