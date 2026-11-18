"""Build a French YouTube Live webcam directory joined to a risk-cell mesh.

Requirements are available in ``ifm_plus/requirements.txt``. Set
``YOUTUBE_API_KEY`` in the environment, then run, for example:

    python ml/build_camera_directory.py --mesh path/to/mon_maillage.parquet \
        --id-column id_carreau_dfci

The YouTube Data API is used only for public live metadata; this script does
not download or store video. Missing coordinates are geocoded through
Nominatim, at its public-service rate limit.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import geopandas as gpd
import pandas as pd
import requests


YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
NOMINATIM_API = "https://nominatim.openstreetmap.org/search"
OUTPUT_FIELDS = ("nom", "url_youtube", "lat", "lon", "id_maille")
SEARCH_QUERIES = (
    "webcam forêt vallée France en direct",
    "webcam montagne forêt France live",
    "webcam littoral plage côte France en direct",
    "webcam parc naturel France live",
    "webcam office de tourisme village station France live",
    "webcam live Alpes France",
    "webcam live Pyrénées France",
    "webcam live Corse",
    "webcam live Var Provence Côte d'Azur",
    "webcam live Landes Gironde",
    "webcam live Ardèche Cévennes",
    "webcam live Massif Central Auvergne",
    "webcam live Vosges Jura",
    "webcam live Bretagne Normandie",
    "webcam météo France en direct",
)
GEOCODING_STOP_WORDS = re.compile(
    r"\b(?:office\s+de\s+tourisme|syndicat\s+d['’]initiative|mairie\s+de|"
    r"webcam|livecam|cam[eé]ra|camera|en\s+direct|en\s+continu|direct|live|"
    r"stream|streaming|panoramique|panorama|vue\s+sur|vue|m[eé]t[eé]o|meteo|"
    r"station\s+de\s+ski|station|domaine\s+skiable|france|uhd|4k|hd|fhd|"
    r"24/7|24h/24|7j/7|\d{3,4}\s*m)\b",
    flags=re.IGNORECASE,
)


def request_json(
    session: requests.Session,
    url: str,
    params: Mapping[str, Any],
    *,
    timeout: float = 25,
) -> dict[str, Any]:
    """Fetch JSON and surface API/network failures without leaking query keys."""
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as error:
            if attempt == 2:
                raise RuntimeError(
                    f"Request to {url.split('?')[0]} failed ({type(error).__name__})."
                ) from error
            time.sleep(2**attempt)
            continue

        if response.status_code == 429 or response.status_code >= 500:
            if attempt < 2:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(30.0, max(1.0, float(retry_after))) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                time.sleep(delay)
                continue
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            message = f"HTTP {response.status_code}"
            if detail:
                message += f": {detail}"
            raise RuntimeError(f"Request to {url.split('?')[0]} failed ({message}).")
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(f"Invalid JSON returned by {url.split('?')[0]}.") from error
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected JSON response from {url.split('?')[0]}.")
        if "error" in payload:
            detail = payload["error"].get("message", "Unknown API error")
            raise RuntimeError(f"API error from {url.split('?')[0]}: {detail}")
        return payload
    raise RuntimeError(f"Request to {url.split('?')[0]} failed after retries.")


def discover_live_video_ids(
    session: requests.Session,
    api_key: str,
    queries: Sequence[str] = SEARCH_QUERIES,
    results_per_query: int = 25,
) -> list[str]:
    """Search active public broadcasts and deduplicate their YouTube IDs."""
    video_ids: list[str] = []
    seen: set[str] = set()
    for query in queries:
        result = request_json(
            session,
            f"{YOUTUBE_API}/search",
            {
                "key": api_key,
                "part": "snippet",
                "q": query,
                "type": "video",
                "eventType": "live",
                "regionCode": "FR",
                "relevanceLanguage": "fr",
                "maxResults": results_per_query,
            },
        )
        for item in result.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if video_id and video_id not in seen:
                seen.add(video_id)
                video_ids.append(video_id)
    return video_ids


def is_active_public_live(video: Mapping[str, Any]) -> bool:
    """Reject upcoming, ended, and non-public broadcasts."""
    snippet = video.get("snippet") or {}
    live = video.get("liveStreamingDetails") or {}
    status = video.get("status") or {}
    return (
        snippet.get("liveBroadcastContent") == "live"
        and status.get("privacyStatus") == "public"
        and bool(live.get("actualStartTime"))
        and not live.get("actualEndTime")
    )


def fetch_active_live_videos(
    session: requests.Session,
    api_key: str,
    video_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Fetch full metadata in API-sized batches and recheck live status."""
    videos: list[dict[str, Any]] = []
    for start in range(0, len(video_ids), 50):
        result = request_json(
            session,
            f"{YOUTUBE_API}/videos",
            {
                "key": api_key,
                "part": "snippet,liveStreamingDetails,recordingDetails,status",
                "id": ",".join(video_ids[start : start + 50]),
                "maxResults": 50,
            },
        )
        videos.extend(video for video in result.get("items", []) if is_active_public_live(video))
    return videos


def valid_coordinates(lat: Any, lon: Any) -> tuple[float, float] | None:
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

def _clean_geo_text(text: str) -> str | None:
    cleaned = GEOCODING_STOP_WORDS.sub(" ", html.unescape(text))
    # Retire les émojis / caractères spéciaux tout en gardant lettres, chiffres, tirets et apostrophes
    cleaned = re.sub(r"[^\w\s'\-àâäéèêëïîôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-_")
    cleaned = re.sub(
        r"^(?:de\s+la|de\s+l['’]|du|des|de|d['’]|à|au|aux|sur|en|le|la|les|l['’])\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip(" .-_")
    if len(cleaned) < 3 or cleaned.isdigit():
        return None
    return cleaned


def build_location_queries(
    title: str,
    location_description: str | None = None,
    channel_title: str | None = None,
) -> list[str]:
    """Génère plusieurs pistes de lieu (segments du titre, description, chaîne)."""
    raw_candidates: list[str] = []
    if location_description:
        raw_candidates.append(location_description)

    # Découpe sur les séparateurs avec espaces (pour garder les noms comme Saint-Tropez)
    parts = re.split(r"\s+[-–—|/:•]\s+|[()\[\]]", html.unescape(title))
    raw_candidates.extend(parts)
    raw_candidates.append(title)
    if channel_title:
        raw_candidates.append(channel_title)

    queries: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        cleaned = _clean_geo_text(raw)
        if not cleaned:
            continue
        query = cleaned if re.search(r"\bfrance\b", cleaned, flags=re.IGNORECASE) else f"{cleaned}, France"
        key = query.casefold()
        if key not in seen:
            seen.add(key)
            queries.append(query)
    return queries


def video_to_candidate(video: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract the title, canonical URL, source coordinates, and geocoding hints."""
    video_id = video.get("id")
    snippet = video.get("snippet") or {}
    title = str(snippet.get("title") or "").strip()
    channel_title = str(snippet.get("channelTitle") or "").strip() or None
    if not video_id or not title:
        return None
    recording = video.get("recordingDetails") or {}
    location = recording.get("location") or {}
    coordinates = valid_coordinates(location.get("latitude"), location.get("longitude"))
    location_description = recording.get("locationDescription")
    if not isinstance(location_description, str):
        location_description = None
    return {
        "nom": title,
        "url_youtube": f"https://www.youtube.com/watch?v={video_id}",
        "lat": coordinates[0] if coordinates else None,
        "lon": coordinates[1] if coordinates else None,
        "_location_queries": build_location_queries(title, location_description, channel_title),
    }


class NominatimGeocoder:
    """Geocoder France (API Adresse en priorité, Nominatim en secours sans crash)."""

    def __init__(
        self,
        session: requests.Session,
        *,
        user_agent: str,
        min_interval: float = 1.1,
        max_requests: int = 80,
    ) -> None:
        self.session = session
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.max_requests = max_requests
        self.requests_made = 0
        self._last_request_at: float | None = None
        self._cache: dict[str, tuple[float, float] | None] = {}

    @property
    def can_request(self) -> bool:
        return self.requests_made < self.max_requests

    def geocode(self, query: str) -> tuple[float, float] | None:
        normalized = query.strip().casefold()
        if normalized in self._cache:
            return self._cache[normalized]

        # 1. API Adresse officielle française (on garde uniquement commune / lieu-dit)
        clean_query = re.sub(r",?\s*france$", "", query, flags=re.IGNORECASE).strip()
        if clean_query:
            try:
                ban_resp = self.session.get(
                    "https://api-adresse.data.gouv.fr/search/",
                    params={"q": clean_query, "limit": 3},
                    timeout=10,
                )
                if ban_resp.ok:
                    for feat in ban_resp.json().get("features") or []:
                        props = feat.get("properties") or {}
                        if props.get("type") not in {"municipality", "locality"}:
                            continue
                        if props.get("score", 0) < 0.45:
                            continue
                        coords = (feat.get("geometry") or {}).get("coordinates") or []
                        if len(coords) >= 2:
                            coordinates = valid_coordinates(coords[1], coords[0])
                            if coordinates:
                                self._cache[normalized] = coordinates
                                return coordinates
            except (requests.RequestException, ValueError, KeyError, TypeError):
                pass

        # 2. Secours via Nominatim (si API Adresse n'a rien trouvé)
        if not self.can_request:
            self._cache[normalized] = None
            return None

        coordinates = None
        for attempt in range(2):
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                if elapsed < self.min_interval:
                    time.sleep(self.min_interval - elapsed)
            self._last_request_at = time.monotonic()
            if attempt == 0:
                self.requests_made += 1
            try:
                response = self.session.get(
                    NOMINATIM_API,
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": 5,
                        "countrycodes": "fr",
                        "addressdetails": 1,
                    },
                    headers={"User-Agent": self.user_agent},
                    timeout=20,
                )
            except requests.RequestException:
                time.sleep(2)
                continue

            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            if response.status_code >= 400:
                break

            try:
                results = response.json()
            except ValueError:
                break
            if isinstance(results, list):
                for result in results:
                    address = result.get("address", {})
                    if address.get("country_code", "").casefold() != "fr":
                        continue
                    coordinates = valid_coordinates(result.get("lat"), result.get("lon"))
                    if coordinates:
                        break
            break

        self._cache[normalized] = coordinates
        return coordinates


def resolve_candidate_locations(
    candidates: Sequence[dict[str, Any]],
    geocoder: NominatimGeocoder,
) -> tuple[list[dict[str, Any]], int]:
    """Fill missing GPS values by trying each extracted location hint."""
    resolved: list[dict[str, Any]] = []
    unresolved = 0
    for candidate in candidates:
        camera = dict(candidate)
        queries = camera.pop("_location_queries", [])
        if camera["lat"] is None or camera["lon"] is None:
            coordinates = None
            for query in queries:
                coordinates = geocoder.geocode(query)
                if coordinates:
                    break
            if not coordinates:
                unresolved += 1
                continue
            camera["lat"], camera["lon"] = coordinates
        resolved.append(camera)
    return resolved, unresolved


def read_mesh(mesh_path: Path) -> gpd.GeoDataFrame:
    """Load a GeoParquet/Parquet or vector file as a georeferenced mesh."""
    if not mesh_path.is_file():
        raise FileNotFoundError(f"Mesh file does not exist: {mesh_path}")
    if mesh_path.suffix.casefold() in {".parquet", ".pq"}:
        return gpd.read_parquet(mesh_path)
    return gpd.read_file(mesh_path)


def validate_mesh(mesh: gpd.GeoDataFrame, id_column: str) -> str:
    """Validate the mesh and return its active geometry-column name."""
    if id_column not in mesh.columns:
        raise ValueError(f"Mesh identifier column not found: {id_column}")
    if mesh.crs is None:
        raise ValueError("Mesh CRS is missing; assign its correct CRS before joining.")
    try:
        geometry_column = mesh.geometry.name
    except AttributeError as error:
        raise ValueError("Mesh has no active geometry column.") from error
    if geometry_column not in mesh.columns:
        raise ValueError("Mesh geometry column is missing.")
    if "__id_maille" in mesh.columns:
        raise ValueError("Mesh already contains the reserved column '__id_maille'.")
    if id_column == geometry_column:
        raise ValueError("Mesh identifier column cannot be the geometry column.")
    if mesh[id_column].isna().any():
        raise ValueError(f"Mesh identifier column contains null values: {id_column}")
    if mesh[id_column].astype(str).duplicated().any():
        raise ValueError(f"Mesh identifier column contains duplicates: {id_column}")
    if mesh.geometry.isna().any() or mesh.geometry.is_empty.any():
        raise ValueError("Mesh contains missing or empty geometries.")
    geometry_types = set(mesh.geometry.geom_type.dropna())
    if not geometry_types or not geometry_types.issubset({"Polygon", "MultiPolygon"}):
        raise ValueError("Mesh geometries must be Polygon or MultiPolygon.")
    return geometry_column


def assign_cameras_to_mesh(
    cameras: Sequence[Mapping[str, Any]],
    mesh: gpd.GeoDataFrame,
    id_column: str,
) -> list[dict[str, Any]]:
    """Spatially join points to polygons and emit only the five public fields."""
    geometry_column = validate_mesh(mesh, id_column)

    unique_cameras: list[Mapping[str, Any]] = []
    seen_urls: set[str] = set()
    for camera in cameras:
        url = str(camera["url_youtube"])
        if url not in seen_urls:
            if valid_coordinates(camera.get("lat"), camera.get("lon")) is None:
                raise ValueError(f"Camera has invalid coordinates: {url}")
            seen_urls.add(url)
            unique_cameras.append(camera)
    if not unique_cameras:
        return []

    mesh_view = mesh[[id_column, geometry_column]].rename(columns={id_column: "__id_maille"})
    mesh_view = gpd.GeoDataFrame(mesh_view, geometry=geometry_column, crs=mesh.crs).to_crs("EPSG:4326")
    points = gpd.GeoDataFrame(
        list(unique_cameras),
        geometry=gpd.points_from_xy(
            [camera["lon"] for camera in unique_cameras],
            [camera["lat"] for camera in unique_cameras],
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
    if matches.empty:
        return []

    matches = matches.assign(__id_sort=matches["__id_maille"].astype(str))
    matches = matches.sort_values(["url_youtube", "__id_sort"], kind="stable")
    matches = matches.drop_duplicates(subset="url_youtube")
    result: list[dict[str, Any]] = []
    for _, row in matches.iterrows():
        result.append(
            {
                "nom": str(row["nom"]),
                "url_youtube": str(row["url_youtube"]),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "id_maille": str(row["__id_maille"]),
            }
        )
    return result


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


def write_sqlite(path: Path, cameras: Sequence[Mapping[str, Any]]) -> None:
    """Replace the cameras table, whose schema contains exactly OUTPUT_FIELDS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables - {"cameras"}:
            raise ValueError(
                f"SQLite database contains other tables: {', '.join(sorted(tables - {'cameras'}))}. "
                "Choose a separate output database."
            )
        if "cameras" in tables:
            columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(cameras)"))
            if columns != OUTPUT_FIELDS:
                raise ValueError(
                    "Existing SQLite cameras table has a different schema; choose a new output database."
                )
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS cameras ("
                "nom TEXT NOT NULL, "
                "url_youtube TEXT NOT NULL UNIQUE, "
                "lat REAL NOT NULL, "
                "lon REAL NOT NULL, "
                "id_maille TEXT NOT NULL)"
            )
            connection.execute("DELETE FROM cameras")
            connection.executemany(
                "INSERT INTO cameras (nom, url_youtube, lat, lon, id_maille) "
                "VALUES (:nom, :url_youtube, :lat, :lon, :id_maille)",
                cameras,
            )
    finally:
        connection.close()


def build_directory(
    *,
    api_key: str,
    mesh_path: Path,
    id_column: str,
    output_json: Path,
    output_sqlite: Path,
    queries: Sequence[str] = SEARCH_QUERIES,
    results_per_query: int = 25,
    max_geocoding_requests: int = 80,
    nominatim_user_agent: str,
) -> tuple[int, int, int]:
    """Discover, validate, geocode, spatially join, and export webcam streams."""
    if output_json.resolve() == output_sqlite.resolve():
        raise ValueError("JSON and SQLite outputs must use different file paths.")
    mesh = read_mesh(mesh_path)
    validate_mesh(mesh, id_column)
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    video_ids = discover_live_video_ids(session, api_key, queries, results_per_query)
    videos = fetch_active_live_videos(session, api_key, video_ids)
    candidates = [
        candidate
        for video in videos
        if (candidate := video_to_candidate(video)) is not None
    ]
    geocoder = NominatimGeocoder(
        session,
        user_agent=nominatim_user_agent,
        max_requests=max_geocoding_requests,
    )
    located, unresolved = resolve_candidate_locations(candidates, geocoder)
    cameras = assign_cameras_to_mesh(located, mesh, id_column)
    write_json(output_json, cameras)
    write_sqlite(output_sqlite, cameras)
    unmatched_mesh = len(located) - len(cameras)
    print(
        f"YouTube IDs: {len(video_ids)}; lives actifs vérifiés: {len(videos)}; "
        f"sans coordonnées: {unresolved}; hors maillage: {unmatched_mesh}; "
        f"annuaire exporté: {len(cameras)}."
    )
    if geocoder.requests_made >= max_geocoding_requests and unresolved:
        print(
            f"Limite Nominatim atteinte ({max_geocoding_requests} requêtes). "
            "Augmentez --max-geocoding-requests pour traiter davantage de flux."
        )
    return len(cameras), unresolved, unmatched_mesh


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mesh", required=True, type=Path, help="Fichier de maillage GeoParquet, Parquet ou vectoriel.")
    parser.add_argument("--id-column", required=True, help="Nom de la colonne d’identifiant de maille.")
    parser.add_argument("--output-json", type=Path, default=Path("camera-data/cameras.json"))
    parser.add_argument("--output-sqlite", type=Path, default=Path("camera-data/cameras.sqlite"))
    parser.add_argument(
        "--youtube-api-key",
        default=os.getenv("YOUTUBE_API_KEY"),
        help="Clé YouTube Data API (ou variable d’environnement YOUTUBE_API_KEY).",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="extra_queries",
        default=[],
        help="Requête de recherche supplémentaire (peut être répétée).",
    )
    parser.add_argument("--results-per-query", type=int, default=25, choices=range(1, 51))
    parser.add_argument("--max-geocoding-requests", type=int, default=80)
    parser.add_argument(
        "--nominatim-user-agent",
        default=os.getenv(
            "NOMINATIM_USER_AGENT",
            "PyroWatchWebcamDirectory/1.0 (+https://github.com/Wazoou/hackathonTN)",
        ),
        help="User-Agent identifiable pour respecter la politique Nominatim.",
    )
    args = parser.parse_args(argv)
    if not args.youtube_api_key:
        parser.error("Définissez YOUTUBE_API_KEY avec une clé YouTube Data API.")
    if args.max_geocoding_requests < 0:
        parser.error("--max-geocoding-requests must be zero or greater.")
    args.queries = (*SEARCH_QUERIES, *args.extra_queries)
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    build_directory(
        api_key=args.youtube_api_key,
        mesh_path=args.mesh,
        id_column=args.id_column,
        output_json=args.output_json,
        output_sqlite=args.output_sqlite,
        queries=args.queries,
        results_per_query=args.results_per_query,
        max_geocoding_requests=args.max_geocoding_requests,
        nominatim_user_agent=args.nominatim_user_agent,
    )


if __name__ == "__main__":
    main()
