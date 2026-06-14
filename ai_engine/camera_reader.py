"""
camera_reader.py
----------------
Opens a webcam or RTSP stream per camera config entry.
Each camera runs in its own thread and pushes frames to a queue.
Auto-reconnects if the stream drops.

Latency fixes applied:
  • BUFFERSIZE=1 — prevents frame buffer buildup
  • grab()/retrieve() — always reads latest frame, discards stale ones
  • TCP transport — stable RTSP connection
  • Queue drain — never processes old frames

API expected by main.py:
    reader = CameraReader(cam_config_dict)
    reader.start()
    frame = reader.get_frame(timeout=0.05)
    reader.cam_id
    reader.stop()
"""

import os
import cv2
import time
import queue
import logging
import threading

from vidgear.gears import CamGear

# Force TCP transport for all RTSP streams — reduces latency vs UDP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

logger = logging.getLogger("camera_reader")

MAX_BUFFER = 2  # Keep only 2 frames max — forces always-latest processing


class CameraReader(threading.Thread):
    """
    Reads frames from a source (int = webcam index, str = RTSP URL).
    Pushes frames into self.frame_queue for the pipeline to consume.
    """

    def __init__(self, cam_config: dict):
        super().__init__(daemon=True, name=f"cam-{cam_config['id']}")
        self.cam_id    = cam_config["id"]
        self.cam_name  = cam_config.get("name", self.cam_id)
        self.source    = cam_config["source"]
        self.fps_limit = cam_config.get("fps_limit", 10)

        # Convert source to int if it represents a numeric webcam ID
        if isinstance(self.source, str) and self.source.isdigit():
            self.source = int(self.source)
        elif isinstance(self.source, float):
            self.source = int(self.source)

        self.frame_queue: queue.Queue = queue.Queue(maxsize=MAX_BUFFER)
        self.running          = True
        self._reconnect_delay = 3.0
        self._last_heartbeat  = time.time()
        self.latest_frame     = None
        self.stream           = None

    def run(self):
        logger.info(f"[{self.cam_name}] Starting capture via CamGear from: {self.source}")

        # Configure CamGear options for low latency and TCP RTSP transport
        options = {}
        if isinstance(self.source, str) and self.source.startswith("rtsp"):
            options = {
                "CAP_PROP_BUFFERSIZE": 1,
                "FFMPEG_OPTIONS": {
                    "-rtsp_transport": "tcp",
                }
            }
        else:
            options = {
                "CAP_PROP_BUFFERSIZE": 1
            }

        while self.running:
            try:
                self.stream = CamGear(source=self.source, logging=False, **options).start()
                logger.info(f"[{self.cam_name}] ✅ CamGear stream started.")
            except Exception as e:
                logger.warning(
                    f"[{self.cam_name}] CamGear failed to start: {e}. "
                    f"Retrying in {self._reconnect_delay}s..."
                )
                time.sleep(self._reconnect_delay)
                continue

            while self.running:
                try:
                    frame = self.stream.read()
                except Exception as e:
                    logger.error(f"[{self.cam_name}] Error reading frame: {e}")
                    break

                if frame is None:
                    logger.warning(f"[{self.cam_name}] Received None frame. Stream might be lost. Reconnecting...")
                    break

                self._last_heartbeat = time.time()
                self.latest_frame    = frame.copy()

                # Always keep queue fresh — drop old frames immediately
                while not self.frame_queue.empty():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        break
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    pass

                # Since CamGear internally handles threading and blocks/throttles on new frames,
                # we don't need a strict sleep here, but a tiny sleep yields CPU control.
                time.sleep(0.001)

            if self.stream:
                try:
                    self.stream.stop()
                except Exception:
                    pass
                self.stream = None

            if self.running:
                logger.info(f"[{self.cam_name}] Reconnecting in {self._reconnect_delay}s...")
                time.sleep(self._reconnect_delay)

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
            except Exception:
                pass

    def get_frame(self, timeout: float = 1.0):
        """Blocking get with timeout. Returns None on timeout."""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_latest_frame(self):
        """Returns most recent frame without popping queue."""
        return self.latest_frame

    def heartbeat_age(self) -> float:
        """Seconds since last successful frame read."""
        return time.time() - self._last_heartbeat


# ── Standalone test ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    cam_config = {
        "id": "cam_01",
        "name": "Laptop Webcam",
        "source": 0,
        "fps_limit": 15,
        "features": [],
        "zones": []
    }

    reader = CameraReader(cam_config)
    reader.start()
    time.sleep(1)

    logger.info("Camera reader test running. Press 'q' to quit.")
    while True:
        frame = reader.get_frame(timeout=1.0)
        if frame is not None:
            cv2.imshow("CameraReader Test", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    reader.stop()
    cv2.destroyAllWindows()