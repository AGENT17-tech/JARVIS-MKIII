"""
JARVIS-MKIII — agents/monitor_agent.py
Continuous background system monitor.
Checks every 60 seconds for anomalies and pushes alerts to the HUD.
Starts automatically with the JARVIS backend.
"""
from __future__ import annotations
import asyncio, time, psutil
from typing import TYPE_CHECKING

# Thresholds
_CPU_THRESH    = 90.0   # %
_CPU_WINDOW    = 30     # seconds sustained above threshold
_RAM_THRESH    = 85.0   # %
_DISK_THRESH   = 90.0   # %
_PROC_CPU_HIGH = 20.0   # % — unknown process alert
_CHECK_INTERVAL = 60    # seconds

# Known/trusted process names (won't trigger unknown-process alert)
_TRUSTED = {
    "systemd", "Xorg", "gnome-shell", "kwin_x11", "kwin_wayland",
    "pulseaudio", "pipewire", "dbus-daemon", "NetworkManager",
    "python3", "python", "uvicorn", "node", "npm", "electron",
    "chrome", "firefox", "code", "vscode", "spotify",
    "kernel", "kthreadd", "ksoftirqd", "kworker", "rcu_sched",
    "journald", "udevd", "containerd", "dockerd",
}


class MonitorAgent:
    """Singleton background monitor — one long-running asyncio task."""

    def __init__(self):
        self._running       = False
        self._task: asyncio.Task | None = None
        self._cpu_high_since: float | None = None
        self._known_procs: set[int] = set()
        self._alerted: set[str]    = set()   # debounce repeated alerts

    def start(self):
        """Start the monitor loop (called once at backend startup)."""
        if self._running:
            return
        self._running = True
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._loop(), name="monitor_agent")
        print("[MONITOR] Background monitor started.")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    # ── Main loop ─────────────────────────────────────────────────────────────
    async def _loop(self):
        # Seed known PIDs on startup — any new process above threshold is "unknown"
        self._known_procs = {p.pid for p in psutil.process_iter(["pid"])}
        await asyncio.sleep(5)   # let system settle

        while self._running:
            try:
                await self._check_all()
            except Exception as e:
                print(f"[MONITOR] Check error: {e}")
            await asyncio.sleep(_CHECK_INTERVAL)

    async def _check_all(self):
        now = time.time()

        # ── CPU sustained high ─────────────────────────────────────────────
        cpu = psutil.cpu_percent(interval=2)
        if cpu > _CPU_THRESH:
            if self._cpu_high_since is None:
                self._cpu_high_since = now
            elif now - self._cpu_high_since >= _CPU_WINDOW:
                msg = f"CPU usage at {cpu:.0f}% for over 30 seconds."
                await self._alert(msg, "cpu_high", critical=True)
        else:
            self._cpu_high_since = None
            self._alerted.discard("cpu_high")

        # ── RAM ───────────────────────────────────────────────────────────
        ram = psutil.virtual_memory().percent
        if ram > _RAM_THRESH:
            await self._alert(f"Memory usage at {ram:.0f}%.", "ram_high", critical=True)
        else:
            self._alerted.discard("ram_high")

        # ── Disk ──────────────────────────────────────────────────────────
        _SKIP_FSTYPES  = {"squashfs", "tmpfs", "devtmpfs"}
        _SKIP_PREFIXES = ("/snap/", "/boot/efi")

        for part in psutil.disk_partitions(all=False):
            mp = part.mountpoint
            # Skip virtual/snap/EFI mount points — they are never real storage
            if any(mp.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if part.fstype in _SKIP_FSTYPES:
                continue
            try:
                usage = psutil.disk_usage(mp)
                pct   = usage.percent
                key   = f"disk_{mp}"
                if pct > _DISK_THRESH:
                    await self._alert(
                        f"Disk {mp} at {pct:.0f}% capacity.",
                        key, critical=False,
                    )
                else:
                    self._alerted.discard(key)
            except Exception:
                continue

        # ── Unknown high-CPU process ──────────────────────────────────────
        current_pids = set()
        for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                pid  = p.pid
                name = (p.info.get("name") or "").lower()
                cpu_p = p.info.get("cpu_percent") or 0
                current_pids.add(pid)
                is_new     = pid not in self._known_procs
                is_trusted = any(t in name for t in _TRUSTED)
                if is_new and not is_trusted and cpu_p > _PROC_CPU_HIGH:
                    await self._alert(
                        f"Unknown process '{p.info['name']}' (PID {pid}) consuming {cpu_p:.0f}% CPU.",
                        f"proc_{pid}", critical=True,
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self._known_procs = current_pids

        # ── JARVIS services ───────────────────────────────────────────────
        await self._check_services()

    async def _check_services(self):
        """Alert if backend port 8000 stops responding."""
        import socket
        key = "backend_down"
        try:
            with socket.create_connection(("127.0.0.1", 8000), timeout=2):
                self._alerted.discard(key)
        except Exception:
            await self._alert(
                "JARVIS backend service appears to be down on port 8000.",
                key, critical=True,
            )

    # ── Alert dispatch ────────────────────────────────────────────────────────
    async def _alert(self, message: str, key: str, critical: bool = False):
        if key in self._alerted:
            return   # already alerted, debounce
        self._alerted.add(key)
        severity = "critical" if critical else "warning"
        print(f"[MONITOR] ALERT [{severity.upper()}]: {message}")

        event = {
            "type":      "monitor_alert",
            "name":      "MONITOR",
            "agent_id":  "MON",
            "status":    "alert",
            "task":      "System monitoring",
            "result":    message,
            "summary":   message,
            "timestamp": int(time.time()),
            "severity":  severity,
        }
        try:
            from agents.agent_dispatcher import dispatcher
            await dispatcher.broadcast_event(event)
        except Exception:
            pass

        # Route through proactive engine (handles HUD push + 10s TTS delay)
        try:
            from core.proactive_engine import engine as proactive_engine
            await proactive_engine.handle_monitor_alert(message, key, critical)
        except Exception:
            # Fallback: speak immediately if engine unavailable
            if critical:
                try:
                    from api.voice_bridge import request_speak
                    await request_speak(f"Sir, {message}")
                except Exception:
                    pass


# ── Singleton ─────────────────────────────────────────────────────────────────
monitor = MonitorAgent()
