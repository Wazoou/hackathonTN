"""Manifeste d'acquisition : trace de chaque téléchargement.

Le manifeste est un JSON lisible dans ``data/raw/_manifest.json``. Il permet
de savoir ce qui a été téléchargé, quand, depuis quelle URL, avec quel
contrôle d'intégrité — et de rendre les scripts idempotents.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def get(self, layer: str) -> dict[str, Any] | None:
        return self.data.get(layer)

    def record(self, layer: str, status: str, **info: Any) -> None:
        self.data[layer] = {
            "status": status,
            "updated_at": utc_now(),
            **info,
        }
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)
