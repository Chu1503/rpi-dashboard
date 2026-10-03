@echo off
setlocal
cd /d "%~dp0"

rem Normal deployments restart only Alfred. They intentionally do not reboot
rem Linux because the UNO Q can lose its HDMI audio card during a cold probe.
rem If Windows cannot resolve alfred.local, the PowerShell deployer automatically
rem falls back to the UNO's known LAN address, 192.168.1.41.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy-to-uno.ps1"
set "ALFRED_DEPLOY_EXIT=%ERRORLEVEL%"

if not "%ALFRED_DEPLOY_EXIT%"=="0" (
  echo.
  echo Deployment failed. Review the error above.
  pause
)

exit /b %ALFRED_DEPLOY_EXIT%
