from huggingface_hub import hf_hub_download
from ultralytics import YOLO

model_path = hf_hub_download(
    repo_id="SalahALHaismawi/yolov26-fire-detection",
    filename="best.pt"
)

model = YOLO(model_path)