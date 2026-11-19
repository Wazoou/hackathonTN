import csv
import re
from pathlib import Path

csv_path = Path("C:/Users/manon/Documents/3A/hackathonTN/camera-data/cameras.csv")

# Lire toutes les lignes
with csv_path.open(encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh, delimiter=";")
    fieldnames = reader.fieldnames
    rows = list(reader)

print(f"Avant nettoyage: {len(rows)} lignes")

# Pattern de page de detail valide: /cameras/france/auvergne-rhone-alpes/{ville}/{slug}-{id}
detail_pattern = re.compile(r"/cameras/france/auvergne-rhone-alpes/[\w-]+/[\w-]+-\d+")

kept = []
removed = []
for r in rows:
    url = r["url_youtube"]
    if url.startswith("https://opencctv.org/cameras/france/auvergne-rhone-alpes/"):
        if detail_pattern.search(url):
            kept.append(r)
        else:
            removed.append(r)
    else:
        kept.append(r)

print(f"Apres nettoyage: {len(kept)} lignes ({len(removed)} supprimees)")

# Reecrire le CSV
with csv_path.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(kept)

print("CSV reecrit.")
