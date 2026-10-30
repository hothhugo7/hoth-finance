@echo off
cd /d "%~dp0"
title Hoth Solutions
".venv\Scripts\python.exe" -m hoth.web.servidor
pause
