"""Sélection des archives bulk dans le catalogue Géoplateforme.

Chaque produit a ses conventions de nommage et ses zones :

================  ==================  =========================================
Produit           Zone                Nom type
================  ==================  =========================================
BD TOPO           ``D033``            ``BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_D033_2026-09-15``
BD Forêt V2       ``D033``            ``BDFORET_2-0__SHP_LAMB93_D033_2017-05-10``
RPG               ``R75``             ``RPG_4-0__GPKG_LAMB93_R75_2025-01-01``
================  ==================  =========================================

Les fonctions renvoient une :class:`SubResource` non résolue (sans lien de
téléchargement) ; le client la complète au moment du téléchargement.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .geopf import GeoPlateformeClient, GeoPlateformeError, SubResource
from .regions import department_zone

log = logging.getLogger("ifmplus")

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


class CatalogError(GeoPlateformeError):
    pass


@dataclass(frozen=True)
class Product:
    key: str
    resource: str
    format: str
    version: str


BDTOPO = Product("bdtopo", "BDTOPO", "GPKG", "3-5")
BDFORET = Product("bdf", "BDFORET", "SHP", "2-0")
RPG = Product("rpg", "RPG", "GPKG", "4-0")


def _date(name: str) -> str:
    match = DATE_RE.search(name)
    return match.group(1) if match else ""


def _latest(candidates: list[SubResource]) -> SubResource | None:
    if not candidates:
        return None
    return max(candidates, key=lambda sub: (sub.edition or "", _date(sub.name), sub.name))


def select_bdtopo(
    client: GeoPlateformeClient,
    dept: str,
    *,
    edition: str | None = None,
) -> SubResource:
    """Dernière édition (ou édition imposée) de la BD TOPO départementale.

    Args:
        dept: code département (``33``).
        edition: ``None``/``latest`` pour la plus récente, sinon une date
            ``YYYY-MM-DD`` (ex. ``2025-03-15``) pour reproductibilité.
    """
    zone = department_zone(dept)
    subs = client.subresources("BDTOPO", zone=zone, fmt="GPKG")
    themes = [sub for sub in subs if "TOUSTHEMES" in sub.name.upper()]
    candidates = themes or subs
    wanted = (edition or "latest").strip()
    if wanted.lower() not in {"latest", "derniere", "dernière", ""}:
        exact = [sub for sub in candidates if wanted in sub.name]
        if not exact:
            raise CatalogError(
                f"Édition BD TOPO {wanted} absente pour {zone}. "
                f"Disponibles : {', '.join(sorted(sub.name for sub in candidates)[-4:])}"
            )
        return exact[0]
    chosen = _latest(candidates)
    if chosen is None:
        raise CatalogError(f"Aucune archive GPKG BD TOPO pour {zone}")
    return chosen


def select_bdforet(
    client: GeoPlateformeClient,
    dept: str,
    *,
    version: str = "2-0",
) -> SubResource:
    """BD Forêt V2 départementale (repli V1 si V2 indisponible)."""
    zone = department_zone(dept)
    subs = client.subresources("BDFORET", zone=zone)
    v2 = [
        sub
        for sub in subs
        if sub.name.upper().startswith(f"BDFORET_{version.replace('-', '-')}".upper())
    ]
    if not v2:
        v2 = [
            sub
            for sub in subs
            if "BDFORET_2-0" in sub.name.upper()
        ]
    candidates = v2 or [
        sub for sub in subs if "BDFORET_1-0" in sub.name.upper()
    ]
    chosen = _latest(candidates)
    if chosen is None:
        raise CatalogError(f"Aucune archive BD Forêt pour {zone}")
    if "BDFORET_2-0" not in chosen.name.upper():
        log.warning(
            "  BD Forêt V2 absente pour %s : repli sur %s", dept, chosen.name
        )
    return chosen


def select_rpg(
    client: GeoPlateformeClient,
    region: str,
    *,
    year: int | None = 2025,
    allow_national_fallback: bool = True,
) -> SubResource:
    """RPG régional de l'année demandée (repli régional puis national).

    Args:
        region: code région Géoplateforme (``R75`` ou ``75``).
        year: millésime souhaité (``2025``) ; le plus récent est utilisé si
            l'année demandée n'est pas diffusée.

    Le RPG 4.0 n'est diffusé que par région pour 2024/2025. Les millésimes
    antérieurs (2023) n'existent qu'en national ``FXX``, beaucoup plus lourd ;
    le repli national est donc désactivé par défaut dans la configuration.
    """
    zone = str(region).strip().upper()
    if not zone.startswith("R"):
        zone = f"R{zone.zfill(2)}"
    subs = client.subresources("RPG", zone=zone, fmt="GPKG")
    regional = [sub for sub in subs if "GPKG" in sub.name.upper()]
    if year is not None:
        dated = [sub for sub in regional if f"_{year}-01-01" in sub.name]
        chosen = _latest(dated)
        if chosen is not None:
            return chosen
        log.warning(
            "  RPG %s absent pour %s : utilisation du millésime régional le plus récent",
            year,
            zone,
        )
    chosen = _latest(regional)
    if chosen is not None:
        return chosen

    if not allow_national_fallback:
        raise CatalogError(f"Aucune archive RPG régionale pour {zone}")

    log.warning(
        "  Aucune archive RPG régionale pour %s : repli sur le national FXX "
        "(archive volumineuse, un seul téléchargement pour toute la France)",
        zone,
    )
    national = client.subresources("RPG", zone="FXX", fmt="GPKG")
    chosen = _latest(national)
    if chosen is None:
        raise CatalogError("Aucune archive RPG nationale FXX")
    return chosen


def rpg_is_national(sub: SubResource) -> bool:
    return "_FXX_" in sub.name.upper()


def rpg_year(sub: SubResource) -> int | None:
    match = re.search(r"_(20\d{2})-01-01", sub.name)
    return int(match.group(1)) if match else None
