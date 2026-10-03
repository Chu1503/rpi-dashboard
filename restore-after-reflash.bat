@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restore-after-reflash.ps1" %*
if errorlevel 1 (
  echo.
  echo Restore failed. Read the error above before closing this window.
  pause
) else (
  echo.
  echo Alfred restore completed successfully.
  pause
)
