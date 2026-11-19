import csv
from pathlib import Path
from collections import Counter

csv_path = Path("C:/Users/manon/Documents/3A/hackathonTN/camera-data/cameras.csv")
with csv_path.open(encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh, delimiter=";")
    rows = list(reader)

print(f"Total webcams: {len(rows)}")

sources = Counter()
for r in rows:
    url = r["url_youtube"]
    if "opencctv.org" in url:
        sources["opencctv.org"] += 1
    elif "worldcam.eu" in url:
        sources["worldcam.eu"] += 1
    elif "youtube.com" in url or "youtu.be" in url:
        sources["youtube"] += 1
    elif "monde-du-voyage" in url:
        sources["monde-du-voyage"] += 1
    elif "france-webcams" in url:
        sources["france-webcams"] += 1
    elif "skylinewebcams" in url:
        sources["skylinewebcams"] += 1
    elif "viewsurf" in url:
        sources["viewsurf"] += 1
    else:
        sources["other"] += 1

for src, count in sources.most_common():
    print(f"  {src}: {count}")

# Villes uniques
villes = set(r["ville"] for r in rows if r["ville"])
print(f"\nVilles uniques: {len(villes)}")

# Quelques exemples d'entrees ARA
ara = [r for r in rows if "opencctv.org/cameras/france/auvergne-rhone-alpes/" in r["url_youtube"] or "worldcam.eu/webcams/europe/france/" in r["url_youtube"]]
print(f"\nWebcams ARA (opencctv + worldcam): {len(ara)}")
