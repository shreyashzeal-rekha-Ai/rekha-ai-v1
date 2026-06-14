"""
routes/zones.py
---------------
REST endpoints for managing restricted zones on cameras.
Zones are persisted in cameras.json under each camera's "zones" array.
"""

import os
import json
from fastapi import APIRouter, HTTPException, Request

ROOT_DIR     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAMERAS_JSON = os.path.join(ROOT_DIR, 'cameras.json')

zones_router = APIRouter()


def _load() -> list:
    with open(CAMERAS_JSON, 'r') as f:
        return json.load(f).get("cameras", [])


def _save(cameras: list):
    with open(CAMERAS_JSON, 'w') as f:
        json.dump({"cameras": cameras}, f, indent=2)


# GET /api/cameras/{cam_id}/zones
@zones_router.get("/cameras/{cam_id}/zones")
def get_zones(cam_id: str):
    cams = _load()
    cam  = next((c for c in cams if c["id"] == cam_id), None)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam.get("zones", [])


# POST /api/cameras/{cam_id}/zones  — add a new zone
@zones_router.post("/cameras/{cam_id}/zones", status_code=201)
async def add_zone(cam_id: str, request: Request):
    data = await request.json()
    # Expected: { "id": "z1", "name": "...", "polygon": [[x,y],...], "alert_on_intrusion": true }
    required = {"id", "name", "polygon"}
    missing  = required - data.keys()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {missing}")

    cams = _load()
    cam  = next((c for c in cams if c["id"] == cam_id), None)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    cam.setdefault("zones", []).append(data)
    _save(cams)
    return data


# DELETE /api/cameras/{cam_id}/zones/{zone_id}
@zones_router.delete("/cameras/{cam_id}/zones/{zone_id}")
def delete_zone(cam_id: str, zone_id: str):
    cams = _load()
    cam  = next((c for c in cams if c["id"] == cam_id), None)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    before      = len(cam.get("zones", []))
    cam["zones"] = [z for z in cam.get("zones", []) if z["id"] != zone_id]
    if len(cam["zones"]) == before:
        raise HTTPException(status_code=404, detail="Zone not found")

    _save(cams)
    return {"deleted": zone_id}
