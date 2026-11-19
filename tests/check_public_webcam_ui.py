"""Exercise the merged webcam navigation without fetching a live camera image.

Run in the dashboard container with the complete CSV mounted.
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from streamlit.proto.WidgetStates_pb2 import WidgetStates

sys.path.insert(0, "/app")
from webcam_directory import WEBCAM_LAYER_ID, load_camera_directory
from webcams import CAMERAS_PATH

cameras = load_camera_directory(CAMERAS_PATH)
assert CAMERAS_PATH.suffix == ".csv" and len(cameras) == 105
camera = cameras[0]
selection = {"selection": {"objects": {WEBCAM_LAYER_ID: [camera]}}}
with patch("webcams._display_webcam_snapshot") as snapshot, \
     patch("webcams.analysis_preview"):
    app = AppTest.from_file("/app/app.py", default_timeout=120).run()
    app.button(key="mode_archives").click().run()
    assert not app.exception and not app.error, app.exception
    assert not app.radio, "L’onglet Webcams doit ouvrir directement la carte"
    event = WidgetStates()
    widget = event.widgets.add()
    widget.id = app.get("deck_gl_json_chart")[0].proto.id
    widget.string_value = json.dumps(selection)
    app._run(event)
    assert not app.exception, app.exception
    assert app.session_state["selected_webcam_url"] == camera["url_youtube"]
    snapshot.assert_called_with(camera["url_youtube"])
    spec = json.loads(app.get("deck_gl_json_chart")[0].proto.json)
    assert spec["mapStyle"] == "app/static/openstreetmap.json"
    style = json.loads(Path("/app/static/openstreetmap.json").read_text())
    assert style["sources"]["openstreetmap"]["tiles"] == [
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    ]
    assert len(spec["layers"][0]["data"]) == 106
    app.button(key="mode_fire_history").click().run()
    assert not app.exception, app.exception
    app.button(key="mode_archives").click().run()
    assert app.session_state["selected_webcam_url"] == camera["url_youtube"]
    assert not app.exception, app.exception
print("Catalogue CSV autonome, 105 vues publiques et une démo, fond OSM, sélection et navigation conservées : OK")
