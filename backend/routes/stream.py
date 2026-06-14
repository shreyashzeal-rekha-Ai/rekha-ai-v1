"""
routes/stream.py — per-camera MJPEG stream (FastAPI edition)

Uses StreamingResponse with a sync generator.
FastAPI runs sync generators in a thread pool automatically,
so time.sleep() inside the generator does NOT block the event loop.
"""

import os
import time
import cv2
import threading
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response

stream_router = APIRouter()

ROOT_DIR     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIPS_DIR    = os.path.join(ROOT_DIR, 'clips')
CAMERAS_JSON = os.path.join(ROOT_DIR, 'cameras.json')

JPEG_QUALITY = 88
STREAM_FPS   = 15
_frame_delay = 1.0 / STREAM_FPS


def _cam_source(cam_id: str):
    try:
        with open(CAMERAS_JSON) as f:
            cams = json.load(f).get("cameras", [])
        cam = next((c for c in cams if c["id"] == cam_id), None)
        if cam:
            return cam.get("source", 0)
    except Exception:
        pass
    return 0


def _generate_from_file(cam_id: str):
    """Serve per-camera latest frame written by the AI engine — never goes black."""
    frame_path = os.path.join(CLIPS_DIR, f'latest_frame_{cam_id}.jpg')
    last_data  = None
    last_mtime = 0.0

    while True:
        try:
            mtime = os.path.getmtime(frame_path)
            if mtime != last_mtime:
                with open(frame_path, 'rb') as f:
                    data = f.read()
                if data:
                    last_data  = data
                    last_mtime = mtime
        except Exception:
            pass

        if last_data:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n'
                   + last_data + b'\r\n')
        time.sleep(_frame_delay)


_cap_lock  = threading.Lock()
_cap_cache: dict = {"cap": None, "src": None}


def _get_cap(source):
    with _cap_lock:
        if _cap_cache["src"] != source or _cap_cache["cap"] is None:
            if _cap_cache["cap"] is not None:
                _cap_cache["cap"].release()
            _cap_cache["cap"] = cv2.VideoCapture(source)
            _cap_cache["src"] = source
        return _cap_cache["cap"]


def _generate_from_cap(source):
    cap      = _get_cap(source)
    last_buf = None
    while True:
        with _cap_lock:
            ok, frame = cap.read()
        if ok:
            ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ret:
                last_buf = buf.tobytes()
        if last_buf:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n'
                   + last_buf + b'\r\n')
        time.sleep(_frame_delay)


def _smart_generate(cam_id: str):
    """
    Unified generator — switches dynamically between two modes every frame:
      • AI-annotated mode : reads latest_frame_{cam_id}.jpg (written by AI engine)
      • Raw-capture mode  : reads directly from the camera when the file is absent
                            (happens immediately after Reset All clears the file)
    This means zones vanish from the stream the instant Reset is clicked, with
    no restart required.
    """
    frame_path = os.path.join(CLIPS_DIR, f'latest_frame_{cam_id}.jpg')
    last_data   = None
    last_mtime  = 0.0
    cap         = None
    cap_source  = None

    while True:
        data = None

        if os.path.exists(frame_path):
            # ── AI-annotated mode ──────────────────────────────────────
            try:
                mtime = os.path.getmtime(frame_path)
                if mtime != last_mtime:
                    with open(frame_path, 'rb') as fh:
                        raw = fh.read()
                    if raw:
                        last_data  = raw
                        last_mtime = mtime
            except Exception:
                pass
            data = last_data

        else:
            # ── Raw-capture fallback (file was deleted on Reset) ───────
            last_data  = None   # discard stale annotated frame
            last_mtime = 0.0
            src = _cam_source(cam_id)
            try:
                if cap is None or cap_source != src:
                    if cap is not None:
                        cap.release()
                    cap        = cv2.VideoCapture(src)
                    cap_source = src
                ok, frame = cap.read()
                if ok:
                    ret, buf = cv2.imencode('.jpg', frame,
                                           [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                    if ret:
                        data = buf.tobytes()
            except Exception:
                pass

        if data:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n'
                   + data + b'\r\n')

        time.sleep(_frame_delay)


# GET /api/cameras/{cam_id}/stream
@stream_router.get("/cameras/{cam_id}/stream")
def stream(cam_id: str):
    return StreamingResponse(
        _smart_generate(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control":               "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        },
    )


# GET /api/cameras/{cam_id}/snapshot
@stream_router.get("/cameras/{cam_id}/snapshot")
def snapshot(cam_id: str):
    frame_path = os.path.join(CLIPS_DIR, f'latest_frame_{cam_id}.jpg')
    if os.path.exists(frame_path):
        try:
            with open(frame_path, 'rb') as f:
                data = f.read()
            return Response(content=data, media_type='image/jpeg')
        except Exception:
            pass

    source    = _cam_source(cam_id)
    cap       = cv2.VideoCapture(source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Camera unavailable")
    ret, buf = cv2.imencode('.jpg', frame)
    if not ret:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Frame encode failed")
    return Response(content=buf.tobytes(), media_type='image/jpeg')