@echo off
title i-Trap Analysis System Launcher
color 0A
echo ========================================================
echo   i-Trap Analysis: Super-Fused Vehicle Intelligence
echo   Standalone Local Desktop Application
echo ========================================================
echo.
cd /d "%~dp0"

echo [1/2] Checking Python & Installing Dependencies if needed...
python -m pip install -r requirements.txt --quiet

echo.
echo [2/2] Launching i-Trap Analysis System in Browser...
python -m streamlit run app.py --server.port 8502

pause
