@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt
python tools\launcher.py check
pause
