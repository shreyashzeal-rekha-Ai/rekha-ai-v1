import os
import sys
import time
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Define your maximum safe temperature here
MAX_TEMP_C = 70

def get_gpu_temp():
    try:
        # Query nvidia-smi for the GPU temperature
        res = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL
        )
        return int(res.decode('utf-8').strip())
    except Exception:
        return None

def shutdown_system():
    logging.critical("CRITICAL: Temperature threshold exceeded! Shutting down system NOW...")
    # /s = shutdown, /f = force close apps, /t 0 = immediately
    os.system("shutdown /s /f /t 0")
    sys.exit(0)

if __name__ == "__main__":
    logging.info(f"Thermal Watchdog Started. Monitoring GPU temperature. Limit: {MAX_TEMP_C}C")
    
    # 70C is extremely cold for a GPU running YOLOv8 at 90FPS. It usually sits around 80C-85C.
    logging.warning(f"Note: 70C is very low for an AI GPU workload. You might experience premature shutdowns.")
    logging.info("Press CTRL+C to stop the watchdog.")
    
    while True:
        gpu_temp = get_gpu_temp()
        
        if gpu_temp is not None:
            logging.info(f"Current GPU Temp: {gpu_temp}C")
            
            if gpu_temp >= MAX_TEMP_C:
                logging.critical(f"DANGER: GPU Temperature is {gpu_temp}C (Limit: {MAX_TEMP_C}C)")
                shutdown_system()
        else:
            logging.error("Could not read GPU temperature. Is an NVIDIA GPU available?")
            
        # Check every 5 seconds
        time.sleep(5)
