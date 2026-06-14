"""
test_webcam.py
--------------
Quick standalone test — opens your laptop webcam and runs BOTH models
live, showing annotated output in a window.

Run from the ai_engine folder:
    python test_webcam.py

Controls:
    Q   — quit
    F   — toggle fire model ON/OFF
    P   — toggle person model ON/OFF
    S   — save a snapshot manually
    M   — toggle motion filter ON/OFF
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import cv2
import time
import numpy as np
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ── Models ───────────────────────────────────────────────────────────
print("\n" + "="*55)
print("  Expert CCTV — Live Webcam Test")
print("="*55)
print("Loading models onto GPU (takes ~2s)...")

from inference_engine import ModelRegistry
from motion_filter    import MotionFilter
from feature_logic.fire_smoke import FireSmokeDetector
from feature_logic.intrusion  import IntrusionDetector

registry      = ModelRegistry.get()
motion_filter = MotionFilter("webcam_test")

print(f"  ✅ Device   : {registry.device}")
print(f"  ✅ fire model  loaded")
print(f"  ✅ person model loaded")
print("\nControls:  Q=quit  F=toggle fire  P=toggle person  M=toggle motion  S=snapshot")
print("-"*55 + "\n")

# ── Camera open ───────────────────────────────────────────────────────
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)   # CAP_DSHOW avoids MSMF errors on Windows
if not cap.isOpened():
    print("❌ ERROR: Cannot open webcam (source=0).")
    print("   Make sure no other app is using the camera (Teams, browser, etc.)")
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

print(f"✅ Webcam opened: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
      f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
      f"@ {int(cap.get(cv2.CAP_PROP_FPS))}fps\n")

# ── State flags ───────────────────────────────────────────────────────
run_fire    = True
run_person  = True
use_motion  = True
snapshot_n  = 0

# ── FPS tracking ──────────────────────────────────────────────────────
fps_counter = 0
fps_display = 0
fps_timer   = time.time()

# ── Colours ───────────────────────────────────────────────────────────
RED    = (0,  40, 220)
ORANGE = (0, 140, 255)
GREEN  = (0, 200,  60)
BLUE   = (220, 80,  20)
WHITE  = (255, 255, 255)
BLACK  = (0,   0,   0)

SNAP_DIR = os.path.join(os.path.dirname(__file__), '..', 'clips')
os.makedirs(SNAP_DIR, exist_ok=True)


def draw_overlay(frame, active_features, motion_flag, fps, detections_log):
    """Draw the HUD on the frame."""
    h, w = frame.shape[:2]

    # ── top bar ──────────────────────────────────────────────────────
    cv2.rectangle(frame, (0, 0), (w, 40), BLACK, -1)
    cv2.putText(frame, "Expert CCTV  |  Live Test",
                (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.75, WHITE, 2)
    cv2.putText(frame, f"FPS: {fps}",
                (w - 110, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, GREEN, 2)

    # ── bottom bar ───────────────────────────────────────────────────
    bar_y = h - 35
    cv2.rectangle(frame, (0, bar_y), (w, h), BLACK, -1)

    # Mode badges
    fire_col   = GREEN if active_features["fire"]   else (80, 80, 80)
    person_col = GREEN if active_features["person"] else (80, 80, 80)
    motion_col = GREEN if motion_flag               else (80, 80, 80)

    cv2.putText(frame, "[F] Fire",   (10,  h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, fire_col,   2)
    cv2.putText(frame, "[P] Person", (110, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, person_col, 2)
    cv2.putText(frame, "[M] Motion Gate", (240, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, motion_col, 2)
    cv2.putText(frame, "[S] Snapshot  [Q] Quit", (w-270, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)

    # ── detection log overlay ────────────────────────────────────────
    for i, line in enumerate(detections_log[-6:]):
        y = 60 + i * 24
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, ORANGE, 2)

    return frame


def draw_boxes(frame, detections):
    """Draw bboxes for each detection."""
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        feature = d["feature"]
        cls     = d["class"]
        conf    = d["confidence"]
        in_zone = d.get("in_zone", False)

        if feature == "fire_smoke":
            color = RED if cls == "fire" else ORANGE
            label = f"{'FIRE' if cls=='fire' else 'SMOKE'}  {conf:.0%}"
        else:
            color = RED if in_zone else BLUE
            label = f"PERSON {'⚠ ZONE' if in_zone else ''}  {conf:.0%}"

        # box
        thickness = 3 if (feature == "fire_smoke" or in_zone) else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # label background
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2)

    return frame


# ════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ════════════════════════════════════════════════════════════════════
detections_log = []
frame_count    = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️  Frame read failed — retrying...")
        time.sleep(0.1)
        continue

    frame_count += 1

    # ── Motion gate ──────────────────────────────────────────────────
    has_motion = True
    if use_motion:
        has_motion = motion_filter.has_motion(frame)

    # ── Inference (every frame while testing) ────────────────────────
    all_detections = []
    if has_motion:
        # Build feature list based on toggles
        features = []
        if run_fire:   features.append("fire_smoke")
        if run_person: features.append("intrusion")

        if features:
            from inference_engine import run_inference
            results = run_inference(registry, frame, features)

            if "fire_smoke" in results:
                dets = FireSmokeDetector.process(results["fire_smoke"], "webcam")
                all_detections.extend(dets)

            if "intrusion" in results:
                # Use the zone from cameras.json
                zones = [{"id": "z1", "name": "Restricted Zone",
                          "polygon": [[100, 100], [500, 100], [500, 400], [100, 400]],
                          "alert_on_intrusion": True}]
                dets = IntrusionDetector.process(results["intrusion"], "webcam", zones)
                all_detections.extend(dets)

    # ── Draw boxes ───────────────────────────────────────────────────
    frame = draw_boxes(frame, all_detections)

    # ── Log detections in console + overlay ─────────────────────────
    if all_detections:
        for d in all_detections:
            if d["feature"] == "fire_smoke":
                line = f"🔥 {d['class'].upper()} conf={d['confidence']:.0%}"
                print(f"  DETECTION: {line}")
            else:
                zone_str = f" → IN ZONE: {d['zone_name']}" if d.get("in_zone") else ""
                line     = f"👤 PERSON conf={d['confidence']:.0%}{zone_str}"
                if d.get("in_zone"):
                    print(f"  ALERT:     {line}")
                else:
                    print(f"  DETECTION: {line}")
            detections_log.append(line)

    # ── FPS counter ──────────────────────────────────────────────────
    fps_counter += 1
    if time.time() - fps_timer >= 1.0:
        fps_display = fps_counter
        fps_counter = 0
        fps_timer   = time.time()

    # ── Motion indicator ─────────────────────────────────────────────
    if use_motion and not has_motion:
        cv2.putText(frame, "MOTION GATE: idle (GPU skipped)",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 120, 120), 1)

    # ── Draw HUD ─────────────────────────────────────────────────────
    frame = draw_overlay(
        frame,
        active_features={"fire": run_fire, "person": run_person},
        motion_flag=use_motion,
        fps=fps_display,
        detections_log=detections_log
    )

    cv2.imshow("Expert CCTV — Live Test (Q to quit)", frame)

    # ── Key handler ──────────────────────────────────────────────────
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    elif key == ord('f'):
        run_fire = not run_fire
        print(f"  Fire model:   {'ON' if run_fire else 'OFF'}")
    elif key == ord('p'):
        run_person = not run_person
        print(f"  Person model: {'ON' if run_person else 'OFF'}")
    elif key == ord('m'):
        use_motion = not use_motion
        print(f"  Motion gate:  {'ON' if use_motion else 'OFF'}")
    elif key == ord('s'):
        snapshot_n += 1
        fn = os.path.join(SNAP_DIR, f"manual_snapshot_{snapshot_n:03d}.jpg")
        cv2.imwrite(fn, frame)
        print(f"  📸 Snapshot saved: {fn}")
        detections_log.append(f"📸 Snapshot saved → {os.path.basename(fn)}")

cap.release()
cv2.destroyAllWindows()
print("\n✅ Test ended cleanly.\n")
