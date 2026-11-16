"""Outils autour du dataset Pyronear `pyro-sdis` (Hugging Face, ~1,3 Go, format YOLO).

  # Images de démo pour les caméras simulées (séquences réelles de caméras SDIS, ~120 Mo)
  python ml/pyro_sdis.py samples --out data/samples --cameras 3

  # Dataset complet au format YOLO pour l'entraînement (à lancer sur Kaggle/Colab)
  python ml/pyro_sdis.py yolo --out datasets/pyro-sdis
"""

import argparse
import collections
from pathlib import Path

import pyarrow.parquet as pq
import requests

BASE = "https://huggingface.co/datasets/pyronear/pyro-sdis/resolve/main/data"
SHARDS = {
    "train": [f"train-0000{i}-of-00003.parquet" for i in range(3)],
    "val": ["val-00000-of-00001.parquet"],
}


def download(name: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / name
    if not path.exists():
        print(f"Téléchargement de {name}...")
        with requests.get(f"{BASE}/{name}", stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            tmp.rename(path)
    return path


def samples(out: Path, n_cameras: int, cache: Path) -> None:
    """Un dossier par caméra, images triées par date -> source FolderSource de l'agent caméra."""
    table = pq.read_table(download(SHARDS["val"][0], cache))
    rows = table.select(["partner", "camera"]).to_pylist()
    top = [k for k, _ in collections.Counter((r["partner"], r["camera"]) for r in rows).most_common(n_cameras)]
    for i, (partner, camera) in enumerate(top, start=1):
        folder = out / f"cam-{i}"
        (folder / "labels").mkdir(parents=True, exist_ok=True)
        idx = [j for j, r in enumerate(rows) if (r["partner"], r["camera"]) == (partner, camera)]
        for row in table.take(idx).to_pylist():
            stem = Path(row["image_name"]).stem
            (folder / f"{stem}.jpg").write_bytes(row["image"]["bytes"])
            (folder / "labels" / f"{stem}.txt").write_text(row["annotations"] or "")
        print(f"{folder} <- {partner}/{camera} ({len(idx)} images)")


def to_yolo(out: Path, cache: Path) -> None:
    for split, shards in SHARDS.items():
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        for shard in shards:
            for batch in pq.ParquetFile(download(shard, cache)).iter_batches(batch_size=256):
                for row in batch.to_pylist():
                    stem = Path(row["image_name"]).stem
                    (out / "images" / split / f"{stem}.jpg").write_bytes(row["image"]["bytes"])
                    (out / "labels" / split / f"{stem}.txt").write_text(row["annotations"] or "")
    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['smoke']\n"
    )
    print(f"Dataset prêt : {out / 'data.yaml'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["samples", "yolo"])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cameras", type=int, default=3)
    p.add_argument("--cache", type=Path, default=Path(".cache/pyro-sdis"))
    a = p.parse_args()
    samples(a.out, a.cameras, a.cache) if a.cmd == "samples" else to_yolo(a.out, a.cache)
