"""
motion_filter.py
----------------
MOG2 background subtraction on CPU.
Gates inference — if no motion detected in frame,
skip YOLO entirely to save GPU cycles.

Returns True if motion is detected, False if static frame.
Each camera gets its own MotionFilter instance.

API expected by main.py:
    mf = MotionFilter(cam_id)
    has_motion = mf.has_motion(frame)
"""

import cv2
import numpy as np
import logging

logger = logging.getLogger("motion_filter")


class MotionFilter:
    """
    Uses MOG2 (Mixture of Gaussians v2) background subtraction.
    Runs entirely on CPU. Designed to be called once per frame
    before inference to decide whether to run YOLO or skip.
    """

    def __init__(
        self,
        cam_id: str = "cam",
        sensitivity: str = "medium",
        min_area: int = 1500,
        blur_ksize: int = 21,
        history: int = 500,
        var_threshold: float = 40.0,
        detect_shadows: bool = False,
    ):
        """
        Args:
            cam_id:          Camera identifier (used for logging only)
            sensitivity:     'low' | 'medium' | 'high' — preset that adjusts min_area
            min_area:        Minimum contour area in pixels to count as motion
            blur_ksize:      Gaussian blur kernel size (must be odd)
            history:         Number of frames MOG2 uses to build background model
            var_threshold:   MOG2 pixel variance threshold to mark as foreground
            detect_shadows:  If True MOG2 marks shadows gray (slower, more accurate)
        """
        self.cam_id = cam_id

        # Sensitivity presets override min_area
        _presets = {"low": 5000, "medium": 1500, "high": 400}
        self.min_area = _presets.get(sensitivity, min_area)

        # Ensure blur kernel is odd
        self.blur_ksize = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1

        # Build MOG2 subtractor
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows,
        )

        # Morphology kernel to close small holes in foreground mask
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        logger.debug(
            f"[{cam_id}] MotionFilter ready | sensitivity={sensitivity} "
            f"min_area={self.min_area}"
        )

    def has_motion(self, frame: np.ndarray) -> bool:
        """
        Main API. Returns True if meaningful motion detected in frame.

        Steps:
          1. Grayscale + Gaussian blur (suppress noise)
          2. MOG2 foreground mask
          3. Morphological close (fill gaps)
          4. Contour check — True if any contour > min_area

        Args:
            frame: BGR numpy frame from OpenCV

        Returns:
            True  → run YOLO inference this frame
            False → skip YOLO (static scene)
        """
        if frame is None:
            return False

        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)
        fg_mask = self._subtractor.apply(blurred)

        _, thresh = cv2.threshold(fg_mask, 127, 255, cv2.THRESH_BINARY)
        closed    = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._morph_kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            if cv2.contourArea(c) >= self.min_area:
                return True

        return False

    def get_debug_mask(self, frame: np.ndarray) -> np.ndarray:
        """Returns processed foreground mask for visual debugging/tuning."""
        if frame is None:
            return np.zeros((480, 640), dtype=np.uint8)
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)
        fg_mask = self._subtractor.apply(blurred)
        _, thresh = cv2.threshold(fg_mask, 127, 255, cv2.THRESH_BINARY)
        closed    = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._morph_kernel, iterations=2)
        return closed

    def reset(self):
        """Resets the background model. Call on stream reconnect."""
        self._subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        logger.info(f"[{self.cam_id}] MotionFilter background model reset.")


# ── Standalone test ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import time

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    source = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cap    = cv2.VideoCapture(source)

    if not cap.isOpened():
        logger.error(f"Cannot open camera: {source}")
        sys.exit(1)

    mf = MotionFilter(cam_id="cam_01", sensitivity="medium")
    logger.info("Motion filter test. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        has_motion = mf.has_motion(frame)
        mask       = mf.get_debug_mask(frame)

        label = "MOTION" if has_motion else "static"
        color = (0, 0, 255) if has_motion else (0, 200, 0)
        cv2.putText(frame, label, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)

        cv2.imshow("Feed", frame)
        cv2.imshow("Mask", mask)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
