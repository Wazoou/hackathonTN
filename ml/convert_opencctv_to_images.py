"""Convertir les URLs de pages opencctv.org en URLs d'image directe.

Pour chaque URL du type https://opencctv.org/cameras/.../nom-123456,
extrait l'ID de caméra (123456) et le remplace par
https://opencctv.org/still/123456.jpg

Ainsi le dashboard peut afficher l'image directement avec st.image.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

CSV_PATH = Path("camera-data/cameras.csv")

_OPCCTV_ID_RE = re.compile(r"-(\d+)(?:/|$)")


def convert_opencctv_url(url: str) -> str:
    """Si c'est une URL de page opencctv.org, retourne l'URL de l'image directe."""
    parsed = urlparse(url)
    if parsed.hostname and "opencctv.org" in parsed.hostname:
        match = _OPCCTV_ID_RE.search(parsed.path)
        if match:
            cam_id = match.group(1)
            return f"https://opencctv.org/still/{cam_id}.jpg"
    return url


def main():
    rows = []
    converted = 0
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        fieldnames = reader.fieldnames
        for row in reader:
            url = (row.get("url_youtube") or "").strip()
            city = (row.get("ville") or "").strip()
            if not url or not city:
                continue
            new_url = convert_opencctv_url(url)
            if new_url != url:
                converted += 1
            rows.append({"url_youtube": new_url, "ville": city})

    # Dédupliquer
    seen = set()
    unique = []
    for row in rows:
        if row["url_youtube"] not in seen:
            seen.add(row["url_youtube"])
            unique.append(row)

    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                                delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(unique)

    print(f"Converti {converted} URL opencctv.org en image directe")
    print(f"Total lignes uniques : {len(unique)}")


if __name__ == "__main__":
    main()
