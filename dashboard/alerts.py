"""Human review of genuine YOLO detections from catalogue webcams and demo."""
import requests
import streamlit as st

from interface import MODE_ARCHIVES, MODE_KEY, section_title
from surveillance import DEMO_URL, api, date_label, frame_image

STATUS = {"open": "À vérifier", "confirmed": "Confirmée", "false_positive": "Fausse alerte"}
FILTERS = ["Tous", *STATUS.values()]
FILTER_KEY = "alerts_status_filter"


def _set_alert_filter(status):
    st.session_state[FILTER_KEY] = status


def alerts():
    st.caption("Une alerte exige au moins deux analyses consécutives au-dessus du seuil. "
               "Le score du modèle ne constitue pas une confirmation d’incendie.")
    if FILTER_KEY not in st.session_state:
        st.session_state[FILTER_KEY] = "Tous"
    status = st.session_state[FILTER_KEY]
    with st.container(key="alert_status_bar"):
        for index, (column, label) in enumerate(zip(st.columns(len(FILTERS)), FILTERS)):
            column.button(label, key=f"alert_status_{index}",
                          type="primary" if status == label else "secondary",
                          on_click=_set_alert_filter, args=(label,),
                          use_container_width=True)
    alert_feed(status)


@st.fragment(run_every="5s")
def alert_feed(status):
    try:
        cameras = [c for c in api("GET", "/cameras") if c.get("detector") == "yolo"]
        # Exclude the old synthetic/dummy agents from genuine detection results.
        items = [a for a in api("GET", "/alerts?limit=1000") if a.get("detector") == "yolo"]
    except (requests.RequestException, ValueError):
        st.warning("Le service de surveillance est momentanément indisponible.")
        return
    public = [c for c in cameras if not c["is_demo"]]
    metrics = st.columns(3)
    metrics[0].metric("Webcams prises en charge", len(public))
    metrics[1].metric("Analysées récemment", sum(bool(c["online"] and not c["last_error"]) for c in public))
    metrics[2].metric("Alertes à vérifier", sum(a["status"] == "open" for a in items))
    errors = [c for c in public if c["last_error"]]
    if errors:
        with st.expander(f"{len(errors)} webcam(s) temporairement en échec"):
            for camera in errors:
                st.write(f"{camera['name']} · {camera['last_error']}")
    if status != "Tous":
        items = [a for a in items if STATUS[a["status"]] == status]
    section_title("Alertes de fumée", "La plus récente par caméra · actualisation toutes les 5 secondes")
    if not items:
        st.info("Aucune alerte pour cette sélection. La surveillance continue en arrière-plan.")
    for alert in items:
        label = ("DÉMONSTRATION · " if alert["is_demo"] else "") + alert["camera_name"]
        with st.container(border=True):
            st.subheader(label)
            st.caption(f"{STATUS[alert['status']]} · {date_label(alert['created_at'])} · "
                       f"Score YOLO {alert['confidence']:.0%} · "
                       f"{alert['lat']:.3f}, {alert['lon']:.3f}")
            try:
                st.image(frame_image(f"/alerts/{alert['id']}/image", [alert]), width=700)
            except (requests.RequestException, OSError, ValueError):
                st.warning("Image de l’alerte indisponible.")
            cols = st.columns(3)
            if cols[0].button("Voir la webcam", key=f"camera_alert_{alert['id']}", use_container_width=True):
                st.session_state["selected_webcam_url"] = DEMO_URL if alert["is_demo"] else alert["source_url"]
                st.session_state[MODE_KEY] = MODE_ARCHIVES
                st.rerun()
            for col, (value, label) in zip(cols[1:], [("confirmed", "Confirmer"), ("false_positive", "Fausse alerte")]):
                if col.button(label, key=f"{value}_{alert['id']}", disabled=alert["status"] == value,
                              use_container_width=True):
                    try:
                        api("PATCH", f"/alerts/{alert['id']}", json={"status": value})
                        st.rerun()
                    except requests.RequestException:
                        st.error("La qualification n’a pas pu être enregistrée.")
