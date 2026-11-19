"""Dashboard Pyro-Watch : carte des risques, archives webcam, historique des incendies."""

import streamlit as st
from interface import (
    MODE_ARCHIVES,
    MODE_FIRE_HISTORY,
    MODE_RISK_MAP,
    apply_theme,
    current_mode,
    header,
    page_intro,
)

st.set_page_config(page_title="Pyro-Watch", layout="wide", initial_sidebar_state="collapsed")


apply_theme()
header()
mode = current_mode()
page_intro(mode)
if mode == MODE_RISK_MAP:
    from risk_map import risk_map
    risk_map()
elif mode == MODE_ARCHIVES:
    from archives import archives
    archives()
elif mode == MODE_FIRE_HISTORY:
    from fire_history import render_fire_history
    render_fire_history()
else:
    st.error(f"Mode de navigation inconnu : {mode}")

st.markdown('<div class="footer"><span>Pyro-Watch · Hackathon Open Data University</span>'
            '<span>Données : BDIFF, Météo-France, Open-Meteo, Pyronear, OpenStreetMap</span></div>',
            unsafe_allow_html=True)
