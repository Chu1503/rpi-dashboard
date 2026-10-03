@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-uno-ssh-key.ps1"
set "ALFRED_KEY_EXIT=%ERRORLEVEL%"

echo.
if "%ALFRED_KEY_EXIT%"=="0" (
  echo Alfred deployment key is ready. Future deployments will not ask for the SSH password.
) else (
  echo Key setup failed. Review the error above.
)
pause
exit /b %ALFRED_KEY_EXIT%
