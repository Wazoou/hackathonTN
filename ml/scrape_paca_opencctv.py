"""Re-scrape propre opencctv.org PACA : seules les vraies caméras (depth 3,
hors catégorie). Ville depuis le texte du lien (accents préservés).
URL stockée = page de détail (valide comme lecteur webcam pour build_camera_directory).
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "camera-data" / "cameras.csv"
BASE = "https://opencctv.org/cameras/france/provence-alpes-cote-dazur"
DETAIL_RE = re.compile(r"^/cameras/france/provence-alpes-cote-dazur/[\w-]+/[\w-]+$")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector; hackathonTN)"})


def seen_urls():
    seen = set()
    if CSV_PATH.is_file():
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                u = (row.get("url_youtube") or "").strip()
                if u:
                    seen.add(u)
    return seen


def city_from_text(text):
    if not text:
        return None
    t = text.strip()
    for sep in (" › ", " - ", " : ", " | ", " Live", " live"):
        if sep in t:
            city = t.split(sep, 1)[0].strip()
            if city and len(city) < 60:
                return city
    # dernier recours : premier mot
    first = t.split()[0] if t.split() else ""
    if first and len(first) < 60:
        return first
    return None


def remove_all_opencctv():
    """Supprime toutes les lignes opencctv du CSV (reprise propre)."""
    if not CSV_PATH.is_file():
        return 0
    rows = []
    removed = 0
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        fieldnames = reader.fieldnames
        for row in reader:
            u = (row.get("url_youtube") or "").strip()
            if "opencctv.org" in u:
                removed += 1
                continue
            rows.append(row)
    if removed:
        with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames,
                                    delimiter=";", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(f"Suppr {removed} anciennes lignes opencctv.")
    return removed


def main(max_pages=14, delay=0.6):
    remove_all_opencctv()
    seen = seen_urls()
    new_rows = []
    total_cams = 0

    for page in range(1, max_pages + 1):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            resp = SESSION.get(url, timeout=20)
        except requests.RequestException as exc:
            print(f"!! page {page} unreachable: {exc}")
            break
        if resp.status_code != 200:
            print(f"!! page {page} status {resp.status_code}, stop.")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        page_cams = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not DETAIL_RE.match(href):
                continue
            # exclut les catégories
            if "/category/" in href:
                continue
            full = urljoin("https://opencctv.org", href)
            city = city_from_text(a.get_text(" ", strip=True))
            if not city:
                # fallback sur le segment ville de l'URL
                segs = [x for x in href.split("/") if x]
                # .../france/region/ville/camera
                city = segs[-2] if len(segs) >= 2 else ""
                city = city.replace("-", " ")
                city = " ".join(w.capitalize() for w in city.split())
            if not city:
                continue
            page_cams.append((full, city))

        # dedupe dans la page
        seen_url = set()
        uniq = []
        for u, c in page_cams:
            if u not in seen_url:
                seen_url.add(u)
                uniq.append((u, c))

        added = 0
        for detail_url, city in uniq:
            total_cams += 1
            if detail_url in seen:
                continue
            seen.add(detail_url)
            new_rows.append({"url_youtube": detail_url, "ville": city})
            added += 1

        print(f"[page {page}] {len(uniq)} vraies camera(s), {added} nouvelle(s)")
        if added == 0 and page > 1:
            break
        time.sleep(delay)

    if not new_rows:
        print("Aucune nouvelle webcam.")
        return

    write_header = not CSV_PATH.is_file() or CSV_PATH.stat().st_size == 0
    with CSV_PATH.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                                delimiter=";", lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    print(f"\n=> {len(new_rows)} nouvelles webcams opencctv PACA ajoutees (total traitee: {total_cams})")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=14)
    ap.add_argument("--delay", type=float, default=0.6)
    a = ap.parse_args()
    main(max_pages=a.max_pages, delay=a.delay)
