import cv2
from ultralytics import YOLO

# ✅ correct path
model = YOLO("best.pt")

cap = cv2.VideoCapture(0)

print("🔥 Fire Detection Started... Press 'q' to exit")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame)
    annotated = results[0].plot()

    cv2.imshow("Fire Detection", annotated)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()