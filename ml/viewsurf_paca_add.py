"""Extrait tous les liens webcam viewsurf de la region PACA depuis la page
d'accueil et les ajoute au CSV avec la ville derivee de l'URL.
URL complete : https://www.viewsurf.com + chemin /univers/.../vue/ID-...
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CSV = Path("camera-data/cameras.csv")
HOME = "https://www.viewsurf.com/"

PACA_CITY_FIX = {
    "lancon-provence": "Lançon-Provence",
    "vedene": "Vedène",
    "la-saulce": "La Saulce",
    "aix-en-provence": "Aix-en-Provence",
    "grasse": "Grasse",
    "menton": "Menton",
    "nice": "Nice",
    "cannes": "Cannes",
    "toulon": "Toulon",
    "saint-tropez": "Saint-Tropez",
    "saint-raphael": "Saint-Raphaël",
    "sainte-maxime": "Sainte-Maxime",
    "sanary-sur-mer": "Sanary-sur-Mer",
    "cavalaire-sur-mer": "Cavalaire-sur-Mer",
    "cassis": "Cassis",
    "la-ciotat": "La Ciotat",
    "cap-dail": "Cap-d'Ail",
    "vallauris": "Vallauris",
    "grimaud": "Grimaud",
    "cagnes-sur-mer": "Cagnes-sur-Mer",
    "la-londe-les-maures": "La Londe-les-Maures",
    "miramas": "Miramas",
    "gap": "Gap",
    "neveche": "Névache",
    "abries-ristolas": "Abriès-Ristolas",
    "ceillac": "Ceillac",
    "larche": "Larche",
    "colmars": "Colmars",
    "saint-jean-saint-nicolas": "Saint-Jean-Saint-Nicolas",
    "saint-etienne-en-devoluy": "Saint-Étienne-en-Dévoluy",
    "les-orres": "Les Orres",
    "le-vernet": "Le Vernet",
    "le-sauze": "Le Sauze",
    "le-monetier-les-bains": "Le Monêtier-les-Bains",
    "vallouise": "Vallouise",
    "molines-en-queyras": "Molines-en-Queyras",
    "crevoux": "Crevoux",
    "arvieux": "Arvieux",
    "saint-paul-sur-ubaye": "Saint-Paul-sur-Ubaye",
    "la-condamine-chatelard": "La Condamine-Chatelard",
    "meolans-revel": "Méolans-Revel",
    "barcelonnette": "Barcelonnette",
    "villar-saint-pancrace": "Villar-Saint-Pancrace",
    "la-chapelle-en-valgaudemar": "La Chapelle-en-Valgaudemar",
    "cervieres": "Cervières",
    "la-salle-les-alpes": "La Salle-les-Alpes",
    "seyne-les-alpes": "Seyne-les-Alpes",
    "ile-du-levant": "Île du Levant",
    "nevache": "Névache",
    "saint raphael": "Saint-Raphaël",
    "frejus": "Fréjus",
    "sainte maxime": "Sainte-Maxime",
    "saint tropez": "Saint-Tropez",
    "saint jean saint nicolas": "Saint-Jean-Saint-Nicolas",
    "saint etienne en devoluy": "Saint-Étienne-en-Dévoluy",
    "le monetier les bains": "Le Monêtier-les-Bains",
    "saint paul sur ubaye": "Saint-Paul-sur-Ubaye",
    "la condamine chatelard": "La Condamine-Chatelard",
    "villar saint pancrace": "Villar-Saint-Pancrace",
    "la chapelle en valgaudemar": "La Chapelle-en-Valgaudemar",
    "seyne les alpes": "Seyne-les-Alpes",
    "ile du levant": "Île du Levant",
}


STOP = {"ski","panoramique","hd","live","depart","retour","vide","espace","domaine","piste",
        "chalet","port","plage","centre","vieux","golfe","ile","etang","a8","a7","a51","a50",
        "a52","a57","a54","a56","autoroute","nord","sud","est","ouest","vers","au","a","de",
        "des","du","le","la","les","d","hiver","ete","printemps","automne","video","direct",
        "station","vue","cam","cam2","cam3","livecam"}

def ville_from_url(path):
    m = re.search(r"-france-provence-alpes-cote-dazur-(.+)$", path)
    if not m:
        return None
    ville_slug = m.group(1)
    # autoroute : couper au numero d'autoroute
    ville_slug = re.split(r"\b(a7|a8|a51|a50|a52|a57|a54|a56|a55|a53|autoroute)\b", ville_slug)[0]
    ville_slug = ville_slug.rstrip("-")
    if ville_slug in PACA_CITY_FIX:
        return PACA_CITY_FIX[ville_slug]
    words = [w for w in ville_slug.split("-") if w and w not in STOP]
    if not words:
        return None
    base = " ".join(words[:3]).lower()
    if base in PACA_CITY_FIX:
        return PACA_CITY_FIX[base]
    return " ".join(w.capitalize() for w in base.split())


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
    r = s.get(HOME, timeout=25)
    html = r.text
    pat = re.compile(r'href="([^"]*france-provence-alpes-cote-dazur[^"]*)"')
    links = sorted(set(pat.findall(html)))
    seen = set()
    if CSV.is_file():
        with CSV.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                u = (row.get("url_youtube") or "").strip()
                if u:
                    seen.add(u)
    new = []
    for path in links:
        full = "https://www.viewsurf.com" + path
        ville = ville_from_url(path)
        if not ville:
            continue
        if full in seen:
            continue
        seen.add(full)
        new.append({"url_youtube": full, "ville": ville})
    if not new:
        print("Aucune nouvelle viewsurf PACA.")
        return
    header_needed = not CSV.is_file() or CSV.stat().st_size == 0
    with CSV.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                           delimiter=";", lineterminator="\n")
        if header_needed:
            w.writeheader()
        w.writerows(new)
    print(f"viewsurf PACA ajoutees: {len(new)}")
    for row in new:
        print("  ", row["ville"], "<-", row["url_youtube"])


if __name__ == "__main__":
    main()
