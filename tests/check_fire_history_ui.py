"""Server smoke test; client filter correctness is checked against Python separately."""
import sys
sys.path.insert(0, '/app')
from streamlit.testing.v1 import AppTest
app = AppTest.from_file('/app/app.py', default_timeout=60)
app.session_state['app_mode'] = 'Historique des incendies'
app.run()
assert not app.exception and not app.error, (app.exception, app.error)
assert not app.slider and not app.select_slider and not app.selectbox
assert len(app.get('iframe')) == 1
html = app.get('iframe')[0].proto.srcdoc
assert 'const records=' in html and 'id="year"' in html
assert 'setComponentValue' not in html
print('Persistent history map with local year/month/season/cause controls: OK')
