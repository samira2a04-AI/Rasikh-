@echo off
echo Starting Rasikh Backend on port 8000...
cd /d "%~dp0"
call .\.venv\Scripts\activate.bat
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
