"""Parcours commun sur les vrais manifestes, dans le conteneur dashboard."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

pyro = json.loads(Path("/archives/manifest.json").read_text())
webcams = json.loads(Path("/archives/manifest-webcams.json").read_text())
with patch("timeline_gauge.render", return_value=None) as gauge:
    at = AppTest.from_file("/app/app.py", default_timeout=30).run()
    assert not at.exception, at.exception
    assert "app_mode" not in at.session_state or at.session_state["app_mode"] == "Carte des archives"
    assert at.selectbox(key="archive_source").value == "all"
    assert len(gauge.call_args.args[5]) == 10
    assert len(gauge.call_args.args[6]) == len(pyro["frames"]) + len(webcams["frames"])
    assert gauge.call_args.kwargs["camera_total"] == 200
    assert at.session_state["archive_camera"] == "webcams:frejus"
    assert not at.checkbox
    print("Toutes les sources : 12 252 images, 200 caméras, 10 repères")

    def click_point(point_id, serial):
        at.session_state["archive_gauge"] = dict(action="select_point", point_id=point_id,
            offset=0, scope=at.session_state["_archive_scope"], serial=serial)
        at.run()
        assert not at.exception, at.exception

    click_point("pyro:07", 1)
    assert at.session_state["archive_point"] == "pyro:07"
    assert at.session_state["archive_camera"].startswith("pyro:")
    assert at.checkbox(key="archive_boxes")
    cursor = at.session_state["archive_cursor"]
    assert any(datetime.fromisoformat(f["timestamp"]) == cursor and f["department"] == "07" for f in pyro["frames"])
    assert at.selectbox(key="archive_source").value == "all"
    assert len(gauge.call_args.args[5]) == 10
    at.button(key="example_pyro").click().run()
    assert not at.exception, at.exception
    assert any("Fumée annotée" == c.value for c in at.caption)
    at.checkbox(key="archive_boxes").uncheck().run()
    assert not at.exception, at.exception
    print("Département, exemple Pyro-SDIS et annotations : OK")

    click_point("webcams:samena", 2)
    assert at.session_state["archive_camera"] == "webcams:samena"
    assert at.session_state["archive_cursor"].year == 2020
    assert not at.checkbox
    assert len(gauge.call_args.args[5]) == 10
    at.button(key="example_webcams:frejus").click().run()
    assert not at.exception, at.exception
    assert at.session_state["archive_cursor"] == datetime(2025, 7, 7, 11, 31)
    assert at.session_state["replay_index"] == 5
    start = gauge.call_args.args[0]
    requested = datetime(2025, 7, 7, 12, 1)
    at.session_state["archive_gauge"] = dict(action="time", point_id="webcams:frejus",
        scope=at.session_state["_archive_scope"], offset=int((requested-start).total_seconds()), serial=3)
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["archive_cursor"] == requested
    assert at.session_state["replay_index"] == 6
    at.button(key="example_webcams:frejus").click().run()
    assert at.session_state["archive_cursor"] == datetime(2025, 7, 7, 11, 31)
    at.button(key="example_webcams:canejan").click().run()
    assert at.session_state["archive_cursor"].year == 2022
    at.button(key="reset_period").click().run()
    assert len(gauge.call_args.args[6]) == len(pyro["frames"]) + len(webcams["frames"])
    assert at.session_state["archive_camera"] == "webcams:canejan"
    at.button(key="example_webcams:frejus").click().run()
    at.selectbox(key="panorama_crop").set_value("Panorama complet").run()
    assert not at.exception, at.exception
    assert at.session_state["replay_index"] == 5
    at.selectbox(key="panorama_crop").set_value("Détail droit").run()
    print("Passage entre sources, exemples et synchronisation temporelle : OK")

    for source, point_count, frame_count in [("pyro", 6, len(pyro["frames"])), ("webcams", 4, 29), ("all", 10, len(pyro["frames"]) + 29)]:
        at.selectbox(key="archive_source").set_value(source).run()
        assert not at.exception, at.exception
        assert len(gauge.call_args.args[5]) == point_count
        assert len(gauge.call_args.args[6]) == frame_count
        if source != "all":
            assert all(p["source_key"] == source for p in gauge.call_args.args[5])
        assert not at.warning
    print("Filtre facultatif : Pyro-SDIS / webcams / toutes les sources OK")

    dates = sorted(datetime.fromisoformat(f["timestamp"]) for f in pyro["frames"] + webcams["frames"])
    occupied = {t.date() for t in dates}
    empty = dates[0].date()
    while empty in occupied:
        empty += timedelta(days=1)
    at.date_input[0].set_value((empty, empty)).run()
    assert not at.exception, at.exception
    assert at.info
    assert len(gauge.call_args.args[5]) == 10 and not gauge.call_args.args[6]
    click_point("webcams:frejus", 4)
    assert at.session_state["archive_cursor"].year == 2025
    at.button(key="example_webcams:frejus").click().run()
    next(b for b in at.button if b.label == "Suivante →").click().run()
    assert not at.exception, at.exception
    assert at.session_state["replay_index"] == 6
    next(b for b in at.button if b.label == "← Précédente").click().run()
    assert at.session_state["replay_index"] == 5
    at.button(key="mode_simulation").click().run()
    assert not at.exception, at.exception
    assert at.session_state["app_mode"] == "Surveillance simulée"
    at.button(key="mode_archives").click().run()
    assert not at.exception, at.exception
    assert at.session_state["app_mode"] == "Carte des archives"
    at.button(key="mode_fire_history").click().run()
    assert not at.exception, at.exception
    assert not at.metric
    assert not at.radio
    month_slider = at.select_slider(key="fire_history_month")
    assert month_slider.value.startswith("2025-")
    month_slider.set_value("2025-01").run()
    assert not at.exception, at.exception
    assert at.session_state["fire_history_month"] == "2025-01"
    assert at.select_slider(key="fire_history_month").value == "2025-12"
    at.select_slider(key="fire_history_month").set_value("2025-01").run()
    assert not at.exception, at.exception
    assert at.session_state["fire_history_month"] == "2025-01"
    at.button(key="mode_archives").click().run()
    assert not at.exception, at.exception
    print("Période vide, lecture, simulation et historique des incendies : OK")
