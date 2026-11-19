import json

hdf_villes = {
    'Lille','Amiens','Calais','Dunkerque','Boulogne-sur-Mer','Arras','Beauvais',
    'Compiègne','Le Touquet','Saint-Omer','Douai','Lens','Valenciennes','Bethune',
    'Berck','Cucq','Wissant','Zuydcoote','Bray-Dunes','Gravelines','Sangatte',
    'Neufchatel-Hardelot','Merlimont','Mers-les-Bains','Le Crotoy','Fort-Mahon-Plage',
    'Saint-Valery-sur-Somme','Cayeux-sur-Mer','Wimereux','Bondues',
    'Faches-Thumesnil','Sainghin-en-Melantois','Marly','Lesquin','Guemps','Bierne',
    'Saint-Pol-sur-Mer','Hestrud','Vervins','Nogentel','Saint-Jans-Cappel',
    'Le Plessis-Belleville','Leffrinckoucke','Grand-Fort-Philippe','Gamaches',
    'Saint-Michel','Courmelles','Ault','Berck-sur-Mer','Boves','Chamant',
    'Arras','Beauvais','Compiègne','Le Touquet','Saint-Omer','Douai','Lens',
    'Valenciennes','Berck','Cucq','Wissant','Zuydcoote','Bray-Dunes','Gravelines',
    'Sangatte','Neufchatel-Hardelot','Merlimont','Mers-les-Bains','Le Crotoy',
    'Fort-Mahon-Plage','Saint-Valery-sur-Somme','Cayeux-sur-Mer','Wimereux',
    'Bondues','Faches-Thumesnil','Sainghin-en-Melantois','Marly','Lesquin',
    'Guemps','Bierne','Saint-Pol-sur-Mer','Hestrud','Vervins','Nogentel',
    'Saint-Jans-Cappel','Le Plessis-Belleville','Leffrinckoucke',
    'Grand-Fort-Philippe','Gamaches','Saint-Michel','Courmelles','Ault',
    'Berck-sur-Mer','Boves','Chamant','Roubaix','Tourcoing','Villeneuve-d\'Ascq',
    'Maubeuge','Soissons','Laon','Château-Thierry','Saint-Quentin','Creil',
    'Senlis','Montdidier','Roye','Péronne','Abbeville','Albert','Montreuil',
    'Étaples','Berck','Rue','Camon','Longueau','Boves','Salouël',
    'Ailly-sur-Somme','Ailly-le-Haut-Clocher','Flixecourt','Noyelles-sur-Mer',
    'Woincourt','Airaines','Oisemont','Molliens-Dreuil','Picquigny',
    'Coulonvillers','Breteuil','Formerie','Marseille-en-Beauvaisis',
    'Grandvilliers','Crèvecœur-le-Grand','Noyon','Roye','Montdidier',
    'Chaulnes','Péronne','Ham','Tergnier','Chauny','Hirson','Vervins','Guise',
    'Ribemont','Villers-Cotterêts','Soissons','Fère-en-Tardenois',
    'Château-Thierry','Condé-en-Brie','Dormans','Épernay','Reims','Laon',
    'Saint-Quentin','Cambrai','Douai','Lens','Liévin','Béthune',
    'Bruay-la-Buissière','Hénin-Beaumont','Carvin','Avion','Marles-les-Mines',
    'Nœux-les-Mines','Barlin','Auchy-les-Mines','Courrières','Oignies',
    'Montigny-en-Gohelle','Sallaumines','Billy-Montigny','Rieulay','Dechy',
    'Sin-le-Noble','Aniche','Lewarde','Guesnain','Flines-lez-Raches','Auby',
    'Faches-Thumesnil','Seclin','Templemars','Phalempin','Pont-à-Marcq',
    'Cysoing','Bourghelles','Cobrieux','Wannehain','Bersée','Bauvin','Provin',
    'Annœullin','Halluin','Don','Sainghin-en-Weppes','Lannoy','Lys-lez-Lannoy',
    'Roubaix','Tourcoing','Mouscron','Wattrelos','Wattignies','La Madeleine',
    'Marcq-en-Barœul','Mouvaux','Wasquehal','Hem','Croix'
}

with open('camera-data/camera.json', encoding='utf-8') as f:
    data = json.load(f)

hdf_in_json = [c for c in data if c['nom'] in hdf_villes]
print(f'Webcams HDF dans camera.json: {len(hdf_in_json)}')
for c in hdf_in_json[:30]:
    print(f"  {c['nom']}: {c['url_youtube'][:60]}...")
if len(hdf_in_json) > 30:
    print(f'  ... et {len(hdf_in_json)-30} autres')

# Vérifier quelles villes HDF du CSV ne sont pas dans le JSON
import csv
csv_cities = set()
with open('camera-data/cameras.csv', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        csv_cities.add(row['ville'].strip())

json_cities = set(c['nom'] for c in data)
missing = csv_cities & hdf_villes - json_cities
print(f'\nVilles HDF dans le CSV mais pas dans camera.json: {len(missing)}')
for c in sorted(missing)[:30]:
    print(f'  {c}')
