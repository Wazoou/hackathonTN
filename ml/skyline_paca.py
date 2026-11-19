import requests, re
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
r = s.get("https://www.skylinewebcams.com/en/webcam/france.html", timeout=25)
html = r.text
links = re.findall(r'href="([^"]*webcam[^"]*)"', html)
paca_keys = ["marseille", "frejus", "fréjus", "menton", "nice", "cannes", "toulon", "aix", "avignon",
             "saint-raphael", "saint-tropez", "grasse", "cassis", "bandol", "sainte-maxime", "sanary",
             "vallauris", "antibes", "beaulieu", "cap-dail"]
seen = set(); out = []
for l in links:
    if l in seen: continue
    seen.add(l)
    tl = l.lower()
    if any(k in tl for k in paca_keys):
        out.append(l)
print("total webcam links:", len(links))
print("PACA candidate links:", len(out))
for l in out:
    print(l)
