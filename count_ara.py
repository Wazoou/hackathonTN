import csv
import re
from pathlib import Path

csv_path = Path("C:/Users/manon/Documents/3A/hackathonTN/camera-data/cameras.csv")
with csv_path.open(encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh, delimiter=";")
    rows = list(reader)

print(f"Total lignes: {len(rows)}")

# Compter les webcams specifiquement ARA
ara_count = 0
ara_by_source = {}
for r in rows:
    url = r["url_youtube"]
    ville = r["ville"]
    is_ara = False
    source = ""
    
    # opencctv ARA detail pages
    if re.search(r"^https://opencctv\.org/cameras/france/auvergne-rhone-alpes/[\w-]+/[\w-]+-\d+", url):
        is_ara = True
        source = "opencctv.org"
    # worldcam ARA (from my collector - these have specific IDs I added)
    elif "worldcam.eu/webcams/europe/france/" in url:
        # Verifier si c'est une ville ARA connue
        ara_villes = {"Aix-les-Bains", "Alpe d'Huez", "Ambert", "Andrezieux-Boutheon", "Aurillac",
            "Bessans", "Besse-et-Saint-Anastaise", "Bonneval-sur-Arc", "Bourg-Saint-Maurice",
            "Brindas", "Chambéon", "Chambery", "Chamonix", "Chamrousse", "Clermont-Ferrand",
            "Col du Chaussy", "Collonges-sous-Saleve", "Cordon", "Courchevel", "Crozet",
            "Die", "Evian-les-Bains", "Faverges-Seythenex", "Gex", "Grand Massif",
            "Grenoble", "La Chapelle-d'Abondance", "La Chapelle-en-Vercors", "La Clusaz",
            "La Plagne", "Lac de Guéry", "Larajasse", "Laval-en-Belledonne", "Le Bourg-d'Oisans",
            "Le Grand-Bornand", "Le Lioran", "Le Puy-en-Velay", "Le Revard", "Le Sappey-en-Chartreuse",
            "Les 3 Vallées", "Les Contamines-Montjoie", "Les Deux Alpes", "Les Gets",
            "Les Karellis", "Lespéron", "Lignerolles", "Lyon", "Manigod", "Megève", "Meribel",
            "Modane", "Monnetier-Mornex", "Mont Blanc", "Mont-Dore", "Montélimar", "Montricher-Albanne",
            "Montriond", "Montvalezan", "Morzine", "Nances", "Nantua", "Ontex", "Orcines",
            "Peisey-Nancroix", "Saint Jean d'Arves", "Saint-Alban-de-Montbel", "Saint-Étienne-de-Boulogne",
            "Saint-Hilaire", "Saint-Hilaire du Touvet", "Saint-Jean-de-Maurienne", "Saint-Martin-d'Ardèche",
            "Saint-Martin-de-Belleville", "Saint-Pierre-de-Bœuf", "Saint-Régis-du-Coin", "Saint-Sorlin-d'Arves",
            "Saint-Vérand", "Salers", "Samoëns", "Sixt-Fer-à-Cheval", "St Gervais", "Sury-le-Comtal",
            "Talloires", "Taninges", "Tassin-la-Demi-Lune", "Tence", "Thonon-les-Bains", "Tignes",
            "Toulon-sur-Allier", "Tournon", "Val d'Isère", "Valloire", "Vallorcine", "Valmeinier",
            "Vaujany", "Venterol", "Villard-de-Lans", "Violay", "Yvoire", "Yzeron"}
        if ville in ara_villes:
            is_ara = True
            source = "worldcam.eu"
    # monde-du-voyage ARA (viewsurf/webcamera24 for Lyon, Grenoble, Clermont-Ferrand)
    elif "viewsurf.com" in url or "webcamera24.com" in url:
        if ville in {"Lyon", "Grenoble", "Clermont-Ferrand"}:
            is_ara = True
            source = "monde-du-voyage"
    # YouTube ARA
    elif "youtube.com" in url or "youtu.be" in url:
        if ville in {"Lyon", "Grenoble", "Annecy", "Chambery"}:
            is_ara = True
            source = "youtube"

    if is_ara:
        ara_count += 1
        ara_by_source[source] = ara_by_source.get(source, 0) + 1

print(f"\nWebcams specifiquement ARA: {ara_count}")
for src, count in sorted(ara_by_source.items()):
    print(f"  {src}: {count}")

# Villes uniques ARA
ara_villes_found = set()
for r in rows:
    url = r["url_youtube"]
    ville = r["ville"]
    if re.search(r"^https://opencctv\.org/cameras/france/auvergne-rhone-alpes/[\w-]+/[\w-]+-\d+", url):
        ara_villes_found.add(ville)
    elif "worldcam.eu/webcams/europe/france/" in url:
        ara_villes_found.add(ville)
    elif ("viewsurf.com" in url or "webcamera24.com" in url) and ville in {"Lyon", "Grenoble", "Clermont-Ferrand"}:
        ara_villes_found.add(ville)
    elif ("youtube.com" in url or "youtu.be" in url) and ville in {"Lyon", "Grenoble", "Annecy", "Chambery"}:
        ara_villes_found.add(ville)

print(f"\nVilles uniques couvertes en ARA: {len(ara_villes_found)}")
print(sorted(ara_villes_found))
