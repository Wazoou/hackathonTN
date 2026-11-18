"""Persistent national risk map: UI interactions stay in the browser.

Avec ``risk-data/meteo`` (ml/build_daily_risk.py), une couche « Risque du jour » est ajoutée :
Python ne renvoie à chaque date qu'un tableau de probabilités par maille, jamais les géométries.
"""
import base64
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from daily_data import DAY_BOUNDS, DAY_COLORS, DAY_LABELS
from risk_payload import build_payload, file_signature
from fire_statistics import history_signature

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BDIFF_RISK_DIR = PROJECT_ROOT / 'pyro-watch-risque-france-bdiff' / 'risk-data'
LEGACY_RISK_DIR = PROJECT_ROOT / 'risk-data'
DEFAULT_RISK_DIR = (
    BDIFF_RISK_DIR
    if any(BDIFF_RISK_DIR.glob('risque_statique_*.geojson'))
    else LEGACY_RISK_DIR
)
RISK_DIR = Path(os.getenv('RISK_DIR', str(DEFAULT_RISK_DIR)))
BDIFF_DIR = Path(os.getenv('BDIFF_DIR', str(PROJECT_ROOT / 'ifm_plus/data/raw/manual/bdiff')))
METEO_DIR = RISK_DIR / 'meteo'
EXAMPLES = {'12/07/2022 · Landiras et La Teste': date(2022, 7, 12),
            '10/08/2022 · canicule': date(2022, 8, 10),
            '15/01/2022 · hiver': date(2022, 1, 15)}
_component = components.declare_component('national_risk_map', path=str(Path(__file__).parent / 'risk_component'))


PAYLOAD_FORMAT = 3  # à incrémenter quand build_payload change : invalide le cache des serveurs déjà lancés


@st.cache_resource(max_entries=2, show_spinner=False)
def cached_payload(signature, fire_signature=(), payload_format=PAYLOAD_FORMAT):
    # Immutable encoded payload. Unlike cache_data, no deep copy of 140k polygons per rerun.
    return build_payload(signature, fire_signature)


def meteo_signature():
    files = ['modele.json', 'meteo.npz', 'mailles.json', 'communes.json', 'feux_bdiff.csv.gz']
    if not all((METEO_DIR / f).exists() for f in files):
        return None
    return tuple((f, (METEO_DIR / f).stat().st_mtime_ns) for f in files)


@st.cache_resource(max_entries=2, show_spinner='Chargement de la météo et du modèle…')
def load_daily(signature, ids):
    """Tableaux alignés sur l'ordre des mailles du payload, pour un calcul vectorisé par date."""
    meta = json.loads((METEO_DIR / 'modele.json').read_text(encoding='utf-8'))
    model = meta['modeles'][meta['modele_retenu']]
    npz = np.load(METEO_DIR / 'meteo.npz', allow_pickle=False)
    dates = pd.DatetimeIndex(npz['dates'].astype(str))
    stations = {s: i for i, s in enumerate(npz['stations'].astype(str))}
    communes = json.loads((METEO_DIR / 'communes.json').read_text(encoding='utf-8'))
    codes = list(communes)
    commune_index = {c: i for i, c in enumerate(codes)}
    commune_station = np.array([stations[communes[c][0]] for c in codes])
    commune_terrain = np.array([communes[c][1] for c in codes])
    cells = json.loads((METEO_DIR / 'mailles.json').read_text(encoding='utf-8'))
    cell_commune = np.array([commune_index.get(cells[i][0], -1) if i in cells else -1 for i in ids])
    cell_share = np.array([cells[i][1] if i in cells else 0.0 for i in ids])
    fires = pd.read_csv(METEO_DIR / 'feux_bdiff.csv.gz', dtype={'code_insee': str}, parse_dates=['date'])
    fires['dept'] = fires['code_insee'].str[:2]
    return {'meta': meta, 'model': model, 'dates': dates, 'z': npz['z'], 'fwi': npz['fwi'],
            'commune_station': commune_station, 'commune_terrain': commune_terrain,
            'cell_commune': cell_commune, 'cell_share': cell_share, 'fires': fires,
            'bdiff_end': pd.Timestamp(meta['bdiff']['fin'])}


def commune_probabilities(d, rows):
    z = d['z'][rows][:, d['commune_station']] + d['model']['coefficients']['log_terrain'] * d['commune_terrain']
    return 1.0 / (1.0 + np.exp(-z))


def _fmt(value):
    return f'{value:g}'.replace('.', ',')


def daily_layer(d, day):
    """Valeurs du jour (pour 10 000) et FWI par maille, dans l'ordre du payload ; -1 = non disponible."""
    row = d['dates'].get_loc(day)
    p_commune = commune_probabilities(d, [row])[0]
    known = d['cell_commune'] >= 0
    values = np.full(len(d['cell_commune']), -1.0, dtype=np.float32)
    values[known] = 1e4 * p_commune[d['cell_commune'][known]] * d['cell_share'][known]
    values[~np.isfinite(values)] = -1.0
    fwi = np.full(len(values), -1.0, dtype=np.float32)
    fwi[known] = d['fwi'][row][d['commune_station'][d['cell_commune'][known]]]
    fwi[~np.isfinite(fwi)] = -1.0
    fires = d['fires'][d['fires']['date'] == day]
    legend = [[name, _fmt(DAY_BOUNDS[i]), _fmt(DAY_BOUNDS[i + 1]) if i < len(DAY_LABELS) - 1 else None, list(rgb)]
              for i, (name, rgb) in enumerate(zip(DAY_LABELS, DAY_COLORS))]
    layer = {'key': f'{day:%Y-%m-%d}', 'label': f'{day:%d/%m/%Y}',
             'values': base64.b64encode(values.tobytes()).decode(), 'fwi': base64.b64encode(fwi.tobytes()).decode(),
             'fires': [[round(x, 4), round(y, 4), dept] for x, y, dept in zip(fires['lon'], fires['lat'], fires['dept'])],
             'legend': legend}
    return layer, float(values[values >= 0].sum() / 1e4), len(fires)


def date_controls(d):
    first, last = max(d['dates'][0].date(), date(2006, 1, 1)), d['dates'][-1].date()
    if 'daily_date' not in st.session_state or not first <= st.session_state['daily_date'] <= last:
        st.session_state['daily_date'] = last
    # Keep the selected date when Streamlit removes the widget on another tab.
    def choose(value):
        st.session_state['daily_date'] = value
        st.session_state['_daily_date_input'] = value

    def remember():
        st.session_state['daily_date'] = st.session_state['_daily_date_input']

    if '_daily_date_input' not in st.session_state or not first <= st.session_state['_daily_date_input'] <= last:
        st.session_state['_daily_date_input'] = st.session_state['daily_date']
    cols = st.columns([1.3, 0.8, 0.9, 2.2])
    chosen = cols[0].date_input('Date du risque du jour', min_value=first, max_value=last, key='_daily_date_input',
                                format='DD/MM/YYYY', on_change=remember)
    cols[1].button('Dernier jour', help=f'{last:%d/%m/%Y}', use_container_width=True,
                   on_click=choose, args=(last,))
    with cols[2].popover('Exemples', use_container_width=True):
        for label, example in EXAMPLES.items():
            if not first <= example <= last:
                continue
            st.button(label, key=f'ex{example}', use_container_width=True,
                      on_click=choose, args=(example,))
    return pd.Timestamp(chosen), cols[3]


def series(d, day):
    start = max(day - timedelta(days=45), d['dates'][0])
    end = min(day + timedelta(days=45), d['dates'][-1])
    rows = np.where((d['dates'] >= start) & (d['dates'] <= end))[0]
    expected = pd.Series(np.nansum(commune_probabilities(d, rows), axis=1), index=d['dates'][rows])
    frame = pd.DataFrame({'Communes avec feu attendues (modèle)': expected})
    if start <= d['bdiff_end']:
        observed = d['fires'][(d['fires']['date'] >= start) & (d['fires']['date'] <= end)].groupby('date').size()
        frame['Feux BDIFF déclarés'] = observed.reindex(expected.index, fill_value=0).astype(float)
        frame.loc[frame.index > d['bdiff_end'], 'Feux BDIFF déclarés'] = np.nan
    return frame


def risk_map():
    signature = file_signature(RISK_DIR)
    if not signature:
        st.info('Aucune carte de risque disponible. Générez les fichiers dans risk-data avec ml/build_static_risk.py.')
        return
    with st.spinner('Préparation de la carte nationale…'):
        payload = cached_payload(signature, history_signature(BDIFF_DIR), PAYLOAD_FORMAT)
    daily, context = None, None
    meteo = meteo_signature()
    if meteo:
        d = load_daily(meteo, tuple(payload['ids']))
        day, info = date_controls(d)
        daily, expected, n_fires = daily_layer(d, day)
        known = day <= d['bdiff_end']
        note = '' if known else f" (BDIFF connu jusqu’au {d['bdiff_end']:%d/%m/%Y})"
        info.markdown(f'<div style="padding-top:30px;font-size:14px">Le {day:%d/%m/%Y} : '
                      f'<b>{expected:.1f}</b> communes avec au moins un feu '.replace('.', ',', 1) +
                      f'attendues sur la couverture météo · <b>{n_fires if known else "—"}</b> feux BDIFF déclarés{note}</div>',
                      unsafe_allow_html=True)
        context = (d, day)
    else:
        st.caption('La couche quotidienne sera disponible après ajout du dossier risk-data/meteo/ (voir DONNEES_EQUIPE.md).')
    _component(payload=payload['payload'], version=payload['version'], daily=daily, key='national_risk_map', default=None)
    if context:
        d, day = context
        with st.expander('Risque et feux déclarés autour de cette date'):
            st.line_chart(series(d, day), height=240)
            auc = d['meta']['apprentissage']['auc_test']
            st.caption(f"{d['meta']['apprentissage']['validation'].capitalize()} : AUC "
                       f"{auc['terrain_et_sous_indices']['auc']:.3f} avec la météo, {auc['terrain_seul']['auc']:.3f} "
                       f"avec le terrain seul. {d['meta']['meteo']['stations']} stations Météo-France, "
                       "indice forêt-météo de Van Wagner (1987). Relecture historique : le modèle final est entraîné sur toute la période disponible.")
