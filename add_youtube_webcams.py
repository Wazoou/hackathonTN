import csv
from pathlib import Path

csv_path = Path("C:/Users/manon/Documents/3A/hackathonTN/camera-data/cameras.csv")

# YouTube webcams ARA trouvees
new_webcams = [
    # Lyon
    ("https://www.youtube.com/watch?v=xds25nuZ8Cw", "Lyon"),
    ("https://www.youtube.com/watch?v=s-J0yE5Tpu4", "Lyon"),
    ("https://www.youtube.com/watch?v=WdgZIE0T4Gs", "Lyon"),
    # Grenoble
    ("https://www.youtube.com/watch?v=7SwNXyeKM_8", "Grenoble"),
    # Annecy
    ("https://www.youtube.com/watch?v=u8onItMI4Ik", "Annecy"),
    ("https://www.youtube.com/watch?v=nu2W1NSn8-A", "Annecy"),
    # Chambery
    ("https://www.youtube.com/watch?v=kAaxN72reh4", "Chambery"),
]

seen = set()
if csv_path.is_file():
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            u = (row.get("url_youtube") or "").strip()
            if u:
                seen.add(u)

added = 0
with csv_path.open("a", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"], delimiter=";", lineterminator="\n")
    for url, ville in new_webcams:
        if url not in seen:
            writer.writerow({"url_youtube": url, "ville": ville})
            seen.add(url)
            added += 1
            print(f"  + {url} ; {ville}")
        else:
            print(f"  - (deja present) {url}")

print(f"\nAjoutes: {added}")
