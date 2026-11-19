"""Live webcam map and demonstration camera.

Supports every kind of webcam source: YouTube live/recorded videos, periodic
image URLs (JPG/PNG refreshed by the provider), HLS/MJPEG streams, etc.
"""

import os
import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
import streamlit.components.v1 as components

from surveillance import (DEMO_CAMERA, DEMO_URL, analysis_preview, camera_id,
                          demo_controls, map_status, monitoring_status)
from interface import section_title
from webcam_directory import (
    WEBCAM_LAYER_ID,
    load_camera_directory,
    selected_camera_url,
    fetch_opencctv_snapshot,
    webcam_display_type,
    webcam_embed_url,
)

CAMERAS_PATH = Path(os.getenv("CAMERAS_PATH") or os.getenv("CAMERAS_JSON_PATH") or
                    Path(__file__).resolve().parent.parent / "camera-data" / "cameras.csv")
LOGGER = logging.getLogger(__name__)

# A custom style URL avoids Streamlit's fallback for tokenless Mapbox objects.
# Its tiles match the risk, archives and history maps.
OSM_MAP_STYLE = "app/static/openstreetmap.json"


def _select_webcam() -> None:
    """Consume a new map event, never replay an old selection on a button rerun."""
    url = selected_camera_url(st.session_state.get("live_webcam_map", {}))
    if url:
        st.session_state["selected_webcam_url"] = url


def _refresh_map_status() -> None:
    monitoring_status.clear()
    st.session_state.pop("webcam_map_snapshot", None)


def _map_data(cameras) -> pd.DataFrame:
    # Streamlit 1.45 includes the complete deck JSON in the widget identity.
    # Freeze monitoring metadata until an explicit refresh, so a new inference
    # cannot replace the widget and discard the click that triggered the rerun.
    signature = json.dumps(cameras, sort_keys=True)
    snapshot = st.session_state.get("webcam_map_snapshot")
    if snapshot is None or snapshot["catalogue"] != signature:
        states = monitoring_status()
        rows = []
        for camera in cameras:
            url = camera["url_youtube"]
            label, color = map_status(states.get(camera_id(url)))
            rows.append({**camera, "analyse": label,
                         "color": [194, 65, 12, 230] if url == DEMO_URL else color})
        snapshot = {"catalogue": signature, "rows": rows}
        st.session_state["webcam_map_snapshot"] = snapshot
    return pd.DataFrame(snapshot["rows"])


def _refreshed_image_url(url: str) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("_pyrowatch_refresh", str(time.time_ns())))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@st.fragment(run_every="15s")
def _display_webcam_snapshot(url: str) -> None:
    if urlsplit(url).hostname == "opencctv.org":
        try:
            image = fetch_opencctv_snapshot(url)
        except requests.RequestException:
            st.warning("Le diffuseur ne répond pas ou l’image n’est pas accessible.")
        except ValueError as error:
            st.warning(f"Impossible d’afficher l’instantané : {error}")
        else:
            st.image(image, use_container_width=True)
    else:
        st.image(_refreshed_image_url(url), use_container_width=True)
    st.caption("Image actualisée environ toutes les 15 secondes, selon la fréquence du diffuseur.")


def live_webcams() -> None:
    if not CAMERAS_PATH.is_file():
        st.info("Le catalogue de webcams est indisponible.")
        return
    try:
        cameras = load_camera_directory(CAMERAS_PATH)
    except (OSError, ValueError):
        LOGGER.exception("Impossible de charger le catalogue de webcams")
        st.error("Le catalogue de webcams n’a pas pu être chargé.")
        return
    if not cameras:
        st.info("L’annuaire ne contient aucune webcam.")
        return

    cameras.append(dict(DEMO_CAMERA))

    section_title(
        "Webcams et flux vidéo",
        "Cliquez sur un repère pour afficher le flux correspondant",
    )
    st.caption(
        f"{len(cameras) - 1} webcams publiques + 1 démonstration · "
        "La disponibilité du direct peut avoir changé depuis la génération de l’annuaire."
    )

    map_col, video_col = st.columns([1.25, 1], gap="large")
    with map_col:
        st.button("Actualiser les états", key="refresh_webcam_states",
                  on_click=_refresh_map_status,
                  help="Actualise les couleurs de surveillance sans changer la webcam affichée.")
        data = _map_data(cameras)
        deck = pdk.Deck(
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data,
                    id=WEBCAM_LAYER_ID,
                    get_position="[lon, lat]",
                    get_fill_color="color",
                    get_line_color=[255, 255, 255, 230],
                    get_line_width=2,
                    line_width_min_pixels=1,
                    get_radius=1800,
                    radius_min_pixels=7,
                    pickable=True,
                    auto_highlight=True,
                )
            ],
            initial_view_state=pdk.ViewState(
                latitude=46.5,
                longitude=2.2,
                zoom=4.6,
                min_zoom=3,
                max_zoom=15,
            ),
            tooltip={"text": "{nom}\nMaille de risque : {id_maille}\n{analyse}"},
            map_provider="carto",
            map_style=OSM_MAP_STYLE,
        )
        st.pydeck_chart(
            deck,
            height=560,
            on_select=_select_webcam,
            selection_mode="single-object",
            key="live_webcam_map",
        )
        st.caption("Bleu : analysée · Rouge : suspicion au dernier passage · "
                   "Gris : en attente ou en échec · Orange : démonstration. "
                   "Le bouton ci-dessus actualise ces états ; les images continuent à se rafraîchir.")

    camera_by_url = {camera["url_youtube"]: camera for camera in cameras}
    selected_url = st.session_state.get("selected_webcam_url")
    selected_camera = camera_by_url.get(selected_url)

    with video_col:
        if selected_camera:
            st.markdown(f"### {selected_camera['nom']}")
            st.caption(f"Maille de risque : {selected_camera['id_maille']}")

            url = selected_camera["url_youtube"]
            if url == DEMO_URL:
                demo_controls("map_demo")
                analysis_preview(camera_id(url))
                return
            with st.expander("Dernière analyse YOLO"):
                analysis_preview(camera_id(url))
            display_type = webcam_display_type(url)

            if display_type == "youtube":
                components.iframe(webcam_embed_url(url), height=360)
                st.link_button("Ouvrir sur YouTube", url)
                st.caption("Si le direct n’est pas intégrable, ouvre-le directement sur YouTube.")
            elif display_type == "image":
                _display_webcam_snapshot(url)
                st.link_button("Ouvrir la webcam", url)
            elif display_type == "video":
                st.video(url)
                st.link_button("Ouvrir le flux", url)
            elif display_type == "mjpeg":
                components.iframe(url, height=360)
                st.link_button("Ouvrir le flux", url)
            else:
                st.info(
                    "Cette URL est une page web plutôt qu’un flux direct ; "
                    "ouvrez-la sur le site du diffuseur."
                )
                st.link_button("Ouvrir la webcam", url)
                st.caption("Le flux s’ouvre dans un nouvel onglet sur le site du diffuseur.")
        else:
            st.info("Sélectionnez un repère sur la carte pour afficher son flux vidéo.")


def webcams() -> None:
    live_webcams()
