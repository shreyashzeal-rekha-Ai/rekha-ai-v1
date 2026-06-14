"""
watchdog.py
-----------
System health monitor. Runs every WATCHDOG_INTERVAL seconds and checks:
  - GPU VRAM usage
  - System RAM usage
  - Thread liveness (heartbeat age per camera)
  - Logs warnings if thresholds breached
  - Can auto-clear queues if RAM is critical
"""

import os
import time
import logging
import threading
import psutil
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger("watchdog")

INTERVAL    = int(os.getenv("WATCHDOG_INTERVAL_SECONDS", 30))
MAX_RAM_PCT = int(os.getenv("MAX_RAM_PERCENT", 85))
MAX_GPU_PCT = int(os.getenv("MAX_GPU_PERCENT", 95))
HEARTBEAT_TIMEOUT = 10  # seconds — camera thread considered dead if no frame this long

try:
    import GPUtil
    _GPU_AVAILABLE = True
except ImportError:
    _GPU_AVAILABLE = False
    logger.warning("[Watchdog] GPUtil not installed — GPU monitoring disabled.")


class Watchdog(threading.Thread):
    """
    Monitors system resources and camera thread health.

    Args:
        camera_readers: list of CameraReader instances to monitor
    """

    def __init__(self, camera_readers: list):
        super().__init__(daemon=True, name="watchdog")
        self.cameras  = camera_readers
        self.running  = True
        self._alerts  = 0

    def run(self):
        logger.info(f"[Watchdog] Started. Interval={INTERVAL}s RAM_MAX={MAX_RAM_PCT}% GPU_MAX={MAX_GPU_PCT}%")
        while self.running:
            time.sleep(INTERVAL)
            self._check_ram()
            self._check_gpu()
            self._check_cameras()

    # ------------------------------------------------------------------

    def _check_ram(self):
        ram = psutil.virtual_memory()
        pct = ram.percent
        used_gb = ram.used / (1024 ** 3)
        total_gb = ram.total / (1024 ** 3)

        if pct >= MAX_RAM_PCT:
            logger.warning(
                f"[Watchdog] ⚠️  HIGH RAM: {pct:.1f}% "
                f"({used_gb:.1f}/{total_gb:.1f} GB) — consider reducing camera count."
            )
        else:
            logger.info(f"[Watchdog] RAM: {pct:.1f}% ({used_gb:.1f}/{total_gb:.1f} GB) ✅")

    def _check_gpu(self):
        if not _GPU_AVAILABLE:
            return
        try:
            gpus = GPUtil.getGPUs()
            for gpu in gpus:
                mem_pct = (gpu.memoryUsed / gpu.memoryTotal) * 100
                load_pct = gpu.load * 100
                if mem_pct >= MAX_GPU_PCT:
                    logger.warning(
                        f"[Watchdog] ⚠️  HIGH GPU VRAM: {mem_pct:.1f}% "
                        f"({gpu.memoryUsed}MB/{gpu.memoryTotal}MB) on {gpu.name}"
                    )
                else:
                    logger.info(
                        f"[Watchdog] GPU '{gpu.name}': "
                        f"VRAM={mem_pct:.1f}% Load={load_pct:.1f}% Temp={gpu.temperature}°C ✅"
                    )
        except Exception as e:
            logger.error(f"[Watchdog] GPU check error: {e}")

    def _check_cameras(self):
        for cam in self.cameras:
            age = cam.heartbeat_age()
            if age > HEARTBEAT_TIMEOUT:
                logger.warning(
                    f"[Watchdog] 💀 Camera '{cam.cam_name}' (id={cam.cam_id}) "
                    f"last frame {age:.1f}s ago — may be frozen or disconnected."
                )
            else:
                logger.info(
                    f"[Watchdog] Camera '{cam.cam_name}': alive ✅ "
                    f"(last frame {age:.1f}s ago, queue={cam.frame_queue.qsize()})"
                )

    def stop(self):
        self.running = False
