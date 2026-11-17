"""Chargement de la configuration YAML du projet IFM+.

Deux périmètres sont supportés :

- ``departement`` : un seul département (mode historique, grille locale) ;
- ``france_metro`` : France métropolitaine, traitée **département par
  département** (une grille 25 m nationale ne tient pas en mémoire), puis
  assemblée en une table nationale unique.

En mode France, ``Config.departements`` liste les départements à traiter et
``Config.for_departement(code)`` renvoie une configuration « fille » dont tous
les chemins par département (bbox, couches WFS, MNT) sont cohérents.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config.yaml"

#: Les 96 départements de France métropolitaine (Corse incluse, DOM exclus).
METRO_DEPARTEMENTS: tuple[str, ...] = tuple(
    [f"{code:02d}" for code in range(1, 20)]
    + ["2A", "2B"]
    + [f"{code:02d}" for code in range(21, 96)]
)

PERIMETRES = ("departement", "france_metro")


def _resolve(root: Path, value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def normalize_dept(code: Any) -> str:
    """Code département canonique : ``"1"`` → ``"01"``, ``"2a"`` → ``"2A"``."""
    text = str(code).strip().upper()
    if text.isdigit():
        return text.zfill(2)
    return text


def parse_departements(value: str | None) -> tuple[str, ...] | None:
    """Analyse ``"33,40"`` / ``"all"`` en tuple de codes normalisés."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"all", "tous", "france", "metro"}:
        return METRO_DEPARTEMENTS
    codes = {normalize_dept(item) for item in text.replace(";", ",").split(",")}
    codes.discard("")
    unknown = sorted(code for code in codes if code not in METRO_DEPARTEMENTS)
    if unknown:
        raise ValueError(
            "Départements hors France métropolitaine ou invalides : "
            + ", ".join(unknown)
        )
    return tuple(sorted(codes))


def _scope_slug(departements: tuple[str, ...]) -> str:
    """Identifiant court et déterministe du périmètre traité."""
    if departements == METRO_DEPARTEMENTS:
        return "france_metro"
    joined = "-".join(departements)
    if len(joined) <= 60:
        return f"france_metro_{joined}"
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:8]
    return f"france_metro_{len(departements)}depts_{digest}"


@dataclass(frozen=True)
class Config:
    """Configuration immuable, chargée depuis ``config.yaml``."""

    root: Path
    perimetre: str
    departements: tuple[str, ...]
    departement: str
    nom_departement: str
    crs: str
    crs_wgs84: str
    resolution_m: float
    buffer_m: float
    date_debut: str
    date_fin: str
    mois_saison: tuple[int, ...]
    tmja_annee: int
    raw_dir: Path
    interim_dir: Path
    processed_dir: Path
    logs_dir: Path
    sources: dict[str, Any] = field(default_factory=dict)
    firms: dict[str, Any] = field(default_factory=dict)
    weather: dict[str, Any] = field(default_factory=dict)
    roads: dict[str, Any] = field(default_factory=dict)
    bulk: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        departement: str | None = None,
        departements: str | tuple[str, ...] | None = None,
        perimetre: str | None = None,
    ) -> "Config":
        cfg_path = Path(
            path or os.environ.get("IFM_CONFIG") or DEFAULT_CONFIG_PATH
        ).resolve()
        if not cfg_path.exists():
            raise FileNotFoundError(f"Configuration introuvable : {cfg_path}")

        with cfg_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        root = cfg_path.parent
        project = data.get("project", {})
        paths = data.get("paths", {})
        sources = data.get("sources", {})
        periode = project.get("periode", {})

        scope = str(perimetre or project.get("perimetre", "departement")).strip().lower()
        if scope not in PERIMETRES:
            raise ValueError(
                f"perimetre inconnu : {scope!r} (attendu : {', '.join(PERIMETRES)})"
            )

        dept = normalize_dept(departement or project.get("departement", "33"))
        mois = tuple(int(m) for m in periode.get("mois_saison", [6, 7, 8, 9]))

        selected: str | tuple[str, ...] | list[str] | None
        if departements is None:
            selected = project.get("departements")
        else:
            selected = departements
        if isinstance(selected, str):
            selected = parse_departements(selected)
        elif selected is not None:
            selected = tuple(selected)
        if selected is not None:
            selected = tuple(normalize_dept(code) for code in selected)
            unknown = sorted(c for c in selected if c not in METRO_DEPARTEMENTS)
            if unknown:
                raise ValueError(
                    "Départements hors France métropolitaine : " + ", ".join(unknown)
                )
            scope = "france_metro"
        elif scope == "france_metro":
            selected = METRO_DEPARTEMENTS
        else:
            selected = (dept,)

        return cls(
            root=root,
            perimetre=scope,
            departements=tuple(selected),
            departement=(selected[0] if scope == "france_metro" else dept),
            nom_departement=str(project.get("nom_departement", "")),
            crs=str(project.get("crs", "EPSG:2154")),
            crs_wgs84=str(project.get("crs_wgs84", "EPSG:4326")),
            resolution_m=float(project.get("resolution_m", 25)),
            buffer_m=float(project.get("buffer_m", 2500)),
            date_debut=str(periode.get("debut", "2018-01-01")),
            date_fin=str(periode.get("fin", "2023-12-31")),
            mois_saison=mois,
            tmja_annee=int(project.get("tmja_annee_reference", 2022)),
            raw_dir=_resolve(root, paths.get("raw", "data/raw")),
            interim_dir=_resolve(root, paths.get("interim", "data/interim")),
            processed_dir=_resolve(root, paths.get("processed", "data/processed")),
            logs_dir=_resolve(root, paths.get("logs", "data/logs")),
            sources=sources,
            firms=data.get("firms", {}),
            weather=data.get("weather", {}),
            roads=data.get("roads", {}),
            bulk=data.get("bulk", {}) or {},
        )

    # ------------------------------------------------------------------
    # Portée et configurations filles
    # ------------------------------------------------------------------
    @property
    def france(self) -> bool:
        """Vrai si le périmètre est national (même partiel)."""
        return self.perimetre == "france_metro"

    @property
    def scope_label(self) -> str:
        """Suffixe des sorties : ``france_metro``/sous-ensemble ou code dept."""
        if not self.france:
            return self.departement
        return _scope_slug(self.departements)

    @staticmethod
    def scope_label_for(departements: tuple[str, ...]) -> str:
        return _scope_slug(tuple(departements))

    def for_departement(self, dept: str) -> "Config":
        """Configuration fille limitée à un département (chemins locaux).

        Le périmètre reste national : ``tmja_path`` et ``communes_scope_path``
        pointent donc toujours vers les fichiers nationaux.
        """
        code = normalize_dept(dept)
        nom = (
            self.nom_departement
            if (not self.france and code == self.departement)
            else ""
        )
        return replace(self, departement=code, nom_departement=nom)

    # ------------------------------------------------------------------
    # Chemins pratiques
    # ------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        for directory in (
            self.raw_dir,
            self.interim_dir,
            self.processed_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def raw(self, layer: str, *parts: str) -> Path:
        return self.raw_dir.joinpath(layer, *parts)

    # -- contours administratifs --------------------------------------
    @property
    def dept_bbox_path(self) -> Path:
        return self.bbox_path(self.departement)

    def bbox_path(self, dept: str) -> Path:
        code = normalize_dept(dept)
        return self.interim_dir / f"dept_{code}_bbox.json"

    @property
    def scope_bbox_path(self) -> Path:
        return self.interim_dir / f"scope_{self.scope_label}_bbox.json"

    @property
    def dept_path(self) -> Path:
        return self.raw("admin", f"dept_{self.departement}.gpkg")

    @property
    def communes_path(self) -> Path:
        return self.raw("admin", f"communes_{self.departement}.gpkg")

    @property
    def departements_france_path(self) -> Path:
        return self.raw("admin", "departements_france_metro.gpkg")

    @property
    def communes_france_path(self) -> Path:
        """Communes du périmètre : national complet ou sous-ensemble demandé."""
        if self.scope_label == "france_metro":
            return self.raw("admin", "communes_france_metro.gpkg")
        return self.raw("admin", f"communes_{self.scope_label}.gpkg")

    @property
    def communes_scope_path(self) -> Path:
        """Communes utilisées dans les features (national en mode France)."""
        return self.communes_france_path if self.france else self.communes_path

    # -- carroyage et couches thématiques -----------------------------
    @property
    def dfci_path(self) -> Path:
        return self.raw("dfci", "dfci_2km.gpkg")

    @property
    def dfci_cells_cache_path(self) -> Path:
        """Carreaux DFCI terrestres déjà rattachés à un département."""
        return self.interim_dir / "dfci_cells_assigned_v2.gpkg"

    def layer_path(self, layer: str, dept: str | None = None) -> Path:
        code = normalize_dept(dept or self.departement)
        return self.raw(layer, f"{layer}_{code}.gpkg")

    @property
    def tmja_france_path(self) -> Path:
        return self.raw("tmja", "tmja_france_metro.gpkg")

    @property
    def tmja_path(self) -> Path:
        """TMJA national en mode France, sinon extrait départemental."""
        return self.tmja_france_path if self.france else self.layer_path("tmja")

    def dem_path(self, resolution: float | None = None) -> Path:
        res = int(resolution or self.resolution_m)
        return self.raw("dem", f"dem_{self.departement}_{res}m.tif")

    # -- sorties ------------------------------------------------------
    @property
    def static_features_path(self) -> Path:
        if self.france:
            return self.processed_dir / f"static_features_{self.scope_label}.parquet"
        return self.processed_dir / f"static_features_{self.departement}.parquet"

    @property
    def static_features_gpkg_path(self) -> Path:
        if self.france:
            return self.processed_dir / f"static_features_{self.scope_label}.gpkg"
        return self.processed_dir / f"static_features_{self.departement}.gpkg"

    @property
    def static_features_metadata_path(self) -> Path:
        if self.france:
            return (
                self.processed_dir
                / f"static_features_{self.scope_label}_metadata.json"
            )
        return self.processed_dir / f"static_features_{self.departement}_metadata.json"

    # ------------------------------------------------------------------
    # Track bulk (Géoplateforme → GeoParquet)
    # ------------------------------------------------------------------
    @property
    def bulk_dir(self) -> Path:
        return self.raw_dir / "bulk"

    def bulk_raw(self, *parts: str) -> Path:
        """Chemin sous ``data/raw/bulk`` (archives temporaires, VRT, couches)."""
        return self.bulk_dir.joinpath(*parts)

    def bulk_layer(self, layer: str, code: str) -> Path:
        """GeoParquet normalisé d'une couche bulk pour un département."""
        return self.bulk_raw(layer, f"{layer}_{code}.parquet")

    @property
    def bulk_manifest_path(self) -> Path:
        return self.bulk_raw("_manifest.json")

    @property
    def bulk_features_path(self) -> Path:
        """Table analytique finale du track bulk.

        Le nom exact ``dfci_2km_features_france.parquet`` n'est utilisé que
        pour le périmètre complet (96 départements) ; un sous-ensemble garde
        un suffixe explicite pour ne jamais écraser la sortie nationale.
        """
        if len(self.departements) == len(METRO_DEPARTEMENTS):
            return self.processed_dir / "dfci_2km_features_france.parquet"
        return self.processed_dir / f"dfci_2km_features_{self.scope_label}.parquet"

    @property
    def bulk_features_gpkg_path(self) -> Path:
        return self.bulk_features_path.with_suffix(".gpkg")

    @property
    def bulk_features_metadata_path(self) -> Path:
        return self.bulk_features_path.with_name(
            self.bulk_features_path.stem + "_metadata.json"
        )

    def bulk_dept_cache_path(
        self,
        resolution: float,
        skip: tuple[str, ...] = (),
        fingerprint: str = "",
    ) -> Path:
        key = "-".join(sorted(skip)) if skip else "all"
        suffix = f"_{fingerprint}" if fingerprint else ""
        return (
            self.processed_dir
            / "dept_bulk"
            / f"features_{self.departement}_{int(resolution)}m_{key}{suffix}.parquet"
        )


    def dept_cache_path(
        self,
        resolution: float,
        skip: tuple[str, ...] = (),
        fingerprint: str = "",
    ) -> Path:
        """Features d'un département, avant assemblage national.

        Le suffixe encode les couches ignorées et une empreinte des fichiers
        d'entrée : un cache produit sans une couche (ou avec `--skip roads`)
        n'est jamais réutilisé par un run complet.
        """
        key = "-".join(sorted(skip)) if skip else "all"
        suffix = f"_{fingerprint}" if fingerprint else ""
        return (
            self.processed_dir
            / "dept"
            / f"static_features_{self.departement}_{int(resolution)}m_{key}{suffix}.parquet"
        )
