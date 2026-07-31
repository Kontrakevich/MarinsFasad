@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
start "" http://127.0.0.1:8070
python -m uvicorn app.main:app --host 127.0.0.1 --port 8070
pause
