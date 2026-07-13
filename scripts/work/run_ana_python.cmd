@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_ana.ps1" -Engine python %*
exit /b %ERRORLEVEL%
