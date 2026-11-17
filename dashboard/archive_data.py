"""Filtres temporels indépendants de Streamlit pour le replay Pyro-SDIS."""
from datetime import datetime, timedelta


def merge_archives(manifests):
    """Unifier les index sans déplacer les fichiers ni confondre leurs positions."""
    merged = {"frames": [], "points": {}, "cameras": {}, "sources": manifests}
    for source, manifest in manifests.items():
        for key, meta in manifest.get("departments", {}).items():
            point_id = f"{source}:{key}"
            merged["points"][point_id] = {
                **meta, "id": point_id, "source_key": source,
                "name": f"Pyro-SDIS · département {key}" if source == "pyro" else meta["name"],
                "location_note": "Repère départemental ; position des caméras inconnue" if source == "pyro"
                    else meta.get("coordinate_precision", "Position publiée de la webcam"),
            }
        for frame in manifest["frames"]:
            camera_id = f"{source}:{frame['camera_id']}"
            point_id = f"{source}:{frame['department']}"
            if point_id not in merged["points"]:
                raise ValueError(f"Point absent du manifeste : {point_id}")
            normalized = {**frame, "camera_id": camera_id, "point_id": point_id,
                          "original_camera_id": frame["camera_id"], "source_key": source}
            if frame.get("sequence_id") is not None:
                normalized["sequence_id"] = f"{source}:{frame['sequence_id']}"
            merged["frames"].append(normalized)
            merged["cameras"].setdefault(camera_id, {
                "id": camera_id, "point_id": point_id, "source_key": source,
                "name": frame["camera_id"] if source == "pyro" else merged["points"][point_id]["name"],
            })
    return merged


def prepare_frames(manifest):
    return sorted(({**f, "time": datetime.fromisoformat(f["timestamp"])}
                   for f in manifest["frames"]), key=lambda f: (f["time"], f["camera_id"]))


def sequences(frames, gap=timedelta(minutes=30)):
    """Respecter les épisodes éditorialisés ; sinon séparer après 30 minutes."""
    result = []
    for frame in sorted(frames, key=lambda f: f["time"]):
        previous = result[-1][-1] if result else None
        same_episode = (previous is not None and frame.get("sequence_id") is not None
                        and frame["sequence_id"] == previous.get("sequence_id"))
        if not result or (not same_episode and (
                frame.get("sequence_id") != previous.get("sequence_id")
                or frame["time"] - previous["time"] > gap)):
            result.append([])
        result[-1].append(frame)
    return result


def active_sequence(frames, cursor):
    for sequence in sequences(frames):
        if sequence[0]["time"] <= cursor <= sequence[-1]["time"]:
            return sequence
    return []


def frames_in_window(frames, cursor, width):
    """Présence réelle d'images, bornes incluses, sans combler les trous."""
    half = width / 2
    return [f for f in frames if cursor - half <= f["time"] <= cursor + half]
