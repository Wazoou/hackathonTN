"""Operational pipeline: real FWI equations, fake HTTP only, isolated persistent archives."""
import base64
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weather.collector import Collector, VARIABLES, evolve, INTERVAL
from weather.storage import Store, unpack
from ml.fwi import step


class Response:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


class Session:
    def __init__(self):
        self.calls = []
        self.temp = 25
        self.missing = False
        self.error = False
    def get(self, url, params, timeout):
        self.calls.append((url, params))
        if self.error:
            raise ConnectionError('réseau absent')
        first = datetime.fromisoformat(params['start_date'])
        last = datetime.fromisoformat(params['end_date'])
        dates = [(first+timedelta(days=i)).date().isoformat() for i in range((last-first).days+1)]
        n = len(dates)
        daily = dict(zip(VARIABLES, [[self.temp]*n, [30]*n, [10]*n, [0]*n]))
        daily['time'] = dates
        if self.missing:
            daily[VARIABLES[0]][0] = None
        item = {'daily': daily, 'daily_units': dict(zip(VARIABLES, ['°C', '%', 'km/h', 'mm']))}
        return Response([item for _ in params['latitude'].split(',')])


class Observations:
    def __init__(self):
        self.calls = []
        self.error = False
    def fetch(self, first, last):
        self.calls.append((first, last))
        if self.error:
            raise RuntimeError('Météo-France indisponible')
        days = (last-first).days+1
        weather = np.tile(np.array([[25,25], [30,30], [10,10], [0,0]], dtype=float), (days,1,1))
        return {'weather': weather, 'imputed': np.zeros_like(weather, dtype=bool)}


class LiveWeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = self.root/'risk/meteo'
        folder.mkdir(parents=True)
        self.ids = ['01000001', '33000001']
        (folder/'stations.json').write_text(json.dumps([{'station': key, 'lat': 45, 'lon': i} for i, key in enumerate(self.ids)]))
        self.model = {'intercept': -5, 'coefficients': {'log_terrain': 1, 'ffmc_100': -2, 'log_dmc': 1, 'log_dc': -.5, 'log_isi': 1}}
        (folder/'modele.json').write_text(json.dumps({'modele_retenu': 'final', 'modeles': {'final': self.model}}))
        np.savez(folder/'meteo.npz', dates=['2026-07-01'], stations=self.ids)
        self.state = np.array([[85., 84.], [6., 5.], [15., 16.]])
        np.savez(folder/'live_initial_state.npz', date=np.array('2026-07-01'), stations=self.ids, state=self.state)
        self.now = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
        self.session = Session()
        self.observations = Observations()
        self.collector = Collector(self.root/'risk', self.root/'weather', session=self.session, clock=lambda:self.now, backfill=self.observations)

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, manifest):
        wrapper = json.loads((self.root/'weather/public'/manifest['bundle']).read_text())
        return json.loads(gzip.decompress(base64.b64decode(wrapper['payload'])))

    def test_live_forecast_exact_state_and_restart_safe_slot(self):
        manifest = self.collector.run_once()
        self.assertIsNone(manifest['error'])
        data = self.bundle(manifest)
        self.assertEqual(data['dates'][0], '2026-07-02')
        self.assertEqual(data['dates'][-1], '2026-07-10')  # J+7, in addition to today
        self.assertEqual(data['stations'], self.ids)
        state = {k:self.state[i] for i,k in enumerate(('ffmc','dmc','dc'))}
        state, _ = step(state, *[np.array(v) for v in ([25,25],[30,30],[10,10],[0,0])], 7)
        with self.collector.store.db() as db:
            day = unpack(db.execute("SELECT data FROM days WHERE date='2026-07-02'").fetchone()[0])
        np.testing.assert_allclose(day['state'], np.stack(list(state.values())))
        self.assertEqual(len(self.session.calls), 1)
        second = Collector(self.root/'risk', self.root/'weather', session=self.session, clock=lambda:self.now)
        self.assertIsNone(second.run_once())
        self.assertEqual(len(self.session.calls), 1)

    def test_same_day_revision_branches_from_anchor_and_changes_map(self):
        first = self.bundle(self.collector.run_once())
        self.now += timedelta(seconds=INTERVAL)
        self.session.temp = 35
        second = self.bundle(self.collector.run_once())
        weather = np.array([[[35,35],[30,30],[10,10],[0,0]]]*len(second['dates']))
        _, expected_z, expected_fwi = evolve(self.model, self.state, weather, second['dates'])
        np.testing.assert_allclose(second['z'], expected_z)
        np.testing.assert_allclose(second['fwi'], expected_fwi)
        self.assertNotEqual(first['z'], second['z'])
        with self.collector.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 2)

    def test_first_partial_slot_still_waits_ninety_minutes(self):
        self.now += timedelta(minutes=59)
        first = self.collector.run_once()
        self.assertEqual(datetime.fromisoformat(first['next_check']), self.now+timedelta(minutes=90))
        self.now += timedelta(minutes=32)  # new wall-clock slot, but not yet 90 minutes
        self.assertIsNone(self.collector.run_once())
        self.now += timedelta(minutes=58)
        self.assertIsNotNone(self.collector.run_once())
        self.assertEqual(len(self.session.calls), 2)

    def test_unchanged_weather_does_not_store_redundant_run(self):
        first = self.collector.run_once()
        self.now += timedelta(seconds=INTERVAL)
        second = self.collector.run_once()
        self.assertEqual(first['version'], second['version'])
        self.assertNotEqual(first['retrieved_at'], second['retrieved_at'])
        with self.collector.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 1)

    def test_failed_or_incomplete_collection_keeps_previous_bundle(self):
        first = self.collector.run_once()
        self.now += timedelta(seconds=INTERVAL)
        self.session.missing = True
        second = self.collector.run_once()
        self.assertIn('manquante', second['error'])
        self.assertEqual(second['version'], first['version'])
        self.assertEqual(second['retrieved_at'], first['retrieved_at'])
        with self.collector.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT sum(cost) FROM attempts').fetchone()[0], 4)

    def test_compaction_preserves_daily_weather_state_and_forecast_evaluation(self):
        self.collector.run_once()
        self.now += timedelta(seconds=INTERVAL)
        self.session.temp = 27
        self.collector.run_once()
        self.now += timedelta(days=9)
        self.collector.store.compact(self.now)
        with self.collector.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM days WHERE consolidated=1').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM evaluation').fetchone()[0], 3)
        # Resuming after a long break fills every missing day and starts at the saved state.
        result = self.collector.run_once()
        self.assertIsNone(result['error'])
        dates = self.bundle(result)['dates']
        self.assertEqual(dates, [(datetime(2026,7,2)+timedelta(days=i)).date().isoformat() for i in range(len(dates))])

    def test_budget_charges_failed_attempts_and_survives_restart(self):
        store = self.collector.store
        now = self.now.timestamp()
        self.assertTrue(store.reserve(now, 550))
        self.assertFalse(store.reserve(now, 1))
        self.assertTrue(store.reserve(now+61, 550))
        with self.assertRaisesRegex(RuntimeError, 'Budget'):
            store.reserve(now+122, 9000)
        other = Store(store.path)
        with self.assertRaisesRegex(RuntimeError, 'Budget'):
            other.reserve(now+180, 9000)

    def test_long_catchup_checkpoints_and_uses_no_openmeteo_quota_for_old_days(self):
        self.now += timedelta(days=40)
        original_save = self.collector.store.save_backfill
        calls = []
        def interrupted(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 2:
                raise RuntimeError('interruption après une tranche')
            return original_save(*args, **kwargs)
        self.collector.store.save_backfill = interrupted
        result = self.collector.run_once()
        self.assertTrue(result['error'])
        self.assertEqual(len(self.session.calls), 0)
        anchor, _ = self.collector.store.anchor()
        self.assertEqual(anchor, calls[0][-1])
        self.now += timedelta(seconds=INTERVAL)
        self.collector.store.save_backfill = original_save
        result = self.collector.run_once()
        self.assertIsNone(result['error'])
        self.assertEqual(self.observations.calls[1][0].isoformat(), (datetime.fromisoformat(anchor)+timedelta(days=1)).date().isoformat())
        self.assertEqual(len(self.session.calls), 1)
        recent_first = self.now.date()-timedelta(days=6)
        self.assertEqual(self.session.calls[0][1]['start_date'], recent_first.isoformat())
        data = self.bundle(result)
        by_date = dict(zip(data['dates'], data['provenance']))
        self.assertEqual(by_date[anchor]['provider'], 'meteofrance')
        self.assertIn('observations', by_date[anchor]['source'])
        self.assertEqual(by_date[self.now.date().isoformat()]['provider'], 'openmeteo')
        with self.collector.store.db() as db:
            self.assertEqual(db.execute('SELECT sum(cost) FROM attempts').fetchone()[0], 2)

    def test_observation_failure_does_not_fall_back_to_openmeteo(self):
        self.now += timedelta(days=20)
        self.observations.error = True
        result = self.collector.run_once()
        self.assertIn('Météo-France', result['error'])
        self.assertEqual(self.session.calls, [])
        with self.collector.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_model_or_station_change_rejected_without_mixing_archives(self):
        path = self.root/'risk/meteo/modele.json'
        meta = json.loads(path.read_text())
        meta['modeles']['final']['intercept'] = -6
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(RuntimeError, 'modèle ou les stations'):
            Collector(self.root/'risk', self.root/'weather')

    def test_missing_initial_state_does_not_publish_fake_risk(self):
        (self.root/'risk/meteo/live_initial_state.npz').unlink()
        result = self.collector.run_once()
        self.assertIsNone(result['version'])
        self.assertTrue(result['error'])


if __name__ == '__main__':
    unittest.main()
