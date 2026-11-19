#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrait les URLs de detail webcam Bretagne depuis fr.worldcam.eu (3 pages).
Sortie : worldcam_brittany.txt  (format URL;ville)
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector bretagne)"})

BASE = "https://fr.worldcam.eu/webcams/europe/france/brittany"
OUT = Path_out = None  # placeholder

BRETON_CITIES = sorted({
    "Rennes","Brest","Saint-Malo","Lorient","Vannes","Quimper","Saint-Brieuc",
    "Concarneau","Douarnenez","Perros-Guirec","Carnac","Quiberon","Paimpol",
    "Morlaix","Lannion","Dinan","Fougères","Fougeres","Vitré","Vitre","Redon",
    "Saint-Pol-de-Léon","Guingamp","Lamballe","Plérin","Plerin","Audierne",
    "Concarneau","Douarnenez","Bénodet","Benodet","Audierne","Crozon","Camaret",
    "Roscoff","Plouguerneau","Landerneau","Quimperlé","Quimperle","Fouesnant",
    "Locronan","Plouhinec","Plomodiern","Trégunc","Tregunc","Moëlan-sur-Mer",
    "Moelan-sur-Mer","Nevez","Pont-l'Abbé","Plomeur","Penmarc'h","Penmarche",
    "Locquirec","Plouescat","Cléder","Kerlouan","Bannalec","Scaër","Scaer",
    "Rosporden","Combrit","Loctudy","Pouldreuzic","Guilvinec","Ergué-Gabéric",
    "Ergue-Gabéric","Pluguffan","Plomelin","Dol-de-Bretagne","Combourg",
    "Bain-de-Bretagne","Auray","Ploemeur","Lanester","Hennebont","Pontivy",
    "Saint-Gildas-de-Rhuys","Sarzeau","Arzon","Étel","Etel","Locmiquélic",
    "Locmiquelic","Belle-Île-en-Mer","Belle-Ile-en-Mer","Île-aux-Moines",
    "Ile-aux-Moines","Ploeren","Damgan","Port-Louis","Groix","Caudan","Penerf",
    "Questembert","Muzillac","Allaire","Sainte-Anne-d'Auray","Baud","Plouay",
    "Guidel","Ploemel","Landéda","Landa","Penmarch","Plestin-les-Grèves",
    "Trébeurden","Trebeurden","Binic","Etables-sur-Mer","Erquy","Pléneuf",
    "Plouha","Tréguier","Treguier","Ploumanac'h","Plouezec","Loguivy",
    "Plogoff","Plouha","Langueux","Hillion","Ploumagoar","Pordic","Yffiniac",
    "Lantic","Ploufragan","Tramain","Saint-Quay-Portrieux","Lancieux",
    "Trévou-Tréguignec","Trevou-Treguignec","Pont-Aven","Pont-l'Abbe",
    "Pointe du Raz","La Trinité-sur-Mer","La Trinite-sur-Mer","Île-Tudy",
    "Ile-Tudy","La Forêt-Fouesnant","Pénestin","Penestin","Plobannalec",
    "Lesconil","Ploudalmézeau","Portsall","Plouescat","Plouézec","Port Lazo",
    "Plougasnou","Térénez","Terenez","Plougonvelin","Trez-Hir","Sarzeau",
    "Port Saint Jacques",
}, key=str.casefold)


def clean_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    p = urlparse(u)
    if not p.scheme or not p.hostname:
        return ""
    return p.geturl()


def extract_city(text: str) -> str | None:
    if not text:
        return None
    tl = text.casefold()
    for city in BRETON_CITIES:
        if city.casefold() in tl:
            return city
    return None


def fetch_page(page: int) -> list[dict]:
    url = BASE if page == 1 else f"{BASE}/p/{page}"
    try:
        resp = SESSION.get(url, timeout=25)
    except requests.RequestException as e:
        print(f"  [worldcam] page {page}: erreur {e}")
        return []
    if resp.status_code != 200:
        print(f"  [worldcam] page {page}: status {resp.status_code}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(" ", strip=True)
        if not text or not href:
            continue
        if not re.search(r"/webcams/europe/france/\d+-", href):
            continue
        full = clean_url(urljoin("https://fr.worldcam.eu", href))
        city = extract_city(text) or extract_city(full)
        rows.append({"url": full, "ville": city or "Inconnu", "text": text})
    return rows


def main():
    all_rows = []
    for page in range(1, 4):
        rows = fetch_page(page)
        print(f"  [worldcam] page {page}: {len(rows)} lien(s) detail")
        all_rows.extend(rows)
        time.sleep(0.3)

    # dedup by url
    seen = set()
    uniq = []
    for r in all_rows:
        if r["url"] not in seen:
            seen.add(r["url"])
            uniq.append(r)
    print(f"\nTotal detail URLs uniques worldcam Bretagne: {len(uniq)}")

    with open("worldcam_brittany.txt", "w", encoding="utf-8") as f:
        for r in uniq:
            f.write(f'{r["url"]};{r["ville"]}\n')
    print("Ecrit dans worldcam_brittany.txt")
    for r in uniq:
        print(f"  {r['ville']} | {r['text']} | {r['url']}")


if __name__ == "__main__":
    main()
