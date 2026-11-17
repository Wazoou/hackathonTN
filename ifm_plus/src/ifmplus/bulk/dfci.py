"""Enrichissement DFCI des tronçons routiers.

Le GPKG bulk de la BD TOPO ne contient **pas** les attributs DFCI
(``piste_dfci``, ``pente_maximale_dfci``…) présents dans le flux WFS de
l'IGN. Ces attributs sont indispensables pour distinguer les pistes de
défense des forêts contre l'incendie du reste du réseau.

Pour ne pas retomber sur un téléchargement WFS massif, on ne récupère que
l'**identifiant** des tronçons DFCI (``cleabs``), sans géométrie :

- réponse de quelques mégaoctets par département au lieu de plusieurs
  centaines de Mo ;
- une seule requête paginée par département, mise en cache ;
- repli heuristique documenté si le WFS est indisponible ou désactivé.

C'est la seule exception WFS du track bulk ; elle est désactivable avec
``--no-dfci-wfs``.
"""

from __future__ import annotations

import logging
import time

import geopandas as gpd
import pandas as pd
import requests

from ..features.typo import strip_accents

log = logging.getLogger("ifmplus")

WFS_URL = "https://data.geopf.fr/wfs/ows"
DFCI_LAYER = "BDTOPO_V3:troncon_de_route"


class WfsDfciError(RuntimeError):
    pass


def _bbox_cql(bbox: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bbox
    return (
        "(piste_dfci=true) AND "
        f"BBOX(geometrie,{minx:.3f},{miny:.3f},{maxx:.3f},{maxy:.3f},'EPSG:2154')"
    )


def fetch_dfci_cleabs(
    bbox: tuple[float, float, float, float],
    *,
    session: requests.Session | None = None,
    page_size: int = 10_000,
    timeout: float = 120.0,
    max_pages: int = 20,
) -> set[str]:
    """Renvoie les ``cleabs`` des tronçons marqués ``piste_dfci=true``.

    Args:
        bbox: emprise Lambert-93 (déjà bufferisée) du département.
        session: session HTTP réutilisable.
        page_size: nombre d'identifiants par requête WFS.
    """
    http = session or requests.Session()
    cql = _bbox_cql(bbox)
    collected: set[str] = set()
    start = 0
    total: int | None = None

    for page in range(max_pages):
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": DFCI_LAYER,
            "outputFormat": "application/json",
            "propertyName": "cleabs",
            "count": str(page_size),
            "startIndex": str(start),
            "CQL_FILTER": cql,
        }
        last_error: Exception | None = None
        payload = None
        for attempt in range(4):
            try:
                response = http.get(WFS_URL, params=params, timeout=timeout)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type.lower():
                    raise WfsDfciError(
                        f"Réponse WFS non JSON ({content_type}) : {response.text[:200]}"
                    )
                payload = response.json()
                break
            except (requests.RequestException, ValueError, WfsDfciError) as exc:
                last_error = exc
                delay = min(30.0, 2.0**attempt)
                log.warning(
                    "  WFS DFCI page %s échouée (%s), nouvel essai dans %.0f s",
                    page + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
        if payload is None:
            raise WfsDfciError(f"WFS DFCI indisponible : {last_error}")

        features = payload.get("features") or []
        if total is None:
            total = int(payload.get("totalFeatures") or payload.get("numberMatched") or 0)
            log.info("  WFS DFCI : %s tronçons à récupérer", f"{total:,}")
        for feature in features:
            cleabs = (feature.get("properties") or {}).get("cleabs")
            if cleabs:
                collected.add(str(cleabs))
        start += len(features)
        if not features or (total is not None and start >= total):
            break

    return collected


def approximate_dfci(roads: gpd.GeoDataFrame) -> pd.Series:
    """Repli heuristique : chemins et routes empierrées peu hiérarchisés.

    Utilisé uniquement si le WFS est désactivé ou en échec. La surestimation
    est assumée et signalée dans les métadonnées (``dfci_source``) : le
    réseau DFCI n'est pas identifiable de façon fiable sans l'attribut
    ``piste_dfci``. On retient les voies non classées (importance 5-6) de
    type chemin/route empierrée/sentier, qui concentrent l'essentiel des
    pistes DFCI de la BD TOPO.
    """
    if roads.empty:
        return pd.Series(dtype="bool", index=roads.index)
    nature = strip_accents(
        roads.get("nature", pd.Series("", index=roads.index))
    )
    importance = pd.to_numeric(
        roads.get("importance", pd.Series(99, index=roads.index)), errors="coerce"
    ).fillna(99)
    return nature.isin({"chemin", "route empierree", "sentier"}) & (importance >= 5)
