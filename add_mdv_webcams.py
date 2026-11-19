import csv
import re
from pathlib import Path

csv_path = Path("C:/Users/manon/Documents/3A/hackathonTN/camera-data/cameras.csv")

# Nouvelles webcams monde-du-voyage ARA (URL;ville)
new_webcams = [
    # Lyon
    ("https://webcamera24.com/camera/france/mont-cindre-lyon/", "Lyon"),
    ("https://webcamera24.com/camera/france/peripherique-nord-lyon/", "Lyon"),
    ("https://www.viewsurf.com/univers/trafic/vue/7380-france-rhone-alpes-lyon-a42a46-autoroute-a42-au-nord-de-lyon-vue-orientee-vers-lyon", "Lyon"),
    ("https://www.viewsurf.com/univers/trafic/vue/7382-france-rhone-alpes-lyon-autoroute-a46-en-peripherie-de-lyon-nord-et-a-proximite-de-la-bifurcation-a46a42-vue-orientee-vers", "Lyon"),
    # Grenoble
    ("https://www.viewsurf.com/univers/trafic/vue/17342-france-rhone-alpes-grenoble-autoroute-a480-a-grenoble-vue-orientee-sur-lentree-et-sortie-de-grenoble-sud", "Grenoble"),
    # Clermont-Ferrand
    ("https://www.viewsurf.com/univers/ville/vue/899-france-auvergne-clermont-ferrand-place-jaude", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/montagne/vue/2382-france-auvergne-clermont-ferrand-panoramique-hd", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/ville/vue/2384-france-auvergne-clermont-ferrand-montjuzet", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/ville/vue/2386-france-auvergne-clermont-ferrand-puy-de-dome", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/ville/vue/3586-france-auvergne-clermont-ferrand-forez", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/trafic/vue/16896-france-auvergne-clermont-ferrand-a75-pres-de-clermont-ferrand-a-hauteur-de-la-pardieu-vue-orientee-vers-paris", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/ville/vue/18428-france-auvergne-clermont-ferrand-place-de-la-victoire", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/trafic/vue/7368-france-auvergne-clermont-ferrand-a71-pres-de-clermont-ferrand-barriere-de-peage-de-clermont-gerzat-vue-orientee-vers-paris", "Clermont-Ferrand"),
    ("https://www.viewsurf.com/univers/ville/vue/3588-france-auvergne-clermont-ferrand-cathedrale", "Clermont-Ferrand"),
]

# Lire les URLs existantes
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
