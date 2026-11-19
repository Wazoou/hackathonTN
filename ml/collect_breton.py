#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecteur de webcams BRETAGNE uniquement (departements 22, 29, 35, 56).
Source : opencctv.org/cameras/france/bretagne (JSON-LD ItemList -> flux direct + ville).
Sortie : bretagne_opencctv.txt  (format URL;ville)
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector bretagne)"})

# Villes bretonnes connues (22, 29, 35, 56) - pour valider / normaliser
BRETON_CITIES = {
    "Saint-Brieuc","Lannion","Perros-Guirec","Ploumanac'h","Trébeurden","Paimpol",
    "Binic","Etables-sur-Mer","Saint-Quay-Portrieux","Erquy","Pléneuf-Val-André",
    "Plouha","Ploubazlanec","Bréhec","Plouezec","Loguivy-de-la-mer","Plogoff",
    "Tréguier","Guingamp","Dinan","Lamballe","Plérin","Plerin","Langueux","Hillion",
    "Brest","Quimper","Concarneau","Douarnenez","Bénodet","Benodet","Audierne",
    "Plougonvelin","Plouarzel","Plouhinec","Plomodiern","Crozon","Camaret-sur-Mer",
    "Roscoff","Plouescat","Cléder","Kerlouan","Trégunc","Tregunc","Moelan-sur-Mer",
    "Moëlan-sur-Mer","Nevez","Pont-l'Abbe","Pont-L'Abbé","Plomeur","Penmarc'h",
    "Penmarche","Locronan","Locquirec","Plouguerneau","Landerneau","Quimperle",
    "Quimperlé","Bannalec","Scaer","Scaër","Rosporden","Fouesnant","Combrit",
    "Loctudy","Ile-Tudy","Île-Tudy","Pouldreuzic","Trebeurden","Treffiagat",
    "Guilvinec","Le Guilvinec","Rennes","Saint-Malo","Dinard","Cancale",
    "Dol-de-Bretagne","Combourg","Fougeres","Fougères","Vitré","Redon",
    "Saint-Pol-de-Léon","Bain-de-Bretagne","Lorient","Vannes","Quiberon","Carnac",
    "Auray","Ploemeur","Lanester","Hennebont","Pontivy","Saint-Gildas-de-Rhuys",
    "Sarzeau","Arzon","Etel","Étel","Locmiquelic","Locmiquélic","Belle-Ile-en-Mer",
    "Belle-Île-en-Mer","Ile-aux-Moines","Île-aux-Moines","Ploeren","Damgan",
    "Port-Louis","Groix","Caudan","Penerf",
}

# Villes de la Loire-Atlantique (44) affichees par erreur sous "Bretagne" par opencctv -> EXCLURE
LOIRE_ATLANTIQUE = {"Nantes","Chapelle","La Chapelle-sur-Erdre","Bouguenais",
                    "Porte de Bouguenais","Porte de Saint-Luce",
                    "Porte de Saint-Luce et la Porte d'Anjou","Saint-Herblain",
                    "Orvault","Coueron","Couëron"}

# Mapping nom foireux -> vraie ville (detecte via l'URL de detail)
URL_CITY_MAP = [
    (r"peripherique-de-rennes", "Rennes"),
    (r"peripherique-de-nantes", None),          # Nantes (44) -> exclure
    (r"n165-a-hauteur-de-caudan", "Caudan"),
    (r"n165-a-hauteur-de-hennebont", "Hennebont"),
    (r"porte-de-bouguenais", None),             # 44 -> exclure
    (r"porte-de-saint-luce", None),             # 44 -> exclure
]


def clean_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    p = urlsplit(u)
    if not p.scheme or not p.hostname:
        return ""
    return p.geturl()


def normalize_city(city: str, detail_url: str) -> str | None:
    """Retourne la ville normalisee, ou None si hors perimetre breton."""
    if not city:
        return None
    c = city.strip()
    # exclure les metadonnées routes / placeholders
    if c.lower() in ("ville",) or c.startswith("N165") or c.startswith("Porte de"):
        # resoudre via l'URL de detail
        for pat, repl in URL_CITY_MAP:
            if re.search(pat, detail_url or ""):
                if repl is None:
                    return None  # hors perimetre (Loire-Atlantique)
                return repl
        return None
    # exclure Loire-Atlantique
    if c in LOIRE_ATLANTIQUE:
        return None
    return c


def collect_opencctv(max_pages: int = 8) -> list[dict]:
    rows = []
    base = "https://opencctv.org/cameras/france/bretagne"
    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            resp = SESSION.get(url, timeout=25)
            if resp.status_code != 200:
                print(f"  [opencctv] page {page}: status {resp.status_code}, stop.")
                break
        except requests.RequestException as e:
            print(f"  [opencctv] page {page}: erreur {e}, stop.")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        found = 0
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text() or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                for el in data.get("itemListElement", []):
                    item = el.get("item", {}) if isinstance(el, dict) else {}
                    content_url = item.get("contentUrl")
                    detail_url = item.get("url", "")
                    loc = item.get("contentLocation", {}) or {}
                    loc_name = loc.get("name", "") if isinstance(loc, dict) else ""
                    # ville depuis contentLocation
                    city = loc_name.split(",")[0].strip() if loc_name else ""
                    city = normalize_city(city, detail_url)
                    if not content_url or not city:
                        continue
                    rows.append({
                        "url": clean_url(content_url),
                        "ville": city,
                        "name": item.get("name", ""),
                        "source": "opencctv",
                    })
                    found += 1
        print(f"  [opencctv] page {page}: {found} camera(s)")
        if found == 0:
            break
        time.sleep(0.4)
    return rows


if __name__ == "__main__":
    rows = collect_opencctv()
    print(f"\nTOTAL opencctv Bretagne (brut): {len(rows)}")
    seen = set()
    uniq = []
    for r in rows:
        if r["url"] not in seen:
            seen.add(r["url"])
            uniq.append(r)
    print(f"Uniques: {len(uniq)}")
    with open("bretagne_opencctv.txt", "w", encoding="utf-8") as f:
        for r in uniq:
            f.write(f'{r["url"]};{r["ville"]}\n')
    print("Ecrit dans bretagne_opencctv.txt")
