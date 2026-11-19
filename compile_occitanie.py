import csv
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("C:/Users/manon/Documents/3A/hackathonTN")
COLLECT = ROOT / "camera-data" / "occitanie_webcams_collecte.csv"
CSV_PATH = ROOT / "camera-data" / "cameras.csv"


def clean_url(url):
    url = url.strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return ""
    return parsed.geturl()


def parse_collect_file(path):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ";" not in line:
                continue
            url, ville = line.split(";", 1)
            url = clean_url(url)
            ville = ville.strip()
            if url and ville:
                rows.append({"url": url, "ville": ville})
    return rows


# --- Nouvelles webcams monde-du-voyage.com (direct viewsurf / webcamera24) ---
mdv_new = [
    # Toulouse
    ("https://webcamera24.com/camera/france/garonne-bazacle-weir-toulouse/", "Toulouse"),
    ("https://www.viewsurf.com/univers/trafic/vue/3000-france-midi-pyrenees-toulouse-a61-pres-de-toulouse-vue-sur-la-gauche-orientee-vers-montpellier-et-sur-la-droite-vers-toulouse-cent", "Toulouse"),
    # Perpignan
    ("https://www.viewsurf.com/univers/ville/vue/10984-france-languedoc-roussillon-perpignan-panoramique-video", "Perpignan"),
    ("https://www.viewsurf.com/univers/ville/vue/10986-france-languedoc-roussillon-perpignan-panoramique-hd", "Perpignan"),
    ("https://www.viewsurf.com/univers/ville/vue/15904-france-languedoc-roussillon-perpignan-panoramique-hd", "Perpignan"),
    ("https://www.viewsurf.com/univers/ville/vue/16534-france-languedoc-roussillon-perpignan-panoramique-hd", "Perpignan"),
    ("https://www.viewsurf.com/univers/ville/vue/16536-france-languedoc-roussillon-perpignan-skatepark", "Perpignan"),
    ("https://www.viewsurf.com/univers/ville/vue/15908-france-languedoc-roussillon-perpignan-place-francois-arago", "Perpignan"),
    ("https://www.viewsurf.com/univers/trafic/vue/14700-france-languedoc-roussillon-perpignan-a9-au-nord-de-perpignan-vue-orientee-vers-lespagne", "Perpignan"),
    ("https://www.viewsurf.com/univers/ville/vue/15906-france-languedoc-roussillon-perpignan-quais-de-la-basse", "Perpignan"),
    ("https://www.viewsurf.com/univers/montagne/vue/11342-france-languedoc-roussillon-perpignan-le-canigou", "Perpignan"),
    # Lourdes
    ("https://www.viewsurf.com/univers/montagne/vue/19268-france-midi-pyrenees-lourdes-pic-du-jer", "Lourdes"),
    ("https://www.viewsurf.com/univers/montagne/vue/19270-france-midi-pyrenees-lourdes-pic-du-jer", "Lourdes"),
    ("https://www.viewsurf.com/univers/montagne/vue/19272-france-midi-pyrenees-lourdes-lourdes", "Lourdes"),
]

rows = parse_collect_file(COLLECT)
print(f"Webcams depuis occitanie_webcams_collecte.csv : {len(rows)}")

# Ajout des nouvelles MDV (dedup par URL)
seen = {r["url"] for r in rows}
added_mdv = 0
for url, ville in mdv_new:
    u = clean_url(url)
    if u and u not in seen:
        rows.append({"url": u, "ville": ville})
        seen.add(u)
        added_mdv += 1
print(f"Webcams monde-du-voyage ajoutees : {added_mdv}")
print(f"Total uniques a ajouter : {len(rows)}")

# Charger l'existant cameras.csv pour dedup final
existing_seen = set()
if CSV_PATH.is_file():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for r in reader:
            u = (r.get("url_youtube") or "").strip()
            if u:
                existing_seen.add(u)

new_rows = [{"url_youtube": r["url"], "ville": r["ville"]} for r in rows if r["url"] not in existing_seen]
print(f"Nouveaux rows a ajouter a cameras.csv (non deja presents) : {len(new_rows)}")

# Ecriture dans cameras.csv
if CSV_PATH.is_file() and CSV_PATH.stat().st_size > 0:
    with CSV_PATH.open("rb") as fh:
        fh.seek(-1, 2)
        last_byte = fh.read(1)
    if last_byte != b"\n":
        with CSV_PATH.open("ab") as fh:
            fh.write(b"\n")

write_header = not CSV_PATH.is_file() or CSV_PATH.stat().st_size == 0
with CSV_PATH.open("a", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=["url_youtube", "ville"], delimiter=";", lineterminator="\n")
    if write_header:
        writer.writeheader()
    writer.writerows(new_rows)

print(f"Ajoutes a cameras.csv : {len(new_rows)}")

# Affichage de la liste complete finale
print("\n=== LISTE FINALE (URL;ville) ===")
for r in rows:
    print(f"{r['url']};{r['ville']}")
print(f"\nTOTAL : {len(rows)} webcams Occitanie")
