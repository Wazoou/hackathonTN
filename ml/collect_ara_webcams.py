"""Collect Auvergne-Rhone-Alpes webcams from opencctv.org and fr.worldcam.eu.

Appends results (url;ville) to camera-data/cameras.csv, avoiding duplicates.
"""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "camera-data" / "cameras.csv"

# Communes Auvergne-Rhone-Alpes (pour extraire la ville quand le titre ne suffit pas)
ARA_CITIES = sorted({
    "Lyon", "Grenoble", "Chambery", "Chambéry", "Annecy", "Saint-Etienne", "Saint-Étienne",
    "Clermont-Ferrand", "Vienne", "Valence", "Bourg-en-Bresse", "Montelimar", "Montélimar",
    "Roanne", "Aurillac", "Le Puy-en-Velay", "Chamonix", "Chamonix-Mont-Blanc", "Megève", "Megeve",
    "Courchevel", "Meribel", "Méribel", "Val d'Isere", "Val-d'Isère", "Tignes", "Albertville",
    "Moûtiers", "Aix-les-Bains", "Villefranche-sur-Saone", "Villefranche-sur-Saône",
    "Montmarault", "Mont-Dore", "Montferrat", "Montmarault", "Montceau-les-Mines",
    "Saint-Gervais-les-Bains", "Saint-Martin-d'Ardeche", "Saint-Martin-d'Hères",
    "Saint-Pierre-de-Belleville", "Saint-Sorlin-d'Arves", "Saint-Jeoire",
    "Saint-Julien-en-Genevois", "Saint-Laurent-en-Royans", "Saint-Maurice-de-Beynost",
    "Sainte-Foy-Tarentaise", "Salers", "Sciez", "Soyons", "Talloires-Montmin", "Thones", "Thônes",
    "Toulon-sur-Allier", "Val de Chaise", "Val Thorens", "Valserhone", "Verel-Pragondran",
    "Vesancy", "Villarodin-Bourget", "Villerest", "Violay", "Voreppe",
    "Abondance", "Aillon-le-Jeune", "Aillon-le-Vieux", "Albiez-Montrond", "Albon", "Allevard",
    "Andrezieux-Boutheon", "Andrezieux-Boutheon", "Anse", "Arandon-Passins", "Aussois",
    "Autrans-Meaudre en Vercors", "Barby", "Bard", "Bernex", "Bessans", "Besse-et-Saint-Anastaise",
    "Bonneval-sur-Arc", "Bourget-en-Huile", "Bourg-Saint-Maurice", "Bouvante", "Brindas",
    "Brides-les-Bains", "Cordon", "Corbonod", "Courchevel", "Cruseilles", "Demi-Quartier",
    "Domerat", "Ecully", "Ecully", "Etrebieres", "Etrembieres", "Ferrieres-sur-Sichon",
    "Flaine", "Flumet", "Frontenas", "Giron", "Gresse-en-Vercors", "Guilherand-Granges",
    "Habere-Poche", "Haut Valromey", "Hauteville", "Huez", "Jarrier", "La Chapelle-d'Abondance",
    "La Chapelle-en-Vercors", "La Chapelle-Rambaud", "La Combe-de-Lancey", "La Giettaz",
    "La Motte-Servolex", "La Plagne-Tarentaise", "La Roche-sur-Foron", "La Tour-en-Maurienne",
    "La Voulte-sur-Rhone", "Laveissiere", "Le Beage", "Le Bessat", "Le Pouzin",
    "Le Reposoir", "Leoncel", "Les Allues", "Les Carroz", "Les Deux Alpes",
    "Les Gets", "Les Contamines-Montjoie", "Loudes", "Magland", "Manigod",
    "Marcols-les-Eaux", "Menthon-Saint-Bernard", "Mezilhac", "Mieussy", "Mijoux",
    "Modane", "Montricher-Albanne", "Murat-le-Quaire", "Noiret table", "Noirétable",
    "Ontex", "Orcines", "Orelle", "Oullins", "Perigny", "Perouges", "Peyrieu", "Planay",
    "Pralognan-la-Vanoise", "Praz-sur-Arly", "Reventin-Vaugris", "Rochemaure", "Romans-sur-Isere",
    "Routière France", "Sain-Bel", "Saint-Agreve", "Saint-Antheme", "Saint-Appolinard",
    "Saint-Bonnet-le-Froid", "Saint-Colomban-des-Villards", "Saint-Etienne-de-Fontbellon",
    "Saint-Etienne-de-Lugdares", "Saint-Genes-Champanelle", "Saint-Jacques-des-Blats",
    "Saint-Jean-de-Maurienne", "Saint-Jean-en-Royans", "Saint-Colomban-des-Villards",
    "Taninges", "Villard-sur-Doron", "Villefranche-sur-Saone", "Voisins",
}, key=str.casefold)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (ARA-webcam-collector)"})


def clean_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return ""
    return parsed.geturl()


def extract_city(text: str, url: str) -> str | None:
    """Extraire la ville depuis le texte ou l'URL."""
    if not text:
        return None
    text_lower = text.casefold()
    # Cherche une ville ARA connue dans le texte
    for city in ARA_CITIES:
        if city.casefold() in text_lower:
            return city
    # Fallback: extraire depuis le chemin d'URL
    parsed = urlparse(url)
    path = parsed.path.lower()
    segments = [s for s in path.split("/") if s]
    for seg in segments:
        seg_clean = re.sub(r"[-\d]+$", "", seg).replace("-", " ").strip()
        for city in ARA_CITIES:
            if city.casefold() == seg_clean.casefold():
                return city
    # Prendre le premier mot avant la virgule (pattern "Ville, Region")
    m = re.match(r"^([A-Za-zÀ-ÿ\s\-']+?)\s*,", text.strip())
    if m:
        candidate = m.group(1).strip()
        for city in ARA_CITIES:
            if city.casefold() == candidate.casefold():
                return city
        return candidate  # retour brut si pas dans la liste
    return None


def append_rows(rows: list[dict[str, str]]) -> int:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if CSV_PATH.is_file():
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                u = (row.get("url_youtube") or "").strip()
                if u:
                    seen.add(u)

    new_rows = []
    for row in rows:
        url = clean_url(row["url"])
        city = (row.get("ville") or "").strip()
        if not url or not city:
            continue
        if url in seen:
            continue
        seen.add(url)
        new_rows.append({"url_youtube": url, "ville": city})

    if not new_rows:
        return 0

    if CSV_PATH.is_file() and CSV_PATH.stat().st_size > 0:
        with CSV_PATH.open("rb") as fh:
            fh.seek(-1, 2)
            last_byte = fh.read(1)
        if last_byte != b"\n":
            with CSV_PATH.open("ab") as fh:
                fh.write(b"\n")

    write_header = not CSV_PATH.is_file() or CSV_PATH.stat().st_size == 0
    with CSV_PATH.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                                delimiter=";", lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def collect_opencctv_ara(max_pages: int = 23) -> list[dict[str, str]]:
    """Scrape opencctv.org Auvergne-Rhone-Alpes regional pages."""
    rows: list[dict[str, str]] = []
    base = "https://opencctv.org/cameras/france/auvergne-rhone-alpes"
    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            resp = SESSION.get(url, timeout=25)
            if resp.status_code != 200:
                print(f"  [opencctv] page {page}: status {resp.status_code}, stop.")
                break
        except requests.RequestException as exc:
            print(f"  [opencctv] page {page}: erreur {exc}, stop.")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        found = 0
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or not href:
                continue
            # Detail camera links
            if not re.search(r"/cameras/france/auvergne-rhone-alpes/", href):
                continue
            full_url = urljoin("https://opencctv.org", href)
            city = extract_city(text, full_url)
            if not city:
                continue
            rows.append({"url": full_url, "ville": city})
            found += 1
        print(f"  [opencctv] page {page}: {found} camera(s)")
        time.sleep(0.25)
    return rows


def collect_worldcam_ara(max_pages: int = 6) -> list[dict[str, str]]:
    """Scrape fr.worldcam.eu Auvergne-Rhone-Alpes regional pages."""
    rows: list[dict[str, str]] = []
    base = "https://fr.worldcam.eu/webcams/europe/france/auvergne-rhone-alpes"
    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}/p/{page}"
        try:
            resp = SESSION.get(url, timeout=25)
            if resp.status_code != 200:
                print(f"  [worldcam] page {page}: status {resp.status_code}, stop.")
                break
        except requests.RequestException as exc:
            print(f"  [worldcam] page {page}: erreur {exc}, stop.")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        found = 0
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or not href:
                continue
            # Worldcam detail URLs look like /webcams/europe/france/1234-slug
            if not re.search(r"/webcams/europe/france/\d+-", href):
                continue
            full_url = urljoin("https://fr.worldcam.eu", href)
            city = extract_city(text, full_url)
            if not city:
                continue
            rows.append({"url": full_url, "ville": city})
            found += 1
        print(f"  [worldcam] page {page}: {found} webcam(s)")
        time.sleep(0.25)
    return rows


def main():
    all_rows: list[dict[str, str]] = []

    print("[opencctv.org ARA] Collecting…")
    try:
        rows = collect_opencctv_ara()
        print(f"  -> {len(rows)} webcams opencctv.org ARA")
        all_rows.extend(rows)
    except Exception as exc:
        print(f"  !! opencctv.org ARA failed: {exc}")

    print("[fr.worldcam.eu ARA] Collecting…")
    try:
        rows = collect_worldcam_ara()
        print(f"  -> {len(rows)} webcams worldcam.eu ARA")
        all_rows.extend(rows)
    except Exception as exc:
        print(f"  !! worldcam.eu ARA failed: {exc}")

    # Dedup
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for row in all_rows:
        u = clean_url(row["url"])
        if u and u not in seen:
            seen.add(u)
            unique.append({"url": u, "ville": row["ville"]})

    print(f"\nTotal unique ARA webcams: {len(unique)}")
    added = append_rows(unique)
    print(f"New rows appended to {CSV_PATH}: {added}")


if __name__ == "__main__":
    main()
