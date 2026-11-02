@echo off
rem Zaklada zadanie Harmonogramu Windows dla Typer AI (dwuklik).
rem Usuniecie zadania: setup_scheduler.bat -Remove
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_scheduler.ps1" %*
pause
