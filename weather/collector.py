"""One national collection per 90-minute slot, bounded quotas and restart-safe archives.

Run from the repository: python -m weather.collector --once
The model is frozen. Current daily risk is revised; this is not an hourly fire probability.
"""
import argparse
import base64
import gzip
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from dashboard.daily_data import weather_term
from dashboard.daily_payload import model_signature
from ml.fwi import step
from weather.storage import Store, unpack

LOG = logging.getLogger('weather')
PARIS = ZoneInfo('Europe/Paris')
VARIABLES = ['temperature_2m_max', 'relative_humidity_2m_min', 'wind_speed_10m_mean', 'precipitation_sum']
INTERVAL = 90 * 60


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.part')
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    temp.replace(path)


def evolve(model, state, weather, dates):
    """Always branch from the last consolidated state; never apply a revision twice."""
    state = {key: np.asarray(state[i], dtype=float).copy() for i, key in enumerate(('ffmc', 'dmc', 'dc'))}
    states, z, fwi = [], [], []
    for row, day in zip(np.asarray(weather, dtype=float), dates):
        state, indices = step(state, *row, int(day[5:7]))
        states.append(np.stack(list(state.values())))
        z.append(weather_term(model, pd.DataFrame(indices)))
        fwi.append(indices['fwi'])
    return np.asarray(states), np.asarray(z, dtype=np.float32), np.asarray(fwi, dtype=np.float32)


class Collector:
    def __init__(self, risk_dir, data_dir, session=None, clock=None, sleep=time.sleep):
        self.meteo = Path(risk_dir) / 'meteo'
        self.folder = Path(data_dir)
        self.public = self.folder / 'public'
        self.store = Store(self.folder / 'weather.sqlite')
        self.session = session or requests.Session()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        self.station_info = json.loads((self.meteo/'stations.json').read_text())
        self.meta = json.loads((self.meteo/'modele.json').read_text())
        self.model = self.meta['modeles'][self.meta['modele_retenu']]
        with np.load(self.meteo/'meteo.npz', allow_pickle=False) as history:
            self.ids = list(history['stations'].astype(str))
            self.history_end = str(history['dates'][-1])
        by_id = {row['station']: row for row in self.station_info}
        self.station_info = [by_id[key] for key in self.ids]
        self.model_version = model_signature(self.model, self.ids)
        existing = self.store.setting('model_version')
        if existing and existing != self.model_version:
            raise RuntimeError('Le modèle ou les stations ont changé : utiliser un nouveau WEATHER_DATA_DIR pour conserver les archives précédentes.')
        self.store.set_setting('model_version', self.model_version)
        self.store.set_setting('model', self.model)
        self.store.set_setting('stations', self.station_info)
        self.api = os.getenv('OPEN_METEO_URL', 'https://api.open-meteo.com/v1/forecast')

    def initialize(self):
        if self.store.setting('initial'):
            if self.store.setting('initial')['date'] != self.history_end:
                raise ValueError('Le socle historique a changé : conserver les anciennes archives et utiliser un nouveau dossier météo LIVE.')
            return
        with np.load(self.meteo/'live_initial_state.npz', allow_pickle=False) as initial:
            if list(initial['stations'].astype(str)) != self.ids or str(initial['date']) != self.history_end:
                raise ValueError('État FWI initial et historique incompatibles ; régénérer live_initial_state.npz.')
            state = initial['state']
            if state.shape != (3, len(self.ids)) or not np.isfinite(state).all():
                raise ValueError('État FWI initial incomplet.')
            self.store.set_setting('initial', {'date': self.history_end, 'state': state.tolist()})

    def request(self, stations, first, last):
        cost = len(stations) * max(1, ((last-first).days+1)/14)
        while not self.store.reserve(self.clock().timestamp(), cost):
            self.sleep(2)
        params = {'latitude': ','.join(str(s['lat']) for s in stations),
                  'longitude': ','.join(str(s['lon']) for s in stations),
                  'daily': ','.join(VARIABLES), 'start_date': first.isoformat(), 'end_date': last.isoformat(),
                  'timezone': 'Europe/Paris', 'wind_speed_unit': 'kmh', 'temperature_unit': 'celsius',
                  'precipitation_unit': 'mm'}
        # Older startup gaps use the matching operational-model archive, not ERA5.
        url = self.api
        if first < self.clock().astimezone(PARIS).date()-timedelta(days=90):
            url = 'https://historical-forecast-api.open-meteo.com/v1/forecast'
        response = self.session.get(url, params=params, timeout=(15, 120))
        response.raise_for_status()
        payload = response.json()
        items = payload if isinstance(payload, list) else [payload]
        if len(items) != len(stations):
            raise ValueError('Réponse Open-Meteo incomplète : nombre de points incorrect.')
        wanted = pd.date_range(first, last).strftime('%Y-%m-%d').tolist()
        arrays = []
        for item in items:
            daily = item.get('daily', {})
            if daily.get('time') != wanted:
                raise ValueError('Réponse Open-Meteo incomplète : dates manquantes.')
            units = item.get('daily_units', {})
            expected_units = ('°C', '%', 'km/h', 'mm')
            if any(units.get(key) != unit for key, unit in zip(VARIABLES, expected_units)):
                raise ValueError('Unités météo incompatibles.')
            values = np.asarray([daily[key] for key in VARIABLES], dtype=np.float32)
            if values.shape != (4, len(wanted)) or not np.isfinite(values).all():
                raise ValueError('Météo manquante : carte précédente conservée, aucune valeur inventée.')
            if ((values[1] < 0) | (values[1] > 100)).any() or (values[2:] < 0).any():
                raise ValueError('Valeurs météo invalides.')
            arrays.append(values)
        return np.stack(arrays, axis=2).transpose(1, 0, 2)

    def fetch(self, first, last):
        chunks = []
        while first <= last:
            end = min(first+timedelta(days=13), last)
            self.store.check_budget(self.clock().timestamp(), len(self.ids))
            batches = []
            for start in range(0, len(self.ids), 50):
                stations = self.station_info[start:start+50]
                LOG.info('Collecte %s → %s : points %s–%s/%s', first, end, start+1, start+len(stations), len(self.ids))
                batches.append(self.request(stations, first, end))
            chunks.append(np.concatenate(batches, axis=2))
            first = end+timedelta(days=1)
        return np.concatenate(chunks, axis=0)

    def publish(self, now, error=None):
        """The manifest is tiny and polled; the compressed bundle is fetched only on change."""
        latest = self.store.setting('latest')
        if latest:
            with self.store.db() as db:
                run = db.execute('SELECT * FROM runs WHERE id=?', (latest['id'],)).fetchone()
            if run is None:
                raise RuntimeError('Dernière collecte introuvable.')
            arrays = unpack(run['data'])
            rows = {}
            for row in self.store.days():
                day = unpack(row['data'])
                rows[row['date']] = {'z': day['z'], 'fwi': day['fwi'], 'issued_at': row['issued_at'],
                                     'consolidated': bool(row['consolidated'])}
            for i, day in enumerate(arrays['dates'].astype(str)):
                if day >= now.astimezone(PARIS).date().isoformat() or day not in rows:
                    rows[day] = {'z': arrays['z'][i], 'fwi': arrays['fwi'][i], 'issued_at': run['issued_at'], 'consolidated': False}
            dates = sorted(rows)
            data = {'model_version': self.model_version, 'stations': self.ids, 'dates': dates,
                    'z': [rows[d]['z'].tolist() for d in dates], 'fwi': [rows[d]['fwi'].tolist() for d in dates],
                    'provenance': [{'issued_at': rows[d]['issued_at'], 'consolidated': rows[d]['consolidated']} for d in dates],
                    'source': 'Open-Meteo · météo modélisée · sélection automatique', 'history_end': self.history_end}
            raw = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
            version = hashlib.sha256(raw).hexdigest()
            target = self.public / f'bundle-{version}.json'
            if not target.exists():
                atomic_json(target, {'version': version, 'payload': base64.b64encode(gzip.compress(raw, mtime=0)).decode()})
            bundle_name = target.name
        else:
            version = bundle_name = None
        manifest = {'version': version, 'bundle': bundle_name, 'today': now.astimezone(PARIS).date().isoformat(),
                    'checked_at': now.isoformat(), 'retrieved_at': self.store.setting('retrieved_at'),
                    'next_check': self.store.next_check(now),
                    'error': error, 'interval_minutes': 90, 'source': 'Open-Meteo · météo modélisée'}
        atomic_json(self.public/'current.json', manifest)
        # Readers may still be fetching the previous manifest: retain the last two bundles.
        for old in sorted(self.public.glob('bundle-*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[2:]:
            if old.name != bundle_name:
                old.unlink(missing_ok=True)
        return manifest

    def run_once(self, force=False):
        now = self.clock()
        slot = int(now.timestamp())//INTERVAL
        if not self.store.claim_slot(slot, now.isoformat(), force=force):
            return None
        # Force is a troubleshooting option, not a quota bypass.
        try:
            self.initialize()
            self.store.compact(now.astimezone(PARIS))
            anchor_date, state = self.store.anchor()
            today = now.astimezone(PARIS).date()
            first = datetime.fromisoformat(anchor_date).date()+timedelta(days=1)
            cutoff = today-timedelta(days=7)
            while first <= cutoff:
                end = min(cutoff, first+timedelta(days=13))
                past_dates = pd.date_range(first, end).strftime('%Y-%m-%d').tolist()
                past_weather = self.fetch(first, end)
                states, z, fwi = evolve(self.model, state, past_weather, past_dates)
                if not np.isfinite(z).all() or not np.isfinite(fwi).all():
                    raise ValueError('Rattrapage FWI incomplet : dernier état conservé.')
                self.store.save_backfill(past_dates, past_weather, states, z, fwi, now.isoformat())
                state, first = states[-1], end+timedelta(days=1)
            last = today+timedelta(days=7)
            dates = pd.date_range(first, last).strftime('%Y-%m-%d').tolist()
            weather = self.fetch(first, last)
            states, z, fwi = evolve(self.model, state, weather, dates)
            if not np.isfinite(z).all() or not np.isfinite(fwi).all():
                raise ValueError('Calcul FWI incomplet : dernière carte conservée.')
            content_hash = hashlib.sha256('|'.join(dates).encode()+weather.tobytes()+state.tobytes()).hexdigest()
            latest = self.store.setting('latest')
            if not latest or latest['content_hash'] != content_hash:
                run_id = now.strftime('%Y%m%dT%H%M%S')+'-'+content_hash[:12]
                arrays = {'dates': np.array(dates), 'weather': weather, 'initial_state': state, 'z': z, 'fwi': fwi}
                self.store.save_run(run_id, now.isoformat(), content_hash, arrays, dates, today.isoformat(), states, z, fwi)
                self.store.set_setting('latest', {'id': run_id, 'content_hash': content_hash})
            self.store.set_setting('retrieved_at', now.isoformat())
            self.store.set_setting('last_error', None)
            result = self.publish(now)
            LOG.info('LIVE et J+1…J+7 publiés ; collecte %s', result['retrieved_at'])
            return result
        except Exception as exc:
            LOG.exception('Collecte interrompue ; dernière carte conservée')
            error = f'Open-Meteo inaccessible (HTTP {exc.response.status_code}).' if isinstance(exc, requests.HTTPError) and exc.response is not None else 'Connexion météo indisponible.' if isinstance(exc, requests.RequestException) else str(exc)
            self.store.set_setting('last_error', error)
            return self.publish(now, error=error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--risk-data', type=Path, default=Path(os.getenv('RISK_DIR', 'risk-data')))
    parser.add_argument('--data', type=Path, default=Path(os.getenv('WEATHER_DATA_DIR', 'data/weather')))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    # Prevent two collectors sharing one archive and spending the quota twice.
    import fcntl
    args.data.mkdir(parents=True, exist_ok=True)
    lock = (args.data/'collector.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    collector = Collector(args.risk_data, args.data)
    collector.publish(collector.clock(), error=collector.store.setting('last_error'))
    while True:
        result = collector.run_once(force=args.force)
        if args.once:
            if result and result.get('error'):
                raise SystemExit(1)
            break
        time.sleep(30)
        args.force = False


if __name__ == '__main__':
    main()
