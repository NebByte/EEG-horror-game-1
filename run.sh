#!/usr/bin/env bash
# One-command launcher for macOS / Linux: start the engine and open the game.
#   ./run.sh
# No DirectX, no build, no headset — the browser/WebGL client runs anywhere.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 run.py
