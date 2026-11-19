import csv
from pathlib import Path

CSV = Path("camera-data/cameras.csv")
OUT = Path("camera-data/paca_liste_finale.txt")

paca = {
    'Marseille','Nice','Cannes','Toulon','Antibes','Aix-en-Provence','Avignon','Arles',
    'Saint-Tropez','Fréjus','Saint-Raphaël','Hyères','Menton','Villefranche-sur-Mer',
    'Grasse','Digne-les-Bains','Gap','Briançon','Cassis','Bandol','Orcières','Risoul',
    'Vars','Embrun','Sisteron','Manosque','Apt','Orange','Carpentras',
    'Saint-Marc-Jaumegarde','Vedène','Lançon-Provence','Martigues','Aubagne','Istres',
    'Salon-de-Provence','Vallauris','Cagnes-sur-Mer','Beaulieu-sur-Mer','Cap-d\'Ail',
    'La Ciotat','Sanary-sur-Mer','Saint-Cyr-sur-Mer','La Seyne-sur-Mer','Le Lavandou',
    'Bormes-les-Mimosas','La Londe-les-Maures','Gassin','Ramatuelle','Cogolin','Grimaud',
    'Saint-Mandrier-sur-Mer','Draguignan','Brignoles','Sainte-Maxime','Roquebrune-sur-Argens',
    'Miramas'
}
rows = []
with CSV.open(encoding="utf-8-sig", newline="") as fh:
    for row in csv.DictReader(fh, delimiter=";"):
        u = (row.get("url_youtube") or "").strip()
        v = (row.get("ville") or "").strip()
        if v in paca and u:
            rows.append((u, v))

with OUT.open("w", encoding="utf-8", newline="") as fh:
    for u, v in rows:
        fh.write(f"{u};{v}\n")

print(f"{len(rows)} entree PACA ecrites dans {OUT}")
# verif doublons d'URL dans la liste PACA
urls = [u for u, _ in rows]
print("doublons d'URL dans liste PACA:", len(urls) - len(set(urls)))
