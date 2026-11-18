"""Observed-file ingestion, station fallback, cache reuse and atomic refresh."""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weather.meteofrance import MeteoFrance, CATALOG
from weather.storage import Store, pack


class NeverNetwork:
    def get(self, *args, **kwargs):
        raise AssertionError('Complete cached observations must not use the network')


class Response:
    def __init__(self, value=None, content=b''):
        self.value, self.content = value, content
    def raise_for_status(self):
        pass
    def json(self):
        return self.value
    def iter_content(self, size):
        yield self.content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class MeteoFranceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.local = self.root/'local';self.local.mkdir()
        self.stations = [{'station':'01000001','dept':'01','lat':45.,'lon':1.},
                         {'station':'33000001','dept':'33','lat':45.,'lon':1.1}]
        self.first, self.last = date(2026,7,1), date(2026,7,2)
    def tearDown(self):
        self.temp.cleanup()
    def files(self, humidity=True, folder=None):
        folder = folder or self.local
        for dept, station in [('01','01000001'),('33','33000001')]:
            rows = [{'NUM_POSTE':station,'AAAAMMJJ':key,'TX':25+i,'FFM':2+i,'RR':i}
                    for i,key in enumerate([20260701,20260702])]
            pd.DataFrame(rows).to_csv(folder/f'Q_{dept}_latest-2025-2026_RR-T-Vent.csv.gz',sep=';',index=False)
            if humidity:
                pd.DataFrame([{'NUM_POSTE':station,'AAAAMMJJ':key,'UN':30+i} for i,key in enumerate([20260701,20260702])]).to_csv(
                    folder/f'Q_{dept}_latest-2025-2026_autres-parametres.csv.gz',sep=';',index=False)
    def provider(self, session=None):
        return MeteoFrance(self.stations, self.root/'cache', self.local, session=session or NeverNetwork(),
                           clock=lambda:datetime(2026,7,10,tzinfo=timezone.utc))

    def test_local_observations_exact_dates_station_order_units_no_network(self):
        self.files()
        result = self.provider().fetch(self.first,self.last)
        np.testing.assert_allclose(result['weather'], [[[25,25],[30,30],[7.2,7.2],[0,0]],[[26,26],[31,31],[10.8,10.8],[1,1]]])
        self.assertFalse(result['imputed'].any())
        self.assertFalse((self.root/'cache').exists())

    def test_missing_station_value_uses_actual_neighbor_and_is_recorded(self):
        self.files()
        path = self.local/'Q_01_latest-2025-2026_autres-parametres.csv.gz'
        data = pd.read_csv(path,sep=';');data.loc[0,'UN']=np.nan;data.to_csv(path,sep=';',index=False)
        result = self.provider().fetch(self.first,self.last)
        self.assertEqual(result['weather'][0,1,0],30)
        self.assertEqual(result['imputed'].sum(),1)
        self.assertTrue(result['imputed'][0,1,0])

    def test_refresh_only_missing_period_and_reuses_catalog_and_download_versions(self):
        self.files(humidity=False)
        content = gzip.compress(b'NUM_POSTE;AAAAMMJJ;UN\n01000001;20260701;40\n01000001;20260702;41\n')
        resources = [{'url':'https://example.test/Q_01_latest-2025-2026_autres-parametres.csv.gz','last_modified':'2026-07-09'},
                     {'url':'https://example.test/Q_01_previous-1950-2024_autres-parametres.csv.gz'},
                     {'url':'https://example.test/Q_99_latest-2025-2026_autres-parametres.csv.gz'}]
        class Session:
            def __init__(self):self.urls=[]
            def get(self,url,**kwargs):
                self.urls.append(url)
                return Response({'resources':resources}) if url==CATALOG else Response(content=content)
        session=Session();provider=self.provider(session)
        result=provider.fetch(self.first,self.last)
        self.assertEqual(session.urls,[CATALOG,resources[0]['url']])
        np.testing.assert_equal(result['weather'][:,1,:],[[40,40],[41,41]])
        provider.fetch(self.first,self.last)
        provider.refresh(self.first,self.last,{'01','33'})
        self.assertEqual(len(session.urls),2)

    def test_incomplete_country_day_raises_without_any_modeled_fallback(self):
        self.files()
        provider=self.provider()
        with patch.object(provider,'refresh'):
            with self.assertRaisesRegex(ValueError,'Aucun repli Open-Meteo'):
                provider.fetch(date(2026,7,1),date(2026,7,3))

    def test_corrupt_download_does_not_replace_an_existing_file(self):
        provider=self.provider();provider.cache.mkdir()
        name='Q_01_latest-2025-2026_autres-parametres.csv.gz'
        target=provider.cache/name;target.write_bytes(b'previous-valid-version')
        class Session:
            def get(self,*args,**kwargs):return Response(content=b'not-gzip')
        provider.session=Session()
        with patch.object(provider,'catalog',return_value=[{'url':'https://example.test/'+name}]):
            with self.assertRaises(gzip.BadGzipFile):provider.refresh(self.first,self.last,{'01'})
        self.assertEqual(target.read_bytes(),b'previous-valid-version')
        self.assertFalse(target.with_suffix('.part').exists())

    def test_old_database_migration_preserves_archives_and_marks_previous_source(self):
        import sqlite3
        path=self.root/'old.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE days(date TEXT PRIMARY KEY,issued_at TEXT NOT NULL,consolidated INTEGER NOT NULL DEFAULT 0,data BLOB NOT NULL)')
            db.execute('INSERT INTO days VALUES (?,?,1,?)',('2026-07-01','2026-07-03T12:00:00+00:00',pack(state=np.zeros((3,2)))))
        store=Store(path);row=store.days()[0]
        self.assertEqual(row['date'],'2026-07-01');self.assertEqual(row['provider'],'openmeteo');self.assertEqual(row['imputed'],0)


if __name__=='__main__':
    unittest.main()
