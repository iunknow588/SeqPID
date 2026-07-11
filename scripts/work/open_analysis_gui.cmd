@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%open_analysis_gui.ps1" %*
exit /b %ERRORLEVEL%
