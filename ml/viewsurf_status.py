import requests
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
r = s.get("https://www.viewsurf.com/", timeout=25)
print("status", r.status_code, "len", len(r.text))
print(r.text[:600])
