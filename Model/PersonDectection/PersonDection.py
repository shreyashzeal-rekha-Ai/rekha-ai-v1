from ultralytics import YOLO
import torch

# 1. Load YOLO11 COCO model (auto-downloads yolo11n.pt on first run)
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
model = YOLO("yolo11n.pt")   # COCO-trained YOLO11 nano
model.fuse()
if torch.cuda.is_available():
    model.model = model.model.half()
model.to(device)

# 2. Perform inference
image = 'https://variety.com/wp-content/uploads/2023/04/MCDNOHA_SP001.jpg'
results = model.predict(image, conf=0.4, iou=0.7, half=torch.cuda.is_available())

# 3. Show results
for result in results:
    boxes = result.boxes
    print("Found objects:", [result.names[int(c)] for c in boxes.cls])
