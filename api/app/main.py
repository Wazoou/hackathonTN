"""API Pyro-Watch : caméras, images, détections et alertes.

Stockage volontairement simple pour le MVP : SQLite + fichiers JPEG sur disque.
"""

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "pyro.db"
FRAMES_DIR = DATA_DIR / "frames"
ALERTS_DIR = DATA_DIR / "alerts"

# Logique d'alerte : on n'alerte qu'après N images consécutives avec une détection
# au-dessus du seuil (limite les faux positifs ponctuels : nuage, reflet...).
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.35"))
MIN_CONSECUTIVE = int(os.getenv("MIN_CONSECUTIVE", "2"))
ALERT_COOLDOWN_S = int(os.getenv("ALERT_COOLDOWN_S", "300"))
OFFLINE_AFTER_S = int(os.getenv("OFFLINE_AFTER_S", "60"))

app = FastAPI(title="Pyro-Watch API", version="0.1.0")
_consecutive: dict[str, int] = {}


def now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def init() -> None:
    for d in (DATA_DIR, FRAMES_DIR, ALERTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS cameras (
                id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL, azimuth REAL,
                last_seen TEXT, last_detections TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT, camera_id TEXT, ts TEXT,
                confidence REAL, bbox TEXT
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, camera_id TEXT, created_at TEXT,
                confidence REAL, bbox TEXT, status TEXT DEFAULT 'open', image TEXT
            );
            """
        )


class CameraIn(BaseModel):
    name: str
    lat: float
    lon: float
    azimuth: float = 0.0


class AlertUpdate(BaseModel):
    status: Literal["open", "confirmed", "false_positive"]


def camera_out(row: sqlite3.Row) -> dict:
    cam = dict(row)
    cam["last_detections"] = json.loads(cam["last_detections"] or "[]")
    last = cam["last_seen"]
    cam["online"] = bool(last) and now() - datetime.fromisoformat(last) < timedelta(
        seconds=OFFLINE_AFTER_S
    )
    return cam


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.put("/cameras/{camera_id}")
def upsert_camera(camera_id: str, cam: CameraIn) -> dict:
    with db() as c:
        c.execute(
            """INSERT INTO cameras (id, name, lat, lon, azimuth) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, lat=excluded.lat,
               lon=excluded.lon, azimuth=excluded.azimuth""",
            (camera_id, cam.name, cam.lat, cam.lon, cam.azimuth),
        )
        return camera_out(c.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone())


@app.get("/cameras")
def list_cameras() -> list[dict]:
    with db() as c:
        return [camera_out(r) for r in c.execute("SELECT * FROM cameras ORDER BY id")]


@app.post("/cameras/{camera_id}/frames")
async def post_frame(
    camera_id: str,
    image: UploadFile = File(...),
    detections: str = Form("[]"),
) -> dict:
    """Reçoit une image + ses détections [{confidence, bbox: [x1,y1,x2,y2] normalisés 0-1}]."""
    dets = json.loads(detections)
    ts = now().isoformat()
    cam_dir = FRAMES_DIR / camera_id
    cam_dir.mkdir(parents=True, exist_ok=True)
    latest = cam_dir / "latest.jpg"
    latest.write_bytes(await image.read())

    alert_id = None
    with db() as c:
        if not c.execute("SELECT 1 FROM cameras WHERE id=?", (camera_id,)).fetchone():
            raise HTTPException(404, f"Caméra inconnue : {camera_id} (faire PUT /cameras/{camera_id})")
        c.execute(
            "UPDATE cameras SET last_seen=?, last_detections=? WHERE id=?",
            (ts, json.dumps(dets), camera_id),
        )
        c.executemany(
            "INSERT INTO detections (camera_id, ts, confidence, bbox) VALUES (?, ?, ?, ?)",
            [(camera_id, ts, d["confidence"], json.dumps(d["bbox"])) for d in dets],
        )

        best = max(dets, key=lambda d: d["confidence"], default=None)
        if best and best["confidence"] >= CONF_THRESHOLD:
            _consecutive[camera_id] = _consecutive.get(camera_id, 0) + 1
        else:
            _consecutive[camera_id] = 0

        if _consecutive[camera_id] >= MIN_CONSECUTIVE:
            since = (now() - timedelta(seconds=ALERT_COOLDOWN_S)).isoformat()
            recent = c.execute(
                "SELECT 1 FROM alerts WHERE camera_id=? AND created_at>?", (camera_id, since)
            ).fetchone()
            if not recent:
                cur = c.execute(
                    "INSERT INTO alerts (camera_id, created_at, confidence, bbox) VALUES (?, ?, ?, ?)",
                    (camera_id, ts, best["confidence"], json.dumps(best["bbox"])),
                )
                alert_id = cur.lastrowid
                snapshot = ALERTS_DIR / f"{alert_id}.jpg"
                shutil.copy(latest, snapshot)
                c.execute("UPDATE alerts SET image=? WHERE id=?", (snapshot.name, alert_id))

    return {"stored": True, "detections": len(dets), "alert_id": alert_id}


@app.get("/cameras/{camera_id}/latest.jpg")
def latest_frame(camera_id: str) -> FileResponse:
    path = FRAMES_DIR / camera_id / "latest.jpg"
    if not path.exists():
        raise HTTPException(404, "Pas encore d'image")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/alerts")
def list_alerts(status: str | None = None, limit: int = 50) -> list[dict]:
    query, args = "SELECT * FROM alerts", []
    if status:
        query += " WHERE status=?"
        args.append(status)
    query += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with db() as c:
        rows = [dict(r) for r in c.execute(query, args)]
    for r in rows:
        r["bbox"] = json.loads(r["bbox"])
    return rows


@app.get("/alerts/{alert_id}/image")
def alert_image(alert_id: int) -> FileResponse:
    path = ALERTS_DIR / f"{alert_id}.jpg"
    if not path.exists():
        raise HTTPException(404, "Image introuvable")
    return FileResponse(path, media_type="image/jpeg")


@app.patch("/alerts/{alert_id}")
def update_alert(alert_id: int, body: AlertUpdate) -> dict:
    """Le pompier qualifie l'alerte : confirmée ou faux positif (données utiles pour ré-entraîner !)."""
    with db() as c:
        cur = c.execute("UPDATE alerts SET status=? WHERE id=?", (body.status, alert_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Alerte introuvable")
    return {"id": alert_id, "status": body.status}


@app.get("/stats")
def stats() -> dict:
    with db() as c:
        by_status = dict(c.execute("SELECT status, COUNT(*) FROM alerts GROUP BY status").fetchall())
        n_det = c.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
    return {"alerts_by_status": by_status, "detections": n_det}
