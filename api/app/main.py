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
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Path as APIPath
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator

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
CameraId = Annotated[str, APIPath(pattern=r"^[A-Za-z0-9_-]{1,80}$")]


class Detection(BaseModel):
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 <= x2 <= 1 and 0 <= y1 <= y2 <= 1):
            raise ValueError("Les coordonnées doivent former un rectangle normalisé")
        return self


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
            CREATE INDEX IF NOT EXISTS alerts_camera_date
                ON alerts(camera_id, created_at DESC, id DESC);
            CREATE VIEW IF NOT EXISTS latest_camera_alerts AS
                SELECT a.* FROM alerts a WHERE a.id=(
                    SELECT newer.id FROM alerts newer WHERE newer.camera_id=a.camera_id
                    ORDER BY newer.created_at DESC, newer.id DESC LIMIT 1
                );
            """
        )
        # Additive migration: keep existing cameras, images and human decisions.
        columns = {r[1] for r in c.execute("PRAGMA table_info(cameras)")}
        for column, definition in {
            "source_url": "TEXT", "is_demo": "INTEGER DEFAULT 0",
            "detector": "TEXT", "last_error": "TEXT", "last_attempt": "TEXT",
            "interval_s": "REAL DEFAULT 120",
        }.items():
            if column not in columns:
                c.execute(f"ALTER TABLE cameras ADD COLUMN {column} {definition}")
        c.execute("""CREATE TABLE IF NOT EXISTS demo_control (
            id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT, active INTEGER DEFAULT 0
        )""")
        c.execute("INSERT OR IGNORE INTO demo_control(id, generation, active) VALUES (1, ?, 0)",
                  (uuid4().hex,))


class CameraIn(BaseModel):
    name: str
    lat: float
    lon: float
    azimuth: float = 0.0
    source_url: str | None = None
    is_demo: bool = False
    detector: str | None = None
    interval_s: float = 120


class CameraFailure(BaseModel):
    error: str


class AlertUpdate(BaseModel):
    status: Literal["open", "confirmed", "false_positive"]


def camera_out(row: sqlite3.Row) -> dict:
    cam = dict(row)
    cam["last_detections"] = json.loads(cam["last_detections"] or "[]")
    last = cam["last_seen"]
    cam["online"] = bool(last) and now() - datetime.fromisoformat(last) < timedelta(
        seconds=max(OFFLINE_AFTER_S, (cam.get("interval_s") or 120) * 3)
    )
    return cam


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.put("/cameras/{camera_id}")
def upsert_camera(camera_id: CameraId, cam: CameraIn) -> dict:
    with db() as c:
        c.execute(
            """INSERT INTO cameras (id, name, lat, lon, azimuth, source_url, is_demo, detector, interval_s)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, lat=excluded.lat,
               lon=excluded.lon, azimuth=excluded.azimuth, source_url=excluded.source_url,
               is_demo=excluded.is_demo, detector=excluded.detector, interval_s=excluded.interval_s""",
            (camera_id, cam.name, cam.lat, cam.lon, cam.azimuth, cam.source_url,
             cam.is_demo, cam.detector, cam.interval_s),
        )
        return camera_out(c.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone())


@app.get("/cameras")
def list_cameras() -> list[dict]:
    with db() as c:
        return [camera_out(r) for r in c.execute("SELECT * FROM cameras ORDER BY id")]


@app.post("/cameras/{camera_id}/failure")
def camera_failure(camera_id: CameraId, body: CameraFailure) -> dict:
    _consecutive[camera_id] = 0
    with db() as c:
        cur = c.execute("UPDATE cameras SET last_error=?, last_attempt=? WHERE id=?",
                        (body.error[:500], now().isoformat(), camera_id))
        if not cur.rowcount:
            raise HTTPException(404, "Caméra inconnue")
    return {"stored": True}


@app.get("/demo")
def demo_state() -> dict:
    with db() as c:
        return dict(c.execute("SELECT generation, active FROM demo_control WHERE id=1").fetchone())


@app.post("/demo/{action}")
def control_demo(action: Literal["start", "reset", "stop"]) -> dict:
    generation = uuid4().hex
    with db() as c:
        c.execute("UPDATE demo_control SET generation=?, active=? WHERE id=1",
                  (generation, int(action == "start")))
        if action in {"start", "reset"}:
            # Reset only the explicit demo; never touch real camera alerts.
            images = c.execute("SELECT image FROM alerts WHERE camera_id='demo-fire'").fetchall()
            c.execute("DELETE FROM alerts WHERE camera_id='demo-fire'")
            c.execute("DELETE FROM detections WHERE camera_id='demo-fire'")
            c.execute("UPDATE cameras SET last_seen=NULL, last_error=NULL, last_detections='[]' WHERE id='demo-fire'")
            for row in images:
                if row["image"]:
                    (ALERTS_DIR / Path(row["image"]).name).unlink(missing_ok=True)
            (FRAMES_DIR / "demo-fire" / "latest.jpg").unlink(missing_ok=True)
    _consecutive.pop("demo-fire", None)
    return {"generation": generation, "active": action == "start"}


@app.post("/cameras/{camera_id}/frames")
async def post_frame(
    camera_id: CameraId,
    image: UploadFile = File(...),
    detections: str = Form("[]"),
    generation: str | None = Form(None),
) -> dict:
    """Reçoit une image + ses détections [{confidence, bbox: [x1,y1,x2,y2] normalisés 0-1}]."""
    try:
        dets = [d.model_dump() for d in TypeAdapter(list[Detection]).validate_json(detections)]
    except ValidationError:
        raise HTTPException(422, "Détections invalides")
    content = await image.read(8 * 1024 * 1024 + 1)
    if not content or len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Image vide ou trop volumineuse")
    ts = now().isoformat()
    cam_dir = FRAMES_DIR / camera_id
    latest = cam_dir / "latest.jpg"

    alert_id = None
    with db() as c:
        if camera_id == "demo-fire":
            control = c.execute("SELECT * FROM demo_control WHERE id=1").fetchone()
            if not control["active"] or generation != control["generation"]:
                raise HTTPException(409, "Séquence de démonstration remplacée ou arrêtée")
        if not c.execute("SELECT 1 FROM cameras WHERE id=?", (camera_id,)).fetchone():
            raise HTTPException(404, f"Caméra inconnue : {camera_id} (faire PUT /cameras/{camera_id})")
        unchanged = camera_id.startswith("public-") and latest.exists() and latest.read_bytes() == content
        cam_dir.mkdir(parents=True, exist_ok=True)
        temporary = cam_dir / "latest.tmp"
        temporary.write_bytes(content)
        temporary.replace(latest)
        c.execute(
            "UPDATE cameras SET last_seen=?, last_attempt=?, last_error=NULL, last_detections=? WHERE id=?",
            (ts, ts, json.dumps(dets), camera_id),
        )
        if unchanged:
            # Re-fetching one frozen snapshot is not a second observation.
            return {"stored": True, "detections": len(dets), "alert_id": None, "unchanged": True}
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
                "SELECT id, status FROM latest_camera_alerts WHERE camera_id=? AND (status='open' OR created_at>?)",
                (camera_id, since)
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
            elif recent["status"] == "open" and best["confidence"] > c.execute("SELECT confidence FROM alerts WHERE id=?", (recent["id"],)).fetchone()[0]:
                c.execute("UPDATE alerts SET confidence=?, bbox=? WHERE id=?",
                          (best["confidence"], json.dumps(best["bbox"]), recent["id"]))
                shutil.copy(latest, ALERTS_DIR / f"{recent['id']}.jpg")

    return {"stored": True, "detections": len(dets), "alert_id": alert_id}


@app.get("/cameras/{camera_id}/latest.jpg")
def latest_frame(camera_id: CameraId) -> FileResponse:
    path = FRAMES_DIR / camera_id / "latest.jpg"
    if not path.exists():
        raise HTTPException(404, "Pas encore d'image")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/alerts")
def list_alerts(status: str | None = None, limit: int = 50) -> list[dict]:
    query, args = """SELECT a.*, c.name AS camera_name, c.lat, c.lon, c.source_url,
        c.is_demo, c.detector FROM latest_camera_alerts a JOIN cameras c ON c.id=a.camera_id""", []
    if status:
        query += " WHERE a.status=?"
        args.append(status)
    query += " ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
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
        open_yolo = c.execute("""SELECT COUNT(*) FROM latest_camera_alerts a JOIN cameras c ON c.id=a.camera_id
            WHERE a.status='open' AND c.detector='yolo'""").fetchone()[0]
    return {"alerts_by_status": by_status, "detections": n_det, "open_yolo_alerts": open_yolo}
