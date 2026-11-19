#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecteur france-webcams.fr - BRETAGNE uniquement.
1. Liste toutes les pages de detalle des webcams depuis les sections departementales
   (22, 29, 35, 56), pagination comprise.
2. Ouvre chaque page de detalle pour recupérer l'URL externe de la webcam
   (vision-environnement, viewsurf, etc.) et la ville.
Sauvegarde incrémentale dans bretagne_francewebcams.txt pour reprise en cas d'interruption.
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
OUT = Path("bretagne_francewebcams.txt")

DEPTS = {
    "22": "https://france-webcams.fr/bretagne/2.26-22-cotes-d-armor.html",
    "29": "https://france-webcams.fr/bretagne/2.27-29-finistere.html",
    "35": "https://france-webcams.fr/bretagne/2.28-35-ille-et-vilaine.html",
    "56": "https://france-webcams.fr/bretagne/2.29-56-morbihan.html",
}

BRETON_CITIES = sorted({
    "Saint-Brieuc","Lannion","Perros-Guirec","Ploumanac'h","Trébeurden","Paimpol",
    "Binic","Etables-sur-Mer","Saint-Quay-Portrieux","Erquy","Pléneuf-Val-André",
    "Plouha","Ploubazlanec","Bréhec","Plouezec","Loguivy-de-la-mer","Plogoff",
    "Tréguier","Guingamp","Dinan","Lamballe","Plérin","Plerin","Langueux","Hillion",
    "Ploumagoar","Pordic","Quessy","Yffiniac","Lantic","Ploufragan","Tramain",
    "Brest","Quimper","Concarneau","Douarnenez","Bénodet","Benodet","Audierne",
    "Plougonvelin","Plouarzel","Plouhinec","Plomodiern","Crozon","Camaret-sur-Mer",
    "Roscoff","Plouescat","Cléder","Kerlouan","Trégunc","Tregunc","Moelan-sur-Mer",
    "Moëlan-sur-Mer","Nevez","Pont-l'Abbe","Pont-L'Abbé","Plomeur","Penmarc'h",
    "Penmarche","Locronan","Locquirec","Plouguerneau","Landerneau","Quimperle",
    "Quimperlé","Bannalec","Scaer","Scaër","Rosporden","Fouesnant","Combrit",
    "Loctudy","Ile-Tudy","Île-Tudy","Pouldreuzic","Trebeurden","Treffiagat",
    "Guilvinec","Le Guilvinec","Plomelin","Pluguffan","Ergue-Gaberic","Ergué-Gabéric",
    "Rennes","Saint-Malo","Dinard","Cancale","Dol-de-Bretagne","Combourg",
    "Fougeres","Fougères","Vitré","Redon","Saint-Pol-de-Léon","Bain-de-Bretagne",
    "Lorient","Vannes","Quiberon","Carnac","Auray","Ploemeur","Lanester",
    "Hennebont","Pontivy","Saint-Gildas-de-Rhuys","Sarzeau","Arzon","Etel","Étel",
    "Locmiquelic","Locmiquélic","Belle-Ile-en-Mer","Belle-Île-en-Mer",
    "Ile-aux-Moines","Île-aux-Moines","Ploeren","Damgan","Port-Louis","Groix",
    "Caudan","Penerf","Questembert","Muzillac","Allaire",
    "Sainte-Anne-d'Auray","Baud","Plouay","Guidel","Ploemel",
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


def list_detail_urls() -> list[dict]:
    items = []
    for dept, start_url in DEPTS.items():
        page = 1
        while True:
            url = start_url if page == 1 else f"{start_url}?p={page - 1}"
            try:
                resp = SESSION.get(url, timeout=25)
                if resp.status_code != 200:
                    break
            except requests.RequestException:
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            count = 0
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
                items.append({"detail_url": full, "title": title, "ville": extract_city(title), "dept": dept})
                count += 1
            print(f"  [fw dept {dept}] page {page}: {count}")
            if not soup.select_one(".navp a.navp"):
                break
            page += 1
            time.sleep(0.15)
        time.sleep(0.15)
    return items


def extract_external(detail_url: str) -> str | None:
    try:
        resp = SESSION.get(detail_url, timeout=20)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    # champ "URL :"
    for label in soup.find_all(string=re.compile(r"^URL\s*:", re.I)):
        parent = label.parent
        if parent:
            a = parent.find("a", href=True)
            if a and "france-webcams.fr" not in a["href"]:
                return clean_url(a["href"])
    # premier lien externe non-reseau-social
    for a in soup.find_all("a", href=True):
        u = a["href"]
        if "france-webcams.fr" in u:
            continue
        if any(s in u for s in ("twitter.com", "facebook.com", "instagram.com", "youtube.com", "x.com", "youtu.be")):
            continue
        if u.startswith("http"):
            return clean_url(u)
    return None


def load_done() -> set:
    done = set()
    if OUT.is_file():
        with OUT.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ";" in line:
                    done.add(line.split(";", 1)[0])
    return done


if __name__ == "__main__":
    done = load_done()
    items = list_detail_urls()
    print(f"\n[fw] pages de detalle listees: {len(items)} (deja traitees: {len(done)})")

    new_count = 0
    with OUT.open("a", encoding="utf-8") as f:
        for it in items:
            if it["detail_url"] in done:
                continue
            ext = extract_external(it["detail_url"])
            ville = it["ville"]
            if not ville:
                ville = extract_city(it["title"])
            if ext and ville:
                f.write(f"{ext};{ville}\n")
                new_count += 1
            elif ext:
                f.write(f"{ext};Inconnu\n")
                new_count += 1
            time.sleep(0.15)

    # dedup final
    seen = set()
    uniq = []
    if OUT.is_file():
        with OUT.open(encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                u = line.split(";", 1)[0]
                if u not in seen:
                    seen.add(u)
                    uniq.append(line)
    with OUT.open("w", encoding="utf-8") as f:
        for line in uniq:
            f.write(line + "\n")
    print(f"[fw] nouveaux ajoutes: {new_count}, total uniques dans fichier: {len(uniq)}")
