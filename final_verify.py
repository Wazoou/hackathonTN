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
    elif "viewsurf.com" in url:
        sources["viewsurf"] += 1
    elif "webcamera24.com" in url:
        sources["webcamera24"] += 1
    elif "skylinewebcams" in url:
        sources["skylinewebcams"] += 1
    elif "france-webcams" in url:
        sources["france-webcams"] += 1
    else:
        sources["other"] += 1

for src, count in sources.most_common():
    print(f"  {src}: {count}")

villes = set(r["ville"] for r in rows if r["ville"])
print(f"\nVilles uniques: {len(villes)}")

# Webcams specifiquement ARA
ara = [r for r in rows if "opencctv.org/cameras/france/auvergne-rhone-alpes/" in r["url_youtube"] or "worldcam.eu/webcams/europe/france/" in r["url_youtube"]]
print(f"Webcams ARA (opencctv + worldcam): {len(ara)}")

# Quelques exemples par source
print("\n--- Exemples YouTube ---")
yt = [r for r in rows if "youtube.com" in r["url_youtube"]]
for r in yt:
    print(f"  {r['url_youtube']} ; {r['ville']}")

print("\n--- Exemples monde-du-voyage (viewsurf/webcamera24) ---")
mdv = [r for r in rows if ("viewsurf.com" in r["url_youtube"] or "webcamera24.com" in r["url_youtube"]) and r not in yt]
for r in mdv[:10]:
    print(f"  {r['url_youtube']} ; {r['ville']}")
if len(mdv) > 10:
    print(f"  ... et {len(mdv)-10} de plus")
