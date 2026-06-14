# Expert CCTV — AI Engine
# Docker Image: NVIDIA CUDA base for GPU acceleration
FROM nvcr.io/nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip python3.11-dev \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Models are mounted as a Docker volume — NOT baked into the image
VOLUME ["/app/models"]

CMD ["python3", "main.py"]
