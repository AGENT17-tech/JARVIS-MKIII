"""
JARVIS-MKIII — system/os_controller.py
OS control layer: file system, process management, network, system config.
All public functions return {"success": bool, "result": str, "error": str}.
"""
from __future__ import annotations
import os, platform, re, shutil, socket, subprocess, pathlib, time
import psutil

# ── Filesystem sandbox ────────────────────────────────────────────────────────
class PathSandbox:
    """Validates file paths against the allowed list from FSConfig."""

    def __init__(self):
        try:
            from config.settings import FS_CFG
            self._allowed = FS_CFG.get_allowed_paths()
        except Exception:
            self._allowed = [pathlib.Path.home()]

    def validate(self, path: str) -> pathlib.Path:
        """Resolve `path` and confirm it is inside an allowed root.

        Raises ValueError if the path is outside all allowed roots.
        """
        p = pathlib.Path(os.path.expanduser(path)).resolve()
        for root in self._allowed:
            try:
                p.relative_to(root)
                return p
            except ValueError:
                continue
        raise ValueError(
            f"Path '{p}' is outside allowed sandbox roots: {self._allowed}"
        )


_path_sandbox = PathSandbox()


# ── Result helper ──────────────────────────────────────────────────────────────
def _R(ok: bool, result: str = "", error: str = "") -> dict:
    return {"success": ok, "result": result, "error": error}

def _expand(path: str) -> str:
    return os.path.expanduser(path)

def _pulse_env() -> dict:
    """Return an env dict with PulseAudio/PipeWire runtime paths set.
    pactl fails with 'Connection refused' when run from a subprocess that
    lacks XDG_RUNTIME_DIR (e.g. the FastAPI worker thread).
    On Windows, os.getuid() does not exist — returns plain env copy.
    """
    env = os.environ.copy()
    if platform.system() != "Windows":
        uid = os.getuid()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("PULSE_RUNTIME_PATH", f"/run/user/{uid}/pulse")
    return env

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ═══════════════════════════════════════════════════════════════════════════════
# FILE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

def create_file(path: str, content: str = "") -> dict:
    try:
        p = pathlib.Path(_expand(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return _R(True, f"Created {p}")
    except Exception as e:
        return _R(False, error=str(e))


def create_directory(path: str) -> dict:
    try:
        p = pathlib.Path(_expand(path))
        p.mkdir(parents=True, exist_ok=True)
        return _R(True, f"Directory created: {p}")
    except Exception as e:
        return _R(False, error=str(e))


def delete(path: str) -> dict:
    try:
        p = pathlib.Path(_expand(path))
        if not p.exists():
            return _R(False, error=f"Path does not exist: {path}")
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return _R(True, f"Deleted {p}")
    except Exception as e:
        return _R(False, error=str(e))


def move(src: str, dest: str) -> dict:
    try:
        shutil.move(_expand(src), _expand(dest))
        return _R(True, f"Moved {src} → {dest}")
    except Exception as e:
        return _R(False, error=str(e))


def copy(src: str, dest: str) -> dict:
    try:
        s = pathlib.Path(_expand(src))
        d = pathlib.Path(_expand(dest))
        if s.is_dir():
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
        return _R(True, f"Copied {src} → {dest}")
    except Exception as e:
        return _R(False, error=str(e))


def read_file(path: str) -> dict:
    try:
        p = pathlib.Path(_expand(path))
        content = p.read_text(errors="replace")
        truncated = content[:2000]
        suffix = f"\n[...truncated — {len(content)} chars total]" if len(content) > 2000 else ""
        return _R(True, truncated + suffix)
    except Exception as e:
        return _R(False, error=str(e))


def list_directory(path: str) -> dict:
    try:
        p = pathlib.Path(_expand(path))
        if not p.exists():
            return _R(False, error=f"Path does not exist: {path}")
        if not p.is_dir():
            return _R(False, error=f"Not a directory: {path}")
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = [f"{p}/"]
        for e in entries[:60]:
            prefix = "  📁 " if e.is_dir() else "  📄 "
            size = ""
            if e.is_file():
                try:
                    size = f"  ({_fmt_size(e.stat().st_size)})"
                except Exception:
                    pass
            lines.append(f"{prefix}{e.name}{size}")
        total = sum(1 for _ in p.iterdir())
        if total > 60:
            lines.append(f"  ... and {total - 60} more")
        return _R(True, "\n".join(lines))
    except Exception as e:
        return _R(False, error=str(e))


def search_files(query: str, root: str = "~") -> dict:
    try:
        root_p = pathlib.Path(_expand(root))
        q = query.lower()
        matches = []
        for p in root_p.rglob("*"):
            try:
                if q in p.name.lower():
                    matches.append(str(p))
                    if len(matches) >= 40:
                        break
            except PermissionError:
                continue
        if not matches:
            return _R(True, f"No files found matching '{query}', sir.")
        return _R(True, f"Found {len(matches)} file(s):\n" + "\n".join(matches))
    except Exception as e:
        return _R(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESS MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def list_processes() -> dict:
    try:
        # First pass to trigger cpu_percent measurement
        for _ in psutil.process_iter(["pid", "name", "cpu_percent"]):
            pass
        time.sleep(0.3)
        procs = sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]),
            key=lambda p: p.info.get("cpu_percent") or 0,
            reverse=True,
        )[:15]
        header = f"{'PID':>7}  {'CPU%':>6}  {'MEM%':>6}  {'STATUS':<10}  NAME"
        sep = "─" * 54
        rows = []
        for p in procs:
            i = p.info
            rows.append(
                f"{i['pid']:>7}  {(i['cpu_percent'] or 0):>5.1f}%  "
                f"{(i['memory_percent'] or 0):>5.1f}%  {(i['status'] or '?'):<10}  {i['name']}"
            )
        return _R(True, "\n".join([header, sep] + rows))
    except Exception as e:
        return _R(False, error=str(e))


def kill_process(name_or_pid: str) -> dict:
    try:
        killed = []
        try:
            pid = int(name_or_pid)
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            killed.append(f"PID {pid} ({name})")
        except ValueError:
            for p in psutil.process_iter(["pid", "name"]):
                if name_or_pid.lower() in (p.info.get("name") or "").lower():
                    p.terminate()
                    killed.append(f"PID {p.pid} ({p.name()})")
        if not killed:
            return _R(False, error=f"No process matching '{name_or_pid}' found.")
        return _R(True, f"Terminated: {', '.join(killed)}")
    except Exception as e:
        return _R(False, error=str(e))


def get_process_info(name: str) -> dict:
    try:
        found = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            if name.lower() in (p.info.get("name") or "").lower():
                i = p.info
                found.append(
                    f"PID={i['pid']}  CPU={i['cpu_percent'] or 0:.1f}%  "
                    f"MEM={i['memory_percent'] or 0:.1f}%  STATUS={i['status']}"
                )
        if not found:
            return _R(False, error=f"No process matching '{name}'.")
        return _R(True, "\n".join(found))
    except Exception as e:
        return _R(False, error=str(e))


def set_priority(pid: int, nice_value: int) -> dict:
    try:
        p = psutil.Process(int(pid))
        p.nice(int(nice_value))
        return _R(True, f"PID {pid} priority set to nice={nice_value}")
    except Exception as e:
        return _R(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

def get_network_status() -> dict:
    try:
        lines = []
        addrs  = psutil.net_if_addrs()
        stats  = psutil.net_if_stats()
        for iface, addr_list in addrs.items():
            st     = stats.get(iface)
            status = "UP" if (st and st.isup) else "DOWN"
            for a in addr_list:
                if hasattr(a, "family") and a.family.name in ("AF_INET", "AF_INET6"):
                    lines.append(f"{iface:<12} [{status}]  {a.address}")
        return _R(True, "\n".join(lines) if lines else "No network interfaces found.")
    except Exception as e:
        return _R(False, error=str(e))


def scan_local_network() -> dict:
    try:
        hostname  = socket.gethostname()
        local_ip  = socket.gethostbyname(hostname)
        subnet    = ".".join(local_ip.split(".")[:3]) + ".0/24"
        result    = subprocess.run(
            ["nmap", "-sn", subnet],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode != 0:
            return _R(False, error=result.stderr or "nmap failed")
        devices = [
            line.replace("Nmap scan report for ", "")
            for line in result.stdout.splitlines()
            if "Nmap scan report" in line
        ]
        return _R(True, f"Subnet {subnet} — {len(devices)} device(s) found:\n" + "\n".join(devices))
    except FileNotFoundError:
        return _R(False, error="nmap not installed. Run: sudo apt install nmap")
    except Exception as e:
        return _R(False, error=str(e))


def get_active_connections() -> dict:
    try:
        conns = psutil.net_connections(kind="inet")
        lines = []
        for c in conns[:25]:
            laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "?"
            raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "—"
            try:
                proc = psutil.Process(c.pid).name() if c.pid else "?"
            except Exception:
                proc = str(c.pid or "?")
            lines.append(f"{c.status:<12}  {laddr:<22}  →  {raddr:<22}  [{proc}]")
        return _R(True, "\n".join(lines) if lines else "No active connections.")
    except Exception as e:
        return _R(False, error=str(e))


def monitor_bandwidth() -> dict:
    try:
        c1 = psutil.net_io_counters()
        time.sleep(1)
        c2 = psutil.net_io_counters()
        sent = (c2.bytes_sent - c1.bytes_sent) / 1024
        recv = (c2.bytes_recv - c1.bytes_recv) / 1024
        return _R(True, f"Upload: {sent:.1f} KB/s  |  Download: {recv:.1f} KB/s")
    except Exception as e:
        return _R(False, error=str(e))


def disconnect_interface(interface: str) -> dict:
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["netsh", "interface", "set", "interface", interface, "disabled"],
                capture_output=True, text=True,
            )
        else:
            result = subprocess.run(
                ["ip", "link", "set", interface, "down"],
                capture_output=True, text=True,
            )
        if result.returncode != 0:
            return _R(False, error=result.stderr or "Command failed")
        return _R(True, f"Interface {interface} disconnected.")
    except Exception as e:
        return _R(False, error=str(e))


def connect_interface(interface: str) -> dict:
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["netsh", "interface", "set", "interface", interface, "enabled"],
                capture_output=True, text=True,
            )
        else:
            result = subprocess.run(
                ["ip", "link", "set", interface, "up"],
                capture_output=True, text=True,
            )
        if result.returncode != 0:
            return _R(False, error=result.stderr or "Command failed")
        return _R(True, f"Interface {interface} connected.")
    except Exception as e:
        return _R(False, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

def set_volume(percent: int) -> dict:
    try:
        pct = max(0, min(100, int(percent)))
        if platform.system() == "Windows":
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from comtypes import CLSCTX_ALL
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                volume.SetMasterVolumeLevelScalar(pct / 100.0, None)
                return _R(True, f"Volume set to {pct}%.")
            except Exception as e:
                return _R(False, error=f"Windows volume control failed: {e}")
        result = subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"],
            capture_output=True, text=True,
            env=_pulse_env(),
        )
        if result.returncode != 0:
            return _R(False, error=result.stderr.strip() or "pactl failed")
        return _R(True, f"Volume set to {pct}%.")
    except Exception as e:
        return _R(False, error=str(e))


def get_volume() -> dict:
    try:
        if platform.system() == "Windows":
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from comtypes import CLSCTX_ALL
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                vol = round(volume.GetMasterVolumeLevelScalar() * 100)
                return _R(True, f"Current volume: {vol}%")
            except Exception as e:
                return _R(False, error=f"Windows volume read failed: {e}")
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True,
            env=_pulse_env(),
        )
        m = re.search(r"(\d+)%", result.stdout)
        vol = m.group(1) if m else "unknown"
        return _R(True, f"Current volume: {vol}%")
    except Exception as e:
        return _R(False, error=str(e))


def set_brightness(percent: int) -> dict:
    try:
        pct = max(1, min(100, int(percent)))
        if platform.system() == "Windows":
            try:
                import screen_brightness_control as sbc
                sbc.set_brightness(pct)
                return _R(True, f"Brightness set to {pct}%.")
            except Exception as e:
                return _R(False, error=f"Windows brightness control failed: {e}")
        result = subprocess.run(
            ["brightnessctl", "set", f"{pct}%"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return _R(False, error=result.stderr or "brightnessctl failed")
        return _R(True, f"Brightness set to {pct}%.")
    except FileNotFoundError:
        return _R(False, error="brightnessctl not installed. Run: sudo apt install brightnessctl")
    except Exception as e:
        return _R(False, error=str(e))


def get_brightness() -> dict:
    try:
        if platform.system() == "Windows":
            try:
                import screen_brightness_control as sbc
                pct = sbc.get_brightness(display=0)
                if isinstance(pct, list):
                    pct = pct[0]
                return _R(True, f"Current brightness: {pct}%")
            except Exception as e:
                return _R(False, error=f"Windows brightness read failed: {e}")
        cur = subprocess.run(["brightnessctl", "get"], capture_output=True, text=True)
        mx  = subprocess.run(["brightnessctl", "max"], capture_output=True, text=True)
        c, m = int(cur.stdout.strip()), int(mx.stdout.strip())
        pct  = round(c / m * 100) if m else 0
        return _R(True, f"Current brightness: {pct}%")
    except Exception as e:
        return _R(False, error=str(e))


def power_sleep() -> dict:
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        else:
            subprocess.Popen(["systemctl", "suspend"])
        return _R(True, "System suspending.")
    except Exception as e:
        return _R(False, error=str(e))


def power_reboot() -> dict:
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/r", "/t", "0"])
        else:
            subprocess.Popen(["systemctl", "reboot"])
        return _R(True, "Rebooting now, sir.")
    except Exception as e:
        return _R(False, error=str(e))


def power_shutdown() -> dict:
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/s", "/t", "0"])
        else:
            subprocess.Popen(["systemctl", "poweroff"])
        return _R(True, "Shutting down, sir.")
    except Exception as e:
        return _R(False, error=str(e))


def list_startup_apps() -> dict:
    try:
        if platform.system() == "Windows":
            return _R(False, error="Service management not supported on Windows. Use Task Scheduler or NSSM.")
        result = subprocess.run(
            ["systemctl", "list-unit-files", "--user", "--state=enabled"],
            capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.splitlines() if "enabled" in l][:25]
        return _R(True, "\n".join(lines) if lines else "No user startup services enabled.")
    except Exception as e:
        return _R(False, error=str(e))


def enable_startup(service: str) -> dict:
    try:
        if platform.system() == "Windows":
            return _R(False, error="Service management not supported on Windows. Use Task Scheduler or NSSM.")
        result = subprocess.run(
            ["systemctl", "--user", "enable", service],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return _R(False, error=result.stderr)
        return _R(True, f"Service '{service}' enabled at startup.")
    except Exception as e:
        return _R(False, error=str(e))


def disable_startup(service: str) -> dict:
    try:
        if platform.system() == "Windows":
            return _R(False, error="Service management not supported on Windows. Use Task Scheduler or NSSM.")
        result = subprocess.run(
            ["systemctl", "--user", "disable", service],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return _R(False, error=result.stderr)
        return _R(True, f"Service '{service}' disabled.")
    except Exception as e:
        return _R(False, error=str(e))
