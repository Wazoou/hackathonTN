"""Carte de risque statique par carreau DFCI 2 km (combustible × pression humaine)."""
import json
import os
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from risk_data import LAYERS, apply_scores, class_ranges

RISK_DIR = Path(os.getenv("RISK_DIR", "risk-data"))
DEPT_NAMES = {"06": "Alpes-Maritimes", "07": "Ardèche", "13": "Bouches-du-Rhône", "33": "Gironde",
              "34": "Hérault", "40": "Landes", "83": "Var"}
MODES = {"multiplicatif": "Combustible modulé par la pression humaine",
         "additif": "Moyenne pondérée des deux piliers"}


@st.cache_data
def load_geojson(path, mtime):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def legend(layer):
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px">'
        f'<span style="width:14px;height:14px;border-radius:3px;background:rgb{rgb}"></span>'
        f'{name} ({low}–{high})</span>' if high else
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px">'
        f'<span style="width:14px;height:14px;border-radius:3px;background:rgb{rgb}"></span>'
        f'{name} (≥ {low})</span>' for name, low, high, rgb in class_ranges(layer))
    st.markdown(f'<div style="font-size:12px;color:#253747;margin:4px 0 8px">{items}</div>',
                unsafe_allow_html=True)


def risk_map():
    files = sorted(RISK_DIR.glob("risque_statique_*.geojson"))
    st.markdown('<p class="eyebrow">Prévention · solution 1</p>', unsafe_allow_html=True)
    st.subheader("Carte de risque de départ de feu")
    if not files:
        st.info(f"Aucune carte de risque dans `{RISK_DIR}`. Générez-la avec "
                "`python ml/build_static_risk.py --features static_features_33.gpkg --out risk-data` "
                "(voir README, section « Carte de risque statique »).")
        return

    depts = {f.stem.removeprefix("risque_statique_"): f for f in files}
    sample = load_geojson(str(files[0]), files[0].stat().st_mtime)["features"][:1]
    layers = [k for k in LAYERS if k != "p_feu" or (sample and "p_feu" in sample[0]["properties"])]
    choices = (["all"] if len(depts) > 1 else []) + list(depts)
    map_col, side = st.columns([3, 1.15], gap="medium")
    with side:
        dept = st.selectbox("Département", choices, format_func=lambda d: "Tous les départements"
                            if d == "all" else f"{DEPT_NAMES.get(d, 'Département')} ({d})")
        layer = st.radio("Couche affichée", layers, format_func=LAYERS.get)
        mode = st.radio("Combinaison", list(MODES), format_func=lambda m: m.capitalize(),
                        help="\n\n".join(f"**{k}** : {v}" for k, v in MODES.items()),
                        disabled=layer != "score")
        poids = st.slider("Poids du combustible", 0.0, 1.0, 0.6, 0.05,
                          disabled=layer != "score" or mode != "additif",
                          help="Seulement en mode additif ; le reste va à la pression humaine.")
        opacite = st.slider("Opacité", 0.2, 1.0, 0.7, 0.05)

    paths = list(depts.values()) if dept == "all" else [depts[dept]]
    merged = {"type": "FeatureCollection", "features": [
        f for p in paths for f in load_geojson(str(p), p.stat().st_mtime)["features"]]}
    data = apply_scores(merged, layer, mode, poids, alpha=round(255 * opacite))
    table = pd.DataFrame([f["properties"] for f in data["features"]])
    proba = layer == "p_feu"
    unit = " %/an" if proba else " / 100"

    with side:
        a, b = st.columns(2)
        a.metric("Carreaux", f"{len(table):,}".replace(",", " "))
        b.metric("Médiane", f"{table['valeur'].median():.1f} %" if proba else f"{table['valeur'].median():.0f}")
        high = table["classe"].isin(["Élevé", "Très élevé"]).mean()
        st.metric("Carreaux en classe élevée ou plus", f"{high:.1%}")

    with map_col:
        layer_obj = pdk.Layer(
            "GeoJsonLayer", data, pickable=True, stroked=True, filled=True,
            get_fill_color="properties.fill", get_line_color=[255, 255, 255, 60], line_width_min_pixels=0.3,
            auto_highlight=True, highlight_color=[33, 110, 85, 200])
        bounds = _bounds(data)
        span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        st.pydeck_chart(pdk.Deck(
            layers=[layer_obj], map_style="light",
            initial_view_state=pdk.ViewState(latitude=(bounds[1] + bounds[3]) / 2,
                                             longitude=(bounds[0] + bounds[2]) / 2,
                                             zoom=8 if span < 2 else 7 if span < 4 else 5.5),
            tooltip={"html": "<b>{commune}</b> ({dept}) · carreau {id}<br/>"
                             f"<b>{LAYERS[layer]}</b> : {{valeur}}{unit} ({{classe}})<br/>"
                             + ("Probabilité annuelle : {p_feu} %<br/>" if "p_feu" in layers and not proba else "")
                             + "Score : {score} · combustible {s_combustible} · humain {s_humain}<br/>"
                             "Forêt {foret_frac_pct} · résineux {resineux_frac_pct} · WUI {wui_frac_pct}",
                     "style": {"fontSize": "12px"}}),
            height=620)
        legend(layer)
        if proba:
            st.caption("**Probabilité qu'au moins un feu de forêt démarre dans l'année** dans ce carreau de 2 km, "
                       "d'après une régression logistique sur les feux BDIFF 2006-2024 (communes des départements "
                       "affichés) et les indicateurs de végétation, relief et pression humaine. Moyenne sur "
                       "plusieurs années : sans météo, elle ne dit rien d'un jour donné.")
        else:
            st.caption("Indice de **sensibilité du terrain**, relatif aux départements calculés ensemble : "
                       "végétation (BD Forêt), relief et pression humaine (habitat proche de la forêt, routes, "
                       "trafic, agriculture). Il n'intègre pas la météo et n'est **pas une probabilité**.")

    with st.expander("Carreaux les plus exposés"):
        cols = ["id", "commune", "dept", "valeur", "score", "s_combustible", "s_humain"]
        top = table.nlargest(15, "valeur")[cols + (["p_feu"] if "p_feu" in table and not proba else [])]
        st.dataframe(top.rename(columns={"id": "Carreau DFCI", "commune": "Commune", "dept": "Dépt",
                                         "valeur": LAYERS[layer],
                                         "score": "Score", "s_combustible": "Combustible",
                                         "s_humain": "Humain", "p_feu": "Proba. %/an"}),
                     hide_index=True, use_container_width=True)
    meta = paths[0].with_suffix(".json")
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
