"""Shared monitoring UI and stable identifiers for webcam selection."""
import hashlib
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from PIL import Image, ImageDraw

API_URL = os.getenv("API_URL", "http://api:8000")
DEMO_ID = "demo-fire"
DEMO_URL = "demo://mimizan"
DEMO_CAMERA = dict(nom="Mimizan · Démonstration", url_youtube=DEMO_URL,
                   lat=44.201, lon=-1.231, id_maille="Démonstration · position illustrative")


def camera_id(url):
    return DEMO_ID if url == DEMO_URL else "public-" + hashlib.sha256(url.encode()).hexdigest()[:16]


def api(method, path, **kwargs):
    response = requests.request(method, API_URL + path, timeout=(2, 8), **kwargs)
    response.raise_for_status()
    return response.json()


def date_label(value):
    if not value:
        return "En attente"
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m à %H:%M:%S")


@st.cache_data(ttl=5, show_spinner=False)
def monitoring_status():
    try:
        return {c["id"]: c for c in api("GET", "/cameras") if c.get("detector") == "yolo"}
    except (requests.RequestException, ValueError):
        return {}


def map_status(camera):
    if not camera:
        return "En attente d’analyse YOLO", [125, 140, 155, 190]
    if camera.get("last_error"):
        return "Dernière collecte en échec", [125, 140, 155, 190]
    if not camera.get("last_seen"):
        return "En attente d’analyse YOLO", [125, 140, 155, 190]
    if not camera.get("online"):
        return f"Analyse ancienne · {date_label(camera['last_seen'])}", [125, 140, 155, 190]
    detection = any(d["confidence"] >= 0.35 for d in camera["last_detections"])
    label = "Suspicion de fumée" if detection else "Dernière analyse sans détection au seuil d’alerte"
    return f"{label} · {date_label(camera['last_seen'])}", ([220, 65, 40, 230] if detection else [0, 122, 204, 190])


def annotated_image(content, detections):
    image = Image.open(io.BytesIO(content)).convert("RGB")
    draw = ImageDraw.Draw(image)
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        box = (int(x1 * image.width), int(y1 * image.height),
               int(x2 * image.width), int(y2 * image.height))
        draw.rectangle(box, outline="#ef562f", width=max(2, image.width // 300))
        label = f"Fumee {detection['confidence']:.0%}"
        left, top = box[:2]
        draw.rectangle((left, max(0, top - 19), left + 110, max(19, top)), fill="#9a3412")
        draw.text((left + 3, max(0, top - 17)), label, fill="white")
    return image


def frame_image(path, detections):
    response = requests.get(API_URL + path, timeout=(2, 8))
    response.raise_for_status()
    return annotated_image(response.content, detections)


def demo_controls(key):
    st.caption("DÉMONSTRATION · Vidéo locale en boucle, position illustrative à Mimizan. Détection réelle par YOLO.")
    try:
        state = api("GET", "/demo")
    except requests.RequestException:
        st.info("Les commandes de démonstration seront disponibles lorsque le service d’analyse sera joignable.")
        return
    cols = st.columns(3)
    if cols[0].button("Relancer la démo" if state["active"] else "Lancer la démo",
                      key=key + "_start", type="primary", use_container_width=True):
        try:
            api("POST", "/demo/start")
            st.rerun()
        except requests.RequestException:
            st.error("Impossible de démarrer la démonstration.")
    if cols[1].button("Arrêter", key=key + "_stop", disabled=not state["active"], use_container_width=True):
        try:
            api("POST", "/demo/stop")
            st.rerun()
        except requests.RequestException:
            st.error("Impossible d’arrêter la démonstration.")
    if cols[2].button("Réinitialiser", key=key + "_reset", use_container_width=True,
                      help="Arrête la vidéo et efface uniquement les alertes de démonstration."):
        try:
            api("POST", "/demo/reset")
            st.rerun()
        except requests.RequestException:
            st.error("Impossible de réinitialiser la démonstration.")


@st.fragment(run_every="2s")
def analysis_preview(cam_id):
    try:
        camera = next((c for c in api("GET", "/cameras") if c["id"] == cam_id), None)
        if not camera:
            st.info("Cette caméra est en attente de prise en charge par le moteur YOLO.")
            return
        if camera.get("last_error"):
            st.warning("Dernière tentative d’analyse en échec : " + camera["last_error"])
        if not camera.get("last_seen"):
            st.info("En attente de la première image analysée." if cam_id != DEMO_ID else
                    "Lancez la démonstration pour analyser la vidéo.")
            return
        st.image(frame_image(f"/cameras/{cam_id}/latest.jpg", camera["last_detections"]),
                 use_container_width=True)
        st.caption(f"Dernière analyse YOLO : {date_label(camera['last_seen'])}. "
                   "Les cadres signalent des suspicions de fumée à vérifier.")
    except (requests.RequestException, OSError, ValueError):
        st.info("Le dernier résultat d’analyse n’est pas encore disponible.")
