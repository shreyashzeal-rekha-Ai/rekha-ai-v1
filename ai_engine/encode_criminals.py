"""
encode_criminals.py
--------------------
Run this ONCE (or whenever you add new criminal photos) to build
the criminal_encodings.pkl watchlist file.

Usage:
    cd C:\\Users\\aditya\\Desktop\\IEEE-Hackthon\\Expert_CCTV\\ai_engine
    python encode_criminals.py

Folder structure:
    ai_engine/models/criminal_faces/
        PersonName1/
            photo1.jpg
            photo2.jpg
        PersonName2/
            photo1.jpg
"""

import os
import pickle
import face_recognition

FACES_DIR      = os.path.join(os.path.dirname(__file__), "models", "criminal_faces")
ENCODINGS_FILE = os.path.join(os.path.dirname(__file__), "models", "criminal_encodings.pkl")

known_encodings = []
known_names     = []

print(f"[INFO] Scanning faces from: {FACES_DIR}")

if not os.path.exists(FACES_DIR):
    os.makedirs(FACES_DIR)
    print(f"[INFO] Created {FACES_DIR} — add sub-folders with criminal photos and re-run.")
else:
    for person_name in os.listdir(FACES_DIR):
        person_dir = os.path.join(FACES_DIR, person_name)
        if not os.path.isdir(person_dir):
            continue
        print(f"[INFO] Encoding: {person_name}")
        for img_file in os.listdir(person_dir):
            img_path = os.path.join(person_dir, img_file)
            try:
                image     = face_recognition.load_image_file(img_path)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    known_encodings.append(encodings[0])
                    known_names.append(person_name)
                    print(f"  ✅ {img_file}")
                else:
                    print(f"  ⚠️  No face in {img_file} — skipping")
            except Exception as e:
                print(f"  ❌ Error on {img_file}: {e}")

print(f"\n[INFO] Total encodings: {len(known_encodings)}")
data = {"encodings": known_encodings, "names": known_names}
with open(ENCODINGS_FILE, "wb") as f:
    pickle.dump(data, f)
print(f"[SUCCESS] Saved to {ENCODINGS_FILE}")
