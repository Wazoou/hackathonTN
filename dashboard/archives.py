"""Carte et lecteur communs aux archives Pyro-SDIS et aux webcams."""
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

from archive_data import frames_in_window, merge_archives, prepare_frames, sequences
from timeline_gauge import render as render_gauge

ARCHIVE_DIR = Path(os.getenv("ARCHIVE_DIR", "archives-data"))
SOURCE_LABELS = {"all": "Toutes les sources", "pyro": "Pyro-SDIS", "webcams": "Webcams"}


@st.cache_data
def load_manifest(path, mtime):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data
def load_collection(files):
    return merge_archives({source: load_manifest(path, mtime) for source, path, mtime in files})


def stop_playback():
    st.session_state["archive_playing"] = False


def seek_timeline(timestamp):
    st.session_state["archive_cursor"] = timestamp
    stop_playback()


def move_frame(step, count):
    st.session_state["replay_index"] = min(count - 1, max(0, st.session_state.get("replay_index", 0) + step))
    stop_playback()


def choose_point(point_id, collection, preferred_camera=None, focus=None, narrow=False):
    frames = [f for f in prepare_frames(collection) if f["point_id"] == point_id
              and (preferred_camera is None or f["camera_id"] == preferred_camera)]
    if not frames:
        return
    cursor = focus or st.session_state.get("archive_cursor", frames[0]["time"])
    nearby = frames_in_window(frames, cursor, timedelta(seconds=st.session_state.get("archive_window", 3600)))
    target = min(nearby or frames, key=lambda f: abs(f["time"] - cursor))
    st.session_state["archive_point"] = point_id
    st.session_state["archive_camera"] = target["camera_id"]
    chosen = st.session_state.get("archive_dates", ())
    if narrow or len(chosen) != 2 or not chosen[0] <= target["time"].date() <= chosen[1]:
        st.session_state["archive_dates"] = (frames[0]["time"].date(), frames[-1]["time"].date())
    seek_timeline(cursor if nearby else target["time"])


def source_changed(collection):
    source = st.session_state["archive_source"]
    frames = [f for f in prepare_frames(collection) if source == "all" or f["source_key"] == source]
    st.session_state["archive_dates"] = (frames[0]["time"].date(), frames[-1]["time"].date())
    stop_playback()


def archives():
    files = []
    for source, name in [("pyro", "manifest.json"), ("webcams", "manifest-webcams.json")]:
        path = ARCHIVE_DIR / name
        if path.exists():
            files.append((source, str(path), path.stat().st_mtime_ns))
    if not files:
        st.info("Aucune archive importée. Importez Pyro-SDIS ou l’échantillon de webcams.")
        return
    collection = load_collection(tuple(files))
    all_frames = prepare_frames(collection)
    if not all_frames:
        st.info("Aucune image dans les archives importées.")
        return
    if st.session_state.get("_archive_collection") != "unified-v1":
        for key in list(st.session_state):
            if key.startswith("archive_") or key in ("last_gauge_serial", "last_map_serial", "reader_signature", "replay_index"):
                del st.session_state[key]
        st.session_state["_archive_collection"] = "unified-v1"
    st.session_state.setdefault("archive_source", "all")
    if st.session_state["archive_source"] not in ("all", *collection["sources"]):
        st.session_state["archive_source"] = "all"
    counts = {source: sum(f["source_key"] == source for f in all_frames) for source in collection["sources"]}
    st.caption(f"{len(all_frames):,} images · {len(collection['cameras'])} caméras · "
               + " · ".join(f"{SOURCE_LABELS[source]} : {count:,}" for source, count in counts.items()))
    source = st.session_state["archive_source"]
    if source != "all":
        st.caption(f"Source affichée : {SOURCE_LABELS[source]}")
    frames = [f for f in all_frames if source == "all" or f["source_key"] == source]
    points = {key: value for key, value in collection["points"].items()
              if source == "all" or value["source_key"] == source}
    days = sorted({f["time"].date() for f in all_frames})
    st.session_state.setdefault("archive_dates", (days[0], days[-1]))
    default = next((f for f in frames if f["camera_id"] == "webcams:frejus" and f["timestamp"] == "2025-07-07T11:31:00"), frames[0])
    st.session_state.setdefault("archive_cursor", default["time"])
    st.session_state.setdefault("archive_point", default["point_id"])
    st.session_state.setdefault("archive_camera", default["camera_id"])
    pending = st.session_state.get("archive_gauge")
    if (isinstance(pending, dict) and pending.get("action") == "select_point"
            and pending.get("scope") == st.session_state.get("_archive_scope")
            and pending.get("serial") != st.session_state.get("last_map_serial")
            and pending.get("point_id") in points):
        choose_point(pending["point_id"], collection)
        st.session_state["last_map_serial"] = pending["serial"]
        st.session_state["last_gauge_serial"] = pending["serial"]
    with st.popover("↗ Explorer un exemple"):
        for point in points.values():
            if point["source_key"] == "webcams":
                st.button(point["episode"], key=f"example_{point['id']}", on_click=choose_point,
                          args=(point["id"], collection), kwargs={"focus": datetime.fromisoformat(point["focus"]), "narrow": True},
                          use_container_width=True)
        pyro_frames = [f for f in frames if f["source_key"] == "pyro"]
        if pyro_frames:
            example = next((f for f in pyro_frames if f["boxes"]), pyro_frames[0])
            st.button("Pyro-SDIS · fumée annotée", key="example_pyro", on_click=choose_point,
                      args=(example["point_id"], collection), kwargs={"preferred_camera": example["camera_id"], "focus": example["time"], "narrow": True},
                      use_container_width=True)
    windows = {900: "15 minutes", 3600: "1 heure", 21600: "6 heures", 86400: "1 jour", 604800: "7 jours", 2592000: "30 jours"}
    with st.popover("⚙ Affiner la période et les sources"):
        width = st.select_slider("Largeur de la fenêtre observée", options=list(windows), value=3600,
                                 format_func=windows.get, key="archive_window", on_change=stop_playback)
        st.selectbox("Sources", ["all"] + list(collection["sources"]), format_func=SOURCE_LABELS.get,
                     key="archive_source", on_change=source_changed, args=(collection,))
        chosen = st.date_input("Période des archives", min_value=days[0], max_value=days[-1],
                               key="archive_dates", on_change=stop_playback)
    if len(chosen) != 2:
        st.info("Sélectionnez la date de fin de la période.")
        return
    period = [f for f in frames if chosen[0] <= f["time"].date() <= chosen[1]]
    times = sorted({f["time"] for f in period}) or [datetime.combine(chosen[0], time.min), datetime.combine(chosen[1], time.max)]
    cursor = st.session_state["archive_cursor"]
    if not times[0] <= cursor <= times[-1]:
        cursor = times[0]
    scope = source + "|" + times[0].isoformat() + "|" + times[-1].isoformat()
    st.session_state["_archive_scope"] = scope
    message = st.session_state.get("archive_gauge")
    if (isinstance(message, dict) and message.get("action") == "time" and message.get("scope") == scope
            and message.get("serial") != st.session_state.get("last_gauge_serial")):
        cursor = times[0] + timedelta(seconds=min(max(0, int(message["offset"])), int((times[-1] - times[0]).total_seconds())))
        st.session_state["last_gauge_serial"] = message["serial"]
        stop_playback()
    st.session_state["archive_cursor"] = cursor
    window_frames = frames_in_window(period, cursor, timedelta(seconds=width))
    if st.session_state.get("archive_point") not in points:
        st.session_state["archive_point"] = (window_frames or period or frames)[0]["point_id"]
    render_gauge(times[0], times[-1], cursor, [f["time"] for f in period], width,
                 list(points.values()), period, st.session_state["archive_point"], scope=scope,
                 camera_total=len({f["camera_id"] for f in frames}))
    if not period:
        st.info("Aucune image sur cette période pour les sources choisies. La carte reste accessible ; cliquez sur un point pour rejoindre ses données.")
    by_camera = {}
    for frame in frames:
        by_camera.setdefault(frame["camera_id"], []).append(frame)
    with st.expander("Changer de caméra ou de séquence"):
        point_id = st.selectbox("Point de la carte", list(points), format_func=lambda key: points[key]["name"],
                                key="archive_point", on_change=stop_playback)
        cameras = [key for key in by_camera if collection["cameras"][key]["point_id"] == point_id]
        if st.session_state.get("archive_camera") not in cameras:
            candidate = min((f for key in cameras for f in by_camera[key]), key=lambda f: abs(f["time"] - cursor))
            st.session_state["archive_camera"] = candidate["camera_id"]
        camera = st.selectbox("Caméra", cameras, format_func=lambda key: collection["cameras"][key]["name"],
                              key="archive_camera", on_change=stop_playback)
        camera_sequences = sequences(by_camera[camera])
        signature = (camera, chosen, cursor, source)
        if st.session_state.get("archive_signature") != signature:
            st.session_state["archive_sequence"] = min(range(len(camera_sequences)), key=lambda i: min(abs(f["time"] - cursor) for f in camera_sequences[i]))
            st.session_state["archive_signature"] = signature
        sequence_id = st.selectbox("Séquence disponible", range(len(camera_sequences)), key="archive_sequence",
            format_func=lambda i: f"{camera_sequences[i][0]['time']:%d/%m/%Y %H:%M} → {camera_sequences[i][-1]['time']:%d/%m/%Y %H:%M} · {len(camera_sequences[i])} images",
            on_change=stop_playback)
        sequence = camera_sequences[sequence_id]
        st.button("Placer la timeline au début de cette séquence", key="seek_sequence", on_click=choose_point,
                  args=(point_id, collection), kwargs={"preferred_camera": camera, "focus": sequence[0]["time"]})
        show_boxes = st.checkbox("Afficher les annotations de référence (fumée)", value=True, key="archive_boxes") if collection["cameras"][camera]["source_key"] == "pyro" else False
    point = points[point_id]
    webcam = point["source_key"] == "webcams"
    st.markdown(f"**{collection['cameras'][camera]['name']}** · {SOURCE_LABELS[point['source_key']]}")
    st.caption(point["location_note"])
    if webcam:
        st.caption(point["evidence"] + " · aucune prédiction du modèle")
        st.write(point["description"])
    else:
        st.caption("Cadres orange : annotations humaines de référence, pas prédictions YOLO.")
    current = frames_in_window(by_camera[camera], cursor, timedelta(seconds=width))
    if not current or not period:
        st.caption("Aucune image de cette caméra dans la fenêtre observée. Séquence la plus proche affichée.")
        st.button("Rejoindre les images de cette caméra", key="seek_camera", on_click=choose_point,
                  args=(point_id, collection), kwargs={"preferred_camera": camera})
    if st.session_state.get("reader_signature") != signature + (sequence_id,):
        st.session_state["replay_index"] = min(range(len(sequence)), key=lambda i: abs(sequence[i]["time"] - cursor))
        st.session_state["reader_signature"] = signature + (sequence_id,)
        stop_playback()
    player(sequence, show_boxes, point if webcam else None)
    with st.expander("Provenance des archives"):
        manifest = collection["sources"][point["source_key"]]
        if webcam:
            st.markdown(f"Images : [{point['source']}]({point['source_url']})")
            if point.get("evidence_url"):
                st.markdown(f"[Documentation de l’événement]({point['evidence_url']})")
            st.caption(point["coordinate_source"])
            st.caption(manifest["license_note"])
            st.write("Les vues de comparaison ne sont pas des annotations négatives de référence.")
        else:
            st.write(f"Source : {manifest['source']} · révision : {manifest['revision']}")
            st.write(f"{counts['pyro']:,} images françaises ; splits conservés dans les métadonnées : {manifest['splits']}.")
            st.caption("Les positions des caméras Pyro-SDIS ne sont pas fournies. Les losanges sont des repères départementaux.")
            st.caption("Les images d’entraînement ne sont pas un test indépendant pour un modèle entraîné dessus.")
        st.caption("Dates conservées telles qu’affichées par chaque source ; le fuseau Pyro-SDIS n’est pas renseigné. Leur correspondance exacte entre sources n’est pas garantie.")
        st.caption("Vert : images disponibles. Gris : aucune image dans la fenêtre. Ces couleurs ne représentent pas des détections.")


@st.fragment(run_every=1)
def player(sequence, show_boxes, camera_meta=None):
    count = len(sequence)
    st.session_state.setdefault("replay_index", 0)
    if st.session_state.get("archive_playing"):
        st.session_state["replay_index"] = min(count - 1, st.session_state["replay_index"] + 1)
        if st.session_state["replay_index"] == count - 1:
            stop_playback()
    left, mid, right, speed = st.columns([1, 1, 1, 3])
    left.button("← Précédente", on_click=move_frame, args=(-1, count), disabled=st.session_state["replay_index"] == 0)
    if mid.button("Pause" if st.session_state.get("archive_playing") else "▶ Lecture", disabled=count < 2):
        if st.session_state["replay_index"] == count - 1:
            st.session_state["replay_index"] = 0
        st.session_state["archive_playing"] = not st.session_state.get("archive_playing", False)
    right.button("Suivante →", on_click=move_frame, args=(1, count), disabled=st.session_state["replay_index"] == count - 1)
    speed.caption("Lecture : 1 image par seconde · dates source affichées sous l’image")
    if count > 1:
        st.select_slider("Position dans la séquence", options=list(range(count)), key="replay_index",
                         format_func=lambda i: sequence[i]["time"].strftime("%d/%m %H:%M" if camera_meta else "%H:%M:%S"),
                         on_change=stop_playback)
    index = st.session_state["replay_index"]
    frame = sequence[index]
    image_path = (ARCHIVE_DIR / frame["image"]).resolve()
    if not image_path.is_relative_to(ARCHIVE_DIR.resolve()) or not image_path.exists():
        st.error("Image d’archive introuvable. Réimportez les données.")
        return
    with Image.open(image_path) as original:
        img = original.convert("RGB")
    if show_boxes:
        draw = ImageDraw.Draw(img)
        for box in frame["boxes"]:
            x1, y1, x2, y2 = box
            draw.rectangle((x1 * img.width, y1 * img.height, x2 * img.width, y2 * img.height),
                           outline="#f97316", width=max(2, img.width // 350))
    name = camera_meta["name"] if camera_meta else frame.get("original_camera_id", frame["camera_id"])
    suffix = camera_meta["credit"] if camera_meta else frame.get("split", "val")
    st.image(img, caption=f"{name} · {frame['time']:%d/%m/%Y %H:%M:%S} · "
                         f"image {index + 1}/{count} · {suffix}", use_container_width=True)
    if camera_meta:
        st.caption(frame["time_basis"])
        st.markdown(f"[Ouvrir l’image source]({frame['source_url']})")
    if index:
        delta = frame["time"] - sequence[index - 1]["time"]
        st.caption(f"Intervalle réel depuis l’image précédente : {delta.total_seconds():g} secondes.")
    st.caption("Image non annotée · YOLO à connecter" if camera_meta else
               ("Fumée annotée" if frame["boxes"] else "Aucune fumée annotée sur cette image"))
