@echo off
setlocal

set "ALFRED_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ALFRED_ROOT%scripts\start-windows.ps1"

if errorlevel 1 (
  echo.
  echo Alfred could not start. Review the message above.
  pause
  exit /b 1
)

endlocal
