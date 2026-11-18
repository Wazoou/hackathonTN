"""Collect public webcams from multiple French sources and merge them into

camera-data/cameras.csv (columns: url_youtube;ville), then rebuild the
directory (camera-data/camera.json) with ml/build_camera_directory.py.

Sources currently supported:
  * opencctv.org        - 2,653+ live cameras in France (traffic, ski, beach…)
  * fr.worldcam.eu      - ~711 active cameras in France
  * livepublicwebcams.com - ~98 verified YouTube live streams (FR subset)

Usage:

    python ml/collect_webcams.py [--max-pages 50] [--only opencctv|worldcam|livepublic]

The collector is best-effort: if a source is unreachable or changes its HTML
structure, it is skipped and the remaining sources are still processed.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "camera-data" / "cameras.csv"
BUILD_SCRIPT = ROOT / "ml" / "build_camera_directory.py"

# ---------------------------------------------------------------------------
# French communes (non-exhaustive, used to extract the city from a page title)
# ---------------------------------------------------------------------------
FRENCH_CITIES = sorted({
    "Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Strasbourg",
    "Montpellier", "Bordeaux", "Lille", "Rennes", "Reims", "Le Havre",
    "Saint-Etienne", "Toulon", "Grenoble", "Dijon", "Angers", "Nimes",
    "Villeurbanne", "Le Mans", "Aix-en-Provence", "Clermont-Ferrand",
    "Brest", "Limoges", "Tours", "Amiens", "Perpignan", "Metz", "Besancon",
    "Orleans", "Mulhouse", "Rouen", "Caen", "Nancy", "Saint-Denis", "Argenteuil",
    "Roubaix", "Tourcoing", "Montreuil", "Cayenne", "Fort-de-France",
    "Saint-Pierre", "Mamoudzou", "Saint-Denis", "Saint-Paul", "Saint-Louis",
    "Saint-Andre", "Le Tampon", "Saint-Benoit", "Saint-Leu", "Possession",
    "Sainte-Marie", "Sainte-Suzanne", "Sainte-Clotilde", "Saint-Joseph",
    "Ajaccio", "Bastia", "Calvi", "Propriano", "Porto-Vecchio",
    "Biarritz", "Bayonne", "Anglet", "Hossegor", "Capbreton", "Biscarrosse",
    "Mimizan", "Arcachon", "La Teste-de-Buch", "Carcans", "Hourtin",
    "Cannes", "Antibes", "Juan-les-Pins", "Menton", "Villefranche-sur-Mer",
    "Saint-Tropez", "Sainte-Maxime", "Fréjus", "Saint-Raphaël", "Toulon",
    "Hyères", "Cassis", "Bandol", "Saint-Cyr-sur-Mer", "La Ciotat",
    "Montpellier", "Sète", "Agde", "Cap d'Agde", "Valras-Plage", "Palavas-les-Flots",
    "Banyuls-sur-Mer", "Collioure", "Argelès-sur-Mer", "Canet-en-Roussillon",
    "Saint-Cyprien", "Le Grau-du-Roi", "Aigues-Mortes", "La Grande-Motte",
    "Nantes", "Saint-Nazaire", "La Baule", "Pornichet", "Pornic", "Noirmoutier",
    "Les Sables-d'Olonne", "La Tranche-sur-Mer", "Saint-Jean-de-Monts",
    "Notre-Dame-de-Monts", "Saint-Gilles-Croix-de-Vie", "Piriac-sur-Mer",
    "Le Croisic", "La Turballe", "Quiberon", "Carnac", "La Trinité-sur-Mer",
    "Bénodet", "Concarneau", "Quimper", "Brest", "Lorient", "Vannes",
    "Saint-Malo", "Dinard", "Cancale", "Saint-Brieuc", "Paimpol", "Perros-Guirec",
    "Trébeurden", "Ploumanac'h", "Roscoff", "Ouistreham", "Courseulles-sur-Mer",
    "Trouville-sur-Mer", "Deauville", "Honfleur", "Le Havre", "Dieppe",
    "Fécamp", "Étretat", "Yport", "Veules-les-Roses", "Criel-sur-Mer",
    "Mers-les-Bains", "Le Tréport", "Fort-Mahon-Plage", "Berck", "Le Touquet",
    "Boulogne-sur-Mer", "Calais", "Dunkerque", "Gravelines", "Wissant",
    "Sainte-Maxime", "Ramatuelle", "Gassin", "Grimaud", "Cogolin",
    "Sainte-Anne", "Saint-François", "Deshaies", "Bouillante",
    "Saint-Malo", "Cargèse", "Porto", "Piana", "Girolata", "Scandola",
    "Annecy", "Chamonix", "Megève", "Courchevel", "Méribel", "Val d'Isère",
    "Tignes", "Les Arcs", "La Plagne", "Flaine", "Les Gets", "Morzine",
    "Avoriaz", "Châtel", "Alpe d'Huez", "Les Deux Alpes", "Grenoble",
    "Chambéry", "Aix-les-Bains", "Albertville", "Moûtiers", "Bourg-Saint-Maurice",
    "Ault", "Onival", "Cayeux-sur-Mer", "Mers-les-Bains", "Le Tréport",
    "Brest", "Lorient", "Vannes", "Saint-Nazaire", "La Rochelle", "Royan",
    "Oléron", "Île de Ré", "Arcachon", "Bordeaux", "Bayonne", "Biarritz",
    "Hendaye", "Saint-Jean-de-Luz", "Ciboure", "Urrugne", "Ascain",
    "Sare", "Ainhoa", "Espelette", "Itxassou", "Cambo-les-Bains",
}, key=str.casefold)

# Known webcam image/stream providers (used to recognise direct image URLs)
DIRECT_IMAGE_HOSTS = {
    "images-webcams.windy.com", "trinum.com", "skaping.com", "webcam-hd.com",
    "vision-environnement.com", "viewsurf.com", "livepublicwebcams.com",
}


def extract_city_from_title(title: str, fallback: str | None = None) -> str | None:
    """Try to recognise a French commune inside a page title."""
    if not title:
        return fallback
    title_lower = title.casefold()
    for city in FRENCH_CITIES:
        if city.casefold() in title_lower:
            return city
    return fallback


def extract_city_from_url(url: str) -> str | None:
    """Try to recognise a French commune inside a webcam URL path."""
    if not url:
        return None
    parsed = urlparse(url)
    path = parsed.path.lower()
    segments = [s for s in path.split("/") if s]
    for seg in segments:
        seg_clean = re.sub(r"[-\d]+$", "", seg).replace("-", " ")
        seg_clean = seg_clean.strip()
        for city in FRENCH_CITIES:
            if city.casefold() == seg_clean.casefold():
                return city
    return None


def resolve_city(text: str | None, url: str | None = None) -> str | None:
    """Resolve a city name from page title, falling back to the URL path."""
    city = extract_city_from_title(text) if text else None
    if not city and url:
        city = extract_city_from_url(url)
    return city


def clean_url(url: str) -> str:
    """Normalise a URL (strip tracking params, keep scheme+host+path)."""
    if not url:
        return ""
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return ""
    return parsed.geturl()


def append_rows(rows: list[dict[str, str]]) -> int:
    """Append new rows to the CSV, avoiding duplicates. Returns number added."""
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

    # Ensure the existing file ends with a newline before appending
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


# ===========================================================================
# Source collectors
# ===========================================================================

def collect_opencctv(max_pages: int = 60, delay: float = 0.3) -> list[dict[str, str]]:
    """Scrape opencctv.org France camera list."""
    rows: list[dict[str, str]] = []
    base = "https://opencctv.org/cameras/france"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})

    for page in range(1, max_pages + 1):
        url = f"{base}?page={page}" if page > 1 else base
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                break
        except requests.RequestException:
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Each camera card typically contains a link + title text like
        # "Chessy: Disney Village Live" or "Besancon: Doubs Rivotte Live"
        found_on_page = 0
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or not href:
                continue
            # Only keep camera detail links (they usually contain a slug)
            if not re.search(r"/cameras/france/[\w-]+", href):
                continue
            full_url = urljoin("https://opencctv.org", href)
            city = resolve_city(text, full_url)
            if not city:
                # Try to extract city before the colon: "Besancon: Doubs Rivotte"
                m = re.match(r"^([A-Za-zÀ-ÿ\s\-']+):", text or "")
                if m:
                    city = m.group(1).strip()
            if not city:
                continue
            rows.append({"url": full_url, "ville": city})
            found_on_page += 1

        if found_on_page == 0:
            break
        time.sleep(delay)

    return rows


def collect_worldcam(max_pages: int = 40, delay: float = 0.3) -> list[dict[str, str]]:
    """Scrape fr.worldcam.eu France webcam list."""
    rows: list[dict[str, str]] = []
    base = "https://fr.worldcam.eu/webcams/europe/france"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})

    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}/{page}"
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                break
        except requests.RequestException:
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        found_on_page = 0

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or not href:
                continue
            # Worldcam detail URLs look like /webcams/europe/france/17838-...
            if not re.search(r"/webcams/europe/france/\d+-", href):
                continue
            full_url = urljoin("https://fr.worldcam.eu", href)
            city = resolve_city(text, full_url)
            if not city:
                # "Ville - Nom" -> take the part before the dash
                m = re.match(r"^([A-Za-zÀ-ÿ\s\-']+)\s*[-–]\s*", text or "")
                if m:
                    city = m.group(1).strip()
            if not city:
                continue
            rows.append({"url": full_url, "ville": city})
            found_on_page += 1

        if found_on_page == 0:
            break
        time.sleep(delay)

    return rows


def collect_livepublicwebcams() -> list[dict[str, str]]:
    """Scrape the verified YouTube live streams from livepublicwebcams.com."""
    rows: list[dict[str, str]] = []
    url = "https://livepublicwebcams.com/fr/public-webcams-map"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})

    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            return rows
    except requests.RequestException:
        return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "youtube.com/watch" not in href and "youtu.be/" not in href:
            continue
        text = link.get_text(" ", strip=True)
        parent_text = link.parent.get_text(" ", strip=True) if link.parent else text
        city = resolve_city(parent_text, href) or resolve_city(text, href)
        if not city:
            continue
        rows.append({"url": href, "ville": city})

    return rows


def collect_france_webcams(max_pages: int = 80, delay: float = 0.3) -> list[dict[str, str]]:
    """Scrape france-webcams.fr (1,200+ webcams across France)."""
    rows: list[dict[str, str]] = []
    base = "https://france-webcams.fr/"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})

    # Try regional index pages
    regions = [
        "auvergne-rhone-alpes", "bourgogne-franche-comte", "bretagne",
        "centre-val-de-loire", "corse", "grand-est", "hauts-de-france",
        "ile-de-france", "normandie", "nouvelle-aquitaine", "occitanie",
        "pays-de-la-loile", "pays-de-la-loire", "provence-alpes-cote-dazur",
    ]
    for region in regions:
        url = f"{base}{region}/"
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                continue
        except requests.RequestException:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        found_on_page = 0

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or not href:
                continue
            # Webcam detail pages usually contain an ID number
            if not re.search(r"/webcam[-/]", href):
                continue
            full_url = urljoin(base, href)
            city = resolve_city(text, full_url)
            if not city:
                continue
            rows.append({"url": full_url, "ville": city})
            found_on_page += 1

        time.sleep(delay)

    return rows


def collect_monde_du_voyage(max_pages: int = 50, delay: float = 0.3) -> list[dict[str, str]]:
    """Scrape monde-du-voyage.com/france/webcams (1,131 webcams)."""
    rows: list[dict[str, str]] = []
    base = "https://www.monde-du-voyage.com/france/webcams"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})

    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                break
        except requests.RequestException:
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        found_on_page = 0

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(" ", strip=True)
            if not text or not href:
                continue
            # Detail pages usually mention "Ouvrir la webcam" or contain a provider
            if not re.search(r"/france/webcams/", href):
                continue
            full_url = urljoin(base, href)
            city = resolve_city(text, full_url)
            if not city:
                continue
            rows.append({"url": full_url, "ville": city})
            found_on_page += 1

        if found_on_page == 0:
            break
        time.sleep(delay)

    return rows


# ===========================================================================
# Main
# ===========================================================================

def run(only: str | None = None, max_pages: int = 60) -> None:
    all_rows: list[dict[str, str]] = []

    if only in (None, "opencctv"):
        print("[opencctv.org] Collecting…")
        try:
            rows = collect_opencctv(max_pages=max_pages)
            print(f"  -> {len(rows)} webcams found on opencctv.org")
            all_rows.extend(rows)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! opencctv.org failed: {exc}")

    if only in (None, "worldcam"):
        print("[fr.worldcam.eu] Collecting…")
        try:
            rows = collect_worldcam(max_pages=max_pages)
            print(f"  -> {len(rows)} webcams found on worldcam.eu")
            all_rows.extend(rows)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! worldcam.eu failed: {exc}")

    if only in (None, "livepublic"):
        print("[livepublicwebcams.com] Collecting…")
        try:
            rows = collect_livepublicwebcams()
            print(f"  -> {len(rows)} webcams found on livepublicwebcams.com")
            all_rows.extend(rows)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! livepublicwebcams.com failed: {exc}")

    if only in (None, "francewebcams"):
        print("[france-webcams.fr] Collecting…")
        try:
            rows = collect_france_webcams()
            print(f"  -> {len(rows)} webcams found on france-webcams.fr")
            all_rows.extend(rows)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! france-webcams.fr failed: {exc}")

    if only in (None, "mondevoyage"):
        print("[monde-du-voyage.com] Collecting…")
        try:
            rows = collect_monde_du_voyage()
            print(f"  -> {len(rows)} webcams found on monde-du-voyage.com")
            all_rows.extend(rows)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! monde-du-voyage.com failed: {exc}")

    # Deduplicate by URL before writing
    seen_urls: set[str] = set()
    unique_rows: list[dict[str, str]] = []
    for row in all_rows:
        u = clean_url(row["url"])
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_rows.append({"url": u, "ville": row["ville"]})

    print(f"\nTotal unique webcams collected: {len(unique_rows)}")
    added = append_rows(unique_rows)
    print(f"New rows appended to {CSV_PATH}: {added}")

    # Rebuild the directory in a subprocess so the build script does not
    # receive this collector's CLI flags.
    print(f"\nRebuilding directory with {BUILD_SCRIPT}…")
    import subprocess
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT)],
        capture_output=True, text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f"Build script exited with code {result.returncode}")
        if result.stderr:
            print(result.stderr[-2000:])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect French webcams from public sources")
    parser.add_argument("--only", choices=["opencctv", "worldcam", "livepublic", "francewebcams", "mondevoyage"],
                        help="Only collect from one source")
    parser.add_argument("--max-pages", type=int, default=60,
                        help="Max pages to scrape per paginated source")
    args = parser.parse_args()
    run(only=args.only, max_pages=args.max_pages)
