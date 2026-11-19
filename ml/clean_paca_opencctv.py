"""Regénère mes 220 entrées opencctv PACA avec des villes propres
(ville = segment d'URL opencctv, accentué), à ajouter au CSV restauré.
"""
import csv
from pathlib import Path

SRC = Path("camera-data/mes_paca_opencctv.csv")
OUT = Path("camera-data/paca_opencctv_clean.csv")

ACC = {
    "nevache": "Névache",
    "cervieres": "Cervières",
    "saint-raphael": "Saint-Raphaël",
    "frejus": "Fréjus",
    "le-monetier-les-bains": "Le Monêtier-les-Bains",
    "saint-etienne-de-tinee": "Saint-Étienne-de-Tinée",
    "saint-etienne-en-devoluy": "Saint-Étienne-en-Dévoluy",
    "saint-martin-vesubie": "Saint-Martin-Vésubie",
    "saint-michel-de-chaillol": "Saint-Michel-de-Chaillol",
    "saint-veran": "Saint-Véran",
    "sainte-anastasie-sur-issole": "Sainte-Anastasie-sur-Issole",
    "sollies-pont": "Solliès-Pont",
    "val-des-pres": "Val-des-Prés",
    "super-devoluy": "Super Dévoluy",
    "le-devoluy": "Le Dévoluy",
    "saint-julien-en-beauchene": "Saint-Julien-en-Beauchéne",
    "chateau-ville-vieille": "Château-Ville-Vieille",
    "col-des-guerins": "Col des Guérins",
    "montgenevre": "Montgenèvre",
    "vedene": "Vedène",
    "villar-darene": "Villar d'Arène",
    "hyeres": "Hyères",
    "orcieres": "Orcières",
    "barcelonnette": "Barcelonnette",
    "sainte-maxime": "Sainte-Maxime",
    "valserres": "Valserres",
    "vallouise-pelvoux": "Vallouise-Pelvoux",
    "saint-firmin": "Saint-Firmin",
    "embrun": "Embrun",
    "gap": "Gap",
    "grasse": "Grasse",
    "risoul": "Risoul",
    "vars": "Vars",
    "allos": "Allos",
    "ceillac": "Ceillac",
    "larche": "Larche",
    "isola": "Isola",
    "auron": "Auron",
    "menton": "Menton",
    "nice": "Nice",
    "antibes": "Antibes",
    "cannes": "Cannes",
    "cassis": "Cassis",
    "toulon": "Toulon",
    "marseille": "Marseille",
    "saint-tropez": "Saint-Tropez",
    "aix-en-provence": "Aix-en-Provence",
    "avignon": "Avignon",
}


def ville_from_segment(seg):
    if seg in ACC:
        return ACC[seg]
    words = seg.replace("-", " ").split()
    return " ".join(w.capitalize() for w in words)


def main():
    seen = set()
    rows = []
    with SRC.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for r in reader:
            u = (r.get("url_youtube") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            segs = [x for x in u.split("/") if x]
            seg = segs[-2] if len(segs) >= 4 else (segs[-1] if segs else "")
            ville = ville_from_segment(seg)
            rows.append({"url_youtube": u, "ville": ville})
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                           delimiter=";", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"Écrit {len(rows)} entrées propres dans {OUT}")
    from collections import Counter
    c = Counter(r["ville"] for r in rows)
    for v, n in c.most_common(15):
        print(f"  {n:3d} {v}")


if __name__ == "__main__":
    main()
