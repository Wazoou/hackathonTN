"""Extraction ciblée des archives 7z de la Géoplateforme.

Les livraisons IGN contiennent beaucoup d'annexes (PDF, métadonnées, shapefiles
multiples). Extraire l'archive entière gaspille du disque et du temps. Ce
module ne sort que les membres utiles (GPKG ou jeu shapefile complet) et
renvoie leurs chemins.
"""

from __future__ import annotations

import fnmatch
import logging
import shutil
from pathlib import Path
from typing import Iterable

import py7zr

log = logging.getLogger("ifmplus")

#: Suffixes nécessaires pour qu'un shapefile soit lisible.
SHAPEFILE_SUFFIXES = (".shp", ".shx", ".dbf", ".prj", ".cpg")


class ArchiveError(RuntimeError):
    pass


def list_members(archive: Path) -> list[str]:
    """Liste les membres d'une archive 7z sans l'extraire."""
    with py7zr.SevenZipFile(archive) as bundle:
        return bundle.getnames()


def _matches(
    name: str,
    suffixes: tuple[str, ...] | None,
    substrings: tuple[str, ...] | None,
    globs: tuple[str, ...] | None,
) -> bool:
    lower = name.lower()
    if suffixes and not lower.endswith(tuple(s.lower() for s in suffixes)):
        return False
    if substrings and not any(token.lower() in lower for token in substrings):
        return False
    if globs and not any(fnmatch.fnmatch(lower, pattern.lower()) for pattern in globs):
        return False
    return True


def extract_members(
    archive: Path,
    destination: Path,
    *,
    suffixes: tuple[str, ...] | None = None,
    substrings: tuple[str, ...] | None = None,
    globs: tuple[str, ...] | None = None,
    clean: bool = False,
) -> list[Path]:
    """Extrait uniquement les membres correspondant aux filtres.

    Args:
        archive: archive ``.7z`` téléchargée.
        destination: dossier racine d'extraction (créé au besoin).
        suffixes: suffixes autorisés, ex. ``(".gpkg",)``.
        substrings: jetons devant apparaître dans le chemin, ex.
            ``("FORMATION_VEGETALE",)``.
        globs: motifs ``fnmatch`` supplémentaires.
        clean: supprime le dossier de destination avant extraction.

    Returns:
        Chemins des fichiers extraits (fichiers uniquement).
    """
    if not archive.exists():
        raise FileNotFoundError(f"Archive absente : {archive}")
    if clean and destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)

    with py7zr.SevenZipFile(archive) as bundle:
        names = bundle.getnames()
        selected = [
            name
            for name in names
            if _matches(name, suffixes, substrings, globs)
        ]
        if not selected:
            raise ArchiveError(
                f"Aucun membre correspondant dans {archive.name} "
                f"(filtres suffixes={suffixes}, substrings={substrings}, globs={globs})"
            )
        log.info(
            "  extraction de %s membre(s) sur %s…",
            len(selected),
            len(names),
        )
        bundle.extract(path=destination, targets=selected)

    files = [destination / name for name in selected if (destination / name).is_file()]
    if not files:
        raise ArchiveError(f"Extraction vide pour {archive.name}")
    return files


def find_one(files: Iterable[Path], *needles: str) -> Path:
    """Premier fichier dont le nom contient tous les jetons demandés."""
    tokens = [needle.lower() for needle in needles]
    for path in files:
        name = path.name.lower()
        if all(token in name for token in tokens):
            return path
    raise FileNotFoundError(
        "Fichier introuvable parmi : " + ", ".join(path.name for path in files)
    )


def purge(path: Path) -> None:
    """Supprime un dossier temporaire sans faire échouer le pipeline."""
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:  # pragma: no cover - verrou Windows résiduel
        log.warning("  purge incomplète de %s : %s", path, exc)
