"""
routes/alerts.py
----------------
REST endpoints for alert data.
Primary: MongoDB
Fallback: alerts.json written by alert_engine
"""

import os
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALERTS_JSON = os.path.join(ROOT_DIR, 'alerts.json')
MONGO_URI   = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB    = os.getenv("MONGO_DB",  "expert_cctv")

alerts_router = APIRouter()


def _get_col():
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    client.server_info()
    return client[MONGO_DB]["alerts"]


def _read_json_alerts() -> list:
    """Read alerts from the JSON fallback file."""
    try:
        with open(ALERTS_JSON, 'r') as f:
            return json.load(f)
    except Exception:
        return []


# GET /api/alerts?limit=50&cam_id=cam_01&feature=fire_smoke
@alerts_router.get("/alerts")
def get_alerts(
    limit:   int            = Query(default=50,   le=200),
    cam_id:  Optional[str]  = Query(default=None),
    feature: Optional[str]  = Query(default=None),
):
    try:
        # Try MongoDB first
        from pymongo import DESCENDING
        col  = _get_col()
        q    = {}
        if cam_id:  q["cam_id"]  = cam_id
        if feature: q["feature"] = feature
        docs = list(col.find(q).sort("timestamp", DESCENDING).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        pass

    # Fallback: read from JSON file
    alerts = _read_json_alerts()
    if cam_id:  alerts = [a for a in alerts if a.get("cam_id")  == cam_id]
    if feature: alerts = [a for a in alerts if a.get("feature") == feature]
    return alerts[:limit]


# GET /api/alerts/stats
@alerts_router.get("/alerts/stats")
def get_stats():
    try:
        from datetime import datetime, timedelta, timezone
        from pymongo import MongoClient
        IST   = timezone(timedelta(hours=5, minutes=30), name="IST")
        since = (datetime.now(IST) - timedelta(hours=24)).isoformat()
        col      = _get_col()
        pipeline = [
            {"$match":  {"timestamp": {"$gte": since}}},
            {"$group":  {"_id": "$feature", "count": {"$sum": 1}}},
            {"$sort":   {"count": -1}},
        ]
        results = list(col.aggregate(pipeline))
        return {"last_24h": {r["_id"]: r["count"] for r in results}}
    except Exception:
        pass

    # Fallback: count from JSON
    alerts = _read_json_alerts()
    counts: dict = {}
    for a in alerts:
        f = a.get("feature", "unknown")
        counts[f] = counts.get(f, 0) + 1
    return {"last_24h": counts}


# DELETE /api/alerts
@alerts_router.delete("/alerts")
def clear_alerts(feature: Optional[str] = Query(default=None)):
    deleted = 0
    query = {}
    if feature:
        query["feature"] = feature

    try:
        col     = _get_col()
        result  = col.delete_many(query)
        deleted = result.deleted_count
    except Exception:
        pass

    # Clear JSON file
    try:
        alerts = _read_json_alerts()
        if feature:
            alerts = [a for a in alerts if a.get("feature") != feature]
        else:
            alerts = []
        with open(ALERTS_JSON, 'w') as f:
            json.dump(alerts, f)
    except Exception:
        pass

    # Delete corresponding clips from the clips directory
    try:
        clips_dir = os.path.join(ROOT_DIR, 'clips')
        if os.path.exists(clips_dir):
            for fn in os.listdir(clips_dir):
                if fn.endswith(('.mp4', '.jpg')) and not fn.startswith('latest_frame'):
                    # if feature is not specified, delete all clips
                    # if feature is specified, only delete if the filename contains the feature
                    if feature is None or f"_{feature}_" in fn:
                        try:
                            os.remove(os.path.join(clips_dir, fn))
                        except Exception as e:
                            print(f"Error removing file {fn}: {e}")
    except Exception as e:
        print(f"Error reading clips directory: {e}")

    return {"deleted": deleted}


import asyncio
from fastapi.responses import StreamingResponse

# Set of active SSE client queues
sse_clients = set()

# POST /api/alerts/notify  — called by AI Engine to push real-time alerts
@alerts_router.post("/alerts/notify")
async def notify_alert(alert_doc: dict):
    # Put alert in all active SSE client queues
    for q in list(sse_clients):
        try:
            await q.put(alert_doc)
        except Exception:
            pass
    return {"status": "ok"}


# GET /api/alerts/events  — SSE stream called by frontend React app
@alerts_router.get("/alerts/events")
async def alerts_stream():
    q = asyncio.Queue()
    sse_clients.add(q)

    async def event_generator():
        try:
            while True:
                # Keepalive ping every 10 seconds to prevent connection drops
                try:
                    alert = await asyncio.wait_for(q.get(), timeout=10.0)
                    yield f"data: {json.dumps(alert)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"ping\": true}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            sse_clients.discard(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# GET /api/analytics/vehicles
@alerts_router.get("/analytics/vehicles")
def get_vehicle_analytics():
    path = os.path.join(ROOT_DIR, 'vehicle_counts.json')
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


# GET /api/analytics/footfall
@alerts_router.get("/analytics/footfall")
def get_footfall_analytics():
    path = os.path.join(ROOT_DIR, 'footfall_counts.json')
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}
