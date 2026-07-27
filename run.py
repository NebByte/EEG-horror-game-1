#!/usr/bin/env python3
"""One-command launcher (cross-platform): start the engine and open the game.

    python run.py

Starts the FastAPI engine, waits for it to answer /v1/health, then opens the
browser/WebGL client (the engine that replaced the DirectX runtime). Works on
Windows, macOS and Linux — no compilation, no headset, no cloud required.
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
BASE = f"http://{HOST}:{PORT}"


def _up() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/v1/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    print("Starting the EEG Horror Engine…")
    engine = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "engine.main:app", "--host", HOST, "--port", str(PORT)]
    )
    try:
        for _ in range(60):
            if _up():
                break
            time.sleep(0.5)
        else:
            print("Engine did not come up. Install deps: pip install -r requirements-dev.txt")
            engine.terminate()
            return 1

        print(f"Engine up. Opening THE BACKROOMS at {BASE}/")
        print("  · WASD move · mouse look · Shift sprint · F flashlight · Esc pause")
        print("  · Find 3 Almond Waters, then reach the Exit — something stalks the halls")
        print("  · 'Connect Mind Link' reads a real NeuroSky headset via the engine")
        print("  · Classic raycaster client: " + BASE + "/classic.html")
        print("  · API docs: " + BASE + "/docs")
        webbrowser.open(f"{BASE}/")
        print("\nPress Ctrl+C here to stop the engine.")
        engine.wait()
    except KeyboardInterrupt:
        print("\nStopping the engine.")
    finally:
        engine.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
