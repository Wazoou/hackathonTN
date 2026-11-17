"""Persistent national risk map: UI interactions stay in the browser."""
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from risk_payload import build_payload, file_signature

RISK_DIR = Path(os.getenv('RISK_DIR', 'risk-data'))
_component = components.declare_component('national_risk_map', path=str(Path(__file__).parent / 'risk_component'))


@st.cache_resource(max_entries=2, show_spinner=False)
def cached_payload(signature):
    # Immutable encoded payload. Unlike cache_data, no deep copy of 140k polygons per rerun.
    return build_payload(signature)


def risk_map():
    st.markdown('<p class="eyebrow">Prévention · sensibilité du terrain</p>', unsafe_allow_html=True)
    st.subheader('Carte de risque de départ de feu')
    signature = file_signature(RISK_DIR)
    if not signature:
        st.info('Aucune carte de risque disponible. Générez les fichiers dans risk-data avec ml/build_static_risk.py.')
        return
    with st.spinner('Préparation de la carte nationale…'):
        payload = cached_payload(signature)
    _component(payload=payload['payload'], version=payload['version'], key='national_risk_map', default=None)
