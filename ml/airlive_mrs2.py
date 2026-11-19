import requests, re
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (webcam-collector)"})
r = s.get("https://cam.airlive.net/", timeout=25)
h = r.text
print("marseille count:", h.lower().count("marseille"), "marignane:", h.lower().count("marignane"))
idx = h.lower().find("marseille")
if idx >= 0:
    snippet = re.sub(r"\s+", " ", h[max(0, idx - 120):idx + 200])
    print("SNIP:", snippet)
for pat in [r"https?://[^\"\']+\.m3u8[^\"\']*", r"youtube\.com/(?:embed|live)/[A-Za-z0-9_-]+", r"youtu\.be/[A-Za-z0-9_-]+"]:
    ms = re.findall(pat, h)
    print(pat, "->", len(ms), ms[:5])
