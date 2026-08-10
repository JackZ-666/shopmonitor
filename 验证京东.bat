@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo [ERROR] Python not found & pause & exit /b 1)
python tools\verify_jd_union.py
pause
