"""Carte de risque statique par carreau DFCI 2 km (combustible × pression humaine)."""
import json
import os
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from risk_data import CLASSES, LAYERS, apply_scores

RISK_DIR = Path(os.getenv("RISK_DIR", "risk-data"))
MODES = {"multiplicatif": "Combustible modulé par la pression humaine",
         "additif": "Moyenne pondérée des deux piliers"}


@st.cache_data
def load_geojson(path, mtime):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def legend():
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px">'
        f'<span style="width:14px;height:14px;border-radius:3px;background:rgb{rgb}"></span>'
        f'{name} ({low}–{low + 20 if low < 80 else 100})</span>' for low, name, rgb in CLASSES)
    st.markdown(f'<div style="font-size:12px;color:#253747;margin:4px 0 8px">{items}</div>',
                unsafe_allow_html=True)


def risk_map():
    files = sorted(RISK_DIR.glob("risque_statique_*.geojson"))
    st.markdown('<p class="eyebrow">Prévention · solution 1</p>', unsafe_allow_html=True)
    st.subheader("Carte de risque statique")
    if not files:
        st.info(f"Aucune carte de risque dans `{RISK_DIR}`. Générez-la avec "
                "`python ml/build_static_risk.py --features static_features_33.gpkg --out risk-data` "
                "(voir README, section « Carte de risque statique »).")
        return

    depts = {f.stem.removeprefix("risque_statique_"): f for f in files}
    map_col, side = st.columns([3, 1.15], gap="medium")
    with side:
        dept = st.selectbox("Département", list(depts), format_func=lambda d: f"Département {d}")
        layer = st.radio("Couche affichée", list(LAYERS), format_func=LAYERS.get)
        mode = st.radio("Combinaison", list(MODES), format_func=lambda m: m.capitalize(),
                        help="\n\n".join(f"**{k}** : {v}" for k, v in MODES.items()),
                        disabled=layer != "score")
        poids = st.slider("Poids du combustible", 0.0, 1.0, 0.6, 0.05,
                          disabled=layer != "score" or mode != "additif",
                          help="Seulement en mode additif ; le reste va à la pression humaine.")
        opacite = st.slider("Opacité", 0.2, 1.0, 0.7, 0.05)

    path = depts[dept]
    data = apply_scores(load_geojson(str(path), path.stat().st_mtime), layer, mode, poids,
                        alpha=round(255 * opacite))
    table = pd.DataFrame([f["properties"] for f in data["features"]])

    with side:
        a, b = st.columns(2)
        a.metric("Carreaux", f"{len(table):,}".replace(",", " "))
        b.metric("Valeur médiane", f"{table['valeur'].median():.0f}")
        st.metric("Carreaux ≥ 60 (élevé)", f"{(table['valeur'] >= 60).mean():.1%}")

    with map_col:
        layer_obj = pdk.Layer(
            "GeoJsonLayer", data, pickable=True, stroked=True, filled=True,
            get_fill_color="properties.fill", get_line_color=[255, 255, 255, 60], line_width_min_pixels=0.3,
            auto_highlight=True, highlight_color=[33, 110, 85, 200])
        bounds = _bounds(data)
        st.pydeck_chart(pdk.Deck(
            layers=[layer_obj], map_style="light",
            initial_view_state=pdk.ViewState(latitude=(bounds[1] + bounds[3]) / 2,
                                             longitude=(bounds[0] + bounds[2]) / 2, zoom=8),
            tooltip={"html": "<b>{commune}</b> · carreau {id}<br/>"
                             f"<b>{LAYERS[layer]}</b> : {{valeur}} / 100 ({{classe}})<br/>"
                             "Score : {score} · combustible {s_combustible} · humain {s_humain}<br/>"
                             "Forêt {foret_frac_pct} · résineux {resineux_frac_pct} · WUI {wui_frac_pct}",
                     "style": {"fontSize": "12px"}}),
            height=620)
        legend()
        st.caption("Indice de **sensibilité du terrain**, relatif au département : végétation (BD Forêt), "
                   "relief et pression humaine (habitat proche de la forêt, routes, trafic, agriculture). "
                   "Il n'intègre pas la météo et n'est **pas une probabilité** de départ de feu.")

    with st.expander("Carreaux les plus exposés"):
        top = table.nlargest(15, "valeur")[["id", "commune", "valeur", "score", "s_combustible", "s_humain"]]
        st.dataframe(top.rename(columns={"id": "Carreau DFCI", "commune": "Commune", "valeur": LAYERS[layer],
                                         "score": "Score", "s_combustible": "Combustible",
                                         "s_humain": "Humain"}),
                     hide_index=True, use_container_width=True)
    meta = path.with_suffix(".json")
    if meta.exists():
        with st.expander("Sources et formules"):
            st.json(json.loads(meta.read_text(encoding="utf-8")), expanded=False)


def _bounds(geojson):
    xs, ys = [], []
    for feature in geojson["features"]:
        geom = feature["geometry"]
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for polygon in polygons:
            for x, y, *_ in polygon[0]:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (-0.6, 44.8, -0.6, 44.8)
