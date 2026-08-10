@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo [ERROR] Python not found in PATH & pause & exit /b 1)
python tools\launcher.py start
pause
