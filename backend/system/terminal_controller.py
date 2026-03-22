"""
JARVIS-MKIII — system/terminal_controller.py
Runs shell commands and manages system packages on behalf of Jarvis.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUDO SETUP (one-time, required for privileged package commands):
  sudo visudo -f /etc/sudoers.d/jarvis
  Add these lines exactly:
      kiko ALL=(ALL) NOPASSWD: /usr/bin/apt
      kiko ALL=(ALL) NOPASSWD: /usr/bin/snap
  Then: sudo chmod 0440 /etc/sudoers.d/jarvis

  flatpak is invoked with --user so it needs no sudo.
  Ensure flatpak + the flathub remote are set up:
      sudo apt install flatpak
      flatpak remote-add --user --if-not-exists flathub \
          https://dl.flathub.org/repo/flathub.flatpakrepo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations
import asyncio, re, shutil

# Package names must be sane before touching any package manager
_PKG_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9.+_-]*$')

# Lines to retain from long command output
_MAX_LINES = 20


# ── Output helpers ─────────────────────────────────────────────────────────────

def _trim(text: str, max_lines: int = _MAX_LINES) -> str:
    """Cap long output; strip blank lines throughout."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    if len(lines) <= max_lines:
        return "\n".join(lines)
    omitted = len(lines) - max_lines
    head    = lines[:3]
    tail    = lines[-(max_lines - 3):]
    return "\n".join(head) + f"\n... [{omitted} lines omitted] ...\n" + "\n".join(tail)


def _last_line(text: str) -> str:
    """Return the last non-empty line of a text block."""
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _combined(result: dict) -> str:
    return (result.get("stdout", "") + " " + result.get("stderr", "")).lower()


# ── Core runner ───────────────────────────────────────────────────────────────

async def _run(cmd: list[str] | str, *, shell: bool = False) -> dict:
    if shell:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    raw_out, raw_err = await proc.communicate()
    return {
        "stdout":     _trim(raw_out.decode(errors="replace")),
        "stderr":     _trim(raw_err.decode(errors="replace")),
        "returncode": proc.returncode,
    }


# ── "Package not found" detectors ─────────────────────────────────────────────
# Only cascade to the next source when the *current* source genuinely has no
# record of the package — not when it fails for network / permission reasons.

def _apt_not_found(result: dict) -> bool:
    c = _combined(result)
    return (
        "unable to locate package" in c
        or "has no installation candidate" in c
        or "no packages found" in c
    )


def _snap_not_found(result: dict) -> bool:
    c = _combined(result)
    return (
        "snap not found" in c
        or "no snap found" in c
        # snap find returns rc=0 but says "No matching snaps for …"
        or "no matching snaps" in c
        # snap install with an unknown name
        or ('error' in c and 'not found' in c)
    )


def _flatpak_not_found(result: dict) -> bool:
    c = _combined(result)
    return (
        "no remote refs found" in c
        or "no matches found" in c
        or "app not found" in c
        or "not found" in c
    )


# ── Smart installer ───────────────────────────────────────────────────────────

async def smart_install(name: str) -> dict:
    """
    Try apt → snap → flatpak in order.
    Cascade to the next source only when the current one has no record of
    the package (not on network errors or dependency failures).
    Returns a result dict with an extra 'source' key (which manager succeeded)
    and optionally 'not_found': True if all three failed.
    """
    if not _PKG_RE.match(name):
        return {
            "stdout": "", "stderr": f"Invalid package name: {name!r}",
            "returncode": 1, "source": None,
        }

    # ── 1. apt ────────────────────────────────────────────────────────────────
    r = await _run(["sudo", "/usr/bin/apt", "install", "-y", name])
    if r["returncode"] == 0:
        return {**r, "source": "apt"}
    if not _apt_not_found(r):
        return {**r, "source": None}   # apt failed for a real reason — stop

    # ── 2. snap ───────────────────────────────────────────────────────────────
    if shutil.which("snap"):
        r = await _run(["sudo", "/usr/bin/snap", "install", name])
        if r["returncode"] == 0:
            return {**r, "source": "snap"}
        if not _snap_not_found(r):
            return {**r, "source": None}

    # ── 3. flatpak ────────────────────────────────────────────────────────────
    if shutil.which("flatpak"):
        r = await _run(
            ["flatpak", "install", "--user", "-y", "flathub", name]
        )
        if r["returncode"] == 0:
            return {**r, "source": "flatpak"}
        if not _flatpak_not_found(r):
            return {**r, "source": None}

    # ── All three exhausted ───────────────────────────────────────────────────
    return {
        "stdout": "", "stderr": f"{name} not found in apt, snap, or flatpak.",
        "returncode": 1, "source": None, "not_found": True,
    }


# ── Package search ────────────────────────────────────────────────────────────

def _parse_apt_search(text: str) -> list[dict]:
    """Parse 'apt-cache search' output → list of {name, description}."""
    results = []
    for line in text.splitlines():
        line = line.strip()
        if " - " in line:
            pkg, _, desc = line.partition(" - ")
            results.append({"name": pkg.strip(), "description": desc.strip()})
    return results


def _parse_snap_search(text: str) -> list[dict]:
    """
    Parse 'snap find' tabular output → list of {name, description}.
    First line is the header; subsequent lines are data rows.
    """
    results = []
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return results
    # Header columns: Name  Version  Publisher  Notes  Summary
    # Determine column offsets from the header line.
    header = lines[0]
    name_col    = header.lower().find("name")
    summary_col = header.lower().find("summary")
    for line in lines[1:]:
        if len(line) <= name_col:
            continue
        name_end = line.find(" ", name_col + 1)
        name_end = name_end if name_end > 0 else summary_col
        pkg_name = line[name_col:name_end].strip()
        summary  = line[summary_col:].strip() if summary_col > 0 and len(line) > summary_col else ""
        if pkg_name:
            results.append({"name": pkg_name, "description": summary})
    return results


async def search_package(name: str) -> dict:
    """
    Search apt-cache and snap for <name>; return top 3 hits from each.
    Result dict: {"apt": [...], "snap": [...]}
    Each entry: {"name": str, "description": str}
    """
    async def _empty():
        return {"stdout": "", "stderr": "", "returncode": 0}

    apt_r, snap_r = await asyncio.gather(
        _run(["apt-cache", "search", name]),
        _run(["snap", "find", name]) if shutil.which("snap") else _empty(),
    )
    return {
        "apt":  _parse_apt_search(apt_r["stdout"])[:3],
        "snap": _parse_snap_search(snap_r["stdout"])[:3],
    }


# ── Simple installers (kept for remove / direct use) ─────────────────────────

async def install_package(name: str) -> dict:
    """Direct apt install — use smart_install() for the cascade."""
    if not _PKG_RE.match(name):
        return {"stdout": "", "stderr": f"Invalid package name: {name!r}", "returncode": 1}
    return await _run(["sudo", "/usr/bin/apt", "install", "-y", name])


async def remove_package(name: str) -> dict:
    """Remove a package via apt (tries snap autoremove as fallback)."""
    if not _PKG_RE.match(name):
        return {"stdout": "", "stderr": f"Invalid package name: {name!r}", "returncode": 1}
    r = await _run(["sudo", "/usr/bin/apt", "remove", "-y", name])
    if r["returncode"] == 0:
        return r
    # If apt says it doesn't know the package, try snap
    if _apt_not_found(r) and shutil.which("snap"):
        return await _run(["sudo", "/usr/bin/snap", "remove", name])
    return r


async def update_system() -> dict:
    """Run apt update && apt upgrade -y."""
    return await _run(
        "sudo /usr/bin/apt update && sudo /usr/bin/apt upgrade -y",
        shell=True,
    )


async def execute(command: str) -> dict:
    """Run an arbitrary shell command. Returns stdout/stderr/returncode."""
    return await _run(command, shell=True)


# ── Result formatter (TTS-safe one-liner) ─────────────────────────────────────

def format_result(action: str, payload: str | None, result: dict) -> str:
    """
    Convert a result dict into a single TTS-friendly sentence.
    Personality rules: 'Done, sir.' on success / 'That did not go as planned, sir.' on failure.
    """
    rc       = result["returncode"]
    out      = result.get("stdout", "")
    err      = result.get("stderr", "")
    source   = result.get("source")
    not_found = result.get("not_found", False)

    # ── All-source-exhausted case ──────────────────────────────────────────────
    if not_found and action == "install":
        return (
            f"I was unable to locate {payload} through standard channels, sir. "
            "You may need to provide a direct download link."
        )

    if rc == 0:
        if action == "install":
            via = f" via {source}" if source else ""
            return f"Done, sir. {payload} has been installed{via} successfully."
        if action == "remove":
            return f"Done, sir. {payload} has been removed."
        if action == "update":
            return "Done, sir. All system packages are up to date."
        summary = _last_line(out) or "Command completed with no output."
        return f"Done, sir. {summary}"

    # ── Failure ────────────────────────────────────────────────────────────────
    error_line = _last_line(err or out) or "Unknown error."
    if action == "install":
        return f"That did not go as planned, sir. Failed to install {payload}: {error_line}"
    if action == "remove":
        return f"That did not go as planned, sir. Failed to remove {payload}: {error_line}"
    if action == "update":
        return f"That did not go as planned, sir. System update failed: {error_line}"
    return f"That did not go as planned, sir. {error_line}"
