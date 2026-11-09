@echo off
cd /d "%~dp0"
title Hoth Finance
".venv\Scripts\python.exe" -m hoth.web.servidor
pause
