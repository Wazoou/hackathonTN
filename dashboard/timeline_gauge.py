"""Carte persistante : aperçu local au glissement, synchronisation au relâchement."""
from pathlib import Path

import streamlit.components.v1 as components

_gauge = components.declare_component("archive_time_gauge", path=str(Path(__file__).parent / "timeline_component"))


def render(start, end, cursor, timestamps, width_seconds, points, frames, selected_point,
           scope, camera_total=None):
    duration = max(1, int((end - start).total_seconds()))
    bins = [0] * 160
    offsets = sorted({int((t - start).total_seconds()) for t in timestamps})
    for timestamp in timestamps:
        i = min(159, int((timestamp - start).total_seconds() / duration * 160))
        bins[max(0, i)] += 1
    return _gauge(start=start.isoformat(), end=end.isoformat(), duration=duration,
                  cursor=int((cursor - start).total_seconds()), bins=bins, offsets=offsets,
                  width_seconds=width_seconds, points=points,
                  frames=[{"offset": int((f["time"] - start).total_seconds()),
                           "point_id": f["point_id"], "camera": f["camera_id"]} for f in frames],
                  selected_point=selected_point, scope=scope, camera_total=camera_total,
                  key="archive_gauge", default=None)
