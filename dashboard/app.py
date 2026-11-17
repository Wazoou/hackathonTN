"""Dashboard Pyro-Watch : carte des caméras, flux en direct, alertes à qualifier."""

import io
import os

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from PIL import Image, ImageDraw
from interface import apply_theme, header

API_URL = os.getenv("API_URL", "http://localhost:8000")
REFRESH_S = int(os.getenv("REFRESH_S", "5"))

st.set_page_config(page_title="Pyro-Watch", page_icon="🔥", layout="wide", initial_sidebar_state="collapsed")


def api(path: str, **kw):
    r = requests.get(f"{API_URL}{path}", timeout=10, **kw)
    r.raise_for_status()
    return r


def draw_boxes(img_bytes: bytes, boxes: list[dict]) -> Image.Image:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)
    for b in boxes:
        x1, y1, x2, y2 = b["bbox"]
        d.rectangle([x1 * w, y1 * h, x2 * w, y2 * h], outline="red", width=max(2, w // 300))
        d.text((x1 * w + 4, max(0, y1 * h - 14)), f"fumée {b['confidence']:.0%}", fill="red")
    return img


@st.fragment(run_every=REFRESH_S)
def live() -> None:
    try:
        cameras = api("/cameras").json()
        open_alerts = api("/alerts", params={"status": "open"}).json()
    except requests.RequestException as e:
        st.error(f"API injoignable ({API_URL}) : {e}")
        return

    alert_cams = {a["camera_id"] for a in open_alerts}
    c1, c2, c3 = st.columns(3)
    c1.metric("Caméras en ligne", f"{sum(c['online'] for c in cameras)} / {len(cameras)}")
    c2.metric("Alertes ouvertes", len(open_alerts))
    c3.metric("Caméras avec détection", sum(bool(c["last_detections"]) for c in cameras))

    if cameras:
        df = pd.DataFrame(cameras)
        df["color"] = df.apply(
            lambda c: [220, 38, 38] if c["id"] in alert_cams
            else ([34, 160, 70] if c["online"] else [150, 150, 150]),
            axis=1,
        )
        st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color="color",
                              get_radius=1500, radius_min_pixels=8, pickable=True),
                ],
                initial_view_state=pdk.ViewState(latitude=df.lat.mean(), longitude=df.lon.mean(), zoom=6.5),
                tooltip={"text": "{name}"},
            ),
            height=350,
        )

    st.subheader("📹 Flux caméras")
    cols = st.columns(3)
    for i, cam in enumerate(cameras):
        with cols[i % 3]:
            status = "🔴 ALERTE" if cam["id"] in alert_cams else ("🟢 en ligne" if cam["online"] else "⚫ hors ligne")
            st.markdown(f"**{cam['name']}** — {status}")
            try:
                img = draw_boxes(api(f"/cameras/{cam['id']}/latest.jpg").content, cam["last_detections"])
                st.image(img, use_container_width=True)
            except requests.RequestException:
                st.caption("Pas encore d'image")

    st.subheader("🚨 Alertes à qualifier")
    if not open_alerts:
        st.success("Aucune alerte ouverte")
    names = {c["id"]: c["name"] for c in cameras}
    for a in open_alerts:
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                try:
                    st.image(draw_boxes(api(f"/alerts/{a['id']}/image").content, [a]), use_container_width=True)
                except requests.RequestException:
                    st.caption("Image indisponible")
            with right:
                st.markdown(f"### Alerte #{a['id']}")
                st.write(f"Caméra : **{names.get(a['camera_id'], a['camera_id'])}**")
                st.write(f"Confiance : **{a['confidence']:.0%}**")
                st.write(f"Heure : {a['created_at'][:19].replace('T', ' ')} UTC")
                if st.button("✅ Feu confirmé", key=f"ok{a['id']}"):
                    requests.patch(f"{API_URL}/alerts/{a['id']}", json={"status": "confirmed"}, timeout=10)
                    st.rerun()
                if st.button("❌ Faux positif", key=f"fp{a['id']}"):
                    requests.patch(f"{API_URL}/alerts/{a['id']}", json={"status": "false_positive"}, timeout=10)
                    st.rerun()


apply_theme()
header()
with st.sidebar:
    st.caption("Espace de travail")
    mode = st.radio("Mode", ["Carte des archives", "Carte de risque", "Surveillance simulée"],
                    index=1 if st.query_params.get("view") == "risk" else 0)
if mode == "Carte des archives":
    from archives import archives
    archives()
elif mode == "Carte de risque":
    from risk_map import risk_map
    risk_map()
else:
    st.caption("Démonstration : images synthétiques et détections simulées avec la configuration par défaut.")
    live()
