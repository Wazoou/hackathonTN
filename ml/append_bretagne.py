#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ajoute les webcans Bretagne collectees à camera-data/cameras.csv (dedup par URL)."""
from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "camera-data" / "cameras.csv"
SRC = Path(__file__).resolve().parent / "bretagne_collecte_final.txt"


def clean_url(u: str) -> str:
    u = u.strip()
    if not u:
        return ""
    p = urlparse(u)
    if not p.scheme or not p.hostname:
        return ""
    return p.geturl()


def main():
    seen = set()
    if CSV_PATH.is_file():
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                u = (row.get("url_youtube") or "").strip()
                if u:
                    seen.add(u)

    new_rows = []
    with SRC.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ";" not in line:
                continue
            url, ville = line.split(";", 1)
            url = clean_url(url)
            ville = ville.strip()
            if not url or not ville:
                continue
            if url in seen:
                continue
            seen.add(url)
            new_rows.append({"url_youtube": url, "ville": ville})

    if not new_rows:
        print("Aucune nouvelle ligne à ajouter.")
        return

    if CSV_PATH.is_file() and CSV_PATH.stat().st_size > 0:
        with CSV_PATH.open("rb") as fh:
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                with CSV_PATH.open("ab") as fh2:
                    fh2.write(b"\n")

    write_header = not CSV_PATH.is_file() or CSV_PATH.stat().st_size == 0
    with CSV_PATH.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                                delimiter=";", lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    print(f"{len(new_rows)} nouvelles webcans ajoutees à {CSV_PATH}")


if __name__ == "__main__":
    main()
