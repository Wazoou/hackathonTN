"""Vérifier la carte de risque dans le conteneur :
docker compose exec -T dashboard python - < tests/check_risk_ui.py"""
import json
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

files = sorted(Path(os.getenv("RISK_DIR", "/risk")).glob("risque_statique_*.geojson"))
assert files, "aucun risque_statique_*.geojson : lancer ml/build_static_risk.py"
cells = json.loads(files[0].read_text())["features"]
props = cells[0]["properties"]
assert {"id", "s_combustible", "s_humain"} <= props.keys()
assert all(0 <= c["properties"][k] <= 100 for c in cells for k in ("s_combustible", "s_humain"))

app = AppTest.from_file("/app/app.py", default_timeout=60).run()
app.sidebar.radio[0].set_value("Carte de risque").run()
assert not app.exception, app.exception
for layer in ("s_combustible", "s_humain", "score"):
    next(r for r in app.radio if r.label == "Couche affichée").set_value(layer).run()
    assert not app.exception, app.exception
next(r for r in app.radio if r.label == "Combinaison").set_value("additif").run()
assert not app.exception, app.exception
print(f"Carte de risque : {len(cells)} carreaux ({files[0].name}), trois couches et deux modes affichés")
