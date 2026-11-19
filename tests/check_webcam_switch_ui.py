"""Real Pydeck selection events while starting a demo and changing cameras.

The chart is deliberately NOT mocked: its widget identity caused the regression.
Run in the dashboard container, with tests mounted.
"""
import json
import sys
from unittest.mock import patch

from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest

sys.path.insert(0, "/app")
from surveillance import DEMO_CAMERA, DEMO_URL, camera_id
from webcam_directory import WEBCAM_LAYER_ID, load_camera_directory
from webcams import CAMERAS_PATH

cameras = load_camera_directory(CAMERAS_PATH)
state = {"active": False, "generation": "test"}
operations = []


def api(method, path, **kwargs):
    operations.append((method, path))
    if method == "POST":
        state["active"] = path.endswith("start")
    return state


def select(app, camera):
    event = WidgetStates()
    widget = event.widgets.add()
    widget.id = app.get("deck_gl_json_chart")[0].proto.id
    widget.string_value = json.dumps({"selection": {"objects": {WEBCAM_LAYER_ID: [camera]}}})
    app._run(event)
    assert not app.exception, app.exception
    assert app.session_state["selected_webcam_url"] == camera["url_youtube"]


with patch("webcams.monitoring_status", return_value={}) as statuses, \
     patch("surveillance.api", side_effect=api), \
     patch("webcams.analysis_preview") as preview, \
     patch("webcams._display_webcam_snapshot") as snapshot:
    app = AppTest.from_string("from webcams import live_webcams\nlive_webcams()", default_timeout=30).run()
    assert not app.exception, app.exception
    chart_id = app.get("deck_gl_json_chart")[0].proto.id
    select(app, DEMO_CAMERA)
    app.button(key="map_demo_start").click().run()
    assert not app.exception, app.exception
    assert state["active"]
    # New model results arriving during the demo must not replace the chart.
    statuses.return_value = {camera_id(cameras[0]["url_youtube"]): {
        "online": True, "last_seen": "2026-11-19T15:00:00+00:00",
        "last_detections": [{"confidence": 0.8}], "last_error": None}}
    for camera in [cameras[0], cameras[-1], cameras[10]]:
        select(app, camera)
        assert app.get("deck_gl_json_chart")[0].proto.id == chart_id
        snapshot.assert_called_with(camera["url_youtube"])
        preview.assert_called_with(camera_id(camera["url_youtube"]))
        assert not any(b.key == "map_demo_start" for b in app.button)
    assert statuses.call_count == 1
    # A link from Alertes must win over an older map selection.
    select(app, DEMO_CAMERA)
    app.session_state["selected_webcam_url"] = cameras[0]["url_youtube"]
    app.run()
    assert app.session_state["selected_webcam_url"] == cameras[0]["url_youtube"]
    snapshot.assert_called_with(cameras[0]["url_youtube"])
    # Explicit metadata refresh preserves the selected camera.
    app.button(key="refresh_webcam_states").click().run()
    assert not app.exception, app.exception
    assert app.session_state["selected_webcam_url"] == cameras[0]["url_youtube"]
    assert statuses.call_count == 2
    select(app, DEMO_CAMERA)
    app.button(key="map_demo_stop").click().run()
    assert not state["active"] and not app.exception, app.exception
    assert ("POST", "/demo/start") in operations
    assert ("POST", "/demo/stop") in operations
print("Carte réelle : démo → 3 webcams → démo, sélection stable, lien externe et actualisation OK")
