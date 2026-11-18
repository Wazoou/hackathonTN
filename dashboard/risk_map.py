"""Persistent national risk map: UI interactions stay in the browser."""
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from risk_payload import build_payload, file_signature

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BDIFF_RISK_DIR = PROJECT_ROOT / 'pyro-watch-risque-france-bdiff' / 'risk-data'
LEGACY_RISK_DIR = PROJECT_ROOT / 'risk-data'
DEFAULT_RISK_DIR = (
    BDIFF_RISK_DIR
    if any(BDIFF_RISK_DIR.glob('risque_statique_*.geojson'))
    else LEGACY_RISK_DIR
)
RISK_DIR = Path(os.getenv('RISK_DIR', str(DEFAULT_RISK_DIR)))
_component = components.declare_component('national_risk_map', path=str(Path(__file__).parent / 'risk_component'))


@st.cache_resource(max_entries=2, show_spinner=False)
def cached_payload(signature):
    # Immutable encoded payload. Unlike cache_data, no deep copy of 140k polygons per rerun.
    return build_payload(signature)


def risk_map():
    st.subheader('Carte de risque de départ de feu')
    signature = file_signature(RISK_DIR)
    if not signature:
        st.info('Aucune carte de risque disponible. Générez les fichiers dans risk-data avec ml/build_static_risk.py.')
        return
    with st.spinner('Préparation de la carte nationale…'):
        payload = cached_payload(signature)
    _component(payload=payload['payload'], version=payload['version'], key='national_risk_map', default=None)
