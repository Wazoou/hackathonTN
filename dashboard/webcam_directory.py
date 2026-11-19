"""Read and validate the generated webcam directory.

Supports every kind of webcam source: YouTube live/recorded videos, periodic
image URLs (JPG/PNG refreshed by the provider), HLS/MJPEG streams, etc.
"""

import csv
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import requests


CAMERA_FIELDS = ("nom", "url_youtube", "lat", "lon", "id_maille")
WEBCAM_LAYER_ID = "public-webcams"
VALID_SCHEMES = {"http", "https"}
_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_MAX_WEBCAM_IMAGE_BYTES = 8 * 1024 * 1024


def load_camera_directory(path: Path) -> list[dict]:
    """Load a complete CSV or generated JSON with the same validation rules.

    The versioned CSV contains positions and risk-cell identifiers, so viewing
    cameras never requires geocoding, a raw mesh, or a generated local JSON.
    ``url_youtube`` is retained as the historical field name for all feed types.
    """
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            first_line = handle.readline()
            handle.seek(0)
            reader = csv.DictReader(handle, delimiter=";" if ";" in first_line else ",")
            columns = {"ville", "url_youtube", "lat", "lon", "id_maille"}
            if not columns.issubset(reader.fieldnames or []):
                raise ValueError(f"Le CSV {path} doit contenir {', '.join(sorted(columns))}.")
            payload = []
            for row in reader:
                if None in row:
                    raise ValueError(f"Ligne CSV invalide dans {path} : trop de colonnes.")
                if not any(value and value.strip() for value in row.values()):
                    continue
                payload.append({
                    "nom": row["ville"], "url_youtube": row["url_youtube"],
                    "lat": row["lat"], "lon": row["lon"], "id_maille": row["id_maille"],
                })
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON invalide dans {path} : {error.msg}.") from error

    if not isinstance(payload, list):
        raise ValueError(f"L’annuaire {path} doit contenir une liste de webcams.")

    cameras = []
    seen_urls = set()
    for index, camera in enumerate(payload, start=1):
        if not isinstance(camera, dict) or set(camera) != set(CAMERA_FIELDS):
            raise ValueError(
                f"Entrée {index} de {path} : les champs attendus sont "
                f"{', '.join(CAMERA_FIELDS)}."
            )
        name, url, maille = camera["nom"], camera["url_youtube"], camera["id_maille"]
        if not all(isinstance(value, str) and value.strip() for value in (name, url, maille)):
            raise ValueError(f"Entrée {index} de {path} : nom, URL et maille doivent être renseignés.")
        if not is_valid_webcam_url(url):
            raise ValueError(f"Entrée {index} de {path} : URL de webcam non valide.")
        if url in seen_urls:
            raise ValueError(f"Entrée {index} de {path} : URL de webcam en double.")
        seen_urls.add(url)

        coordinates = []
        for field, minimum, maximum in (("lat", -90, 90), ("lon", -180, 180)):
            value = camera[field]
            if isinstance(value, bool):
                raise ValueError(f"Entrée {index} de {path} : coordonnée {field} non valide.")
            try:
                coordinate = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Entrée {index} de {path} : coordonnée {field} non valide."
                ) from error
            if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
                raise ValueError(f"Entrée {index} de {path} : coordonnée {field} hors limites.")
            coordinates.append(coordinate)

        cameras.append(
            {
                "nom": name.strip(),
                "url_youtube": url,
                "lat": coordinates[0],
                "lon": coordinates[1],
                "id_maille": maille.strip(),
            }
        )
    return cameras


def is_valid_webcam_url(url: str) -> bool:
    """Accept any http(s) URL pointing to a webcam feed or player page."""
    if not url or not isinstance(url, str):
        return False
    if not _URL_RE.match(url.strip()):
        return False
    parsed = urlparse(url)
    return parsed.scheme.lower() in VALID_SCHEMES and bool(parsed.hostname)


def youtube_video_id(url: str) -> str | None:
    """Extract the video identifier from a YouTube URL, if it is one."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }:
        return None
    if parsed.hostname == "youtu.be":
        path_parts = [part for part in parsed.path.split("/") if part]
        video_id = path_parts[0] if len(path_parts) == 1 else ""
    elif parsed.path == "/watch":
        from urllib.parse import parse_qs

        video_id = parse_qs(parsed.query).get("v", [""])[0]
    else:
        path_parts = [part for part in parsed.path.split("/") if part]
        video_id = (
            path_parts[1]
            if len(path_parts) == 2 and path_parts[0] in {"live", "embed"}
            else ""
        )
    return video_id if re.fullmatch(r"[A-Za-z0-9_-]+", video_id) else None


def webcam_embed_url(url: str) -> str:
    """Return an embeddable URL for the webcam.

    YouTube watch/live URLs are converted to their embed form (tracking
    parameters such as ``?si=...`` are stripped). Any other URL is returned
    as-is.
    """
    video_id = youtube_video_id(url)
    if video_id is not None:
        return f"https://www.youtube.com/embed/{video_id}"
    return url


def webcam_display_type(url: str) -> str:
    """Classify a webcam URL for display purposes.

    Returns one of:
    * ``"youtube"`` — a YouTube watch/live video (embed in an iframe).
    * ``"image"``   — a direct image snapshot (JPG/PNG).
    * ``"video"``   — a direct video or HLS stream.
    * ``"mjpeg"``   — a direct MJPEG stream.
    * ``"external"``— any other page/stream (open in a new tab).
    """
    video_id = youtube_video_id(url)
    if video_id is not None:
        return "youtube"
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
        return "image"
    if path.endswith((".m3u8", ".mp4", ".webm", ".ogv", ".ogg")):
        return "video"
    if path.endswith((".mjpg", ".mjpeg")):
        return "mjpeg"
    return "external"


def fetch_opencctv_snapshot(url: str) -> bytes:
    """Fetch an OpenCCTV image server-side to avoid browser cross-origin blocks."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "opencctv.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Seules les images HTTPS d’OpenCCTV sont prises en charge ici.")

    with requests.get(
        url,
        timeout=(5, 10),
        allow_redirects=False,
        stream=True,
    ) as response:
        if response.status_code != 200:
            raise ValueError(f"Le diffuseur a répondu HTTP {response.status_code}.")
        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            raise ValueError("Le diffuseur n’a pas renvoyé une image.")

        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > _MAX_WEBCAM_IMAGE_BYTES:
                raise ValueError("L’image dépasse la taille maximale autorisée.")
        if not content:
            raise ValueError("Le diffuseur a renvoyé une image vide.")
        return bytes(content)


def selected_camera_url(map_state: Mapping) -> str | None:
    """Return the URL selected in the webcam map, if any."""
    selection = map_state.get("selection", {})
    if not isinstance(selection, Mapping):
        return None
    objects = selection.get("objects", {})
    if not isinstance(objects, Mapping):
        return None
    selected = objects.get(WEBCAM_LAYER_ID, [])
    if not selected or not isinstance(selected[0], Mapping):
        return None
    url = selected[0].get("url_youtube")
    return url if isinstance(url, str) else None
