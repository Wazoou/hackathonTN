import csv
from io import StringIO

with open('camera-data/cameras.csv', encoding='utf-8', newline='') as fh:
    content = fh.read()

if '\ufffd' in content:
    print('ATTENTION: Caractères de remplacement trouvés')
else:
    print('Aucun caractère de remplacement - encodage UTF-8 valide')

reader = csv.DictReader(StringIO(content), delimiter=';')
count = 0
paca_count = 0
for row in reader:
    ville = row.get('ville', '')
    if any(c in ville for c in ['Nice', 'Cannes', 'Antibes', 'Menton', 'Fréjus', 'Saint-Tropez', 'Hyères', 'Cassis', 'Toulon', 'Marseille']):
        paca_count += 1
        if count < 5:
            url = row.get('url_youtube', '')
            print(f'  {url[:60]}...;{ville}')
        count += 1
print(f'PACA entries sample count: {paca_count}')