# One-command launcher: starts the engine, waits for it, runs the game, cleans up.
# Usage:  double-click run.bat, or:  powershell -ExecutionPolicy Bypass -File run.ps1 [COM]
param([int]$Com = 7)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # fall back to system python

# First run: auto-acquire the AI's asset plan (models + characters + audio).
if (-not (Test-Path (Join-Path $root "assets\manifest.json"))) {
    Write-Host "First run — auto-downloading assets (models, characters, audio)..."
    & $py (Join-Path $root "tools\fetch_assets.py") "abandoned asylum" "darkness,isolation"
}

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
    Write-Host "Engine did not start. Check that the .venv exists and deps are installed."
    if ($engine) { Stop-Process -Id $engine.Id -Force }
    exit 1
}
Write-Host "Engine up. Launching the game (COM$Com)... WASD move, mouse look, TAB free cursor, Esc quit."

# Run the renderer (blocks until the window is closed).
& (Join-Path $root "runtime\build\runtime.exe") $Com

# Clean up the engine when the game exits.
Write-Host "Game closed. Stopping the engine."
if ($engine) { Stop-Process -Id $engine.Id -Force }
