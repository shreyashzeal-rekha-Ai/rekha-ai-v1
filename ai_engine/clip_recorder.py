"""
clip_recorder.py
----------------
On an alert event, saves a short video clip (CLIP_DURATION seconds)
from the camera's frame buffer to disk. Runs in its own thread so
the main inference pipeline is never blocked.
"""

import os
import cv2
import time
import queue
import logging
import threading
from datetime import datetime, timezone, timedelta

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger("clip_recorder")

CLIP_DIR      = os.path.join(os.path.dirname(__file__), '..', 'clips')
CLIP_DURATION = int(os.getenv("CLIP_DURATION_SECONDS", 10))
SAVE_CLIPS    = os.getenv("SAVE_CLIPS", "True").strip().lower() in ("true", "1", "yes")


class ClipRecorder(threading.Thread):
    """
    Listens on a clip_queue for recording jobs.
    Each job is a dict:
        {
          "cam_id":      str,
          "feature":     str,
          "frame_buffer": list[frame],  ← snapshot of last N frames
          "fps":         int
        }
    """

    def __init__(self):
        super().__init__(daemon=True, name="clip-recorder")
        self.clip_queue: queue.Queue = queue.Queue(maxsize=20)
        self.running = True
        os.makedirs(CLIP_DIR, exist_ok=True)

    def run(self):
        logger.info("[ClipRecorder] Thread started.")
        if not SAVE_CLIPS:
            logger.info("[ClipRecorder] Clip saving is disabled via SAVE_CLIPS.")
            return
        while self.running:
            try:
                job = self.clip_queue.get(timeout=1)
                self._write_clip(job)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[ClipRecorder] Unexpected error: {e}")

    def enqueue(self, cam_id: str, feature: str, frame_buffer: list, fps: int = 10):
        """
        Non-blocking enqueue. Drops the job silently if queue is full
        (prefer live detection over disk I/O backlog).
        """
        if not SAVE_CLIPS:
            return
        job = {
            "cam_id":       cam_id,
            "feature":      feature,
            "frame_buffer": list(frame_buffer),  # snapshot copy
            "fps":          fps
        }
        try:
            self.clip_queue.put_nowait(job)
        except queue.Full:
            logger.warning(f"[ClipRecorder] Clip queue full — skipping clip for {cam_id}/{feature}")

    def _write_clip(self, job: dict):
        cam_id  = job["cam_id"]
        feature = job["feature"]
        frames  = job["frame_buffer"]
        fps     = job["fps"]

        if not frames:
            return

        ts       = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        filename = f"{cam_id}_{feature}_{ts}.mp4"
        filepath = os.path.join(CLIP_DIR, filename)

        h, w     = frames[0].shape[:2]

        # avc1 = H.264 — the ONLY codec Chrome/Edge can play in <video> tag.
        # mp4v = MPEG-4 Visual — browsers refuse to play it (shows black at 0:00).
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        writer = cv2.VideoWriter(filepath, fourcc, fps, (w, h))

        # Fallback: some OpenCV builds don't have avc1 on Windows
        if not writer.isOpened():
            logger.warning("[ClipRecorder] avc1 not available, falling back to mp4v (browser may not play).")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(filepath, fourcc, fps, (w, h))

        for frame in frames:
            writer.write(frame)
        writer.release()


        size_kb = os.path.getsize(filepath) // 1024
        logger.info(f"[ClipRecorder] ✅ Saved clip: {filename} ({size_kb} KB, {len(frames)} frames)")

    def stop(self):
        self.running = False
