"""Carte des incendies recensés dans le fichier IFM+."""

import json
import io
import math
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DATE_COLUMN = "Date de première alerte"
SURFACE_COLUMN = "Surface parcourue (m2)"
CAUSE_COLUMN = "Nature"
MONTH_NAMES = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
MONTH_ABBREVIATIONS = (
    "Janv.", "Fév.", "Mars", "Avr.", "Mai", "Juin",
    "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc.",
)
SEASON_FILTER_ALL = "Toutes les saisons"
CAUSE_FILTER_ALL = "Toutes les causes"
MAP_PERIOD_ALL = "Toute l’année sélectionnée"
MAP_PERIOD_MONTH = "Mois sélectionné"
SEASON_MONTHS = {
    "Hiver": {12, 1, 2},
    "Printemps": {3, 4, 5},
    "Été": {6, 7, 8},
    "Automne": {9, 10, 11},
}
CAUSE_VALUES = {
    "Accidentelle": "Accidentelle",
    "Malveillance": "Malveillance",
    "Foudre (naturelle)": "Naturelle",
}
AREA_RADIUS_SCALE_PX = 0.15
MIN_CIRCLE_RADIUS_PX = 4
MAX_CIRCLE_RADIUS_PX = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIRE_DATA_PATH = Path(os.getenv(
    "FIRE_DATA_PATH",
    str(PROJECT_ROOT / "ifm_plus" / "data" / "raw" / "incendies" / "Incendies.csv"),
))
CENTROID_PATH = Path(__file__).resolve().parent / "assets" / "fire_commune_centroids.csv"
DEPARTMENT_CENTROID_PATH = CENTROID_PATH.with_name('fire_department_centroids.csv')
BDIFF_DIR = Path(os.getenv('BDIFF_DIR', str(PROJECT_ROOT / 'ifm_plus/data/raw/manual/bdiff')))
LEAFLET_VENDOR_PATH = Path(__file__).resolve().parent / "timeline_component" / "vendor"


@st.cache_data(show_spinner=False)
def load_fire_records(
    fire_path: str | tuple[str, ...],
    centroid_path: str,
    fire_mtime_ns: int,
    centroid_mtime_ns: int,
) -> tuple[pd.DataFrame, int]:
    frames = []
    for path in ((fire_path,) if isinstance(fire_path, str) else fire_path):
        lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
        start = next((i for i, line in enumerate(lines) if 'Code INSEE' in line and DATE_COLUMN in line), None)
        if start is None:
            raise ValueError(f'En-tête BDIFF introuvable : {path}')
        frames.append(pd.read_csv(io.StringIO('\n'.join(lines[start:])), sep=';',
                                  dtype={'Code INSEE': 'string', 'Département': 'string', 'Numéro': 'string'}))
    fires = pd.concat(frames, ignore_index=True)
    if {'Année', 'Numéro'} <= set(fires.columns):
        # The same export may be shared twice, or overlap a later export.
        identified = fires[['Année', 'Numéro']].notna().all(axis=1)
        fires = pd.concat([fires[identified].drop_duplicates(['Année', 'Numéro'], keep='last'),
                           fires[~identified]], ignore_index=True)
    required_fire_columns = {
        "Code INSEE",
        "Nom de la commune",
        DATE_COLUMN,
        SURFACE_COLUMN,
        CAUSE_COLUMN,
    }
    missing_fire_columns = required_fire_columns.difference(fires.columns)
    if missing_fire_columns:
        missing_columns = ", ".join(sorted(missing_fire_columns))
        raise ValueError(f"Colonnes manquantes dans le fichier incendies : {missing_columns}")
    fires[DATE_COLUMN] = pd.to_datetime(fires[DATE_COLUMN], errors="coerce")
    invalid_dates = int(fires[DATE_COLUMN].isna().sum())
    if invalid_dates:
        raise ValueError(f"{invalid_dates} date(s) d’incendie sont invalides.")
    fires[SURFACE_COLUMN] = pd.to_numeric(fires[SURFACE_COLUMN], errors="coerce")
    invalid_surfaces = fires[SURFACE_COLUMN].isna() | (fires[SURFACE_COLUMN] < 0)
    if invalid_surfaces.any():
        raise ValueError(f"{int(invalid_surfaces.sum())} surface(s) d’incendie sont invalides.")

    centroids = pd.read_csv(centroid_path, dtype={"Code INSEE": "string"})
    required_centroid_columns = {"Code INSEE", "latitude", "longitude", "precision"}
    missing_centroid_columns = required_centroid_columns.difference(centroids.columns)
    if missing_centroid_columns:
        missing_columns = ", ".join(sorted(missing_centroid_columns))
        raise ValueError(f"Colonnes manquantes dans le fichier de coordonnées : {missing_columns}")
    if centroids["Code INSEE"].duplicated().any():
        raise ValueError("Le fichier de coordonnées contient des codes INSEE en double.")

    fires["Code INSEE"] = fires["Code INSEE"].str.strip()
    centroids["Code INSEE"] = centroids["Code INSEE"].str.strip()
    for column in ("latitude", "longitude"):
        centroids[column] = pd.to_numeric(centroids[column], errors="coerce")

    records = fires.merge(centroids, on="Code INSEE", how="left", validate="many_to_one")
    dept = records.get('Département', records['Code INSEE'].str[:2]).astype('string').str.strip().str.zfill(2)
    if DEPARTMENT_CENTROID_PATH.is_file():
        centers = pd.read_csv(DEPARTMENT_CENTROID_PATH, dtype={'departement': 'string'}).set_index('departement')
        missing = records[['latitude', 'longitude']].isna().any(axis=1)
        for col in ('latitude', 'longitude'):
            records.loc[missing, col] = dept[missing].map(centers[col])
        records.loc[missing & records['latitude'].notna(), 'precision'] = 'département'
    is_overseas = dept.fillna('').str.startswith(('97', '98')) | records["Code INSEE"].fillna("").str.startswith(("97", "98"))
    records["zone"] = is_overseas.map({
        True: "Outre-mer",
        False: "France métropolitaine",
    })
    return records, len(fires)


def available_months(records: pd.DataFrame) -> list[str]:
    dates = records[DATE_COLUMN]
    start = dates.min().to_period("M")
    end = dates.max().to_period("M")
    return [str(month) for month in pd.period_range(start, end, freq="M")]


def format_month(month_key: str) -> str:
    year, month = month_key.split("-")
    return f"{MONTH_NAMES[int(month) - 1].capitalize()} {year}"


def format_slider_month(month_key: str) -> str:
    year, month = month_key.split("-")
    return f"{MONTH_ABBREVIATIONS[int(month) - 1]} {year}"


def fire_records_for_month(records: pd.DataFrame, month_key: str) -> pd.DataFrame:
    record_months = records[DATE_COLUMN].dt.strftime("%Y-%m")
    return records[record_months == month_key]


def fire_records_for_map_period(
    records: pd.DataFrame,
    map_period: str,
    month_key: str,
) -> pd.DataFrame:
    if map_period == MAP_PERIOD_ALL:
        return records
    if map_period == MAP_PERIOD_MONTH:
        return fire_records_for_month(records, month_key)
    raise ValueError(f"Période cartographique inconnue : {map_period}")


def filter_fire_records(
    records: pd.DataFrame,
    season: str = SEASON_FILTER_ALL,
    cause: str = CAUSE_FILTER_ALL,
    year: int | None = None,
) -> pd.DataFrame:
    filtered = records
    if year is not None:
        filtered = filtered[filtered[DATE_COLUMN].dt.year == year]
    if season != SEASON_FILTER_ALL:
        if season not in SEASON_MONTHS:
            raise ValueError(f"Saison inconnue : {season}")
        filtered = filtered[filtered[DATE_COLUMN].dt.month.isin(SEASON_MONTHS[season])]
    if cause != CAUSE_FILTER_ALL:
        if cause not in CAUSE_VALUES:
            raise ValueError(f"Cause inconnue : {cause}")
        normalized_causes = filtered[CAUSE_COLUMN].astype("string").str.strip().str.casefold()
        filtered = filtered[normalized_causes == CAUSE_VALUES[cause].casefold()]
    return filtered


def area_radius_px(surface_m2: float) -> float:
    proportional_radius = math.sqrt(surface_m2 / math.pi) * AREA_RADIUS_SCALE_PX
    return min(MAX_CIRCLE_RADIUS_PX, max(MIN_CIRCLE_RADIUS_PX, proportional_radius))


def build_map_points(records: pd.DataFrame) -> pd.DataFrame:
    located = records.dropna(subset=["latitude", "longitude"])
    points = located.groupby(
        ["latitude", "longitude", "zone", "precision"],
        as_index=False,
        dropna=False,
    ).agg(
        incident_count=("Code INSEE", "size"),
        locations=(
            "Nom de la commune",
            lambda names: ", ".join(sorted(set(names.dropna().astype(str)))),
        ),
        burned_area_m2=(SURFACE_COLUMN, "sum"),
    )
    points["radius_px"] = points["burned_area_m2"].map(area_radius_px)
    return points


def history_records_payload(records: pd.DataFrame) -> list:
    """Keep every event; filtering and aggregation happen locally in the browser."""
    data = []
    for _, row in records.iterrows():
        date = row[DATE_COLUMN]
        data.append([int(date.year), int(date.month),
                     None if pd.isna(row.latitude) else float(row.latitude),
                     None if pd.isna(row.longitude) else float(row.longitude),
                     None if pd.isna(row.precision) else str(row.precision),
                     None if pd.isna(row['Nom de la commune']) else str(row['Nom de la commune']),
                     float(row[SURFACE_COLUMN]),
                     '' if pd.isna(row[CAUSE_COLUMN]) else str(row[CAUSE_COLUMN]).strip().casefold()])
    return data


def build_history_html(records: pd.DataFrame) -> str:
    folder = Path(__file__).parent / 'history_component'
    payload = json.dumps(history_records_payload(records), ensure_ascii=False, allow_nan=False)
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    replacements = {
        '__LEAFLET_CSS__': (LEAFLET_VENDOR_PATH / 'leaflet.css').read_text(),
        '__LEAFLET_JS__': (LEAFLET_VENDOR_PATH / 'leaflet.js').read_text(),
        '__LOGIC_JS__': (folder / 'logic.js').read_text(),
        '__APP_JS__': (folder / 'app.js').read_text(),
        '__RECORDS__': payload,
    }
    import re
    return re.sub('|'.join(replacements), lambda match: replacements[match.group()], (folder / 'index.html').read_text())


def render_fire_history() -> None:
    paths = sorted(set(([FIRE_DATA_PATH] if FIRE_DATA_PATH.is_file() else []) + list(BDIFF_DIR.glob('*.csv'))))
    if not paths:
        st.error('Aucun export BDIFF disponible. Ajoutez les CSV dans les dossiers de données incendies.')
        return
    if not CENTROID_PATH.is_file():
        st.error(f"Fichier de coordonnées introuvable : {CENTROID_PATH}")
        return

    try:
        records, _ = load_fire_records(
            tuple(str(p) for p in paths),
            str(CENTROID_PATH),
            tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths),
            CENTROID_PATH.stat().st_mtime_ns,
        )
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, ValueError) as error:
        st.error(f"Impossible de charger l’historique des incendies : {error}")
        return

    metropolitan_records = records[records["zone"] == "France métropolitaine"]
    if metropolitan_records.empty:
        st.info("Aucun incendie recensé en France métropolitaine.")
        return

    components.html(build_history_html(metropolitan_records), height=790, scrolling=True)
