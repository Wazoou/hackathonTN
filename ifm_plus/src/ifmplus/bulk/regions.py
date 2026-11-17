"""Correspondance département → région et zones Géoplateforme.

Le RPG est diffusé à la maille **régionale** sur la Géoplateforme (codes de
zone ``R11``, ``R24``, …). Ce module centralise la table de correspondance
utilisée pour :

- choisir la bonne archive RPG lors du téléchargement bulk ;
- savoir quels départements peuvent être calculés à partir d'une archive
  régionale déjà extraite ;
- documenter le découpage dans les métadonnées.
"""

from __future__ import annotations

#: Code région INSEE (2 chiffres) → libellé.
REGION_NAMES: dict[str, str] = {
    "11": "Île-de-France",
    "24": "Centre-Val de Loire",
    "27": "Bourgogne-Franche-Comté",
    "28": "Normandie",
    "32": "Hauts-de-France",
    "44": "Grand Est",
    "52": "Pays de la Loire",
    "53": "Bretagne",
    "75": "Nouvelle-Aquitaine",
    "76": "Occitanie",
    "84": "Auvergne-Rhône-Alpes",
    "93": "Provence-Alpes-Côte d'Azur",
    "94": "Corse",
}

#: Départements de France métropolitaine par région (Corse incluse).
REGION_DEPARTEMENTS: dict[str, tuple[str, ...]] = {
    "11": ("75", "77", "78", "91", "92", "93", "94", "95"),
    "24": ("18", "28", "36", "37", "41", "45"),
    "27": ("21", "25", "39", "58", "70", "71", "89", "90"),
    "28": ("14", "27", "50", "61", "76"),
    "32": ("02", "59", "60", "62", "80"),
    "44": ("08", "10", "51", "52", "54", "55", "57", "67", "68", "88"),
    "52": ("44", "49", "53", "72", "85"),
    "53": ("22", "29", "35", "56"),
    "75": ("16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"),
    "76": ("09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"),
    "84": ("01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"),
    "93": ("04", "05", "06", "13", "83", "84"),
    "94": ("2A", "2B"),
}

DEPT_REGION: dict[str, str] = {
    dept: region
    for region, departements in REGION_DEPARTEMENTS.items()
    for dept in departements
}


def region_code(dept: str) -> str:
    """Code région d'un département (``33`` → ``75``)."""
    code = str(dept).strip().upper().zfill(2)
    try:
        return DEPT_REGION[code]
    except KeyError as exc:  # pragma: no cover - garde-fou configuration
        raise KeyError(f"Département hors France métropolitaine : {dept!r}") from exc


def department_zone(dept: str) -> str:
    """Zone Géoplateforme départementale (``33`` → ``D033``, ``2A`` → ``D02A``)."""
    return f"D{str(dept).strip().upper().zfill(3)}"


def region_zone(dept: str) -> str:
    """Zone Géoplateforme de la région d'un département (``33`` → ``R75``)."""
    return f"R{region_code(dept)}"


def region_name(region: str) -> str:
    code = str(region).upper().removeprefix("R").zfill(2)
    return REGION_NAMES.get(code, code)


def departments_of_region(region: str) -> tuple[str, ...]:
    code = str(region).upper().removeprefix("R").zfill(2)
    return REGION_DEPARTEMENTS.get(code, ())


def regions_for(departements: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Groupe les départements demandés par région.

    Returns:
        ``{"75": ("33", "40", ...), ...}`` dans l'ordre des régions.
    """
    grouped: dict[str, list[str]] = {}
    for dept in departements:
        code = str(dept).strip().upper().zfill(2)
        grouped.setdefault(region_code(code), []).append(code)
    return {region: tuple(depts) for region, depts in sorted(grouped.items())}


def region_label(region: str) -> str:
    """Libellé court ``R75 — Nouvelle-Aquitaine``."""
    code = str(region).upper().removeprefix("R").zfill(2)
    return f"R{code} — {region_name(code)}"
