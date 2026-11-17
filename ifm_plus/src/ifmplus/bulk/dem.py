"""MNT Copernicus DEM 30 m : VRT distant et COG Lambert-93 par département.

Le MNT Copernicus est diffusé en tuiles COG 1°×1° sur un bucket public S3.
Plutôt que de télécharger des dizaines de gigaoctets, on :

1. liste dynamiquement les tuiles 1°×1° intersectant les bbox des
   départements demandés ;
2. vérifie leur existence (HEAD S3, résultat mis en cache) ;
3. construit un **VRT** qui pointe vers les tuiles via ``/vsicurl`` ;
4. lit, par département, uniquement la fenêtre nécessaire, la reprojette en
   Lambert-93 à 25 m et l'écrit en **COG ZSTD** (cache réutilisable).

La mémoire reste bornée : une fenêtre départementale à 30 m représente
environ 50–100 Mo, jamais la France entière.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy
from rasterio.warp import reproject
from rasterio.windows import from_bounds

from ..raster import AnalysisGrid

log = logging.getLogger("ifmplus")

S3_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
PIXELS_PER_DEGREE = 3600  # 1 arc-seconde
NODATA = -32767.0


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return (
        f"Copernicus_DSM_COG_10_{ns}{abs(int(lat)):02d}_00_"
        f"{ew}{abs(int(lon)):03d}_00_DEM"
    )


def tile_url(name: str, base: str = S3_BASE) -> str:
    return f"{base.rstrip('/')}/{name}/{name}.tif"


def candidate_tiles(
    bboxes_wgs84: list[tuple[float, float, float, float]],
) -> list[tuple[int, int]]:
    """Tuiles 1°×1° couvrant les emprises WGS84 fournies."""
    tiles: set[tuple[int, int]] = set()
    for west, south, east, north in bboxes_wgs84:
        lat_min = math.floor(south)
        lat_max = math.floor(north - 1e-9)
        lon_min = math.floor(west)
        lon_max = math.floor(east - 1e-9)
        for lat in range(lat_min, lat_max + 1):
            for lon in range(lon_min, lon_max + 1):
                tiles.add((lat, lon))
    return sorted(tiles)


def probe_tiles(
    tiles: list[tuple[int, int]],
    cache_path: Path,
    *,
    refresh: bool = False,
    timeout: float = 30.0,
) -> list[tuple[int, int]]:
    """Vérifie l'existence des tuiles sur S3 (cache JSON)."""
    cache: dict[str, bool] = {}
    if cache_path.exists() and not refresh:
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}

    available: list[tuple[int, int]] = []
    session = requests.Session()
    checked = 0
    for lat, lon in tiles:
        name = tile_name(lat, lon)
        known = cache.get(name)
        if known is None:
            try:
                response = session.head(tile_url(name), timeout=timeout, allow_redirects=True)
                if response.status_code not in (200, 404):
                    response.raise_for_status()
                    raise RuntimeError(f"Statut inattendu pour la tuile {name}: {response.status_code}")
                known = response.status_code == 200
            except requests.RequestException as exc:
                raise RuntimeError(f"Tuile {name} non vérifiée ; relancer le téléchargement") from exc
            cache[name] = known
            checked += 1
            if checked % 20 == 0:
                time.sleep(0.2)
        if known:
            available.append((lat, lon))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    log.info(
        "  MNT : %s tuiles candidates, %s disponibles (%s vérifiées)",
        len(tiles),
        len(available),
        checked,
    )
    return available


def build_vrt(tiles: list[tuple[int, int]], path: Path, *, source_paths=None) -> Path:
    """Mosaïque mono-bande, avec les dimensions réelles de chaque tuile.

    La largeur des tuiles Copernicus varie avec la latitude (notamment au
    nord de 50°). Lire les en-têtes évite un décalage dans le nord de la France.
    ``source_paths`` permet de vérifier la mosaïque sur des GeoTIFF locaux.
    """
    if not tiles:
        raise RuntimeError("Aucune tuile Copernicus disponible pour le VRT")
    records = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="60",
                      GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_VERSION="1.1"):
        for lat, lon in tiles:
            filename = (str(source_paths[(lat, lon)]) if source_paths is not None
                        else f"/vsicurl/{tile_url(tile_name(lat, lon))}")
            with rasterio.open(filename) as src:
                if src.crs is None or src.crs.to_epsg() != 4326:
                    raise RuntimeError(f"CRS Copernicus inattendu : {filename}")
                records.append((filename, src.width, src.height, src.bounds, src.nodata))
    left = min(row[3].left for row in records)
    right = max(row[3].right for row in records)
    bottom = min(row[3].bottom for row in records)
    top = max(row[3].top for row in records)
    pixel = 1.0 / PIXELS_PER_DEGREE
    width = math.ceil((right - left) / pixel - 1e-8)
    height = math.ceil((top - bottom) / pixel - 1e-8)
    sources = []
    for filename, src_width, src_height, bounds, nodata in records:
        sources.append(
            '    <ComplexSource resampling="bilinear">\n'
            f'      <SourceFilename relativeToVRT="0">{escape(filename)}</SourceFilename>\n'
            '      <SourceBand>1</SourceBand>\n'
            f'      <SourceProperties RasterXSize="{src_width}" RasterYSize="{src_height}" DataType="Float32"/>\n'
            f'      <SrcRect xOff="0" yOff="0" xSize="{src_width}" ySize="{src_height}"/>\n'
            f'      <DstRect xOff="{(bounds.left-left)/pixel}" yOff="{(top-bounds.top)/pixel}" '
            f'xSize="{(bounds.right-bounds.left)/pixel}" ySize="{(bounds.top-bounds.bottom)/pixel}"/>\n'
            + (f'      <NODATA>{nodata}</NODATA>\n' if nodata is not None else '')
            + '    </ComplexSource>'
        )
    xml = (
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">\n'
        '  <SRS>EPSG:4326</SRS>\n'
        f'  <GeoTransform>{left}, {pixel}, 0, {top}, 0, {-pixel}</GeoTransform>\n'
        '  <VRTRasterBand dataType="Float32" band="1">\n'
        f'    <NoDataValue>{NODATA}</NoDataValue>\n'
        + '\n'.join(sources) + '\n  </VRTRasterBand>\n</VRTDataset>\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")
    log.info("  VRT MNT : %s tuiles dans une seule bande, %s×%s px", len(tiles), width, height)
    return path


def ensure_vrt(
    cfg,
    *,
    refresh: bool = False,
) -> Path:
    """Construit le VRT couvrant les départements du périmètre."""
    from ..geoutils import read_bbox_wgs84

    bboxes = [read_bbox_wgs84(cfg.for_departement(dept)) for dept in cfg.departements]
    candidates = candidate_tiles(bboxes)
    cache = cfg.bulk_raw("dem", "tiles_index_v2.json")
    available = probe_tiles(candidates, cache, refresh=refresh)
    path = cfg.bulk_raw("dem", f"copernicus_{cfg.scope_label}.vrt")
    return build_vrt(available, path)


def _read_window(
    vrt_path: Path,
    bbox_wgs84: tuple[float, float, float, float],
    grid: AnalysisGrid,
) -> np.ndarray:
    west, south, east, north = bbox_wgs84
    destination = np.full(grid.shape, np.nan, dtype="float32")
    env = rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_MULTIPLEX="NO",
        # Avoid parallel range reads hanging after a connection failure.
        GDAL_HTTP_MULTIRANGE="SERIAL",
        GDAL_HTTP_CONNECTTIMEOUT="20",
        GDAL_HTTP_VERSION="1.1",
        GDAL_HTTP_TIMEOUT="60",
        GDAL_HTTP_MAX_RETRY="2",
        GDAL_NUM_THREADS="1",
        VRT_VIRTUAL_OVERVIEWS="NO",
    )
    with env, rasterio.open(vrt_path) as src:
        window = from_bounds(west, south, east, north, src.transform)
        data = src.read(1, window=window, masked=True)
        if data.size == 0:
            raise RuntimeError("Fenêtre MNT vide")
        source = data.astype("float32").filled(np.nan)
        reproject(
            source=source,
            destination=destination,
            src_transform=src.window_transform(window),
            src_crs=src.crs,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            resampling=Resampling.bilinear,
            dst_nodata=np.nan,
        )
    return destination


def write_cog(array: np.ndarray, path: Path, grid: AnalysisGrid) -> Path:
    """Écrit un COG ZSTD (création via GTiff temporaire + CreateCopy)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp.tif")
    data = np.where(np.isfinite(array), array, -9999.0).astype("float32")
    with rasterio.open(
        tmp,
        "w",
        driver="GTiff",
        height=grid.height,
        width=grid.width,
        count=1,
        dtype="float32",
        crs=grid.crs,
        transform=grid.transform,
        nodata=-9999.0,
        tiled=True,
        blockxsize=512,
        blockysize=512,
        compress="zstd",
    ) as dst:
        dst.write(data, 1)
    if path.exists():
        path.unlink()
    rio_copy(
        tmp,
        path,
        driver="COG",
        COMPRESS="ZSTD",
        LEVEL="9",
        BLOCKSIZE="512",
        BIGTIFF="IF_SAFER",
        OVERVIEWS="IGNORE_EXISTING",
        RESAMPLING="AVERAGE",
    )
    tmp.unlink(missing_ok=True)
    return path


def ensure_department_dem(
    cfg,
    dept: str,
    vrt_path: Path,
    *,
    resolution: float | None = None,
    force: bool = False,
) -> Path:
    """COG Lambert-93 25 m du département, lu depuis le VRT distant."""
    from ..geoutils import read_bbox, read_bbox_wgs84

    resolution = float(resolution or cfg.resolution_m)
    sub = cfg.for_departement(dept)
    output = cfg.bulk_raw("dem", f"dem_{dept}_{int(resolution)}m.tif")
    from ..coverage import valid_bulk_dem
    metadata = output.with_suffix(".json")
    if not force and valid_bulk_dem(output):
        return output

    bbox = read_bbox(sub)
    bbox_wgs84 = read_bbox_wgs84(sub)
    grid = AnalysisGrid.from_bounds(bbox, resolution, cfg.crs)
    log.info("  MNT %s : lecture fenêtrée via VRT (%s×%s px)", dept, grid.width, grid.height)
    array = _read_window(vrt_path, bbox_wgs84, grid)
    if not np.isfinite(array).any():
        raise RuntimeError(f"MNT vide pour le département {dept}")
    write_cog(array, output, grid)
    metadata.write_text(json.dumps({"mosaic_version": 2, "source_vrt": str(vrt_path),
                                    "department": dept, "resolution_m": resolution}), encoding="utf-8")
    log.info("  MNT %s -> %s", dept, output.name)
    return output
