"""Transactional weather history; no per-cell snapshots and no automatic model training."""
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


def pack(**arrays):
    out = io.BytesIO()
    np.savez_compressed(out, **arrays)
    return out.getvalue()


def unpack(blob):
    with np.load(io.BytesIO(blob), allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS attempts (ts REAL NOT NULL, cost REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS slots (slot INTEGER PRIMARY KEY, checked_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, issued_at TEXT NOT NULL,
                content_hash TEXT NOT NULL, data BLOB NOT NULL);
              CREATE TABLE IF NOT EXISTS days (date TEXT PRIMARY KEY, issued_at TEXT NOT NULL,
                consolidated INTEGER NOT NULL DEFAULT 0, data BLOB NOT NULL);
              CREATE TABLE IF NOT EXISTS evaluation (target TEXT NOT NULL, lead INTEGER NOT NULL,
                run_id TEXT NOT NULL REFERENCES runs(id), PRIMARY KEY(target,lead));
            ''')

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def setting(self, key, default=None):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else default

    def set_setting(self, key, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def reserve(self, now, cost, daily_limit=9800):
        """Charge attempts, including failed requests, before making any HTTP call."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            day = db.execute('SELECT coalesce(sum(cost),0) FROM attempts WHERE ts>?', (now-86400,)).fetchone()[0]
            month = db.execute('SELECT coalesce(sum(cost),0) FROM attempts WHERE ts>?', (now-31*86400,)).fetchone()[0]
            minute = db.execute('SELECT coalesce(sum(cost),0) FROM attempts WHERE ts>?', (now-60,)).fetchone()[0]
            if day + cost > daily_limit or month + cost > 295000:
                raise RuntimeError('Budget Open-Meteo atteint ; dernière carte conservée, reprise au prochain créneau.')
            if minute + cost > 550:
                return False
            db.execute('INSERT INTO attempts VALUES (?,?)', (now, cost))
            db.execute('DELETE FROM attempts WHERE ts<?', (now-32*86400,))
        return True

    def check_budget(self, now, cost):
        """Avoid starting a full national window when only a partial window fits."""
        with self.db() as db:
            day = db.execute('SELECT coalesce(sum(cost),0) FROM attempts WHERE ts>?', (now-86400,)).fetchone()[0]
            month = db.execute('SELECT coalesce(sum(cost),0) FROM attempts WHERE ts>?', (now-31*86400,)).fetchone()[0]
        if day+cost > 9800 or month+cost > 295000:
            raise RuntimeError('Budget Open-Meteo atteint ; rattrapage sauvegardé, reprise au prochain créneau disponible.')

    def claim_slot(self, slot, checked_at, force=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT checked_at FROM slots ORDER BY checked_at DESC LIMIT 1').fetchone()
            if not force and previous and (datetime.fromisoformat(checked_at)-datetime.fromisoformat(previous[0])).total_seconds() < 5400:
                return False
            if force:
                db.execute('INSERT OR REPLACE INTO slots VALUES (?,?)', (slot, checked_at))
                return True
            return db.execute('INSERT OR IGNORE INTO slots VALUES (?,?)', (slot, checked_at)).rowcount == 1

    def next_check(self, now):
        with self.db() as db:
            row = db.execute('SELECT checked_at FROM slots ORDER BY checked_at DESC LIMIT 1').fetchone()
        return ((datetime.fromisoformat(row[0]) if row else now)+timedelta(seconds=5400)).isoformat()

    def days(self):
        with self.db() as db:
            return db.execute('SELECT * FROM days ORDER BY date').fetchall()

    def anchor(self):
        with self.db() as db:
            row = db.execute('SELECT * FROM days WHERE consolidated=1 ORDER BY date DESC LIMIT 1').fetchone()
        if row:
            return row['date'], unpack(row['data'])['state']
        initial = self.setting('initial')
        if initial is None:
            raise RuntimeError('État FWI initial absent : lancer ml/prepare_live_state.py.')
        return initial['date'], np.asarray(initial['state'], dtype=float)

    def save_run(self, run_id, issued_at, content_hash, arrays, dates, today, states, z, fwi):
        """Publish all stations atomically; update only the still-provisional daily archive."""
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO runs VALUES (?,?,?,?)',
                       (run_id, issued_at, content_hash, pack(**arrays)))
            for i, day in enumerate(dates):
                if day >= today:
                    continue
                payload = pack(weather=arrays['weather'][i], state=states[i], z=z[i], fwi=fwi[i])
                db.execute('''INSERT INTO days(date,issued_at,data) VALUES (?,?,?)
                  ON CONFLICT(date) DO UPDATE SET issued_at=excluded.issued_at,data=excluded.data
                  WHERE days.consolidated=0''', (day, issued_at, payload))
            for lead in (1, 3, 7):
                target = (np.datetime64(today) + np.timedelta64(lead, 'D')).astype(str)
                if target in dates:
                    db.execute('INSERT OR REPLACE INTO evaluation VALUES (?,?,?)', (target, lead, run_id))

    def save_backfill(self, dates, weather, states, z, fwi, issued_at):
        """Commit each completed historical window, so even a multi-day catch-up resumes."""
        with self.db() as db:
            for i, day in enumerate(dates):
                db.execute('INSERT OR REPLACE INTO days VALUES (?,?,1,?)',
                           (day, issued_at, pack(weather=weather[i], state=states[i], z=z[i], fwi=fwi[i])))

    def compact(self, now, retention_days=7):
        """Consolidate a day before deleting revisions; retain runs used for J+1/J+3/J+7 evaluation."""
        cutoff = (now.date() - timedelta(days=retention_days)).isoformat()
        with self.db() as db:
            db.execute('UPDATE days SET consolidated=1 WHERE date<=?', (cutoff,))
            db.execute('''DELETE FROM runs WHERE issued_at<? AND id NOT IN
              (SELECT run_id FROM evaluation)''', ((now-timedelta(days=retention_days)).isoformat(),))
            db.execute('DELETE FROM slots WHERE checked_at<?', ((now-timedelta(days=32)).isoformat(),))
            db.execute('PRAGMA incremental_vacuum')
