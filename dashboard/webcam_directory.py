"""Read and validate the generated YouTube webcam directory."""

import json
import math
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse


CAMERA_FIELDS = ("nom", "url_youtube", "lat", "lon", "id_maille")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def load_camera_directory(path: Path) -> list[dict]:
    """Load the generated JSON and reject malformed or unsafe entries."""
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
        if not is_youtube_video_url(url):
            raise ValueError(f"Entrée {index} de {path} : URL YouTube non valide.")
        if url in seen_urls:
            raise ValueError(f"Entrée {index} de {path} : URL YouTube en double.")
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


def is_youtube_video_url(url: str) -> bool:
    """Accept standard YouTube watch, short, live, and embed URLs only."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in YOUTUBE_HOSTS:
        return False
    if parsed.hostname == "youtu.be":
        return bool(parsed.path.strip("/"))
    if parsed.path == "/watch":
        return bool(parse_qs(parsed.query).get("v", [""])[0])
    return parsed.path.startswith(("/live/", "/embed/")) and bool(parsed.path.rsplit("/", 1)[-1])


def selected_camera_url(map_state: Mapping) -> str | None:
    """Return the URL selected in the webcam map, if any."""
    selection = map_state.get("selection", {})
    if not isinstance(selection, Mapping):
        return None
    objects = selection.get("objects", {})
    if not isinstance(objects, Mapping):
        return None
    selected = objects.get("youtube_cameras", [])
    if not selected or not isinstance(selected[0], Mapping):
        return None
    url = selected[0].get("url_youtube")
    return url if isinstance(url, str) else None
