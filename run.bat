@echo off
rem One-click launcher (Windows) — starts the engine and opens the WebGL game.
rem The browser client replaces the old DirectX runtime; nothing to compile.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
