"""One shared YOLO model for the public catalogue and the explicit demo camera.

Downloads are bounded and concurrent; inference is serial, with demo priority.
Nothing runs in the Streamlit request/render loop.
"""
import csv
import hashlib
import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

from detectors import make_detector
from sources import HttpSnapshotSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("monitor")
API = os.getenv("API_URL", "http://api:8000")
INTERVAL = max(30, float(os.getenv("WEBCAM_INTERVAL", "120")))
DEMO_INTERVAL = max(0.5, float(os.getenv("DEMO_INTERVAL", "0.5")))
DEMO_ID = "demo-fire"


def camera_id(url):
    return "public-" + hashlib.sha256(url.encode()).hexdigest()[:16]


def catalogue(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [dict(id=camera_id(r["url_youtube"]), name=r["ville"],
                     lat=float(r["lat"]), lon=float(r["lon"]), source_url=r["url_youtube"],
                     is_demo=False, detector="yolo", interval_s=INTERVAL)
                for r in csv.DictReader(f, delimiter=";")]


def request(method, path, **kwargs):
    response = requests.request(method, API + path, timeout=(3, 15), **kwargs)
    response.raise_for_status()
    return response.json()


def send_frame(cam_id, image, detections, generation=None):
    import json
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    data = {"detections": json.dumps(detections)}
    if generation:
        data["generation"] = generation
    return request("POST", f"/cameras/{cam_id}/frames",
                   files={"image": ("frame.jpg", buf.getvalue(), "image/jpeg")}, data=data)


def report_failure(cam_id, error):
    log.warning("%s: %s", cam_id, error)
    try:
        request("POST", f"/cameras/{cam_id}/failure", json={"error": str(error)})
    except requests.RequestException:
        log.exception("Impossible de signaler l’échec")


class DemoVideo:
    """Sample the looping video by elapsed time, independent of inference speed."""
    def __init__(self, path):
        import cv2
        self.cv2 = cv2
        self.capture = cv2.VideoCapture(str(path))
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.duration = self.capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps else 0
        if not self.capture.isOpened() or self.duration <= 0:
            raise ValueError(f"Vidéo de démonstration illisible : {path}")
        self.started = time.monotonic()

    def read(self):
        seconds = (time.monotonic() - self.started) % self.duration
        self.capture.set(self.cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = self.capture.read()
        if not ok:
            raise RuntimeError("Impossible de lire la vidéo de démonstration")
        return Image.fromarray(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB))

    def close(self):
        self.capture.release()


def main():
    import torch
    torch.set_num_threads(max(1, int(os.getenv("YOLO_THREADS", "2"))))
    detector = make_detector("yolo", os.getenv("YOLO_WEIGHTS", "hf://pyronear/yolo11s_sensitive-detector/best.pt"),
                             float(os.getenv("YOLO_CONF", "0.2")), int(os.getenv("YOLO_IMGSZ", "1024")))
    cameras = catalogue(os.getenv("CAMERAS_PATH", "/camera-directory/cameras.csv"))
    demo = dict(id=DEMO_ID, name="Mimizan · Démonstration", lat=44.201, lon=-1.231,
                is_demo=True, detector="yolo", interval_s=DEMO_INTERVAL)
    while True:
        try:
            for camera in [*cameras, demo]:
                request("PUT", f"/cameras/{camera['id']}", json=camera)
            break
        except requests.RequestException:
            log.exception("API indisponible, nouvelle tentative dans 5 s")
            time.sleep(5)
    log.info("YOLO prêt : %d webcams publiques et une caméra de démonstration", len(cameras))
    due = {c["id"]: 0 for c in cameras}
    pending = {}
    generation, video = None, None
    next_demo, next_poll = 0, 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        while True:
            current = time.monotonic()
            if current >= next_poll:
                try:
                    state = request("GET", "/demo")
                    if state["generation"] != generation:
                        if video:
                            video.close()
                        video = None
                        generation = state["generation"]
                        if state["active"]:
                            video = DemoVideo(os.getenv("DEMO_VIDEO", "/demo/depart-feu.mp4"))
                            next_demo = 0
                    if not state["active"] and video:
                        video.close()
                        video = None
                except Exception as error:
                    report_failure(DEMO_ID, error)
                next_poll = time.monotonic() + 0.5
            if video and time.monotonic() >= next_demo:
                next_demo = time.monotonic() + DEMO_INTERVAL
                try:
                    image = video.read()
                    result = send_frame(DEMO_ID, image, detector.predict(image), generation)
                    if result.get("alert_id"):
                        log.info("Alerte réelle YOLO de démonstration : %s", result["alert_id"])
                except Exception as error:
                    if isinstance(error, requests.HTTPError) and error.response.status_code == 409:
                        log.info("Ancienne image de démonstration écartée après une commande")
                    else:
                        report_failure(DEMO_ID, error)
            # Only one public inference per iteration, so the demo stays responsive.
            ready = next((future for future in pending if future.done()), None)
            if ready:
                camera = pending.pop(ready)
                try:
                    image = ready.result()
                    result = send_frame(camera["id"], image, detector.predict(image))
                    if result.get("alert_id"):
                        log.info("Alerte YOLO %s : %s", camera["name"], result["alert_id"])
                except Exception as error:
                    report_failure(camera["id"], error)
            in_flight = {c["id"] for c in pending.values()}
            for camera in sorted(cameras, key=lambda c: due[c["id"]]):
                if len(pending) >= 4:
                    break
                if due[camera["id"]] <= time.monotonic() and camera["id"] not in in_flight:
                    pending[pool.submit(HttpSnapshotSource(camera["source_url"]).read)] = camera
                    due[camera["id"]] = time.monotonic() + INTERVAL
            time.sleep(0.05)


if __name__ == "__main__":
    main()
