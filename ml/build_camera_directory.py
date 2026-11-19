"""Create a webcam directory from a CSV of links and French cities.

Accepts every kind of webcam source: YouTube live/recorded videos, periodic
image URLs (JPG/PNG refreshed by the provider), HLS/MJPEG streams, etc.

Run from the repository root:

    python ml/build_camera_directory.py

The script reads camera-data/cameras.csv, geocodes each city through the public
French Address API, and places the point in the risk-cell mesh. No API key is
needed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import geopandas as gpd
import pandas as pd
import requests


ADRESSE_API = "https://api-adresse.data.gouv.fr/search/"
OUTPUT_FIELDS = ("nom", "url_youtube", "lat", "lon", "id_maille")
VALID_SCHEMES = {"http", "https"}
_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def is_valid_webcam_url(url: str) -> bool:
    """Accept any http(s) URL pointing to a webcam feed or player page."""
    if not url or not isinstance(url, str):
        return False
    if not _URL_RE.match(url.strip()):
        return False
    parsed = urlparse(url)
    return parsed.scheme.lower() in VALID_SCHEMES and bool(parsed.hostname)


def valid_coordinates(lat: object, lon: object) -> tuple[float, float] | None:
    """Return finite WGS84 coordinates, or None for absent/invalid values."""
    try:
        latitude, longitude = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def geocode_city(session: requests.Session, city: str) -> tuple[float, float]:
    """Resolve a French commune name without a key, rejecting ambiguous matches."""
    try:
        response = session.get(
            ADRESSE_API,
            params={"q": city, "type": "municipality", "limit": 5},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(f"Impossible de géolocaliser « {city} » : service indisponible.") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("Réponse invalide du service de géolocalisation.") from error
    if not isinstance(payload, Mapping) or not isinstance(payload.get("features"), list):
        raise RuntimeError("Réponse invalide du service de géolocalisation.")

    matches: list[tuple[float, tuple[float, float], str]] = []
    for feature in payload["features"]:
        if not isinstance(feature, Mapping):
            continue
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            continue
        if properties.get("type") != "municipality":
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        point = valid_coordinates(coordinates[1], coordinates[0])
        if point is None:
            continue
        try:
            score = float(properties.get("score", 0))
        except (TypeError, ValueError):
            continue
        if score >= 0.45:
            label = str(properties.get("city") or properties.get("name") or city)
            matches.append((score, point, label))

    if not matches:
        raise ValueError(f"Ville « {city} » introuvable. Vérifiez son nom.")
    matches.sort(key=lambda result: result[0], reverse=True)
    best_score, best_point, _ = matches[0]
    alternatives = {
        point
        for score, point, label in matches
        if score >= best_score - 0.05 and point != best_point
    }
    if alternatives:
        raise ValueError(
            f"Ville « {city} » ambiguë. Ajoutez son département, par exemple « {city}, 33 »."
        )
    return best_point


def read_camera_csv(
    path: Path,
    *,
    output_fn: Callable[[str], None] = print,
) -> list[dict[str, str]]:
    """Read and validate URL/city rows from a comma- or semicolon-separated CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"Fichier CSV introuvable : {path}")

    with path.open(encoding="utf-8-sig", newline="") as handle:
        first_line = handle.readline()
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
        handle.seek(0)
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError(f"Le CSV {path} est vide. Ajoutez les colonnes url_youtube et ville.")
        columns = {
            field.strip().casefold(): field
            for field in reader.fieldnames
            if field and field.strip()
        }
        if "url_youtube" not in columns or "ville" not in columns:
            raise ValueError(
                f"Le CSV {path} doit contenir les colonnes url_youtube et ville."
            )

        seen_urls: set[str] = set()
        cameras: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Ligne {line_number} du CSV {path} : trop de colonnes.")
            url = (row.get(columns["url_youtube"]) or "").strip()
            city = (row.get(columns["ville"]) or "").strip()
            if not url and not city:
                continue
            if not url or not city:
                raise ValueError(
                    f"Ligne {line_number} du CSV {path} : URL de webcam et ville obligatoires."
                )
            if not is_valid_webcam_url(url):
                raise ValueError(f"Ligne {line_number} du CSV {path} : URL de webcam non valide.")
            if url in seen_urls:
                output_fn(f"Ligne {line_number} : lien déjà présent, ignoré ({url}).")
                continue
            seen_urls.add(url)
            cameras.append({"nom": city, "url_youtube": url})
    return cameras


def read_mesh(mesh_path: Path) -> gpd.GeoDataFrame:
    """Load a GeoParquet/Parquet or vector file as a georeferenced mesh."""
    if not mesh_path.is_file():
        raise FileNotFoundError(f"Maillage introuvable : {mesh_path}")
    if mesh_path.suffix.casefold() in {".parquet", ".pq"}:
        return gpd.read_parquet(mesh_path)
    return gpd.read_file(mesh_path)


def validate_mesh(mesh: gpd.GeoDataFrame, id_column: str) -> str:
    """Validate the mesh and return its active geometry-column name."""
    if id_column not in mesh.columns:
        raise ValueError(f"Colonne d’identifiant de maille absente : {id_column}")
    if mesh.crs is None:
        raise ValueError("Le système de coordonnées du maillage est absent.")
    try:
        geometry_column = mesh.geometry.name
    except AttributeError as error:
        raise ValueError("Le maillage ne contient pas de géométrie active.") from error
    if geometry_column not in mesh.columns:
        raise ValueError("La colonne de géométrie du maillage est absente.")
    if "__id_maille" in mesh.columns:
        raise ValueError("Le maillage contient déjà la colonne réservée '__id_maille'.")
    if id_column == geometry_column or mesh[id_column].isna().any():
        raise ValueError(f"Colonne d’identifiant de maille invalide : {id_column}")
    if mesh[id_column].astype(str).duplicated().any():
        raise ValueError(f"Identifiants de maille en double : {id_column}")
    if mesh.geometry.isna().any() or mesh.geometry.is_empty.any():
        raise ValueError("Le maillage contient des géométries absentes ou vides.")
    geometry_types = set(mesh.geometry.geom_type.dropna())
    if not geometry_types or not geometry_types.issubset({"Polygon", "MultiPolygon"}):
        raise ValueError("Les géométries du maillage doivent être des polygones.")
    return geometry_column


def assign_cameras_to_mesh(
    cameras: Sequence[Mapping[str, Any]],
    mesh: gpd.GeoDataFrame,
    id_column: str,
) -> list[dict[str, Any]]:
    """Join camera points to risk cells and emit the dashboard's five public fields."""
    geometry_column = validate_mesh(mesh, id_column)
    if not cameras:
        return []

    mesh_view = mesh[[id_column, geometry_column]].rename(columns={id_column: "__id_maille"})
    mesh_view = gpd.GeoDataFrame(mesh_view, geometry=geometry_column, crs=mesh.crs).to_crs("EPSG:4326")
    points = gpd.GeoDataFrame(
        list(cameras),
        geometry=gpd.points_from_xy(
            [camera["lon"] for camera in cameras],
            [camera["lat"] for camera in cameras],
        ),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(
        points,
        mesh_view[["__id_maille", geometry_column]],
        how="left",
        predicate="within",
    )
    matches = joined[joined["__id_maille"].notna()]
    unmatched_points = points.loc[~points.index.isin(matches.index)]
    if not unmatched_points.empty:
        boundary_matches = gpd.sjoin(
            unmatched_points,
            mesh_view[["__id_maille", geometry_column]],
            how="inner",
            predicate="intersects",
        )
        matches = pd.concat([matches, boundary_matches])

    matched_urls = set(matches["url_youtube"])
    outside_mesh = points.loc[~points["url_youtube"].isin(matched_urls)].copy()
    if not outside_mesh.empty:
        outside_mesh["__id_maille"] = "Hors maillage"
        matches = pd.concat([matches, outside_mesh])

    matches = matches.assign(__id_sort=matches["__id_maille"].astype(str))
    matches = matches.sort_values(["url_youtube", "__id_sort"], kind="stable")
    matches = matches.drop_duplicates(subset="url_youtube")
    return [
        {
            "nom": str(row["nom"]),
            "url_youtube": str(row["url_youtube"]),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "id_maille": str(row["__id_maille"]),
        }
        for _, row in matches.iterrows()
    ]


def write_json(path: Path, cameras: Sequence[Mapping[str, Any]]) -> None:
    """Write the public directory atomically as a UTF-8 JSON array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(list(cameras), handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def build_directory(
    *,
    mesh_path: Path,
    id_column: str,
    input_csv: Path,
    output_json: Path,
    output_fn: Callable[[str], None] = print,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Rebuild the webcam JSON to exactly match the CSV."""
    mesh = read_mesh(mesh_path)
    validate_mesh(mesh, id_column)
    geocoding_session = session or requests.Session()
    geocoding_session.headers.update({"Accept": "application/geo+json"})
    csv_cameras = read_camera_csv(input_csv, output_fn=output_fn)

    new_entries: list[dict[str, Any]] = []
    skipped_geocode: list[str] = []
    coordinates_by_city: dict[str, tuple[float, float] | None] = {}
    for camera in csv_cameras:
        city_key = " ".join(camera["nom"].split()).casefold()
        if city_key not in coordinates_by_city:
            try:
                coordinates_by_city[city_key] = geocode_city(
                    geocoding_session, camera["nom"]
                )
            except (ValueError, RuntimeError) as exc:
                coordinates_by_city[city_key] = None
                skipped_geocode.append(f"{camera['nom']} ({exc})")
                output_fn(f"Ville « {camera['nom']} » ignorée : {exc}")
        coordinates = coordinates_by_city[city_key]
        if coordinates is None:
            continue
        lat, lon = coordinates
        new_entries.append({**camera, "lat": lat, "lon": lon})
        output_fn(f"Ville « {camera['nom']} » localisée : {lat:.5f}, {lon:.5f}.")

    if skipped_geocode:
        output_fn(
            f"{len(skipped_geocode)} ville(s) ignorée(s) lors du géocodage : "
            + "; ".join(skipped_geocode[:10])
            + (" ..." if len(skipped_geocode) > 10 else "")
        )

    located = assign_cameras_to_mesh(new_entries, mesh, id_column)
    write_json(output_json, located)
    output_fn(f"Annuaire synchronisé avec le CSV : {len(located)} webcam(s) dans {output_json}.")
    return located


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("camera-data/cameras.csv"),
        help="CSV contenant les colonnes url_youtube et ville.",
    )
    parser.add_argument(
        "--mesh",
        type=Path,
        default=Path("ifm_plus/data/raw/dfci/dfci_2km.gpkg"),
        help="Maillage des risques GeoParquet, Parquet ou vectoriel.",
    )
    parser.add_argument("--id-column", default="id_carreau_dfci", help="Colonne d’identifiant de maille.")
    parser.add_argument("--output-json", type=Path, default=Path("camera-data/camera.json"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        build_directory(
            mesh_path=args.mesh,
            id_column=args.id_column,
            input_csv=args.input_csv,
            output_json=args.output_json,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Erreur : {error}") from error


if __name__ == "__main__":
    main()
