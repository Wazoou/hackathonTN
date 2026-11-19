import requests, re

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
r = s.get("https://www.viewsurf.com/", timeout=25)
html = r.text
pat = re.compile(r'href="([^"]*france-provence-alpes-cote-d-azur[^"]*)"')
links = sorted(set(pat.findall(html)))
print("liens PACA viewsurf:", len(links))
for l in links:
    print(l)
