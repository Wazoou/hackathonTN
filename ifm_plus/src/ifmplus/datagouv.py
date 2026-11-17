"""Client minimal pour l'API data.gouv.fr et téléchargements robustes."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("ifmplus")

CHUNK = 1 << 20  # 1 Mio


def make_session(retries: int = 4) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "ifm-plus/0.1 (hackathon Open Data University; contact: equipe)",
            "Accept-Encoding": "gzip, deflate",
        }
    )
    return session


def sha256(path: Path, block: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(block):
            digest.update(chunk)
    return digest.hexdigest()


class DataGouvClient:
    def __init__(self, base_url: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or make_session()

    # ------------------------------------------------------------------
    # Métadonnées
    # ------------------------------------------------------------------
    def dataset(self, slug: str) -> dict[str, Any]:
        url = f"{self.base_url}/datasets/{slug}/"
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return response.json()

    def pick_resource(
        self,
        dataset: dict[str, Any],
        formats: Iterable[str] | None = None,
        title_contains: str | None = None,
    ) -> dict[str, Any]:
        """Choisit la première ressource correspondant aux critères."""
        wanted = {f.lower().lstrip(".") for f in formats} if formats else None
        candidates = dataset.get("resources", [])

        for resource in candidates:
            fmt = str(resource.get("format") or "").lower().lstrip(".")
            title = str(resource.get("title") or "")
            if wanted and fmt not in wanted:
                continue
            if title_contains and title_contains.lower() not in title.lower():
                continue
            if resource.get("url"):
                return resource

        raise LookupError(
            f"Aucune ressource {formats or ''} dans le jeu de données "
            f"{dataset.get('slug') or dataset.get('title')!r}"
        )

    # ------------------------------------------------------------------
    # Téléchargement
    # ------------------------------------------------------------------
    def download(
        self,
        url: str,
        destination: Path,
        force: bool = False,
        expected_size: int | None = None,
    ) -> Path:
        if destination.exists() and destination.stat().st_size > 0 and not force:
            log.info("  déjà présent : %s", destination.name)
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_name(destination.name + ".part")

        log.info("  téléchargement %s", url)
        with self.session.get(url, stream=True, timeout=(30, 300)) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            written = 0
            next_log = 25 << 20
            with tmp.open("wb") as fh:
                for chunk in response.iter_content(CHUNK):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    written += len(chunk)
                    if written >= next_log:
                        if total:
                            log.info(
                                "    %.0f / %.0f Mo",
                                written / 1e6,
                                total / 1e6,
                            )
                        else:
                            log.info("    %.0f Mo", written / 1e6)
                        next_log += 25 << 20

        if expected_size and abs(tmp.stat().st_size - int(expected_size)) > 1024:
            raise IOError(
                f"Taille inattendue pour {url} : {tmp.stat().st_size} octets "
                f"(attendu {expected_size})"
            )

        tmp.replace(destination)
        log.info(
            "  -> %s (%.1f Mo)", destination.name, destination.stat().st_size / 1e6
        )
        return destination
