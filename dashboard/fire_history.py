"""Carte des incendies recensés dans le fichier IFM+."""

import json
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
SEASON_FILTER_ALL = "Toutes les saisons"
CAUSE_FILTER_ALL = "Toutes les causes"
MAP_PERIOD_ALL = "Tous les incendies"
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
LEAFLET_VENDOR_PATH = Path(__file__).resolve().parent / "timeline_component" / "vendor"


@st.cache_data(show_spinner=False)
def load_fire_records(
    fire_path: str,
    centroid_path: str,
    fire_mtime_ns: int,
    centroid_mtime_ns: int,
) -> tuple[pd.DataFrame, int]:
    fires = pd.read_csv(
        fire_path,
        sep=";",
        skiprows=2,
        encoding="utf-8-sig",
        dtype={"Code INSEE": "string"},
    )
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
    is_overseas = records["Code INSEE"].fillna("").str.startswith(("97", "98"))
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
) -> pd.DataFrame:
    filtered = records
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


def build_leaflet_map_html(points: pd.DataFrame) -> str:
    leaflet_css = (LEAFLET_VENDOR_PATH / "leaflet.css").read_text(encoding="utf-8")
    leaflet_js = (LEAFLET_VENDOR_PATH / "leaflet.js").read_text(encoding="utf-8")
    fire_points = [
        {
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "incident_count": int(row.incident_count),
            "locations": str(row.locations),
            "burned_area_m2": float(row.burned_area_m2),
            "radius_px": float(row.radius_px),
        }
        for row in points.itertuples()
    ]
    points_json = json.dumps(fire_points, ensure_ascii=False)
    points_json = (
        points_json.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{leaflet_css}</style>"
        "<style>html,body,#map{height:100%;margin:0}body{font:13px system-ui,sans-serif}</style>"
        f"<script>{leaflet_js}</script>"
        "</head><body><div id='map' aria-label='Carte des incendies en France'></div>"
        f"<script>const firePoints={points_json};"
        "const map=L.map('map',{scrollWheelZoom:true}).setView([46.5,2.3],6);"
        "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',"
        "{attribution:'&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>',maxZoom:19}).addTo(map);"
        "for(const fire of firePoints){"
        "const marker=L.circleMarker([fire.latitude,fire.longitude],{radius:fire.radius_px,color:'#7d0a14',"
        "weight:1,fillColor:'#cd232d',fillOpacity:0.75}).addTo(map);"
        "const tooltip=document.createElement('div');"
        "const place=document.createElement('strong');place.textContent=fire.locations;"
        "const count=document.createElement('div');count.textContent='Incendies : '+fire.incident_count;"
        "const surface=document.createElement('div');surface.textContent='Surface brûlée : '+fire.burned_area_m2.toLocaleString('fr-FR')+' m²';"
        "tooltip.append(place,count,surface);marker.bindTooltip(tooltip);}"
        "requestAnimationFrame(()=>map.invalidateSize());</script></body></html>"
    )


def render_fire_history() -> None:
    if not FIRE_DATA_PATH.is_file():
        st.error(f"Fichier d’incendies introuvable : {FIRE_DATA_PATH}")
        return
    if not CENTROID_PATH.is_file():
        st.error(f"Fichier de coordonnées introuvable : {CENTROID_PATH}")
        return

    try:
        records, _ = load_fire_records(
            str(FIRE_DATA_PATH),
            str(CENTROID_PATH),
            FIRE_DATA_PATH.stat().st_mtime_ns,
            CENTROID_PATH.stat().st_mtime_ns,
        )
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, ValueError) as error:
        st.error(f"Impossible de charger l’historique des incendies : {error}")
        return

    metropolitan_records = records[records["zone"] == "France métropolitaine"]
    if metropolitan_records.empty:
        st.info("Aucun incendie recensé en France métropolitaine.")
        return

    filter_columns = st.columns(3)
    with filter_columns[0]:
        selected_map_period = st.selectbox(
            "Incendies affichés",
            [MAP_PERIOD_ALL, MAP_PERIOD_MONTH],
            key="fire_history_map_period",
        )
    with filter_columns[1]:
        selected_season = st.selectbox(
            "Saison",
            [SEASON_FILTER_ALL, *SEASON_MONTHS],
            key="fire_history_season",
        )
    with filter_columns[2]:
        selected_cause = st.selectbox(
            "Cause",
            [CAUSE_FILTER_ALL, *CAUSE_VALUES],
            key="fire_history_cause",
        )

    filtered_records = filter_fire_records(
        metropolitan_records,
        selected_season,
        selected_cause,
    )
    if filtered_records.empty:
        st.info("Aucun incendie ne correspond aux filtres sélectionnés.")
        return

    months = available_months(filtered_records)
    if st.session_state.get("fire_history_month") not in months:
        st.session_state["fire_history_month"] = months[-1]
    selected_month = st.select_slider(
        "Mois et année",
        options=months,
        format_func=format_month,
        key="fire_history_month",
        label_visibility="collapsed",
    )
    month_records = fire_records_for_map_period(
        filtered_records,
        selected_map_period,
        selected_month,
    )
    if month_records.empty:
        st.info(f"Aucun incendie recensé en {format_month(selected_month)}.")
        return
    located = month_records.dropna(subset=["latitude", "longitude"])

    unmapped_count = len(month_records) - len(located)
    if unmapped_count:
        st.warning(
            f"{unmapped_count:,} incendie(s) sans coordonnées ne sont pas représentés sur la carte."
        )
    if located.empty:
        st.info(f"Aucun incendie recensé en {format_month(selected_month)}.")
        return

    points = build_map_points(located)
    try:
        map_html = build_leaflet_map_html(points)
    except OSError as error:
        st.error(f"Impossible de charger les fichiers cartographiques : {error}")
        return
    components.html(map_html, height=620, scrolling=False)
