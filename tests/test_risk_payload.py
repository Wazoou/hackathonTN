import base64
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from risk_payload import file_signature, build_payload
from risk_data import combine, color, to_scale

class RiskPayloadTests(unittest.TestCase):
    def test_lossless_geometry_properties_and_all_score_variants(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            features=[]
            for i, (c,h) in enumerate([(0,100),(100,0),(80.3,41.7),(50.5,61.3)]):
                features.append({'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[1.123456789,2],[3,2],[3,4],[1.123456789,2]]]},
                    'properties':{'id':str(i),'dept':'01','commune':'<script>test</script>',
                                  's_combustible':c,'s_humain':h,'p_feu':7.23+i,'pente_moy_deg':None}})
            path=folder/'risque_statique_01.geojson'
            path.write_text(json.dumps({'type':'FeatureCollection','features':features}))
            sig=file_signature(folder); packed=build_payload(sig)
            data=json.loads(gzip.decompress(base64.b64decode(packed['payload'])))
            self.assertEqual(data['features'],features)
            for i,f in enumerate(features):
                c,h=f['properties']['s_combustible'],f['properties']['s_humain']
                self.assertEqual(data['scores']['multiplicatif'][i]/10,combine(c,h))
                for step in range(21):
                    self.assertEqual(data['scores'][f'additif:{step}'][i]/10,combine(c,h,'additif',step/20))
                self.assertEqual(data['probability_colors'][i],color(to_scale(f['properties']['p_feu'],'p_feu'),255))
            self.assertIn('p_feu',data['layers'])
            features[0]['properties'].pop('p_feu')
            path.write_text(json.dumps({'type':'FeatureCollection','features':features}))
            updated=file_signature(folder)
            self.assertNotEqual(updated,sig)
            data=json.loads(gzip.decompress(base64.b64decode(build_payload(updated)['payload'])))
            self.assertNotIn('p_feu',data['layers'])
            self.assertEqual(data['probability_colors'],[])
            # Metadata changes invalidate the payload too.
            before=file_signature(folder)
            path.with_suffix('.json').write_text('{"indicateurs_exclus":["tmja_max"]}')
            self.assertNotEqual(file_signature(folder),before)

    def test_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            f={'properties':{'id':'same','dept':'01','s_combustible':0,'s_humain':0}}
            Path(folder,'risque_statique_01.geojson').write_text(json.dumps({'features':[f,f]}))
            with self.assertRaisesRegex(ValueError,'dupliquées'):
                build_payload(file_signature(folder))

if __name__=='__main__':unittest.main()
