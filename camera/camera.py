"""Agent caméra (équivalent simplifié de pyro-engine) :
capture une image toutes les INTERVAL secondes -> détection -> envoi à l'API.
"""

import io
import json
import logging
import os
import time

import requests

from detectors import make_detector
from sources import make_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("camera")

API_URL = os.getenv("API_URL", "http://localhost:8000")
CAMERA_ID = os.getenv("CAMERA_ID", "cam-1")
CAMERA = {
    "name": os.getenv("CAMERA_NAME", CAMERA_ID),
    "lat": float(os.getenv("CAMERA_LAT", "44.73")),
    "lon": float(os.getenv("CAMERA_LON", "4.60")),
    "azimuth": float(os.getenv("CAMERA_AZIMUTH", "0")),
}
SOURCE = os.getenv("SOURCE", "synthetic")
INTERVAL = float(os.getenv("INTERVAL", "5"))
DETECTOR = os.getenv("DETECTOR", "dummy")
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "hf://pyronear/yolo11s_sensitive-detector/best.pt")
YOLO_CONF = float(os.getenv("YOLO_CONF", "0.15"))
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", "1024"))
FRAME_STEP = int(os.getenv("FRAME_STEP", "25"))


def register() -> None:
    while True:
        try:
            requests.put(f"{API_URL}/cameras/{CAMERA_ID}", json=CAMERA, timeout=5).raise_for_status()
            log.info("Caméra %s enregistrée auprès de %s", CAMERA_ID, API_URL)
            return
        except requests.RequestException as e:
            log.warning("API injoignable (%s), nouvel essai dans 3 s", e)
            time.sleep(3)


def main() -> None:
    register()
    source = make_source(SOURCE, CAMERA["name"], FRAME_STEP)
    detector = make_detector(DETECTOR, YOLO_WEIGHTS, YOLO_CONF, YOLO_IMGSZ)
    log.info("Source=%s  Détecteur=%s", type(source).__name__, type(detector).__name__)

    while True:
        start = time.time()
        try:
            img = source.read()
            dets = detector.predict(img)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            r = requests.post(
                f"{API_URL}/cameras/{CAMERA_ID}/frames",
                files={"image": ("frame.jpg", buf.getvalue(), "image/jpeg")},
                data={"detections": json.dumps(dets)},
                timeout=15,
            )
            r.raise_for_status()
            res = r.json()
            if res.get("alert_id"):
                log.warning("🔥 ALERTE %s créée", res["alert_id"])
            elif dets:
                log.info("%d détection(s), conf max %.2f", len(dets), max(d["confidence"] for d in dets))
        except Exception as e:  # une caméra ne doit jamais s'arrêter pour une erreur ponctuelle
            log.error("Erreur : %s", e)
            if isinstance(e, requests.HTTPError) and e.response.status_code == 404:
                register()
        time.sleep(max(0.0, INTERVAL - (time.time() - start)))


if __name__ == "__main__":
    main()
