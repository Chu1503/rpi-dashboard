@echo off
setlocal
cd /d "%~dp0"

echo Keep the TV powered on and leave it on the UNO's HDMI input.
echo This performs one full UNO reboot so Linux can detect HDMI audio.
echo Normal deploy-to-uno.bat updates do not reboot the UNO.
echo.

set "ALFRED_KEY=%USERPROFILE%\.ssh\alfred_uno_ed25519"
set "ALFRED_TARGET=arduino@alfred.local"
powershell.exe -NoLogo -NoProfile -Command "if (-not (Test-NetConnection alfred.local -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue)) { exit 1 }" >nul 2>&1
if errorlevel 1 set "ALFRED_TARGET=arduino@192.168.1.41"
set "ALFRED_REBOOT=DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus xfce4-session-logout --reboot --fast"
if exist "%ALFRED_KEY%" (
  ssh -i "%ALFRED_KEY%" -o IdentitiesOnly=yes %ALFRED_TARGET% "%ALFRED_REBOOT%"
) else (
  ssh %ALFRED_TARGET% "%ALFRED_REBOOT%"
)

if errorlevel 1 (
  echo.
  echo The reboot command did not complete. Check the address and password above.
  pause
  exit /b 1
)

echo.
echo Reboot requested. Alfred should return in about 30 seconds with HDMI audio.
timeout /t 12 /nobreak >nul
exit /b 0
