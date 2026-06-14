@echo off
title Expert CCTV Auto Start

echo Waiting for system startup...
timeout /t 20 /nobreak > nul

echo Starting AI Engine...
start "AI Engine" cmd /k "cd /d C:\Users\sonyc\OneDrive\Desktop\Rekha-ai1_CCTV\Rekha-ai1_CCTV\ai_engine && python main.py"

timeout /t 5 /nobreak > nul

echo Starting Backend...
start "Backend" cmd /k "cd /d C:\Users\sonyc\OneDrive\Desktop\Rekha-ai1_CCTV\Rekha-ai1_CCTV\backend && python app.py"

timeout /t 5 /nobreak > nul

echo Starting Frontend...
start "Frontend" cmd /k "cd /d C:\Users\sonyc\OneDrive\Desktop\Rekha-ai1_CCTV\Rekha-ai1_CCTV\frontend && npm run dev"

timeout /t 10 /nobreak > nul

start http://localhost:5173

echo Expert CCTV Started