#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecteur france-webcams.fr BRETAGNE (borne).
- 1ere page de chaque departement (22, 29, 35, 56) -> URLs de detail
- Ouverture de chaque detail pour extraire l'URL externe (vision-environnement, viewsurf, youtube...)
Sortie : bretagne_francewebcams_bounded.txt  (format URL;ville)
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector bretagne fw)"})

BASE = "https://france-webcams.fr"
OUT = Path("bretagne_francewebcams_bounded.txt")

DEPTS = {
    "22": "https://france-webcams.fr/bretagne/2.26-22-cotes-d-armor.html",
    "29": "https://france-webcams.fr/bretagne/2.27-29-finistere.html",
    "35": "https://france-webcams.fr/bretagne/2.28-35-ille-et-vilaine.html",
    "56": "https://france-webcams.fr/bretagne/2.29-56-morbihan.html",
}

BRETON_CITIES = sorted({
    "Rennes","Brest","Saint-Malo","Lorient","Vannes","Quimper","Saint-Brieuc",
    "Concarneau","Douarnenez","Perros-Guirec","Carnac","Quiberon","Paimpol",
    "Morlaix","Lannion","Dinan","Fougères","Fougeres","Vitré","Vitre","Redon",
    "Saint-Pol-de-Léon","Guingamp","Lamballe","Plérin","Plerin","Audierne",
    "Bénodet","Benodet","Crozon","Camaret","Roscoff","Plouguerneau","Landerneau",
    "Quimperlé","Quimperle","Fouesnant","Locronan","Plouhinec","Plomodiern",
    "Trégunc","Tregunc","Moëlan-sur-Mer","Moelan-sur-Mer","Nevez","Pont-l'Abbé",
    "Plomeur","Penmarc'h","Penmarche","Locquirec","Plouescat","Cléder","Kerlouan",
    "Bannalec","Scaër","Scaer","Rosporden","Combrit","Loctudy","Pouldreuzic",
    "Guilvinec","Ergué-Gabéric","Ergue-Gabéric","Pluguffan","Plomelin",
    "Dol-de-Bretagne","Combourg","Bain-de-Bretagne","Auray","Ploemeur","Lanester",
    "Hennebont","Pontivy","Saint-Gildas-de-Rhuys","Sarzeau","Arzon","Étel","Etel",
    "Locmiquélic","Locmiquelic","Belle-Île-en-Mer","Belle-Ile-en-Mer",
    "Île-aux-Moines","Ile-aux-Moines","Ploeren","Damgan","Port-Louis","Groix",
    "Caudan","Penerf","Questembert","Muzillac","Allaire","Sainte-Anne-d'Auray",
    "Baud","Plouay","Guidel","Ploemel","Landéda","Penmarch","Plestin-les-Grèves",
    "Trébeurden","Trebeurden","Binic","Etables-sur-Mer","Erquy","Pléneuf",
    "Plouha","Tréguier","Treguier","Ploumanac'h","Plouezec","Loguivy","Plogoff",
    "Langueux","Hillion","Ploumagoar","Pordic","Yffiniac","Lantic","Ploufragan",
    "Tramain","Saint-Quay-Portrieux","Lancieux","Trévou-Tréguignec","Trevou-Treguignec",
    "Pont-Aven","Pont-l'Abbe","Pointe du Raz","La Trinité-sur-Mer","La Trinite-sur-Mer",
    "Île-Tudy","Ile-Tudy","La Forêt-Fouesnant","Pénestin","Penestin","Plobannalec",
    "Lesconil","Ploudalmézeau","Portsall","Plouescat","Plouézec","Port Lazo",
    "Plougasnou","Térénez","Terenez","Plougonvelin","Trez-Hir",
}, key=str.casefold)


def clean_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    p = urlsplit(u)
    if not p.scheme or not p.hostname:
        return ""
    return p.geturl()


def extract_city(title: str) -> str | None:
    if not title:
        return None
    tl = title.casefold()
    for city in BRETON_CITIES:
        if city.casefold() in tl:
            return city
    return None


def list_detail_urls(start_url: str) -> list[dict]:
    items = []
    try:
        resp = SESSION.get(start_url, timeout=25)
        if resp.status_code != 200:
            return items
    except requests.RequestException:
        return items
    soup = BeautifulSoup(resp.text, "html.parser")
    for h2 in soup.select("h2.titre_site a, .titre_site a"):
        href = h2.get("href")
        title = h2.get_text(" ", strip=True)
        if not href:
            continue
        full = urljoin(BASE, href)
        if "/bretagne/" not in full:
            continue
        if not re.search(r"/1\.\d+-", full):
            continue
        items.append({"detail_url": full, "title": title, "ville": extract_city(title)})
    return items


def extract_external(detail_url: str) -> str | None:
    try:
        resp = SESSION.get(detail_url, timeout=20)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for label in soup.find_all(string=re.compile(r"^URL\s*:", re.I)):
        parent = label.parent
        if parent:
            a = parent.find("a", href=True)
            if a and "france-webcams.fr" not in a["href"]:
                return clean_url(a["href"])
    for a in soup.find_all("a", href=True):
        u = a["href"]
        if "france-webcams.fr" in u:
            continue
        if any(s in u for s in ("twitter.com", "facebook.com", "instagram.com", "youtube.com", "x.com", "youtu.be")):
            continue
        if u.startswith("http"):
            return clean_url(u)
    return None


def main():
    all_items = []
    for dept, start_url in DEPTS.items():
        items = list_detail_urls(start_url)
        print(f"  [fw dept {dept}] page 1: {len(items)} detail URLs")
        all_items.extend(items)
        time.sleep(0.2)

    # dedup detail URLs
    seen = set()
    uniq = []
    for it in all_items:
        if it["detail_url"] not in seen:
            seen.add(it["detail_url"])
            uniq.append(it)
    print(f"\nTotal detail URLs uniques: {len(uniq)}")

    rows = []
    for it in uniq:
        ext = extract_external(it["detail_url"])
        ville = it["ville"]
        if not ville:
            ville = extract_city(it["title"])
        if ext and ville:
            rows.append((ext, ville))
        elif ext:
            rows.append((ext, "Inconnu"))
        time.sleep(0.15)

    # dedup by external URL
    seen_urls = set()
    final = []
    for u, v in rows:
        if u not in seen_urls:
            seen_urls.add(u)
            final.append((u, v))

    with open(OUT, "w", encoding="utf-8") as f:
        for u, v in final:
            f.write(f"{u};{v}\n")
    print(f"\nEcrit dans {OUT}: {len(final)} webcams")
    for u, v in final:
        print(f"  {v} | {u}")


if __name__ == "__main__":
    main()
