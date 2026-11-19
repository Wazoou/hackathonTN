"""Verify alert review and navigation without model/network calls."""
import sys
from unittest.mock import patch
from PIL import Image
from streamlit.testing.v1 import AppTest
sys.path.insert(0, "/app")

camera = dict(id="demo-fire", name="Mimizan · Démonstration", lat=44.201, lon=-1.231,
              is_demo=True, detector="yolo", last_seen="2026-11-19T14:00:00+00:00",
              last_detections=[], online=True, last_error=None)
alert = dict(id=999, camera_id="demo-fire", camera_name=camera["name"], is_demo=True,
             detector="yolo", status="open", confidence=0.87, bbox=[0.1, 0.2, 0.5, 0.8],
             lat=camera["lat"], lon=camera["lon"], created_at=camera["last_seen"], source_url=None)
def api(method, path, **kwargs):
    if path == "/cameras":
        return [camera]
    if path.startswith("/alerts?"):
        return [alert]
    if method == "PATCH":
        alert["status"] = kwargs["json"]["status"]
    return dict(active=True, generation="test")


with patch("alerts.api", side_effect=api), patch("surveillance.api", side_effect=api), \
     patch("alerts.frame_image", return_value=Image.new("RGB", (100, 60))), \
     patch("surveillance.frame_image", return_value=Image.new("RGB", (100, 60))):
    app = AppTest.from_file("/app/app.py", default_timeout=120).run()
    app.button(key="mode_alerts").click().run()
    assert not app.exception, app.exception
    assert not app.selectbox
    app.button(key="alert_status_1").click().run()
    assert not app.exception, app.exception
    assert any("Mimizan" in s.value for s in app.subheader)
    app.button(key="confirmed_999").click().run()
    assert not app.exception, app.exception
    assert alert["status"] == "confirmed"
    app.button(key="alert_status_2").click().run()
    assert not app.exception, app.exception
    app.button(key="camera_alert_999").click().run()
    assert not app.exception, app.exception
    assert app.session_state["selected_webcam_url"] == "demo://mimizan"
    assert any("Mimizan" in h.value for h in app.subheader)
print("Onglet Alertes : filtre d’état, image, qualification et navigation vers la webcam OK")
