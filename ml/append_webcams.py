"""Ajoute des entrées (url;ville) au CSV cameras.csv en dédupliquant par URL."""
import csv
import sys
from pathlib import Path

CSV = Path("camera-data/cameras.csv")


def load_seen():
    seen = set()
    if CSV.is_file():
        with CSV.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                u = (row.get("url_youtube") or "").strip()
                if u:
                    seen.add(u)
    return seen


def append_file(src_path, label):
    seen = load_seen()
    new = []
    with src_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            u = (row.get("url_youtube") or row.get("url") or "").strip()
            v = (row.get("ville") or "").strip()
            if not u or not v:
                continue
            if u in seen:
                continue
            seen.add(u)
            new.append({"url_youtube": u, "ville": v})
    if not new:
        print(f"[{label}] 0 nouvelle(s)")
        return 0
    header_needed = not CSV.is_file() or CSV.stat().st_size == 0
    with CSV.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                           delimiter=";", lineterminator="\n")
        if header_needed:
            w.writeheader()
        w.writerows(new)
    print(f"[{label}] {len(new)} nouvelle(s) ajoutée(s)")
    return len(new)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        append_file(Path(p), p)
