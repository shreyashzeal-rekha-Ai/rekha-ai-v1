from ultralytics import YOLO
from vidgear.gears import CamGear
import cv2
import torch

print("CUDA Available:", torch.cuda.is_available())

model = YOLO("yolo11n.pt")

# Move model to GPU
model.to("cuda")

stream = CamGear(
    source="rtsp://admin:admin2026@192.168.1.21:554/cam/realmonitor?channel=1&subtype=1"
).start()

frame_count = 0
last_annotated = None

while True:

    frame = stream.read()

    if frame is None:
        break

    frame = cv2.resize(frame, (640, 360))

    frame_count += 1

    if frame_count % 3 == 0:

        results = model(
            frame,
            classes=[0],
            verbose=False,
            device="cuda"
        )

        last_annotated = results[0].plot()

    if last_annotated is not None:
        cv2.imshow("PERSON DETECTION", last_annotated)

    if cv2.waitKey(1) == 27:
        break

stream.stop()
cv2.destroyAllWindows()