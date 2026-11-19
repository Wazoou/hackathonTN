"""Dédupliquer camera-data/cameras.csv par URL (garde la première occurrence)."""
import csv
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "camera-data" / "cameras.csv"

def main():
    rows = []
    seen = set()
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        fieldnames = reader.fieldnames
        for row in reader:
            url = (row.get("url_youtube") or "").strip()
            city = (row.get("ville") or "").strip()
            if not url or not city:
                continue
            if url in seen:
                continue
            seen.add(url)
            rows.append({"url_youtube": url, "ville": city})

    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"],
                                delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Dédupliqué : {len(rows)} entrées uniques écrites dans {CSV_PATH}")

if __name__ == "__main__":
    main()
