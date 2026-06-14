"""
routes/cameras.py
-----------------
REST endpoints for camera config (read from cameras.json).
"""

import os
import json
from fastapi import APIRouter, HTTPException, Request

ROOT_DIR     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAMERAS_JSON = os.path.join(ROOT_DIR, 'cameras.json')

cameras_router = APIRouter()


def _load() -> list:
    with open(CAMERAS_JSON, 'r') as f:
        return json.load(f).get("cameras", [])


def _save(cameras: list):
    with open(CAMERAS_JSON, 'w') as f:
        json.dump({"cameras": cameras}, f, indent=2)


# GET /api/cameras
@cameras_router.get("/cameras")
def get_cameras():
    try:
        return _load()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/cameras/{cam_id}
@cameras_router.get("/cameras/{cam_id}")
def get_camera(cam_id: str):
    try:
        cams = _load()
        cam  = next((c for c in cams if c["id"] == cam_id), None)
        if not cam:
            raise HTTPException(status_code=404, detail="Camera not found")
        return cam
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# PATCH /api/cameras/{cam_id}/features  — toggle features
@cameras_router.patch("/cameras/{cam_id}/features")
async def update_features(cam_id: str, request: Request):
    try:
        data     = await request.json()
        features = data.get("features", [])
        cams     = _load()
        cam      = next((c for c in cams if c["id"] == cam_id), None)
        if not cam:
            raise HTTPException(status_code=404, detail="Camera not found")
        cam["features"] = features
        _save(cams)
        return cam
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# POST /api/cameras/{cam_id}/config  — full config from Settings Panel
# Saves enabled features + drawn zones + counting/perimeter lines all at once.
@cameras_router.post("/cameras/{cam_id}/config")
async def update_config(cam_id: str, request: Request):
    """
    Payload from SettingsPage.jsx:
    {
        "name":           "Custom Name",
        "source":         "rtsp://...",
        "features":       ["intrusion", "loitering", ...],
        "zones":          [ { id, name, type, shape, points, polygon, line, alert_on_* } ],
        "counting_line":  [[x1,y1],[x2,y2]] | null,
        "perimeter_line": [[x1,y1],[x2,y2]] | null
    }
    Writes the full updated camera config to cameras.json.
    The AI engine picks up changes on next 5-second hot-reload cycle.
    """
    try:
        data = await request.json()
        if not data:
            raise HTTPException(status_code=400, detail="Empty payload")

        cams = _load()
        cam  = next((c for c in cams if c["id"] == cam_id), None)
        if not cam:
            raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

        # Update metadata
        if "name" in data:
            cam["name"] = data["name"]
        if "source" in data:
            cam["source"] = data["source"]

        # Update enabled features list
        if "features" in data:
            cam["features"] = data["features"]

        # Update zones (replace entirely)
        if "zones" in data:
            cam["zones"] = data["zones"]

        # Update counting line (footfall)
        if "counting_line" in data:
            cam["counting_line"] = data["counting_line"]

        # Update perimeter line
        if "perimeter_line" in data:
            cam["perimeter_line"] = data["perimeter_line"]

        # Update feature-specific settings
        if "full_frame_analytics" in data:
            cam["full_frame_analytics"] = bool(data["full_frame_analytics"])
        if "loitering_timeout_seconds" in data:
            cam["loitering_timeout_seconds"] = int(data["loitering_timeout_seconds"])
        if "crowd_threshold" in data:
            cam["crowd_threshold"] = int(data["crowd_threshold"])
        if "missing_person_timeout_seconds" in data:
            cam["missing_person_timeout_seconds"] = int(data["missing_person_timeout_seconds"])
        if "missing_person_target_count" in data:
            cam["missing_person_target_count"] = int(data["missing_person_target_count"])
        if "footfall_view_type" in data:
            cam["footfall_view_type"] = str(data["footfall_view_type"])
        if "footfall_invert" in data:
            cam["footfall_invert"] = bool(data["footfall_invert"])
        if "tampering_sensitivity" in data:
            cam["tampering_sensitivity"] = int(data["tampering_sensitivity"])
        if "personal_monitoring_timeout_seconds" in data:
            cam["personal_monitoring_timeout_seconds"] = int(data["personal_monitoring_timeout_seconds"])
        # Phase 2 Animal Detection settings
        if "animal_detection_mode" in data:
            cam["animal_detection_mode"] = str(data["animal_detection_mode"])
        if "animal_confidence" in data:
            cam["animal_confidence"] = float(data["animal_confidence"])
        # Phase 3 Vehicle Counting settings
        if "vehicle_detection_mode" in data:
            cam["vehicle_detection_mode"] = str(data["vehicle_detection_mode"])
        if "vehicle_confidence" in data:
            cam["vehicle_confidence"] = float(data["vehicle_confidence"])
        if "vehicle_count_threshold" in data:
            cam["vehicle_count_threshold"] = int(data["vehicle_count_threshold"])
        # Phase 4 Abandoned Object settings
        if "abandoned_object_mode" in data:
            cam["abandoned_object_mode"] = str(data["abandoned_object_mode"])
        if "abandoned_timeout_seconds" in data:
            cam["abandoned_timeout_seconds"] = int(data["abandoned_timeout_seconds"])
        if "abandoned_confidence" in data:
            cam["abandoned_confidence"] = float(data["abandoned_confidence"])
        # Phase 5 ANPR settings
        if "anpr_mode" in data:
            cam["anpr_mode"] = str(data["anpr_mode"])
        if "anpr_confidence" in data:
            cam["anpr_confidence"] = float(data["anpr_confidence"])
        # Feature-level schedule windows
        for sched_key in (
            "loitering_schedule", "crowd_schedule", "missing_person_schedule",
            "footfall_schedule", "tampering_schedule",
            "personal_monitoring_schedule", "perimeter_schedule",
        ):
            if sched_key in data:
                cam[sched_key] = data[sched_key]   # None or {enabled, days, start, end}

        _save(cams)

        return {
            "status":   "ok",
            "cam_id":   cam_id,
            "name":     cam["name"],
            "source":   cam["source"],
            "features": cam["features"],
            "zones":    len(cam.get("zones", [])),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=505, detail=str(e))


# POST /api/cameras — Add a new camera
@cameras_router.post("/cameras")
async def add_camera(request: Request):
    try:
        data = await request.json()
        cams = _load()

        # Find highest camera ID suffix (e.g. cam_04 -> 4)
        max_idx = 0
        for c in cams:
            cid = c.get("id", "")
            if cid.startswith("cam_"):
                try:
                    idx = int(cid.split("_")[1])
                    if idx > max_idx:
                        max_idx = idx
                except (IndexError, ValueError):
                    pass
        new_idx = max_idx + 1
        new_id = f"cam_{new_idx:02d}"

        new_cam = {
            "id": new_id,
            "name": data.get("name", f"CP Plus - Channel {new_idx}"),
            "source": data.get("source", ""),
            "fps_limit": 30,
            "features": [],
            "loitering_timeout_seconds": 15,
            "crowd_threshold": 3,
            "missing_person_timeout_seconds": 180,
            "personal_monitoring_timeout_seconds": 30,
            "counting_line": None,
            "perimeter_line": None,
            "anpr_mode": "full_frame",
            "anpr_confidence": 0.40,
            "zones": []
        }

        cams.append(new_cam)
        _save(cams)
        return new_cam
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /api/cameras/{cam_id} — Delete a camera
@cameras_router.delete("/cameras/{cam_id}")
def delete_camera(cam_id: str):
    try:
        cams = _load()
        cam  = next((c for c in cams if c["id"] == cam_id), None)
        if not cam:
            raise HTTPException(status_code=404, detail="Camera not found")

        cams = [c for c in cams if c["id"] != cam_id]
        _save(cams)

        # Try to delete latest frame file if it exists
        try:
            latest_frame_path = os.path.join(ROOT_DIR, "clips", f"latest_frame_{cam_id}.jpg")
            if os.path.exists(latest_frame_path):
                os.remove(latest_frame_path)
        except Exception:
            pass

        return {"status": "ok", "deleted": cam_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /api/cameras/{cam_id}/zones — Wipe all zones, lines and features for a camera
@cameras_router.delete("/cameras/{cam_id}/zones")
def clear_camera_zones(cam_id: str):
    """
    Clears zones, counting_line, perimeter_line, and features list for the camera.
    Also deletes the latest annotated frame file so the stream immediately shows
    an unannotated raw feed while the AI engine hot-reloads (~1 s).
    """
    try:
        cams = _load()
        cam  = next((c for c in cams if c["id"] == cam_id), None)
        if not cam:
            raise HTTPException(status_code=404, detail="Camera not found")

        cam["features"]       = []
        cam["zones"]          = []
        cam["counting_line"]  = None
        cam["perimeter_line"] = None

        _save(cams)

        # Delete the annotated latest-frame file so the stream immediately
        # falls back to unannotated raw capture while the AI engine reloads.
        clips_dir  = os.path.join(ROOT_DIR, 'clips')
        frame_path = os.path.join(clips_dir, f'latest_frame_{cam_id}.jpg')
        try:
            if os.path.exists(frame_path):
                os.remove(frame_path)
        except Exception:
            pass

        return {"status": "ok", "cam_id": cam_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
