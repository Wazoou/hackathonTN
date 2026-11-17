"""Client de l'API de téléchargement bulk de la Géoplateforme (Atom).

L'IGN expose ses archives sous ``https://data.geopf.fr/telechargement`` selon
la norme Atom RFC 4287. Trois niveaux sont utilisés :

1. ``/capabilities`` : catalogue des ressources (BDTOPO, BDFORET, RPG…) ;
2. ``/resource/{RESSOURCE}`` : sous-ressources (une par département/région et
   par édition), filtrables par ``zone`` et ``format`` ;
3. ``/resource/{RESSOURCE}/{SOUS_RESSOURCE}`` : entrée de téléchargement avec
   le lien ``alternate``, la taille et l'empreinte MD5 de l'archive ;
4. ``/download/...`` : archive ``.7z`` (ou ``.zip``) à proprement parler.

Le client gère :

- la **pagination** (``page`` / ``limit``, 50 entrées max) ;
- la **limitation de débit** (10 requêtes/s/IP côté IGN) ;
- les **retries** avec back-off exponentiel ;
- le **téléchargement reprenable** (fichier ``.part`` + en-tête ``Range``) ;
- le **garde-fou disque** avant d'écrire une archive volumineuse ;
- un fichier annexe ``.download.json`` (URL, taille, ETag, date).
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("ifmplus")

GEOPF_BASE = "https://data.geopf.fr/telechargement"
ATOM = "{http://www.w3.org/2005/Atom}"
GPF = "{https://data.geopf.fr/annexes/ressources/xsd/gpf_dl.xsd}"
ATOM_NS = {"atom": ATOM.strip("{}")}


class GeoPlateformeError(RuntimeError):
    """Erreur fonctionnelle de l'API Géoplateforme."""


@dataclass(frozen=True)
class SubResource:
    """Sous-ressource téléchargeable (une archive par couple zone/édition)."""

    resource: str
    name: str
    zone: str | None = None
    format: str | None = None
    edition: str | None = None
    download_url: str = ""
    size: int | None = None
    md5: str | None = None

    @property
    def resource_url(self) -> str:
        return f"{GEOPF_BASE}/resource/{self.resource}/{self.name}"

    @property
    def suffix(self) -> str:
        suffix = Path(self.download_url).suffix.lower()
        return suffix or ".7z"


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    size: int
    cached: bool
    url: str
    md5: str | None = None
    edition: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def human_bytes(value: float | None) -> str:
    if value is None:
        return "?"
    units = ("o", "Ko", "Mo", "Go", "To")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value:.0f} o"


class _RateLimiter:
    """Espacement minimal entre deux requêtes HTTP (thread-safe)."""

    def __init__(self, min_interval_s: float = 0.12):
        self.min_interval_s = max(0.0, float(min_interval_s))
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval_s <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = self.min_interval_s - (now - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class GeoPlateformeClient:
    """Client Atom minimal, réutilisable et reprenable."""

    def __init__(
        self,
        base_url: str = GEOPF_BASE,
        *,
        timeout: float = 90.0,
        min_interval_s: float = 0.12,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.limiter = _RateLimiter(min_interval_s)
        self.session = session or self._make_session()

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    @staticmethod
    def _make_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "User-Agent": "ifmplus-bulk/1.0 (Open Data University; Python requests)",
                "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.8",
            }
        )
        return session

    def _get(self, url: str, **params) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(5):
            self.limiter.wait()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code in (429, 500, 502, 503, 504):
                    raise GeoPlateformeError(
                        f"HTTP {response.status_code} sur {response.url}"
                    )
                response.raise_for_status()
                return response
            except (requests.RequestException, GeoPlateformeError) as exc:
                last_error = exc
                delay = min(30.0, 1.5**attempt)
                log.warning(
                    "Requête Géoplateforme échouée (%s), nouvel essai dans %.0f s",
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise GeoPlateformeError(f"Échec de {url} : {last_error}")

    # ------------------------------------------------------------------
    # Catalogue Atom
    # ------------------------------------------------------------------
    @staticmethod
    def _entries(root: ET.Element) -> list[ET.Element]:
        return root.findall(f"{ATOM}entry")

    @staticmethod
    def _total(root: ET.Element) -> int:
        return int(root.get(f"{GPF}totalentries") or 0)

    def _paginate(
        self,
        url: str,
        *,
        max_pages: int = 40,
        **params,
    ) -> Iterator[ET.Element]:
        page = 1
        seen = 0
        while page <= max_pages:
            query = {"lang": "fre", "page": page, "limit": 50, **params}
            response = self._get(url, **query)
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError as exc:
                raise GeoPlateformeError(f"Réponse Atom illisible : {url}") from exc
            entries = self._entries(root)
            total = self._total(root)
            for entry in entries:
                yield entry
                seen += 1
            if not entries or seen >= total:
                break
            page += 1

    def subresources(
        self,
        resource: str,
        *,
        zone: str | None = None,
        fmt: str | None = None,
    ) -> list[SubResource]:
        """Liste les sous-ressources d'un produit, éventuellement filtrées.

        Args:
            resource: nom Géoplateforme (``BDTOPO``, ``BDFORET``, ``RPG``…).
            zone: code zone (``D033``, ``R75``, ``FXX``).
            fmt: format majeur (``GPKG``, ``SHP``…). Le filtre est appliqué
                côté serveur *et* côté client (les libellés pouvant varier).
        """
        params: dict[str, str] = {}
        if zone:
            params["zone"] = zone
        if fmt:
            params["format"] = fmt

        result: list[SubResource] = []
        for entry in self._paginate(
            f"{self.base_url}/resource/{resource}", **params
        ):
            name = (entry.findtext(f"{ATOM}title", namespaces=ATOM_NS) or "").strip()
            if not name:
                continue
            entry_zone = entry.find(f"{GPF}zone")
            entry_format = entry.find(f"{GPF}format")
            edition = entry.findtext(f"{GPF}editionDate")
            fmt_term = entry_format.get("term") if entry_format is not None else None
            zone_term = entry_zone.get("term") if entry_zone is not None else None
            if fmt and fmt_term and fmt_term.upper() != fmt.upper():
                continue
            result.append(
                SubResource(
                    resource=resource,
                    name=name,
                    zone=zone_term or zone,
                    format=fmt_term or fmt,
                    edition=edition,
                )
            )
        return result

    def resolve(self, sub: SubResource) -> SubResource:
        """Complète une sous-ressource (lien, taille, MD5) en une requête."""
        response = self._get(sub.resource_url, lang="fre")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise GeoPlateformeError(f"Entrée Atom illisible : {sub.name}") from exc

        entries = self._entries(root)
        if not entries:
            raise GeoPlateformeError(f"Aucune archive pour {sub.name}")

        entry = entries[0]
        link = None
        for candidate in entry.findall(f"{ATOM}link"):
            if candidate.get("rel") == "alternate" and candidate.get("href"):
                link = candidate
                break
        if link is None:
            raise GeoPlateformeError(f"Lien de téléchargement absent pour {sub.name}")

        size = link.get(f"{GPF}length")
        return SubResource(
            resource=sub.resource,
            name=sub.name,
            zone=sub.zone,
            format=sub.format,
            edition=sub.edition or root.findtext(f"{GPF}editionDate"),
            download_url=link.get("href", ""),
            size=int(size) if size and size.isdigit() else None,
            md5=(entry.findtext(f"{ATOM}content") or "").strip() or None,
        )

    def pick(
        self,
        resource: str,
        predicate,
        *,
        zone: str | None = None,
        fmt: str | None = None,
        description: str = "",
    ) -> SubResource:
        """Choisit la sous-ressource triée par nom décroissant.

        Les noms Géoplateforme se terminent par la date d'édition
        (``..._2025-03-15``), donc l'ordre lexicographique décroissant donne
        naturellement l'édition la plus récente.
        """
        candidates = [
            sub
            for sub in self.subresources(resource, zone=zone, fmt=fmt)
            if predicate(sub)
        ]
        if not candidates:
            raise GeoPlateformeError(
                f"Aucune sous-ressource {resource} ne correspond à {description or predicate}"
            )
        candidates.sort(key=lambda sub: (sub.edition or "", sub.name), reverse=True)
        return candidates[0]

    # ------------------------------------------------------------------
    # Téléchargement
    # ------------------------------------------------------------------
    @staticmethod
    def _free_bytes(path: Path) -> int:
        return shutil.disk_usage(path).free

    def _disk_guard(self, destination: Path, required: int | None) -> None:
        if not required:
            return
        free = self._free_bytes(destination.parent)
        # Marge pour l'extraction 7z et les conversions GeoParquet.
        needed = int(required * 3.5) + 2 * 1024**3
        if free < needed:
            raise GeoPlateformeError(
                f"Espace disque insuffisant dans {destination.parent} : "
                f"{human_bytes(free)} libres, {human_bytes(needed)} estimés "
                f"pour une archive de {human_bytes(required)}"
            )

    def download(
        self,
        sub: SubResource,
        destination: Path,
        *,
        force: bool = False,
        expected_size: int | None = None,
        progress: bool = True,
    ) -> DownloadResult:
        """Télécharge une archive avec reprise sur interruption.

        Le fichier final n'apparaît qu'une fois complet (``os.replace`` du
        ``.part``), ce qui rend le pipeline idempotent : un fichier présent
        est considéré comme valide (taille vérifiée si connue).
        """
        if not sub.download_url:
            sub = self.resolve(sub)
        size = expected_size or sub.size
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists() and not force:
            actual = destination.stat().st_size
            if size is None or actual == size:
                log.info(
                    "  archive déjà présente : %s (%s)",
                    destination.name,
                    human_bytes(actual),
                )
                return DownloadResult(
                    path=destination,
                    size=actual,
                    cached=True,
                    url=sub.download_url,
                    md5=sub.md5,
                    edition=sub.edition,
                )
            log.warning(
                "  taille inattendue pour %s (%s au lieu de %s) : reprise",
                destination.name,
                human_bytes(actual),
                human_bytes(size),
            )

        self._disk_guard(destination, size)
        part = destination.with_suffix(destination.suffix + ".part")
        if force and part.exists():
            part.unlink()

        attempt = 0
        last_error: Exception | None = None
        while attempt < 6:
            offset = part.stat().st_size if part.exists() else 0
            if size is not None and offset > size:
                log.warning("  .part plus gros que prévu, redémarrage")
                part.unlink()
                offset = 0
            if size is not None and offset == size and offset > 0:
                break
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            try:
                self.limiter.wait()
                started = time.monotonic()
                with self.session.get(
                    sub.download_url,
                    headers=headers,
                    stream=True,
                    timeout=(30, 600),
                ) as response:
                    if offset and response.status_code == 200:
                        # Le serveur ignore Range : on repart de zéro.
                        log.info("  reprise non supportée, téléchargement complet")
                        part.unlink(missing_ok=True)
                        offset = 0
                    elif offset and response.status_code != 206:
                        raise GeoPlateformeError(
                            f"HTTP {response.status_code} pour une reprise"
                        )
                    response.raise_for_status()
                    mode = "ab" if offset else "wb"
                    written = offset
                    next_report = 0.10
                    with part.open(mode) as handle:
                        for chunk in response.iter_content(chunk_size=2 * 1024**2):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            written += len(chunk)
                            if size and progress and written / size >= next_report:
                                elapsed = max(time.monotonic() - started, 0.1)
                                speed = (written - offset) / elapsed / 1024**2
                                log.info(
                                    "    %5.1f %%  %s / %s  (%.1f Mo/s)",
                                    100 * written / size,
                                    human_bytes(written),
                                    human_bytes(size),
                                    speed,
                                )
                                next_report += 0.10
                attempt = 0
                break
            except (requests.RequestException, GeoPlateformeError, OSError) as exc:
                last_error = exc
                attempt += 1
                delay = min(60.0, 2.0**attempt)
                log.warning(
                    "  téléchargement interrompu (%s), reprise dans %.0f s (%s/6)",
                    exc,
                    delay,
                    attempt,
                )
                time.sleep(delay)

        if not part.exists():
            raise GeoPlateformeError(
                f"Téléchargement impossible : {sub.download_url} ({last_error})"
            )

        actual = part.stat().st_size
        if size is not None and actual != size:
            raise GeoPlateformeError(
                f"Archive incomplète : {destination.name} "
                f"({human_bytes(actual)} au lieu de {human_bytes(size)})"
            )
        os.replace(part, destination)

        metadata = {
            "url": sub.download_url,
            "resource": sub.resource,
            "sub_resource": sub.name,
            "edition": sub.edition,
            "size": actual,
            "md5": sub.md5,
            "downloaded_at": utc_now(),
        }
        try:
            import json

            destination.with_suffix(destination.suffix + ".json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:  # métadonnée accessoire
            pass

        log.info("  archive prête : %s (%s)", destination.name, human_bytes(actual))
        return DownloadResult(
            path=destination,
            size=actual,
            cached=False,
            url=sub.download_url,
            md5=sub.md5,
            edition=sub.edition,
        )
