"""
JARVIS-MKIII — watchdog.py
Self-healing service monitor.

State machine per service:
  UNKNOWN   → first check pending
  HEALTHY   → all checks passing
  DEGRADED  → 1 consecutive failure  (log warning, no restart)
  FAILED    → 2+ consecutive failures (attempt restart)
  RECOVERING→ restart attempted, waiting for confirmation
  CRITICAL  → 3 restart attempts failed this hour (notify HUD, stop retrying)

Limits:
  - Max 3 restarts per service per hour
  - 60 s cooldown between restarts
  - Check interval: 30 s
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

# ── Config ─────────────────────────────────────────────────────────────────────

CHECK_INTERVAL   = 30        # seconds between full sweep
RESTART_COOLDOWN = 60        # seconds between restart attempts
MAX_RESTARTS_PER_HOUR = 3    # per service per hour
FAILURES_DIR     = Path(__file__).parent / "failures"
ALERT_URL        = "http://localhost:8000/internal/alert"
HTTP_TIMEOUT     = 3         # seconds for HTTP checks

# States
UNKNOWN    = "UNKNOWN"
HEALTHY    = "HEALTHY"
DEGRADED   = "DEGRADED"
FAILED     = "FAILED"
RECOVERING = "RECOVERING"
CRITICAL   = "CRITICAL"

# ── Service definitions ────────────────────────────────────────────────────────
# type "http"    → check_http(url)
# type "process" → check_process(match)
# type "user_svc"→ systemctl --user is-active {unit}
# systemd_user   → restart via systemctl --user restart {unit}
# systemd_system → restart via systemctl restart {unit}  (needs sudo / polkit)
#                  falls back to no-op with CRITICAL notification

SERVICES: list[dict] = [
    {
        "name":        "jarvis-backend",
        "type":        "http",
        "url":         "http://localhost:8000/health",
        "unit":        "jarvis-backend.service",
        "systemd":     "user",
    },
    {
        "name":        "jarvis-voice",
        "type":        "process",
        "match":       "voice_orchestrator",
        "unit":        "jarvis-voice.service",
        "systemd":     "user",
    },
    {
        "name":        "jarvis-whatsapp",
        "type":        "http",
        "url":         "http://localhost:3001/status",
        "unit":        "jarvis-whatsapp.service",
        "systemd":     "user",
    },
    {
        "name":        "jarvis-proactive",
        "type":        "http",
        "url":         "http://localhost:8000/proactive/status",
        "unit":        "jarvis-backend.service",   # lives inside backend
        "systemd":     "user",
    },
    {
        "name":        "ollama",
        "type":        "http",
        "url":         "http://localhost:11434",
        "unit":        "ollama.service",
        "systemd":     "system",
    },
]

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[WATCHDOG] %(asctime)s %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watchdog")

# ── Per-service state ──────────────────────────────────────────────────────────

class ServiceState:
    def __init__(self, cfg: dict) -> None:
        self.cfg              = cfg
        self.name             = cfg["name"]
        self.state            = UNKNOWN
        self.consecutive_fail = 0
        self.last_restart: datetime | None = None
        self.restart_times: deque[datetime] = deque()   # timestamps this hour
        self.total_restarts   = 0

    @property
    def restarts_this_hour(self) -> int:
        cutoff = datetime.now() - timedelta(hours=1)
        while self.restart_times and self.restart_times[0] < cutoff:
            self.restart_times.popleft()
        return len(self.restart_times)

    def record_restart(self) -> None:
        self.restart_times.append(datetime.now())
        self.last_restart = datetime.now()
        self.total_restarts += 1


# ── Checks ─────────────────────────────────────────────────────────────────────

async def check_http(url: str, session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as resp:
            return resp.status < 500
    except Exception:
        return False


def check_process(match: str) -> bool:
    """Scan /proc/*/cmdline for the match string."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", match],
            capture_output=True, text=True, timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


# ── Restart ────────────────────────────────────────────────────────────────────

def restart_service(svc: ServiceState) -> bool:
    cfg  = svc.cfg
    unit = cfg.get("unit", svc.name + ".service")
    mode = cfg.get("systemd", "user")

    if mode == "user":
        cmd = ["systemctl", "--user", "restart", unit]
    else:
        # system service — try without sudo first (polkit may allow it)
        cmd = ["systemctl", "restart", unit]

    log.info("Restarting %s via: %s", svc.name, " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            log.info("Restart of %s succeeded.", svc.name)
            return True
        log.warning("Restart of %s failed (rc=%d): %s", svc.name, result.returncode, result.stderr.strip())
        return False
    except Exception as e:
        log.error("Restart of %s raised: %s", svc.name, e)
        return False


# ── Failure logging ────────────────────────────────────────────────────────────

def log_failure(svc_name: str, reason: str, unit: str = "") -> None:
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = FAILURES_DIR / f"{svc_name}_{ts}.log"

    journal_lines = ""
    if unit:
        try:
            result = subprocess.run(
                ["journalctl", "--user", "-u", unit, "-n", "50", "--no-pager"],
                capture_output=True, text=True, timeout=10,
            )
            journal_lines = result.stdout or result.stderr
        except Exception as e:
            journal_lines = f"(could not retrieve journal: {e})"

    content = (
        f"JARVIS Watchdog Failure Report\n"
        f"================================\n"
        f"Timestamp : {datetime.now().isoformat()}\n"
        f"Service   : {svc_name}\n"
        f"Reason    : {reason}\n"
        f"\n--- Last 50 journal lines ({unit}) ---\n"
        f"{journal_lines}\n"
    )
    log_file.write_text(content)
    log.info("Failure log written: %s", log_file)


# ── HUD alert ──────────────────────────────────────────────────────────────────

async def notify_hud(
    message:  str,
    severity: str,
    session:  aiohttp.ClientSession,
    source:   str = "watchdog",
) -> None:
    payload = {"message": message, "severity": severity, "source": source}
    try:
        async with session.post(
            ALERT_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status not in (200, 201):
                log.warning("HUD alert returned %d", resp.status)
    except Exception as e:
        log.debug("HUD notify failed (backend may be down): %s", e)


# ── State machine tick ─────────────────────────────────────────────────────────

async def tick(svc: ServiceState, session: aiohttp.ClientSession) -> None:
    cfg  = svc.cfg
    name = svc.name

    # 1. Run health check
    if cfg["type"] == "http":
        healthy = await check_http(cfg["url"], session)
    elif cfg["type"] == "process":
        healthy = check_process(cfg["match"])
    else:
        healthy = False

    # 2. Advance state machine
    if healthy:
        if svc.state not in (HEALTHY, UNKNOWN):
            log.info("%-20s recovered → HEALTHY", name)
            if svc.state == RECOVERING:
                await notify_hud(f"{name} recovered successfully.", "info", session)
        svc.consecutive_fail = 0
        svc.state = HEALTHY
        return

    # --- unhealthy path ---
    svc.consecutive_fail += 1

    if svc.state == CRITICAL:
        # Already gave up — just keep logging
        log.warning("%-20s still down (CRITICAL, not retrying)", name)
        return

    if svc.consecutive_fail == 1:
        svc.state = DEGRADED
        log.warning("%-20s check failed (DEGRADED, monitoring)", name)
        return

    # 2+ consecutive failures
    if svc.state in (UNKNOWN, HEALTHY, DEGRADED):
        svc.state = FAILED
        reason = f"{svc.consecutive_fail} consecutive failed checks"
        log.error("%-20s → FAILED (%s)", name, reason)
        log_failure(name, reason, cfg.get("unit", ""))
        await notify_hud(f"{name} FAILED: {reason}", "error", session)

    # Rate limiting
    if svc.restarts_this_hour >= MAX_RESTARTS_PER_HOUR:
        svc.state = CRITICAL
        msg = f"{name} entered CRITICAL state — {MAX_RESTARTS_PER_HOUR} restart attempts exhausted this hour."
        log.critical("%-20s %s", name, msg)
        log_failure(name, msg + " No further restarts.", cfg.get("unit", ""))
        await notify_hud(msg, "critical", session)
        return

    # Cooldown check
    if svc.last_restart and (datetime.now() - svc.last_restart).total_seconds() < RESTART_COOLDOWN:
        remaining = int(RESTART_COOLDOWN - (datetime.now() - svc.last_restart).total_seconds())
        log.info("%-20s cooldown: %ds remaining before next restart", name, remaining)
        return

    # Attempt restart
    svc.state = RECOVERING
    svc.record_restart()
    log.info("%-20s attempting restart (attempt %d/hour)…", name, svc.restarts_this_hour)
    await notify_hud(f"{name} restarting (attempt {svc.restarts_this_hour}/{MAX_RESTARTS_PER_HOUR})…", "warning", session)

    ok = restart_service(svc)
    if not ok:
        log.error("%-20s restart command failed.", name)
        log_failure(name, "restart command failed", cfg.get("unit", ""))
        await notify_hud(f"{name} restart command failed.", "error", session)


# ── Main loop ──────────────────────────────────────────────────────────────────

async def main() -> None:
    states = [ServiceState(s) for s in SERVICES]
    log.info("Watchdog started — monitoring %d services, interval=%ds", len(states), CHECK_INTERVAL)
    for s in states:
        log.info("  • %-22s [%s]", s.name, s.cfg["type"])

    async with aiohttp.ClientSession() as session:
        while True:
            log.info("── sweep ──")
            for svc in states:
                try:
                    await tick(svc, session)
                except Exception as e:
                    log.error("Unhandled error in tick for %s: %s", svc.name, e)
            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
