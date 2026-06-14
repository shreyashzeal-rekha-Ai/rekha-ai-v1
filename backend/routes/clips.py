"""
routes/clips.py
---------------
REST endpoints for listing and serving saved alert clips/snapshots.

KEY FIX: HTML5 <video> requires HTTP 206 Partial Content (Range requests).
Without it the browser cannot seek/buffer and playback fails entirely.
We implement the Range header response manually for .mp4 files.
"""

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse, RedirectResponse, Response

ROOT_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIPS_DIR = os.path.join(ROOT_DIR, 'clips')

clips_router = APIRouter()

# Filename pattern: cam_01_fire_smoke_20260423_134430.mp4
_PATTERN = re.compile(
    r'^(?P<cam_id>[^_]+(?:_\d+)?)_(?P<feature>.+?)_(?P<date>\d{8})_(?P<time>\d{6})\.(?P<ext>mp4|jpg)$'
)

FEATURE_SEVERITY = {
    "fire_smoke":          "CRITICAL",
    "no_go_zone":          "CRITICAL",
    "weapon_detection":    "CRITICAL",
    "criminal_face":       "CRITICAL",
    "intrusion":           "HIGH",
    "perimeter":           "HIGH",
    "missing_person":      "HIGH",
    "tampering":           "HIGH",
    "loitering":           "MEDIUM",
    "crowd":               "MEDIUM",
    "personal_monitoring": "MEDIUM",
    "footfall":            "LOW",
    "animal_detection":    "HIGH",
    "vehicle_detection":   "MEDIUM",
}


def _parse_filename(fn: str) -> dict | None:
    """Parse a clip filename into structured metadata."""
    m = _PATTERN.match(fn)
    if not m:
        return None
    d = m.group("date")   # 20260423
    t = m.group("time")   # 134430
    try:
        dt  = datetime.strptime(d + t, "%Y%m%d%H%M%S").replace(tzinfo=IST)
        iso = dt.isoformat()
    except ValueError:
        dt  = None
        iso = None

    feature = m.group("feature")
    return {
        "filename":   fn,
        "cam_id":     m.group("cam_id"),
        "feature":    feature,
        "ext":        m.group("ext"),
        "type":       "video" if m.group("ext") == "mp4" else "image",
        "severity":   FEATURE_SEVERITY.get(feature, "MEDIUM"),
        "timestamp":  iso,
        "date_label": dt.strftime("%d %b %Y") if dt else d,
        "time_label": dt.strftime("%H:%M:%S")  if dt else t,
        "size_kb":    os.path.getsize(os.path.join(CLIPS_DIR, fn)) // 1024,
        "url":        f"/api/clips/{fn}",
        "thumb_url":  f"/api/clips/{fn}" if m.group("ext") == "jpg" else None,
    }


# GET /api/clips  — list all clips with parsed metadata
@clips_router.get("/clips")
def list_clips(
    feature: Optional[str] = Query(default=None),
    cam_id:  Optional[str] = Query(default=None),
    type:    Optional[str] = Query(default=None),   # "image" | "video"
    limit:   int           = Query(default=200),
):
    try:
        files = sorted(
            [f for f in os.listdir(CLIPS_DIR)
             if f.endswith(('.mp4', '.jpg')) and not f.startswith('latest_frame')],
            reverse=True
        )
        clips = []
        for fn in files:
            meta = _parse_filename(fn)
            if meta is None:
                continue
            if feature and meta["feature"] != feature:
                continue
            if cam_id and meta["cam_id"] != cam_id:
                continue
            if type and meta["type"] != type:
                continue
            clips.append(meta)
            if len(clips) >= limit:
                break

        # Group by (cam_id, feature, date, time) — pair jpg + mp4 together
        paired: dict = {}
        for c in clips:
            key = f"{c['cam_id']}_{c['feature']}_{c['date_label']}_{c['time_label']}"
            if key not in paired:
                paired[key] = {**c, "has_video": False, "has_image": False}
            if c["type"] == "video":
                paired[key]["has_video"] = True
                paired[key]["video_url"] = c["url"]
            else:
                paired[key]["has_image"] = True
                paired[key]["image_url"] = c["url"]
                paired[key]["thumb_url"] = c["url"]
                paired[key]["url"]       = c["url"]

        result = sorted(paired.values(), key=lambda x: x.get("timestamp", ""), reverse=True)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/clips/{filename}  — serve image snapshots or redirect mp4 to video endpoint
@clips_router.get("/clips/{filename}")
def serve_clip(filename: str):
    if filename.endswith(".mp4"):
        return RedirectResponse(url=f"/api/clips/video/{filename}")
    filepath = os.path.join(CLIPS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, media_type="image/jpeg")


# GET /api/clips/video/{filename}  — stream MP4 with Range support
# Browsers REQUIRE HTTP 206 Partial Content to play video in <video> tag
@clips_router.get("/clips/video/{filename:path}")
def stream_video(filename: str, request: Request):
    filepath = os.path.join(CLIPS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    file_size    = os.path.getsize(filepath)
    range_header = request.headers.get("Range")

    # No Range header — return full file with Accept-Ranges hint
    if not range_header:
        with open(filepath, "rb") as f:
            data = f.read()
        return Response(
            content=data,
            status_code=200,
            media_type="video/mp4",
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges":  "bytes",
            },
        )

    # Parse "Range: bytes=start-end"
    byte1, byte2 = 0, file_size - 1
    m = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if m:
        byte1 = int(m.group(1))
        if m.group(2):
            byte2 = int(m.group(2))

    # Clamp to file bounds
    byte2  = min(byte2, file_size - 1)
    length = byte2 - byte1 + 1

    with open(filepath, "rb") as f:
        f.seek(byte1)
        data = f.read(length)

    return Response(
        content=data,
        status_code=206,
        media_type="video/mp4",
        headers={
            "Content-Range":  f"bytes {byte1}-{byte2}/{file_size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(len(data)),
            "Cache-Control":  "no-cache",
        },
    )


# DELETE /api/clips/{filename}
@clips_router.delete("/clips/{filename}")
def delete_clip(filename: str):
    filepath = os.path.join(CLIPS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
    except Exception as e:
        print(f"Error removing file {filepath}: {e}")
        
    # Also delete paired file (jpg ↔ mp4)
    base = os.path.splitext(filepath)[0]
    for ext in (".jpg", ".mp4"):
        paired = base + ext
        if os.path.exists(paired):
            try:
                os.remove(paired)
            except Exception as e:
                print(f"Error removing paired file {paired}: {e}")

    # Delete corresponding alert from DB
    meta = _parse_filename(filename)
    if meta and meta.get("timestamp"):
        try:
            from routes.alerts import _get_col, _read_json_alerts, ALERTS_JSON
            import json
            
            col = _get_col()
            # Match cam_id, feature, and timestamp prefix (since filename has no ms)
            query = {
                "cam_id": meta["cam_id"],
                "feature": meta["feature"],
                "timestamp": {"$regex": f"^{meta['timestamp']}"}
            }
            col.delete_many(query)

            # JSON file fallback
            alerts = _read_json_alerts()
            filtered_alerts = [
                a for a in alerts 
                if not (a.get("cam_id") == meta["cam_id"] and 
                        a.get("feature") == meta["feature"] and 
                        str(a.get("timestamp", "")).startswith(meta["timestamp"]))
            ]
            with open(ALERTS_JSON, 'w') as f:
                json.dump(filtered_alerts, f)
        except Exception as e:
            print("Failed to delete alert from DB:", e)

    return {"deleted": filename}
