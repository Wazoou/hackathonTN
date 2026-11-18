"""Observed daily station data for old gaps; public files, independent of Open-Meteo quotas."""
import gzip
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

LOG = logging.getLogger('weather.meteofrance')
CATALOG = 'https://www.data.gouv.fr/api/1/datasets/donnees-climatologiques-de-base-quotidiennes/'
PATTERN = re.compile(r'Q_(?P<dept>\w{2,3})_(?:previous|latest)-(?P<start>\d{4})-(?P<end>\d{4})_(?P<family>RR-T-Vent|autres-parametres)\.csv\.gz$')
FAMILIES = {'RR-T-Vent': {'TX': 0, 'FFM': 2, 'RR': 3}, 'autres-parametres': {'UN': 1}}


class MeteoFrance:
    def __init__(self, stations, cache, local=None, session=None, clock=None):
        self.stations = stations
        self.ids = [s['station'] for s in stations]
        self.cache = Path(cache)
        self.local = Path(local) if local else None
        self.session = session or requests.Session()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.depts = {}
        for i, station in enumerate(stations):
            dept = str(station.get('dept', station['station'][:2])).zfill(2)
            self.depts.setdefault('20' if dept in ('2A', '2B') else dept, []).append(i)
        lat = np.asarray([s['lat'] for s in stations], dtype=float)
        lon = np.asarray([s['lon'] for s in stations], dtype=float)
        distance = (np.radians(lat[:, None]-lat[None, :])**2
                    + (np.radians(lon[:, None]-lon[None, :])*np.cos(np.radians((lat[:, None]+lat[None, :])/2)))**2)
        np.fill_diagonal(distance, np.inf)
        self.neighbors = np.argsort(distance, axis=1)[:, :min(5, len(stations)-1)]

    def paths(self, dept, family, first, last):
        paths = {}
        for folder in (self.local, self.cache):
            if folder is None:
                continue
            for path in folder.glob(f'Q_{dept}_*_{family}.csv.gz'):
                match = PATTERN.fullmatch(path.name)
                if match and int(match['start']) <= last.year and int(match['end']) >= first.year:
                    if path.name not in paths or path.stat().st_mtime_ns > paths[path.name].stat().st_mtime_ns:
                        paths[path.name] = path
        return sorted(paths.values(), key=lambda p:p.stat().st_mtime_ns)

    def read(self, first, last):
        dates = pd.date_range(first, last)
        keys = dates.strftime('%Y%m%d').astype(int)
        weather = np.full((len(dates), 4, len(self.ids)), np.nan, dtype=float)
        for dept, positions in self.depts.items():
            ids = [self.ids[i] for i in positions]
            for family, columns in FAMILIES.items():
                frames = []
                for path in self.paths(dept, family, first, last):
                    for chunk in pd.read_csv(path, sep=';', usecols=['NUM_POSTE', 'AAAAMMJJ', *columns],
                                             dtype={'NUM_POSTE': str}, chunksize=100000):
                        chunk['NUM_POSTE'] = chunk['NUM_POSTE'].str.strip().str.zfill(8)
                        chunk['AAAAMMJJ'] = pd.to_numeric(chunk['AAAAMMJJ'], errors='coerce')
                        selected = chunk[chunk['NUM_POSTE'].isin(ids) & chunk['AAAAMMJJ'].between(keys[0], keys[-1])]
                        if not selected.empty:
                            frames.append(selected)
                if frames:
                    frame = pd.concat(frames).drop_duplicates(['NUM_POSTE', 'AAAAMMJJ'], keep='last')
                    for column, variable in columns.items():
                        frame[column] = pd.to_numeric(frame[column], errors='coerce')
                        grid = frame.pivot(index='AAAAMMJJ', columns='NUM_POSTE', values=column).reindex(index=keys, columns=ids).to_numpy(dtype=float)
                        if column == 'FFM':
                            grid *= 3.6  # historical training also uses mean wind, m/s -> km/h
                        weather[:, variable, positions] = grid
        invalid = ~np.isfinite(weather)
        invalid[:, 0] |= (weather[:, 0] < -90) | (weather[:, 0] > 65)
        invalid[:, 1] |= (weather[:, 1] < 0) | (weather[:, 1] > 100)
        invalid[:, 2:] |= weather[:, 2:] < 0
        weather[invalid] = np.nan
        missing_depts = {dept: {family for family, columns in FAMILIES.items()
                               if any(not np.isfinite(weather[:, variable, positions]).all() for variable in columns.values())}
                         for dept, positions in self.depts.items()}
        missing_depts = {dept: families for dept, families in missing_depts.items() if families}
        original = weather.copy()
        # Same five-neighbor limit as the historical pipeline. Donors must have an
        # actual observation: never propagate a substitution through other stations.
        for i in range(len(self.ids)):
            for neighbor in self.neighbors[i]:
                gap = ~np.isfinite(weather[:, :, i])
                if not gap.any():
                    break
                weather[:, :, i][gap] = original[:, :, neighbor][gap]
        imputed = ~np.isfinite(original) & np.isfinite(weather)
        return weather, imputed, missing_depts

    def catalog(self):
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache/'catalog.json'
        if path.exists():
            cached = json.loads(path.read_text())
            if self.clock().timestamp()-cached['checked_at'] < 6*3600:
                return cached['resources']
        response = self.session.get(CATALOG, timeout=(15, 90))
        response.raise_for_status()
        resources = response.json()['resources']
        temp = path.with_suffix('.part')
        temp.write_text(json.dumps({'checked_at': self.clock().timestamp(), 'resources': resources}))
        temp.replace(path)
        return resources

    def refresh(self, first, last, depts):
        metadata = self.cache/'downloads.json'
        versions = json.loads(metadata.read_text()) if metadata.exists() else {}
        wanted = []
        for resource in self.catalog():
            name = Path(urlparse(resource.get('url', '')).path).name
            match = PATTERN.fullmatch(name)
            if match and match['dept'] in depts and int(match['start']) <= last.year and int(match['end']) >= first.year:
                if isinstance(depts, dict) and match['family'] not in depts[match['dept']]:
                    continue
                wanted.append((name, resource))
        if not wanted:
            raise ValueError('Aucun fichier Météo-France pour la période manquante.')
        for name, resource in wanted:
            tag = hashlib.sha256(json.dumps({k:resource.get(k) for k in ('url', 'last_modified', 'filesize', 'checksum')}, sort_keys=True).encode()).hexdigest()
            target = self.cache/name
            if target.exists() and versions.get(name) == tag:
                continue
            LOG.info('Téléchargement Météo-France : %s', name)
            temp = target.with_suffix('.part')
            try:
                with self.session.get(resource['url'], stream=True, timeout=(15, 180)) as response:
                    response.raise_for_status()
                    with temp.open('wb') as handle:
                        for chunk in response.iter_content(1 << 20):
                            handle.write(chunk)
                # Keep a previously valid cache file if the response is not gzip.
                with gzip.open(temp, 'rb') as handle:
                    while handle.read(1 << 20):
                        pass
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
            versions[name] = tag
            meta_temp = metadata.with_suffix('.part')
            meta_temp.write_text(json.dumps(versions, sort_keys=True))
            meta_temp.replace(metadata)

    def fetch(self, first, last):
        LOG.info('Rattrapage Météo-France observé : %s → %s', first, last)
        try:
            weather, imputed, missing_depts = self.read(first, last)
            if not np.isfinite(weather).all():
                self.refresh(first, last, missing_depts)
                weather, imputed, _ = self.read(first, last)
            if not np.isfinite(weather).all():
                missing = np.argwhere(~np.isfinite(weather))[0]
                day = (pd.Timestamp(first)+pd.Timedelta(days=int(missing[0]))).date()
                raise ValueError(f'Observations Météo-France incomplètes le {day}, station {self.ids[missing[2]]}, même avec les cinq voisines. Aucun repli Open-Meteo pour le rattrapage ancien.')
            return {'weather': weather, 'imputed': imputed}
        except requests.RequestException as exc:
            raise RuntimeError('Rattrapage Météo-France indisponible ; dernière carte conservée, sans dépense du quota Open-Meteo.') from exc
