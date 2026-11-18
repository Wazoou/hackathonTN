"""Live YouTube webcam map and recorded archive views."""

import os
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from archives import archives
from interface import section_title
from webcam_directory import load_camera_directory, selected_camera_url

CAMERAS_JSON_PATH = Path(
    os.getenv(
        "CAMERAS_JSON_PATH",
        str(Path(__file__).resolve().parent.parent / "camera-data" / "cameras.json"),
    )
)


def live_webcams() -> None:
    if not CAMERAS_JSON_PATH.is_file():
        st.info(
            f"Aucun annuaire de webcams trouvé ({CAMERAS_JSON_PATH}). "
            "Depuis la racine du dépôt, définissez votre clé YouTube Data API "
            "dans PowerShell et générez l’annuaire :"
        )
        st.code(
            '$env:YOUTUBE_API_KEY = "votre-cle-api"\n'
            "python ml\\build_camera_directory.py "
            '--mesh "ifm_plus\\data\\raw\\dfci\\dfci_2km.gpkg" '
            "--id-column id_carreau_dfci",
            language="powershell",
        )
        st.caption(
            "Le fichier créé dans camera-data sera visible par Docker ; "
            "rechargez ensuite cette page. Ne partagez pas votre clé API."
        )
        return
    try:
        cameras = load_camera_directory(CAMERAS_JSON_PATH)
    except (OSError, ValueError) as error:
        st.error(f"Impossible de charger l’annuaire de webcams : {error}")
        return
    if not cameras:
        st.info("L’annuaire ne contient aucune webcam YouTube.")
        return

    section_title(
        "Webcams YouTube en direct",
        "Cliquez sur un repère pour afficher le flux correspondant",
    )
    st.caption(
        f"{len(cameras)} webcam(s) géolocalisée(s) · "
        "La disponibilité du direct peut avoir changé depuis la génération de l’annuaire."
    )

    map_col, video_col = st.columns([1.25, 1], gap="large")
    with map_col:
        data = pd.DataFrame(cameras)
        deck = pdk.Deck(
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data,
                    id="youtube_cameras",
                    get_position="[lon, lat]",
                    get_fill_color=[0, 122, 204, 190],
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
                zoom=5,
                min_zoom=3,
                max_zoom=15,
            ),
            tooltip={"text": "{nom}\nMaille de risque : {id_maille}"},
        )
        map_state = st.pydeck_chart(
            deck,
            height=560,
            on_select="rerun",
            selection_mode="single-object",
            key="youtube_webcam_map",
        )

    camera_by_url = {camera["url_youtube"]: camera for camera in cameras}
    selected_url = selected_camera_url(map_state)
    if selected_url in camera_by_url:
        st.session_state["selected_youtube_webcam"] = selected_url
    selected_url = st.session_state.get("selected_youtube_webcam")
    selected_camera = camera_by_url.get(selected_url)

    with video_col:
        if selected_camera:
            st.markdown(f"### {selected_camera['nom']}")
            st.caption(f"Maille de risque : {selected_camera['id_maille']}")
            st.video(selected_camera["url_youtube"])
            st.link_button("Ouvrir sur YouTube", selected_camera["url_youtube"])
        else:
            st.info("Sélectionnez un repère sur la carte pour afficher son flux vidéo.")


def webcams() -> None:
    view = st.radio(
        "Contenu webcam",
        ("Flux YouTube", "Archives enregistrées"),
        horizontal=True,
        label_visibility="collapsed",
        key="webcam_content_view",
    )
    if view == "Flux YouTube":
        live_webcams()
    else:
        archives()
