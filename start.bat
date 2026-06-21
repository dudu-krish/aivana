@echo off
cd /d "%~dp0"
echo Stopping anything on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
echo Starting Agent Studio on http://127.0.0.1:8000
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
