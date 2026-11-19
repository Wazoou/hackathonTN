"""Sources d'images : synthétique, dossier d'images, vidéo/RTSP, snapshot HTTP (webcam publique)."""

import io
import logging
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw

IMG_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m3u8"}


class SyntheticSource:
    """Paysage généré : permet de tester toute la chaîne sans aucune donnée."""

    def __init__(self, name: str, size=(1280, 720)):
        self.name, self.size, self.t = name, size, 0

    def read(self) -> Image.Image:
        w, h = self.size
        img = Image.new("RGB", self.size)
        d = ImageDraw.Draw(img)
        for y in range(h // 2):  # ciel en dégradé
            k = y / (h / 2)
            d.line([(0, y), (w, y)], fill=(int(110 + 80 * k), int(160 + 60 * k), 235))
        pts = [(x, h // 2 + int(40 * math.sin(x / 140 + self.t / 10))) for x in range(0, w + 20, 20)]
        d.polygon(pts + [(w, h), (0, h)], fill=(46, 92, 46))  # collines
        d.text((15, 15), f"{self.name}  {datetime.now():%Y-%m-%d %H:%M:%S}", fill="white")
        self.t += 1
        return img


class FolderSource:
    """Rejoue en boucle les images d'un dossier (ordre alphabétique = ordre chronologique)."""

    def __init__(self, folder: str):
        self.files = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in IMG_EXT)
        if not self.files:
            raise FileNotFoundError(f"Aucune image dans {folder}")
        self.i = 0

    def read(self) -> Image.Image:
        path = self.files[self.i % len(self.files)]
        self.i += 1
        return Image.open(path).convert("RGB")


class VideoSource:
    """Fichier vidéo (rejoué en boucle) ou flux RTSP. FRAME_STEP = nb d'images sautées entre 2 lectures."""

    def __init__(self, uri: str, frame_step: int = 25):
        import cv2  # import local : OpenCV n'est nécessaire que pour cette source

        self.cv2, self.uri, self.step = cv2, uri, frame_step
        self.cap = cv2.VideoCapture(uri)
        self.is_file = not uri.startswith(("rtsp://", "rtmp://"))

    def read(self) -> Image.Image:
        for _ in range(self.step):
            self.cap.grab()
        ok, frame = self.cap.read()
        if not ok and self.is_file:  # fin de vidéo : on reboucle
            self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError(f"Lecture impossible : {self.uri}")
        return Image.fromarray(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB))


class HttpSnapshotSource:
    """Webcam publique qui expose une image JPEG à une URL fixe."""

    def __init__(self, url: str):
        self.url = url

    def read(self) -> Image.Image:
        with requests.get(self.url, timeout=(4, 10), stream=True,
                          headers={"User-Agent": "pyro-watch-hackathon"}) as r:
            r.raise_for_status()
            if not r.headers.get("Content-Type", "").lower().startswith("image/"):
                raise ValueError("Le diffuseur n’a pas renvoyé une image")
            content = bytearray()
            for chunk in r.iter_content(64 * 1024):
                content.extend(chunk)
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError("Image webcam trop volumineuse")
        return Image.open(io.BytesIO(content)).convert("RGB")


def make_source(spec: str, name: str, frame_step: int = 25):
    if spec == "synthetic":
        return SyntheticSource(name)
    if spec.startswith(("http://", "https://")) and Path(urlparse(spec).path).suffix.lower() not in VIDEO_EXT:
        return HttpSnapshotSource(spec)  # webcam publique : URL d'une image JPEG
    if spec.startswith(("rtsp://", "rtmp://", "http://", "https://")):
        return VideoSource(spec, frame_step)
    path = Path(spec)
    if path.is_dir() and any(p.suffix.lower() in IMG_EXT for p in path.rglob("*")):
        return FolderSource(spec)
    if path.is_file():
        return VideoSource(spec, frame_step)
    logging.getLogger("camera").warning("Source %s introuvable ou vide -> images synthétiques", spec)
    return SyntheticSource(name)

