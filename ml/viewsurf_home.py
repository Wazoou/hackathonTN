import requests, re
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
try:
    r = s.get("https://www.viewsurf.com/", timeout=25)
    print("status", r.status_code, "len", len(r.text))
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    # links mentioning PACA cities or vues
    keys = ["aix", "avignon", "marseille", "toulon", "nice", "cannes", "menton", "grasse",
            "frejus", "bandol", "cassis", "hyères", "hyeres", "saint-tropez", "autoroute",
            "a7", "a8", "aeroport", "gap", "briancon", "orcières", "orciere", "vars", "risoul",
            "ville", "vue"]
    found = []
    for a in soup.find_all("a", href=True):
        h = a["href"]; t = a.get_text(" ", strip=True)
        tl = (h + " " + t).lower()
        if any(k in tl for k in keys):
            found.append((h, t))
    print("liens pertinents page d'accueil:", len(found))
    for h, t in found[:60]:
        print("  ", h, "|", t[:60])
except Exception as e:
    print("ERR", e)
