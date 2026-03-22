"""
JARVIS-MKIII — system/app_controller.py
Launch, close, and list registered applications.
"""
from __future__ import annotations
import json, subprocess
from pathlib import Path

import psutil

REGISTRY_PATH = Path(__file__).parent / "app_registry.json"


def _load_registry() -> dict:
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def _resolve(name: str) -> dict | None:
    """Return the registry entry for a friendly app name, or None."""
    return _load_registry()["apps"].get(name.lower().strip())


# ── Public API ────────────────────────────────────────────────────────────────

def launch_app(name: str) -> str:
    entry = _resolve(name)
    if not entry:
        return f"I don't have '{name}' in my application registry, sir."
    exe = entry["executable"]
    try:
        subprocess.Popen(
            [exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"Launching {name}, sir."
    except FileNotFoundError:
        return f"Executable '{exe}' is not installed on this system, sir."
    except Exception as e:
        return f"Failed to launch {name}, sir: {e}"


def close_app(name: str) -> str:
    entry = _resolve(name)
    if not entry:
        return f"I don't have '{name}' in my application registry, sir."
    proc_name = entry["process"]
    killed = 0
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            pname = proc.info["name"] or ""
            pexe  = proc.info["exe"]  or ""
            if pname.startswith(proc_name) or proc_name in pexe:
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        return f"Closed {name}, sir."
    return f"{name.capitalize()} doesn't appear to be running, sir."


def list_open_apps() -> list[str]:
    """Return friendly names of all registered apps currently running."""
    registry = _load_registry()["apps"]
    running  = set()
    for proc in psutil.process_iter(["name"]):
        try:
            running.add(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    seen_exes: set[str] = set()
    open_apps: list[str] = []
    for friendly, entry in registry.items():
        exe  = entry["executable"]
        proc = entry["process"]
        if exe in seen_exes:
            continue  # already reported this executable under another alias
        if any(r.startswith(proc) or proc.startswith(r) for r in running):
            seen_exes.add(exe)
            open_apps.append(friendly)
    return open_apps
