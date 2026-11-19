import csv
import re
from pathlib import Path

csv_path = Path("C:/Users/manon/Documents/3A/hackathonTN/camera-data/cameras.csv")
with csv_path.open(encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh, delimiter=";")
    rows = list(reader)

ara_rows = []
for r in rows:
    url = r["url_youtube"]
    ville = r["ville"]
    is_ara = False
    
    if re.search(r"^https://opencctv\.org/cameras/france/auvergne-rhone-alpes/[\w-]+/[\w-]+-\d+", url):
        is_ara = True
    elif "worldcam.eu/webcams/europe/france/" in url:
        ara_villes = {"Aix-les-Bains", "Alpe d'Huez", "Ambert", "Andrezieux-Boutheon", "Aurillac",
            "Bessans", "Besse-et-Saint-Anastaise", "Bonneval-sur-Arc", "Bourg-Saint-Maurice",
            "Brindas", "Chambéon", "Chambery", "Chamonix", "Chamrousse", "Clermont-Ferrand",
            "Col du Chaussy", "Collonges-sous-Saleve", "Cordon", "Courchevel", "Crozet",
            "Evian-les-Bains", "Faverges-Seythenex", "Gex", "Grand Massif",
            "Grenoble", "La Chapelle-d'Abondance", "La Chapelle-en-Vercors", "La Clusaz",
            "La Plagne", "Lac de Guéry", "Larajasse", "Laval-en-Belledonne", "Le Bourg-d'Oisans",
            "Le Grand-Bornand", "Le Lioran", "Le Puy-en-Velay", "Le Revard", "Le Sappey-en-Chartreuse",
            "Les 3 Vallées", "Les Contamines-Montjoie", "Les Deux Alpes", "Les Gets",
            "Les Karellis", "Lespéron", "Lignerolles", "Lyon", "Manigod", "Megève", "Megeve",
            "Meribel", "Méribel", "Modane", "Monnetier-Mornex", "Mont-Dore", "Montélimar", "Montferrat",
            "Montmarault", "Montricher-Albanne", "Montriond", "Montvalezan", "Morzine",
            "Nances", "Nantua", "Ontex", "Orcines",
            "Peisey-Nancroix", "Saint Jean d'Arves", "Saint-Alban-de-Montbel", "Saint-Étienne-de-Boulogne",
            "Saint-Hilaire", "Saint-Hilaire du Touvet", "Saint-Jean-de-Maurienne", "Saint-Martin-d'Ardèche",
            "Saint-Martin-de-Belleville", "Saint-Pierre-de-Bœuf", "Saint-Régis-du-Coin", "Saint-Sorlin-d'Arves",
            "Saint-Vérand", "Salers", "Samoëns", "Sixt-Fer-à-Cheval", "St Gervais", "Sury-le-Comtal",
            "Talloires", "Taninges", "Tassin-la-Demi-Lune", "Tence", "Thonon-les-Bains", "Tignes",
            "Toulon-sur-Allier", "Tournon", "Val d'Isère", "Valloire", "Vallorcine", "Valmeinier",
            "Vaujany", "Venterol", "Villard-de-Lans", "Violay", "Yvoire", "Yzeron"}
        if ville in ara_villes:
            is_ara = True
    elif ("viewsurf.com" in url or "webcamera24.com" in url) and ville in {"Lyon", "Grenoble", "Clermont-Ferrand"}:
        is_ara = True
    elif ("youtube.com" in url or "youtu.be" in url) and ville in {"Lyon", "Grenoble", "Annecy", "Chambery"}:
        is_ara = True

    if is_ara:
        ara_rows.append((url, ville))

# Dedup
seen = set()
unique = []
for url, ville in ara_rows:
    if url not in seen:
        seen.add(url)
        unique.append((url, ville))

print(f"Total webcams ARA uniques: {len(unique)}")
print("\n=== LISTE URL;VILLE ===")
for url, ville in unique:
    print(f"{url};{ville}")
