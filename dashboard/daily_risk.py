"""Risque du jour : terrain (p_feu BDIFF) × météo du jour (FWI calculé sur les stations Météo-France)."""
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from daily_data import (DAY_BOUNDS, DAY_COLORS, DAY_LABELS, commune_probabilities, day_class, day_color,
                        fwi_class, weather_term)

RISK_DIR = Path(os.getenv("RISK_DIR", "risk-data"))
METEO_DIR = RISK_DIR / "meteo"
EXAMPLES = {"12/07/2022 · Landiras et La Teste": date(2022, 7, 12),
            "10/08/2022 · canicule": date(2022, 8, 10),
            "15/01/2022 · hiver": date(2022, 1, 15)}
DEPT_NAMES = {"06": "Alpes-Maritimes", "07": "Ardèche", "13": "Bouches-du-Rhône", "33": "Gironde",
              "34": "Hérault", "40": "Landes", "83": "Var"}


def _signature():
    files = sorted(METEO_DIR.glob("*")) if METEO_DIR.exists() else []
    return tuple((str(p), p.stat().st_mtime_ns) for p in files)


@st.cache_resource(show_spinner="Chargement de la météo et du modèle…")
def load(signature):
    meta = json.loads((METEO_DIR / "modele.json").read_text(encoding="utf-8"))
    model = meta["modeles"][meta["modele_retenu"]]
    indices = pd.read_csv(METEO_DIR / "indices.csv.gz", dtype={"station": str}, parse_dates=["date"])
    stations = pd.read_json(METEO_DIR / "stations.json", dtype={"station": str}).set_index("station")
    cells = json.loads((METEO_DIR / "mailles.json").read_text(encoding="utf-8"))
    communes = pd.DataFrame.from_dict(json.loads((METEO_DIR / "communes.json").read_text(encoding="utf-8")),
                                      orient="index", columns=["station", "log_terrain"])
    fires = pd.read_csv(METEO_DIR / "feux_bdiff.csv.gz", dtype={"code_insee": str}, parse_dates=["date"])
    geometry, props = {}, {}
    for dept in meta["departements"]:
        path = RISK_DIR / f"risque_statique_{dept}.geojson"
        for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            if p["id"] in cells:
                geometry[p["id"]] = f["geometry"]
                props[p["id"]] = {"commune": p.get("commune", ""), "dept": dept, "p_feu": p.get("p_feu")}
    # Partie météo du modèle, une fois pour toutes (station × jour).
    indices["z"] = weather_term(model, indices)
    weather = indices.pivot(index="date", columns="station", values="z")
    return meta, model, indices.set_index(["date", "station"]), weather, stations, cells, communes, fires, geometry, props


def expected_series(weather, communes, model, start, end, depts_mask):
    window = weather.loc[start:end]
    z = window[communes["station"]].to_numpy()
    p = commune_probabilities(model, z, communes["log_terrain"].to_numpy())
    return pd.Series((p * depts_mask[None, :]).sum(axis=1), index=window.index)


def legend():
    bounds = DAY_BOUNDS
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px">'
        f'<span style="width:14px;height:14px;border-radius:3px;background:rgb{rgb}"></span>'
        f'{name} ({bounds[i]}–{bounds[i + 1]})</span>' if i < len(DAY_LABELS) - 1 else
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px">'
        f'<span style="width:14px;height:14px;border-radius:3px;background:rgb{rgb}"></span>'
        f'{name} (≥ {bounds[i]})</span>' for i, (name, rgb) in enumerate(zip(DAY_LABELS, DAY_COLORS)))
    st.markdown(f'<div style="font-size:12px;color:#253747;margin:4px 0 8px">Probabilité de départ dans la '
                f'journée, pour 10 000 : {items}<span style="display:inline-flex;align-items:center;gap:6px">'
                f'<span style="width:12px;height:12px;border-radius:50%;border:2px solid #111;background:#fff">'
                f'</span>feu BDIFF déclaré ce jour</span></div>', unsafe_allow_html=True)


def daily_risk():
    st.markdown('<p class="eyebrow">Prévention · terrain × météo du jour</p>', unsafe_allow_html=True)
    st.subheader("Risque du jour")
    if not (METEO_DIR / "modele.json").exists():
        st.info("Aucun modèle météo dans `risk-data/meteo`. Générez-le avec `ml/download_meteo.py` puis "
                "`ml/build_daily_risk.py` (voir README, section « Risque du jour »).")
        return
    meta, model, indices, weather, stations, cells, communes, fires, geometry, props = load(_signature())
    first, last = weather.index.min().date(), weather.index.max().date()

    if "daily_date" not in st.session_state:
        st.session_state["daily_date"] = last
    map_col, side = st.columns([3, 1.15], gap="medium")
    with side:
        chosen = st.date_input("Date", min_value=max(first, date(2006, 1, 1)), max_value=last, key="daily_date",
                               format="DD/MM/YYYY")
        cols = st.columns(2)
        cols[0].button("Dernier jour", use_container_width=True, help=f"{last:%d/%m/%Y}",
                       on_click=st.session_state.update, kwargs={"daily_date": last})
        with cols[1].popover("Exemples", use_container_width=True):
            for label, example in EXAMPLES.items():
                st.button(label, key=f"ex{example}", use_container_width=True,
                          on_click=st.session_state.update, kwargs={"daily_date": example})
        depts = meta["departements"]
        dept = st.selectbox("Département", ["all", *depts], format_func=lambda d: "Tous les départements"
                            if d == "all" else f"{DEPT_NAMES.get(d, 'Département')} ({d})")
        show_fires = st.checkbox("Feux BDIFF de ce jour", value=True,
                                 help=f"Déclarations BDIFF jusqu'au {pd.Timestamp(meta['bdiff']['fin']):%d/%m/%Y}")
        show_stations = st.checkbox("Stations Météo-France", value=False)
        opacity = st.slider("Opacité", 0.2, 1.0, 0.75, 0.05)

    day = pd.Timestamp(chosen)
    day_index = indices.xs(day, level="date")
    z = weather.loc[day, communes["station"]].to_numpy()[None, :]
    p_commune = pd.Series(commune_probabilities(model, z, communes["log_terrain"].to_numpy())[0], index=communes.index)

    features, total = [], 0.0
    for cell_id, (insee, share) in cells.items():
        meta_cell = props.get(cell_id)
        if meta_cell is None or (dept != "all" and meta_cell["dept"] != dept):
            continue
        p = float(p_commune[insee]) * share
        if np.isnan(p):
            continue
        total += p
        station = communes.at[insee, "station"]
        fwi_value = float(day_index["fwi"].get(station, np.nan))
        per = 1e4 * p
        features.append({"type": "Feature", "geometry": geometry[cell_id], "properties": {
            "id": cell_id, "commune": meta_cell["commune"], "dept": meta_cell["dept"],
            "valeur": f"{per:.2f}", "classe": DAY_LABELS[day_class(per)], "fill": day_color(per, round(255 * opacity)),
            "fwi": f"{fwi_value:.1f}", "fwi_classe": fwi_class(fwi_value), "station": stations.at[station, "nom"],
            "p_feu": f"{meta_cell['p_feu']:.2f}"}})
    shown = pd.DataFrame([f["properties"] for f in features])
    shown["v"] = shown["valeur"].astype(float)

    day_fires = fires[fires["date"] == day]
    if dept != "all":
        day_fires = day_fires[day_fires["code_insee"].str[:2] == dept]
    in_dept = communes if dept == "all" else communes[communes.index.str[:2] == dept]
    used = stations.loc[in_dept["station"].unique()]
    fwi_today = day_index.loc[day_index.index.intersection(used.index), "fwi"]

    with side:
        a, b = st.columns(2)
        a.metric("Départs attendus", f"{total:.1f}", help="Somme des probabilités des mailles affichées")
        bdiff_known = day <= pd.Timestamp(meta["bdiff"]["fin"])
        b.metric("Feux BDIFF", f"{len(day_fires)}" if bdiff_known else "—",
                 help="Feux déclarés ce jour" if bdiff_known else "Date postérieure au dernier export BDIFF")
        c, d = st.columns(2)
        c.metric("FWI médian", f"{fwi_today.median():.1f}", help=f"Danger météo : {fwi_class(fwi_today.median())}")
        d.metric("Mailles élevé+", f"{(shown['v'] >= DAY_BOUNDS[3]).mean():.1%}")

    with map_col:
        layers = [pdk.Layer("GeoJsonLayer", {"type": "FeatureCollection", "features": features}, pickable=True,
                            stroked=False, filled=True, get_fill_color="properties.fill", auto_highlight=True,
                            highlight_color=[33, 110, 85, 200])]
        if show_fires and len(day_fires):
            layers.append(pdk.Layer("ScatterplotLayer", day_fires[["lon", "lat"]],
                get_position="[lon, lat]", get_radius=2500, radius_min_pixels=5, stroked=True, filled=True, pickable=False,
                get_fill_color=[255, 255, 255, 200], get_line_color=[17, 17, 17, 255], line_width_min_pixels=2))
        if show_stations:
            layers.append(pdk.Layer("ScatterplotLayer", used.reset_index(), get_position="[lon, lat]", get_radius=1200,
                                    radius_min_pixels=3, get_fill_color=[37, 55, 71, 220], pickable=False))
        lons = [c[0] for f in features[:: max(1, len(features) // 400)] for c in f["geometry"]["coordinates"][0]] \
            if features and features[0]["geometry"]["type"] == "Polygon" else [3.0]
        lats = [c[1] for f in features[:: max(1, len(features) // 400)] for c in f["geometry"]["coordinates"][0]] \
            if features and features[0]["geometry"]["type"] == "Polygon" else [45.5]
        span = max(max(lons) - min(lons), max(lats) - min(lats))
        st.pydeck_chart(pdk.Deck(
            layers=layers, map_style="light",
            initial_view_state=pdk.ViewState(latitude=(min(lats) + max(lats)) / 2, longitude=(min(lons) + max(lons)) / 2,
                                             zoom=8 if span < 2 else 7 if span < 4 else 5.6),
            tooltip={"html": "<b>{commune}</b> ({dept}) · maille {id}<br/>"
                             "<b>Départ dans la journée : {valeur} / 10 000</b> ({classe})<br/>"
                             "FWI {fwi} ({fwi_classe}) · station {station}<br/>"
                             "Terrain : {p_feu} %/an",
                     "style": {"fontSize": "12px"}}),
            height=620)
        legend()
        st.caption(f"**{chosen:%d/%m/%Y}** · probabilité qu'au moins un feu de forêt démarre dans la journée dans "
                   "chaque maille de 2 km : risque du terrain appris sur BDIFF, modulé par l'indice forêt-météo (FWI) "
                   "calculé sur la station Météo-France la plus proche (TX, humidité min, vent moyen, pluie). "
                   "Données météo observées, pas une prévision.")

    with st.expander("Feux attendus et déclarés autour de cette date", expanded=True):
        start, end = max(day - timedelta(days=45), weather.index.min()), min(day + timedelta(days=45), weather.index.max())
        mask = np.ones(len(communes)) if dept == "all" else (communes.index.str[:2] == dept).astype(float)
        exp = expected_series(weather, communes, model, start, end, mask)
        series = pd.DataFrame({"Départs attendus (modèle)": exp})
        if day - timedelta(days=45) <= pd.Timestamp(meta["bdiff"]["fin"]):
            obs = fires[(fires["date"] >= start) & (fires["date"] <= end)]
            if dept != "all":
                obs = obs[obs["code_insee"].str[:2] == dept]
            series["Feux BDIFF déclarés"] = obs.groupby("date").size().reindex(exp.index, fill_value=0)
        st.line_chart(series, height=240)
        st.caption("Sur 2019-2024, période non utilisée pour l'apprentissage, les départs attendus et déclarés "
                   "concordent à l'échelle des communes (rapport 1,06).")
    with st.expander("Méthode et performances"):
        st.json({"auc_test": meta["apprentissage"]["auc_test"], "validation": meta["apprentissage"]["validation"],
                 "modele": model, "meteo": meta["meteo"], "bdiff": meta["bdiff"]}, expanded=False)
