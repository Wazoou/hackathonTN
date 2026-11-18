"""Données climatologiques quotidiennes Météo-France (toutes stations) par département.

Jeu « Données climatologiques de base - quotidiennes » (data.gouv.fr, Licence Ouverte) :
pour chaque département, un fichier historique (1950 à l'an dernier) et un fichier
récent (mis à jour chaque jour), en deux familles : RR-T-Vent (pluie, températures, vent)
et autres-paramètres (humidité). Les noms changent chaque année : on les lit dans
l'API data.gouv.fr plutôt que de les écrire en dur. Les fichiers déjà présents ne sont
retéléchargés que s'ils ont changé de taille (le fichier récent change chaque jour).

    python ml/download_meteo.py --out ifm_plus/data/raw/meteo --departements 06 07 13 33 34 40 83
"""
import argparse
import re
from pathlib import Path

import requests

DATASET = "https://www.data.gouv.fr/api/1/datasets/donnees-climatologiques-de-base-quotidiennes/"
PATTERN = re.compile(r"Q_(?P<dept>\w{2,3})_(?P<period>previous|latest)-\d{4}-\d{4}_(RR-T-Vent|autres-parametres)\.csv\.gz$")


def resources(depts):
    data = requests.get(DATASET, timeout=60).json()
    wanted = []
    for r in data["resources"]:
        name = r["url"].rsplit("/", 1)[-1]
        match = PATTERN.match(name)
        if match and match["dept"] in depts:
            wanted.append((name, r["url"], r.get("filesize")))
    missing = set(depts) - {PATTERN.match(n)["dept"] for n, _, _ in wanted}
    if missing:
        raise RuntimeError(f"Aucun fichier Météo-France pour : {', '.join(sorted(missing))}")
    return wanted


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--departements", nargs="+", required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, url, size in resources(args.departements):
        target = args.out / name
        if target.exists() and size and target.stat().st_size == size:
            continue
        # Une seule version par famille : on retire l'ancienne période (ex. latest-2024-2025).
        family = name.split("-", 1)[0], name.rsplit("_", 1)[-1]
        for old in args.out.glob(f"{family[0]}-*_{family[1]}"):
            if old.name != name:
                old.unlink()
        with requests.get(url, stream=True, timeout=300) as response:
            response.raise_for_status()
            tmp = target.with_suffix(".part")
            with tmp.open("wb") as handle:
                for chunk in response.iter_content(1 << 20):
                    handle.write(chunk)
            tmp.replace(target)
        print(f"{name} ({target.stat().st_size / 1e6:.1f} Mo)")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
