"""Évaluation + fine-tuning YOLO. À lancer sur un GPU (Kaggle : Settings > Accelerator > GPU T4 x2).

  pip install ultralytics huggingface_hub pyarrow
  python ml/pyro_sdis.py yolo --out datasets/pyro-sdis

  # 1) Baseline : le modèle Pyronear tel quel sur un jeu de validation
  python ml/finetune.py eval --data datasets/pyro-sdis/data.yaml

  # 2) Fine-tuning à partir des poids Pyronear (sur VOS données annotées de préférence)
  python ml/finetune.py train --data datasets/mes-cameras/data.yaml --epochs 30

  # 3) Comparer : eval avec --weights runs/detect/<run>/weights/best.pt
"""

import argparse

from huggingface_hub import hf_hub_download
from ultralytics import YOLO

PYRONEAR = ("pyronear/yolo11s_sensitive-detector", "best.pt")


def load(weights: str | None) -> YOLO:
    return YOLO(weights or hf_hub_download(*PYRONEAR))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["eval", "train"])
    p.add_argument("--data", required=True, help="chemin vers data.yaml")
    p.add_argument("--weights", help="poids de départ (défaut : modèle Pyronear)")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--imgsz", type=int, default=1024, help="Pyronear entraîne en 1024 ; 640 = 2x plus rapide")
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--fraction", type=float, default=1.0, help="ex : 0.25 pour un essai rapide")
    a = p.parse_args()

    model = load(a.weights)
    if a.cmd == "eval":
        m = model.val(data=a.data, imgsz=a.imgsz, batch=a.batch)
        print(f"\nmAP50={m.box.map50:.3f}  mAP50-95={m.box.map:.3f}  "
              f"précision={m.box.mp:.3f}  rappel={m.box.mr:.3f}")
    else:
        model.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch,
                    fraction=a.fraction, patience=10, name="pyro-finetune")


if __name__ == "__main__":
    main()
