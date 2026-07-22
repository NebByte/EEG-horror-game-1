@echo off
rem One-click launcher — starts the engine, runs the game, cleans up.
rem Optional: pass the MindLink COM port, e.g.  run.bat 5   (default 7)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
