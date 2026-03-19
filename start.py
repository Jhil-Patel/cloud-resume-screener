#!/usr/bin/env python3
"""
start.py — One-click startup for Cloud Resume Screener
Runs FastAPI backend and opens frontend in browser automatically.

Usage:
  python start.py
  python start.py --port 8080
  python start.py --no-browser
"""

import os, sys, time, argparse, subprocess, webbrowser, threading
from pathlib import Path

def check_dependencies():
    missing = []
    for pkg in ["fastapi", "uvicorn", "spacy", "sklearn", "pdfplumber", "sqlalchemy"]:
        try:
            __import__(pkg if pkg != "sklearn" else "sklearn")
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[!] Missing packages: {', '.join(missing)}")
        print(f"    Run: pip install -r requirements.txt")
        sys.exit(1)
    print("[✓] All dependencies found")

def start_backend(port):
    os.chdir(Path(__file__).parent / "backend")
    cmd = [sys.executable, "-m", "uvicorn", "main:app",
           "--host", "0.0.0.0", "--port", str(port), "--reload"]
    print(f"[✓] Starting FastAPI backend on http://localhost:{port}")
    print(f"[✓] API docs at http://localhost:{port}/docs")
    return subprocess.Popen(cmd)

def open_browser(port, no_browser):
    if no_browser:
        return
    frontend = (Path(__file__).parent / "frontend" / "index.html").resolve()
    time.sleep(2)
    print(f"[✓] Opening frontend: {frontend.as_uri()}")
    webbrowser.open(frontend.as_uri())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print()
    print("  ☁️  Cloud Resume Screener v2.0")
    print("  ──────────────────────────────")
    check_dependencies()

    threading.Thread(target=open_browser, args=(args.port, args.no_browser), daemon=True).start()
    proc = start_backend(args.port)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[✓] Shutting down...")
        proc.terminate()
