import requests, re
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
try:
    r = s.get("https://cam.airlive.net/", timeout=25)
    print("airlive status", r.status_code, "len", len(r.text))
    # marseille links
    for m in re.finditer(r'href="([^"]*)"[^>]*>([^<]*(?:marseille|marignane)[^<]*)', r.text, re.I):
        print("  ", m.group(1), "|", m.group(2)[:70])
    if "marseille" in r.text.lower() or "marignane" in r.text.lower():
        print("contient marseille/marignane")
except Exception as e:
    print("ERR", e)
