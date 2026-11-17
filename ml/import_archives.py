"""Importe tous les splits Pyro-SDIS ; conserve les caméras françaises identifiables.

python ml/import_archives.py --out archives-data
Pour un seul fichier local : --parquet CHEMIN --split val
"""
import argparse
import collections
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq
import requests

SOURCE = "https://huggingface.co/datasets/pyronear/pyro-sdis"
API = "https://huggingface.co/api/datasets/pyronear/pyro-sdis"


def department_for(partner, camera):
    match = re.fullmatch(r"(?:sdis|sis|force)-(\d{2}|2[ab])", partner.lower())
    if match:
        return match[1].upper()
    # Ces caméras portent explicitement le nom de la commune de Salaunes (Gironde).
    if partner.lower() == "engie" and camera.lower().startswith("salaunes-"):
        return "33"
    return None


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_shards(out, revision):
    response = requests.get(API + "/revision/" + revision, timeout=30)
    response.raise_for_status()
    metadata = response.json()
    revision = metadata["sha"]
    names = sorted(f["rfilename"] for f in metadata["siblings"] if f["rfilename"].endswith(".parquet"))
    if not names:
        raise ValueError("Aucun fichier Parquet dans cette version")
    cache = out / "parquet"
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(name):
        path = cache / Path(name).name
        metadata_path = path.with_suffix(".revision")
        if not path.exists() or not metadata_path.exists() or metadata_path.read_text() != revision:
            print(f"Téléchargement {name}", flush=True)
            with requests.get(f"{SOURCE}/resolve/{revision}/{name}", stream=True, timeout=120) as r:
                r.raise_for_status()
                temp = path.with_suffix(".part")
                with temp.open("wb") as f:
                    for block in r.iter_content(1024 * 1024):
                        f.write(block)
                temp.replace(path)
            metadata_path.write_text(revision)
        print(f"Prêt : {path.name} ({path.stat().st_size // 1_000_000} Mo)", flush=True)
        split = Path(name).name.split("-")[0]
        return split, path

    with ThreadPoolExecutor(max_workers=3) as pool:
        shards = list(pool.map(fetch, names))
    return revision, shards


def import_archives(shards, out, departments, revision):
    frames = []
    excluded = collections.Counter()
    split_totals = collections.Counter()
    imported = collections.Counter()
    sources = []
    seen = set()
    duplicates = 0
    (out / "images").mkdir(parents=True, exist_ok=True)
    for split, parquet in shards:
        print(f"Import {parquet.name}", flush=True)
        sources.append({"file": parquet.name, "split": split, "sha256": sha256(parquet)})
        for batch in pq.ParquetFile(parquet).iter_batches(batch_size=32):
            for row in batch.to_pylist():
                split_totals[split] += 1
                partner = row["partner"]
                department = department_for(partner, row["camera"])
                if department is None:
                    excluded[partner] += 1
                    continue
                captured = datetime.strptime(row["date"], "%Y-%m-%dT%H-%M-%S")
                camera_id = f"{partner}/{row['camera']}"
                identity = f"{split}/{camera_id}/{row['image_name']}"
                if identity in seen:
                    duplicates += 1
                    continue
                seen.add(identity)
                filename = hashlib.sha256(identity.encode()).hexdigest() + ".jpg"
                (out / "images" / filename).write_bytes(row["image"]["bytes"])
                boxes = []
                for line in (row["annotations"] or "").splitlines():
                    _, x, y, w, h = map(float, line.split())
                    boxes.append([x - w / 2, y - h / 2, x + w / 2, y + h / 2])
                frames.append({"camera_id": camera_id, "camera": row["camera"],
                               "partner": partner, "department": department, "split": split,
                               "timestamp": captured.isoformat(), "image": f"images/{filename}",
                               "source_name": row["image_name"], "boxes": boxes})
                imported[split] += 1
    frames.sort(key=lambda f: (f["timestamp"], f["camera_id"], f["split"], f["source_name"]))
    # Les repères de départements déjà importés restent réutilisables hors ligne.
    for code in sorted({f["department"] for f in frames}):
        if code in departments:
            continue
        try:
            r = requests.get(f"https://geo.api.gouv.fr/departements/{code}/communes",
                             params={"fields": "nom,code,centre,population"}, timeout=10)
            r.raise_for_status()
        except requests.RequestException:
            if code != "33":
                raise
            # Un repère territorial approximatif permet de consulter les archives
            # même si l'API géographique est indisponible. Ce n'est pas une caméra.
            departments[code] = {"lat": 44.84, "lon": -0.58, "city": "Bordeaux",
                "precision": "department_representative_approximate",
                "source": "Repère manuel approximatif de Bordeaux, pas position d’une caméra"}
            print("Gironde : repère approximatif de Bordeaux (API géographique indisponible)", flush=True)
            continue
        commune = max((c for c in r.json() if c.get("centre")), key=lambda c: c.get("population", 0))
        lon, lat = commune["centre"]["coordinates"]
        departments[code] = {"lat": lat, "lon": lon, "city": commune["nom"],
                             "precision": "department_representative",
                             "source": f"https://geo.api.gouv.fr/communes/{commune['code']}"}
    manifest = {"source": SOURCE, "revision": revision, "split": "+".join(sorted(split_totals)),
                "splits": dict(imported), "source_splits": dict(split_totals), "parquets": sources,
                "timezone": "unspecified", "departments": departments, "frames": frames,
                "excluded_rows": sum(excluded.values()), "excluded_by_partner": dict(excluded),
                "duplicate_rows": duplicates, "source_rows": sum(split_totals.values())}
    temp = out / "manifest.tmp"
    temp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    temp.replace(out / "manifest.json")
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parquet", type=Path)
    p.add_argument("--split", choices=["train", "val"], default="val")
    p.add_argument("--revision", default="main")
    p.add_argument("--out", type=Path, default=Path("archives-data"))
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    old = a.out / "manifest.json"
    departments = json.loads(old.read_text()).get("departments", {}) if old.exists() else {}
    revision, shards = ("local", [(a.split, a.parquet)]) if a.parquet else download_shards(a.out, a.revision)
    manifest = import_archives(shards, a.out, departments, revision)
    print(json.dumps({k: manifest[k] for k in ["source_rows", "source_splits", "splits", "excluded_by_partner", "duplicate_rows"]}), flush=True)
    print(f"{len(manifest['frames'])} images françaises / {len({f['camera_id'] for f in manifest['frames']})} caméras", flush=True)


if __name__ == "__main__":
    main()
