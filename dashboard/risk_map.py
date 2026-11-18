"""Persistent national risk map: UI interactions stay in the browser.

Avec ``risk-data/meteo`` (ml/build_daily_risk.py), une couche « Risque du jour » est ajoutée :
La météo est envoyée une fois ; le curseur et le calcul quotidien restent dans le navigateur.
"""
import base64
import json
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from daily_data import DAY_BOUNDS, DAY_COLORS, DAY_LABELS
from daily_payload import build_daily_payload
from risk_payload import build_payload, file_signature
from fire_statistics import history_signature
from fire_history import FIRE_DATA_PATH, CENTROID_PATH, DEPARTMENT_CENTROID_PATH, DATE_COLUMN, load_fire_records

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


def observation_signature():
    """Invalidate the weather bundle when the separate, newer BDIFF export changes."""
    if not FIRE_DATA_PATH.is_file() or not CENTROID_PATH.is_file():
        return ()
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size)
                 for p in (FIRE_DATA_PATH, CENTROID_PATH, DEPARTMENT_CENTROID_PATH) if p.is_file())


@st.cache_resource(max_entries=2, show_spinner='Chargement de la météo et du modèle…')
def load_daily(signature, ids, observations=()):
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
    bdiff_end = pd.Timestamp(meta['bdiff']['fin'])
    if observations:
        source, centroids = observations[:2]
        recent, _ = load_fire_records(source[0], centroids[0], observations, centroids[1])
        # The precomputed observations already contain the training years. Append only
        # newer years, preserving distinct fires in the same commune on the same day.
        recent = recent[(recent[DATE_COLUMN].dt.year > bdiff_end.year)
                        & (recent['zone'] == 'France métropolitaine')]
        if not recent.empty:
            bdiff_end = max(bdiff_end, recent[DATE_COLUMN].max().normalize())
            located = recent.dropna(subset=['latitude', 'longitude'])
            extra = pd.DataFrame({'code_insee': located['Code INSEE'],
                                  'date': located[DATE_COLUMN].dt.normalize(),
                                  'lon': located['longitude'], 'lat': located['latitude'],
                                  'dept': located.get('Département', located['Code INSEE'].str[:2]).str.strip().str.zfill(2)})
            fires = pd.concat([fires, extra], ignore_index=True)
    return {'meta': meta, 'model': model, 'dates': dates, 'z': npz['z'], 'fwi': npz['fwi'],
            'commune_station': commune_station, 'commune_terrain': commune_terrain,
            'cell_commune': cell_commune, 'cell_share': cell_share, 'fires': fires,
            'bdiff_end': bdiff_end}


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


@st.cache_resource(max_entries=2, show_spinner='Préparation de la navigation temporelle…')
def cached_weather(signature, ids, observations=()):
    return build_daily_payload(load_daily(signature, ids, observations))


def risk_map():
    signature = file_signature(RISK_DIR)
    if not signature:
        st.info('Aucune carte de risque disponible. Générez les fichiers dans risk-data avec ml/build_static_risk.py.')
        return
    with st.spinner('Préparation de la carte nationale…'):
        payload = cached_payload(signature, history_signature(BDIFF_DIR), PAYLOAD_FORMAT)
    weather = None
    meteo = meteo_signature()
    if meteo:
        weather = cached_weather(meteo, tuple(payload['ids']), observation_signature())
    else:
        st.caption('La couche quotidienne sera disponible après ajout du dossier risk-data/meteo/ (voir DONNEES_EQUIPE.md).')
    _component(payload=payload['payload'], version=payload['version'], weather=weather,
               key='national_risk_map', default=None)
