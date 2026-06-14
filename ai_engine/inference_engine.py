"""
inference_engine.py
-------------------
ModelRegistry: loads YOLO models ONCE at startup and serves them
to all camera threads. No model duplication = minimal GPU VRAM usage.

Person model uses .predict() (pure stateless detection) — the per-camera
PersonTracker in person_tracker.py handles all track-ID assignment and
persistence via IoU matching. This avoids cross-camera ByteTrack state
contamination that occurs when .track(persist=True) is shared across cameras.
Fire model uses .track() with its own ByteTrack state.
"""

import os
import logging
import torch
import threading
from ultralytics import YOLO
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger("inference_engine")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Person-based features — all share the same tracked person result
PERSON_FEATURES = {
    "intrusion", "loitering", "footfall", "crowd",
    "missing_person", "no_go_zone", "perimeter", "personal_monitoring",
    "animal_detection",   # Phase 2: reuses person model — zero extra VRAM
    "vehicle_detection",  # Phase 3: reuses person model — zero extra VRAM
    "abandoned_object",   # Phase 4: reuses person model — zero extra VRAM
}

# COCO animal class IDs supported by yolo11x.pt (used when animal_detection enabled)
ANIMAL_CLASS_IDS = [14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

# COCO vehicle class IDs supported by yolo11x.pt (used when vehicle_detection enabled)
VEHICLE_CLASS_IDS = [1, 2, 3, 5, 7]

# COCO luggage class IDs supported by yolo11x.pt (used when abandoned_object enabled)
LUGGAGE_CLASS_IDS = [24, 26, 28]


class ModelRegistry:
    """
    Loads ONLY the models required by the features enabled across all cameras.

    Example:
      - Camera has only "intrusion"  → loads person model only, skips fire_model
      - Camera has "fire_smoke" only → loads fire model only, skips person model
      - Camera has both              → loads both

    Call ModelRegistry.build(all_features) at startup with the full set of
    features enabled across ALL cameras. Call ModelRegistry.get() after that.
    """

    _instance = None

    def __init__(self, all_features: set):
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self._lock = threading.Lock()
        logger.info(f"[ModelRegistry] Device: {self.device}")
        logger.info(f"[ModelRegistry] Features requested: {all_features}")

        # ── Person model — only if any person feature is enabled ────────
        needs_person = bool(all_features & PERSON_FEATURES)
        if needs_person:
            person_path = os.path.join(BASE_DIR, os.getenv("PERSON_MODEL_PATH", "models/yolo11n.pt"))
            logger.info(f"[ModelRegistry] Loading person model: {person_path}")
            self.person_model = self._load(person_path)
            logger.info(f"[ModelRegistry] ✅ person model loaded ({os.path.basename(person_path)})")
        else:
            self.person_model = None
            logger.info("[ModelRegistry] ⏭️  Person model skipped — no person features enabled")

        # ── Fire model — only if fire_smoke is enabled ──────────────────
        needs_fire = "fire_smoke" in all_features
        if needs_fire:
            fire_path = os.path.join(BASE_DIR, os.getenv("FIRE_MODEL_PATH", "models/fire_model.pt"))
            logger.info(f"[ModelRegistry] Loading fire model: {fire_path}")
            self.fire_model = self._load(fire_path)
            logger.info(f"[ModelRegistry] ✅ fire model loaded ({os.path.basename(fire_path)})")
        else:
            self.fire_model = None
            logger.info("[ModelRegistry] ⏭️  Fire model skipped — fire_smoke not enabled")

        # ── Plate model — only if anpr is enabled ───────────────────
        needs_plate = "anpr" in all_features
        if needs_plate:
            plate_path = os.path.join(BASE_DIR, os.getenv("PLATE_MODEL_PATH", "models/plate_model.pt"))
            self._check_and_download_plate_model(plate_path)
            logger.info(f"[ModelRegistry] Loading plate model: {plate_path}")
            self.plate_model = self._load(plate_path)
            logger.info(f"[ModelRegistry] ✅ plate model loaded ({os.path.basename(plate_path)})")
        else:
            self.plate_model = None
            logger.info("[ModelRegistry] ⏭️  Plate model skipped — anpr not enabled")

        logger.info("[ModelRegistry] ✅ Done. Only needed models are in GPU memory.")

    def _load(self, path: str) -> YOLO:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found: {path}")
        model = YOLO(path)
        model.to(self.device)
        return model

    def get_person_model(self) -> YOLO:
        with self._lock:
            if self.person_model is None:
                person_path = os.path.join(BASE_DIR, os.getenv("PERSON_MODEL_PATH", "models/yolov8s.pt"))
                logger.info(f"[ModelRegistry] On-demand loading person model: {person_path}")
                self.person_model = self._load(person_path)
                logger.info(f"[ModelRegistry] ✅ person model loaded")
            return self.person_model

    def get_fire_model(self) -> YOLO:
        with self._lock:
            if self.fire_model is None:
                fire_path = os.path.join(BASE_DIR, os.getenv("FIRE_MODEL_PATH", "models/fire_model.pt"))
                logger.info(f"[ModelRegistry] On-demand loading fire model: {fire_path}")
                self.fire_model = self._load(fire_path)
                logger.info(f"[ModelRegistry] ✅ fire model loaded")
            return self.fire_model

    def _check_and_download_plate_model(self, path: str):
        if os.path.exists(path):
            return
        logger.info(f"[ModelRegistry] Plate model not found at {path}. Automatically downloading...")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        url = "https://huggingface.co/keremberke/yolov8n-license-plate-localization/resolve/main/best.pt"
        try:
            import urllib.request
            logger.info(f"[ModelRegistry] Downloading from {url} ...")
            urllib.request.urlretrieve(url, path)
            logger.info(f"[ModelRegistry] ✅ Download complete. Saved to {path}")
        except Exception as e:
            logger.error(f"[ModelRegistry] ❌ Failed to download plate model: {e}")

    def get_plate_model(self) -> YOLO:
        with self._lock:
            if self.plate_model is None:
                plate_path = os.path.join(BASE_DIR, os.getenv("PLATE_MODEL_PATH", "models/plate_model.pt"))
                self._check_and_download_plate_model(plate_path)
                logger.info(f"[ModelRegistry] On-demand loading plate model: {plate_path}")
                self.plate_model = self._load(plate_path)
                logger.info(f"[ModelRegistry] ✅ plate model loaded")
            return self.plate_model

    @classmethod
    def build(cls, all_features: set) -> "ModelRegistry":
        """Call this ONCE at startup with all features from all cameras."""
        cls._instance = ModelRegistry(all_features)
        return cls._instance

    @classmethod
    def get(cls) -> "ModelRegistry":
        if cls._instance is None:
            raise RuntimeError("ModelRegistry not built yet. Call ModelRegistry.build(features) first.")
        return cls._instance


def run_inference(
    registry: ModelRegistry,
    frame,
    features: list[str],
    fire_lock: "threading.Lock | None" = None,
    person_lock: "threading.Lock | None" = None,
    fire_conf: float = None,       # per-camera override (None → use FIRE_CONFIDENCE env)
    fire_imgsz: int = 640,         # YOLO imgsz for fire model
    fire_frame = None,             # actual high-res frame fed to fire model (cam_03/04 → 1280x720)
                                   # if None, falls back to `frame` (640x360)
) -> dict:
    """
    Run only the models needed for the requested features.

    KEY DESIGN:
      - Person model uses .predict() — STATELESS per call, NO shared ByteTrack.
        This is critical for multi-camera accuracy: .track(persist=True) stores
        ByteTrack state inside the model object, which is shared across cameras,
        causing cross-camera track contamination and detection drops.
        The per-camera PersonTracker (person_tracker.py) handles all tracking
        via IoU re-association — it does NOT need YOLO's ByteTrack IDs.
      - Fire model uses .track() with its own ByteTrack state (single-cam OK).
      - fire_lock and person_lock are SEPARATE so a camera waiting on the fire
        model does NOT block another camera's person detector.
      - result["person_tracked"] is shared by ALL person features on a camera.

    Args:
        registry:    shared ModelRegistry instance
        frame:       numpy BGR frame from OpenCV (should be 640×360 for speed)
        features:    list of enabled feature names
        fire_lock:   threading.Lock protecting fire_model (shared across cameras)
        person_lock: threading.Lock protecting person_model (shared across cameras)

    Returns:
        dict with keys:
          "fire_smoke"      → YOLO result (track)
          "person_tracked"  → YOLO result (predict, NO .boxes.id — PersonTracker assigns IDs)
    """
    results = {}

    # ── Fire model (tracked) — lock only fire inference ──────────────
    if "fire_smoke" in features:
        model = registry.get_fire_model()
        if model is not None:
            conf       = fire_conf if fire_conf is not None else float(os.getenv("FIRE_CONFIDENCE", 0.22))
            iou        = 0.35          # lower IoU = better recall on small overlapping detections
            fire_input = fire_frame if fire_frame is not None else frame
            try:
                if fire_lock is not None:
                    with fire_lock:
                        res = model.track(
                            source=fire_input,
                            conf=conf,
                            iou=iou,
                            persist=True,
                            tracker="bytetrack.yaml",
                            verbose=False,
                            device=registry.device,
                            imgsz=fire_imgsz,
                        )
                else:
                    res = model.track(
                        source=fire_input,
                        conf=conf,
                        iou=iou,
                        persist=True,
                        tracker="bytetrack.yaml",
                        verbose=False,
                        device=registry.device,
                        imgsz=fire_imgsz,
                    )
                results["fire_smoke"] = res[0]
            except Exception as e:
                logger.error(f"[Inference] Fire model error: {e}")

    # ── Person model (.predict — stateless) ──────────────────────────
    # CRITICAL: We use .predict() NOT .track() to avoid shared ByteTrack state
    # contaminating across cameras. The per-camera PersonTracker handles
    # all tracking via IoU matching — YOLO track IDs are not needed.
    needs_person = any(f in PERSON_FEATURES for f in features)
    if needs_person:
        model = registry.get_person_model()
        if model is not None:
            conf = float(os.getenv("PERSON_CONFIDENCE", 0.45))  # Phase 1 fix: raised from 0.25
            iou  = float(os.getenv("PERSON_IOU", "0.50"))       # Phase 1 fix: raised from 0.45
            # Build class filter dynamically:
            # Always detect person (class 0). Also detect COCO animals (14-23)
            # when animal_detection is enabled — single inference pass, zero extra VRAM.
            detect_classes = [0]
            if "animal_detection" in features:
                detect_classes += ANIMAL_CLASS_IDS
            if "vehicle_detection" in features:
                detect_classes += VEHICLE_CLASS_IDS
            if "abandoned_object" in features:
                detect_classes += LUGGAGE_CLASS_IDS
            # Ensure unique sorted classes
            detect_classes = sorted(list(set(detect_classes)))
            try:
                if person_lock is not None:
                    with person_lock:
                        res = model.predict(
                            source=frame,
                            conf=conf,
                            iou=iou,
                            verbose=False,
                            device=registry.device,
                            classes=detect_classes,
                            imgsz=640,
                            agnostic_nms=True,
                        )
                else:
                    res = model.predict(
                        source=frame,
                        conf=conf,
                        iou=iou,
                        verbose=False,
                        device=registry.device,
                        classes=detect_classes,
                        imgsz=640,
                        agnostic_nms=True,
                    )
                results["person_tracked"] = res[0]
            except Exception as e:
                logger.error(f"[Inference] Person detection error: {e}")

    # ── Plate model (.predict — stateless) ───────────────────────────
    if "anpr" in features:
        model = registry.get_plate_model()
        if model is not None:
            conf = float(os.getenv("PLATE_CONFIDENCE", 0.40))
            try:
                if person_lock is not None:
                    with person_lock:
                        res = model.predict(
                            source=frame,
                            conf=conf,
                            iou=0.45,
                            verbose=False,
                            device=registry.device,
                            imgsz=640,
                        )
                else:
                    res = model.predict(
                        source=frame,
                        conf=conf,
                        iou=0.45,
                        verbose=False,
                        device=registry.device,
                        imgsz=640,
                    )
                results["plate_tracked"] = res[0]
            except Exception as e:
                logger.error(f"[Inference] Plate model error: {e}")

    return results
