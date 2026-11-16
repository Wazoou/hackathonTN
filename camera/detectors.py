"""Détecteurs de fumée. Interface commune : predict(image) -> [{"confidence": float, "bbox": [x1,y1,x2,y2]}]
avec des coordonnées normalisées entre 0 et 1.

- DummyDetector : phase 1, simule des "épisodes" de fumée pour faire tourner la chaîne de bout en bout.
- YoloDetector  : phase 2, modèle YOLO (Pyronear ou le vôtre après fine-tuning).
"""

import random

from PIL import Image


class DummyDetector:
    def __init__(self, episode_proba: float = 0.05):
        self.p, self.remaining, self.box = episode_proba, 0, None

    def predict(self, img: Image.Image) -> list[dict]:
        if self.remaining == 0 and random.random() < self.p:
            self.remaining = random.randint(3, 8)  # un épisode dure quelques images
            x, y = random.uniform(0.1, 0.7), random.uniform(0.2, 0.5)
            self.box = [x, y, x + random.uniform(0.08, 0.2), y + random.uniform(0.08, 0.15)]
        if self.remaining == 0:
            return []
        self.remaining -= 1
        return [{"confidence": round(random.uniform(0.4, 0.95), 3), "bbox": self.box}]


class YoloDetector:
    def __init__(self, weights: str, conf: float = 0.15, imgsz: int = 1024):
        from ultralytics import YOLO  # dépendance lourde, chargée seulement si utilisée

        if weights.startswith("hf://"):  # ex : hf://pyronear/yolo11s_sensitive-detector/best.pt
            from huggingface_hub import hf_hub_download

            repo, _, filename = weights[5:].rpartition("/")
            weights = hf_hub_download(repo, filename)
        self.model, self.conf, self.imgsz = YOLO(weights), conf, imgsz

    def predict(self, img: Image.Image) -> list[dict]:
        res = self.model.predict(img, conf=self.conf, imgsz=self.imgsz, verbose=False)[0]
        return [
            {"confidence": round(float(c), 3), "bbox": [round(float(v), 4) for v in box]}
            for box, c in zip(res.boxes.xyxyn.tolist(), res.boxes.conf.tolist())
        ]


def make_detector(kind: str, weights: str, conf: float, imgsz: int):
    if kind == "yolo":
        return YoloDetector(weights, conf, imgsz)
    return DummyDetector()
