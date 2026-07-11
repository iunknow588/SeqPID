@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_level2_analysis.ps1" %*
exit /b %ERRORLEVEL%
