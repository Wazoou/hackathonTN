"""Vérifier le parcours de démonstration sur ses images réelles dans le conteneur."""
import hashlib
import json
from pathlib import Path

manifest = json.loads(Path("/archives/manifest-webcams.json").read_text())
assert len(manifest["frames"]) == 29
assert len(manifest["departments"]) == 4
for frame in manifest["frames"]:
    path = Path("/archives") / frame["image"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == frame["sha256"]
    assert frame["boxes"] == [] and not frame["annotated"]

print("Webcams : 29 images vérifiées sans annotations ajoutées ; parcours : check_archive_ui.py")
