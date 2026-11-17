"""Track bulk France : Géoplateforme → GeoParquet → features DFCI.

Ce sous-package remplace les téléchargements WFS des couches lourdes
(BD TOPO, BD Forêt V2, RPG) par les archives officielles de la
Géoplateforme, traitées en streaming département par département.

Modules :
    geopf      client Atom, reprise et garde-fou disque ;
    catalog    sélection des éditions (BD TOPO, BD Forêt, RPG) ;
    archive    extraction ciblée des 7z ;
    layers     lecture IGN → GeoParquet ;
    dfci       enrichissement léger ``piste_dfci`` ;
    dem        VRT Copernicus distant → COG Lambert-93 ;
    download   orchestration idempotente.
"""

from __future__ import annotations

from .catalog import BDFORET, BDTOPO, RPG
from .download import BULK_LAYERS, BulkResult, ensure_bulk
from .geopf import GeoPlateformeClient, GeoPlateformeError
from .regions import DEPT_REGION, REGION_DEPARTEMENTS, region_code, region_zone

__all__ = [
    "BULK_LAYERS",
    "BulkResult",
    "ensure_bulk",
    "GeoPlateformeClient",
    "GeoPlateformeError",
    "BDTOPO",
    "BDFORET",
    "RPG",
    "DEPT_REGION",
    "REGION_DEPARTEMENTS",
    "region_code",
    "region_zone",
]
