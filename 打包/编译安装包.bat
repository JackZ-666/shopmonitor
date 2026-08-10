@echo off
setlocal
cd /d "%~dp0"
where iscc >nul 2>nul
if %errorlevel%==0 ( iscc "ShopMonitor???.iss" & goto :end )
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" ( "%ISCC%" "ShopMonitor???.iss" & goto :end )
set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" ( "%ISCC%" "ShopMonitor???.iss" & goto :end )
echo [??] ??? Inno Setup?ISCC.exe??
echo ?? https://jrsoftware.org/isinfo.php ???? Inno Setup 6 ??????????????
pause & exit /b 1
:end
pause
