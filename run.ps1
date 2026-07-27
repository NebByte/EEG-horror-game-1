# One-command launcher (Windows): start the engine, open the WebGL game, clean up.
# Usage:  double-click run.bat, or:  powershell -ExecutionPolicy Bypass -File run.ps1
#
# This replaces the old DirectX 12 native runtime. The game now runs in the
# browser (pure canvas + WebAudio) so there is nothing to compile.

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # fall back to system python

Write-Host "Starting the engine (brain)..."
$engine = Start-Process $py -ArgumentList "-m","uvicorn","engine.main:app","--port","8000" `
    -WorkingDirectory $root -PassThru -WindowStyle Minimized

# Wait until the engine answers /v1/health.
$up = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest "http://127.0.0.1:8000/v1/health" -TimeoutSec 1 -UseBasicParsing | Out-Null
        $up = $true; break
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $up) {
    Write-Host "Engine did not start. Install deps:  pip install -r requirements-dev.txt"
    if ($engine) { Stop-Process -Id $engine.Id -Force }
    exit 1
}

Write-Host "Engine up. Opening the game in your browser..."
Write-Host "  WASD/arrows move, mouse look, Esc release cursor. API docs: http://localhost:8000/docs"
Start-Process "http://localhost:8000/"

Write-Host "Game running. Press Enter here to stop the engine."
[void][System.Console]::ReadLine()
if ($engine) { Stop-Process -Id $engine.Id -Force }
