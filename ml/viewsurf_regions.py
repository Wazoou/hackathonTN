import requests, re

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
r = s.get("https://www.viewsurf.com/", timeout=25)
html = r.text
print("len", len(html), "Provence mentions:", html.lower().count("provence"))
# find any href with provence
pat = re.compile(r'href="([^"]*provence[^"]*)"')
for l in sorted(set(pat.findall(html))):
    print("REGION/PROVENCE LINK:", l)
# find region section links generally: /univers/.../...-region-...
regions = set()
for m in re.finditer(r'href="([^"]*france-([a-z0-9\-]+)-[a-z][^"]*)"', html):
    regions.add((m.group(2), m.group(1)))
print("\nRégions trouvées (premières 40):")
for reg, l in sorted(regions)[:40]:
    print(" ", reg, "|", l)
