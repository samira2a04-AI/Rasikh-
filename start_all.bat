@echo off
echo Starting Rasikh Legal Platform (Backend & Frontend)...
start "Rasikh Backend (FastAPI)" cmd /c "%~dp0start_backend.bat"
start "Rasikh Frontend (Vite)" cmd /c "%~dp0start_frontend.bat"
