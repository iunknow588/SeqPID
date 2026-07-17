@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_webui.ps1" %*
exit /b %errorlevel%
