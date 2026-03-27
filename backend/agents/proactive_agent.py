"""
JARVIS-MKIII — agents/proactive_agent.py
Autonomous proactive agent: monitors all data sources every 60 seconds
and interrupts with mission-critical intelligence without being asked.

Monitors:
  calendar      — warns 20 min before events
  github        — alerts on new commits/activity
  system_health — CPU / RAM / VRAM thresholds
  weather       — rain / storm codes for Cairo
  missions      — stale mission (no update in 24h)
  whatsapp      — unread message accumulation

Delivery is delegated to the existing ProactiveEngine.fire_alert()
so the standard 10-second user-interaction cancel logic applies.
"""

from __future__ import annotations
import asyncio, json, time
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "data" / "proactive_config.json"

DEFAULT_CONFIG: dict = {
    "check_interval":        60,
    "calendar_warn_minutes": 20,
    "cpu_threshold":         80,
    "ram_threshold":         85,
    "vram_threshold":        90,
    "mission_stale_hours":   24,
}

# Weather condition strings that warrant an alert (maps to WMO codes 61-99)
_RAIN_STORM_TERMS = {
    "rain", "shower", "thunderstorm", "drizzle", "sleet", "hail", "snow",
}


class ProactiveAgent:

    CHECK_INTERVAL       = 60   # seconds between full scans
    CALENDAR_WARN_MINUTES = 20
    CPU_WARN_THRESHOLD   = 80
    RAM_WARN_THRESHOLD   = 85
    VRAM_WARN_THRESHOLD  = 90
    MISSION_STALE_HOURS  = 24

    def __init__(self):
        self._alerts_today:      dict[str, datetime] = {}
        self._history:           list[dict]          = []
        self._silenced_until:    float               = 0.0
        self._running:           bool                = False
        self._task:              asyncio.Task | None = None
        self._last_scan:         datetime | None     = None
        self._alerts_fired_today: int                = 0
        self._github_last_shas:  dict[str, str]      = {}
        self._config:            dict                = self._load_config()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.run(), name="proactive_agent")
        print("[PROACTIVE] Autonomous agent started.")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    # ── Config ─────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            if CONFIG_PATH.exists():
                return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
        except Exception:
            pass
        return DEFAULT_CONFIG.copy()

    def save_config(self, updates: dict) -> None:
        self._config.update(updates)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self._config, indent=2))

    # ── Main loop ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        await asyncio.sleep(35)   # let backend fully settle
        while self._running:
            try:
                await self._scan_all()
                self._last_scan = datetime.now()
            except Exception as e:
                print(f"[PROACTIVE] Scan error: {e}")
            await asyncio.sleep(self._config.get("check_interval", self.CHECK_INTERVAL))

    async def _scan_all(self) -> None:
        """Run all 6 monitors concurrently."""
        await asyncio.gather(
            self._check_calendar(),
            self._check_github(),
            self._check_system_health(),
            self._check_weather(),
            self._check_missions(),
            self._check_whatsapp(),
            return_exceptions=True,
        )

    async def trigger_scan(self, source: str = "all") -> None:
        """Manually trigger a scan, clearing dedup for that source first."""
        if source == "all":
            self._alerts_today.clear()
            self._last_scan = datetime.now()
            await self._scan_all()
        else:
            # Clear only keys for this source
            self._alerts_today = {
                k: v for k, v in self._alerts_today.items()
                if not k.startswith(source)
            }
            mapping = {
                "calendar":     self._check_calendar,
                "github":       self._check_github,
                "system":       self._check_system_health,
                "system_health":self._check_system_health,
                "weather":      self._check_weather,
                "missions":     self._check_missions,
                "whatsapp":     self._check_whatsapp,
            }
            checker = mapping.get(source)
            if checker:
                await checker()
            self._last_scan = datetime.now()

    # ── Alert deduplication ────────────────────────────────────────────────────

    def _already_alerted_today(self, key: str) -> bool:
        if key not in self._alerts_today:
            return False
        return (datetime.now() - self._alerts_today[key]).total_seconds() < 3600

    def _mark_alerted_today(self, key: str) -> None:
        self._alerts_today[key] = datetime.now()

    # ── Alert delivery ─────────────────────────────────────────────────────────

    async def _interrupt(
        self,
        message:  str,
        priority: str,
        source:   str,
        alert_id: str | None = None,
    ) -> None:
        """Fire an interruption: record in history, push to HUD, speak via TTS."""
        if time.time() < self._silenced_until:
            print(f"[PROACTIVE] Silenced — suppressed: {message[:60]}")
            return

        try:
            from core.text_sanitizer import sanitize_for_tts
            clean = sanitize_for_tts(message)
        except Exception:
            clean = message

        aid = alert_id or f"{source}_{int(time.time())}"

        # Store in history (capped at 50)
        entry = {
            "id":        aid,
            "timestamp": datetime.now().isoformat(),
            "source":    source,
            "priority":  priority,
            "message":   clean,
        }
        self._history.append(entry)
        if len(self._history) > 50:
            self._history.pop(0)
        self._alerts_fired_today += 1

        print(f"[PROACTIVE] [{priority.upper()}] [{source}] {clean}")

        try:
            from integrations.touchdesigner_bridge import on_alert
            on_alert(priority, clean)
        except Exception:
            pass

        # Delegate to existing ProactiveEngine for delivery
        # (handles HUD push → 10s wait → user-cancel check → TTS)
        try:
            from core.proactive_engine import engine as _pe
            await _pe.fire_alert(_pe._make_alert(
                alert_id    = aid,
                alert_type  = source,
                priority    = priority,
                title       = f"{source.replace('_', ' ').upper()}",
                message     = clean,
                hud_message = clean[:90],
            ))
        except Exception as e:
            print(f"[PROACTIVE] Fire alert failed: {e}")

        # Record in Hindsight memory
        try:
            from memory.hindsight import memory
            memory.record("proactive", "assistant", clean,
                          tier=f"proactive_{source}")
        except Exception:
            pass

    # ── Monitor: Calendar ──────────────────────────────────────────────────────

    async def _check_calendar(self) -> None:
        try:
            from config.google_calendar import get_upcoming_events, is_configured
        except ImportError:
            return

        if not is_configured():
            return

        warn_min = self._config.get("calendar_warn_minutes", self.CALENDAR_WARN_MINUTES)
        window_lo = warn_min - 2
        window_hi = warn_min + 2

        try:
            events = await asyncio.to_thread(get_upcoming_events, minutes_ahead=window_hi + 1)
        except Exception as e:
            print(f"[PROACTIVE] Calendar fetch failed: {e}")
            return

        now = datetime.now()
        for event in events:
            start_dt = event.get("_start_dt")
            if start_dt is None:
                continue

            # Strip timezone for local comparison
            if getattr(start_dt, "tzinfo", None) is not None:
                try:
                    import zoneinfo
                    start_dt = start_dt.astimezone(
                        zoneinfo.ZoneInfo("Africa/Cairo")
                    ).replace(tzinfo=None)
                except Exception:
                    start_dt = start_dt.replace(tzinfo=None)

            minutes_until = (start_dt - now).total_seconds() / 60
            if not (window_lo <= minutes_until <= window_hi):
                continue

            event_id = event.get("id", event.get("title", "unknown"))
            key = f"calendar_{event_id}_{now.date().isoformat()}_20min"
            if self._already_alerted_today(key):
                continue

            mins = max(1, int(minutes_until))
            title = event.get("title", "Event")
            location = event.get("location", "")
            loc_text = f" at {location}" if location else ""
            msg = (
                f"Sir, heads up. {title}{loc_text} starts "
                f"in {mins} minute{'s' if mins != 1 else ''}."
            )
            await self._interrupt(msg, priority="high", source="calendar",
                                  alert_id=key)
            self._mark_alerted_today(key)

    # ── Monitor: GitHub ────────────────────────────────────────────────────────

    async def _check_github(self) -> None:
        try:
            from api.weather_calendar import get_github
            repos = await get_github()
        except Exception:
            return

        if not isinstance(repos, list):
            return

        for repo in repos:
            name    = repo.get("name", "")
            commits = repo.get("commits", [])
            if not commits:
                continue

            latest_sha = commits[0].get("sha", "")
            last_known = self._github_last_shas.get(name)

            if last_known is None:
                self._github_last_shas[name] = latest_sha
                continue

            if latest_sha == last_known:
                continue

            self._github_last_shas[name] = latest_sha
            key = f"github_{name}_{latest_sha}"
            if self._already_alerted_today(key):
                continue

            raw_msg   = commits[0].get("message", "")
            truncated = " ".join(raw_msg.split()[:8])
            if len(raw_msg.split()) > 8:
                truncated += "..."
            n = len(commits)
            msg = (
                f"New GitHub activity on {name}. "
                f"{n} commit{'s' if n != 1 else ''} pushed. "
                f"Latest: {truncated}."
            )
            await self._interrupt(msg, priority="low", source="github",
                                  alert_id=key)
            self._mark_alerted_today(key)

            # PHANTOM ZERO — auto-log each new commit to engineering domain
            try:
                import sys as _sys
                from pathlib import Path as _Path
                _phantom_root = _Path(__file__).parent.parent.parent / "phantom"
                if str(_phantom_root.parent) not in _sys.path:
                    _sys.path.insert(0, str(_phantom_root.parent))
                from phantom.phantom_os import get_phantom as _gp
                _gp().log_activity("engineering", "commit", 1,
                                   notes=f"auto: {name} — {truncated}")
            except Exception as _phe:
                print(f"[PHANTOM] GitHub auto-log failed: {_phe}")

    # ── Monitor: System Health ─────────────────────────────────────────────────

    async def _check_system_health(self) -> None:
        try:
            import psutil
            now      = datetime.now()
            date_str = now.date().isoformat()
            hour_str = str(now.hour)

            cpu_thresh = self._config.get("cpu_threshold", self.CPU_WARN_THRESHOLD)
            ram_thresh = self._config.get("ram_threshold", self.RAM_WARN_THRESHOLD)

            cpu = await asyncio.to_thread(psutil.cpu_percent, 1)
            if cpu > cpu_thresh:
                key = f"system_cpu_{date_str}_{hour_str}"
                if not self._already_alerted_today(key):
                    msg = f"Warning sir. CPU at {round(cpu)} percent. System is under heavy load."
                    await self._interrupt(msg, priority="high", source="system_health",
                                          alert_id=key)
                    self._mark_alerted_today(key)

            ram = psutil.virtual_memory().percent
            if ram > ram_thresh:
                key = f"system_ram_{date_str}_{hour_str}"
                if not self._already_alerted_today(key):
                    msg = f"Warning sir. RAM at {round(ram)} percent. Memory is running low."
                    await self._interrupt(msg, priority="high", source="system_health",
                                          alert_id=key)
                    self._mark_alerted_today(key)

            # VRAM via nvidia-smi
            vram_thresh = self._config.get("vram_threshold", self.VRAM_WARN_THRESHOLD)
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    used, total = int(parts[0].strip()), int(parts[1].strip())
                    vram_pct = round(used / total * 100)
                    if vram_pct > vram_thresh:
                        key = f"system_vram_{date_str}_{hour_str}"
                        if not self._already_alerted_today(key):
                            msg = (
                                f"Warning sir. GPU VRAM at {vram_pct} percent. "
                                f"{used} of {total} MiB in use."
                            )
                            await self._interrupt(
                                msg, priority="high", source="system_health",
                                alert_id=key,
                            )
                            self._mark_alerted_today(key)
            except Exception:
                pass

        except Exception as e:
            print(f"[PROACTIVE] System health check error: {e}")

    # ── Monitor: Weather ───────────────────────────────────────────────────────

    async def _check_weather(self) -> None:
        try:
            from api.weather_calendar import get_weather
            w = await get_weather()
            if w.get("error") or w.get("temp") is None:
                return

            condition = w.get("condition", "").lower()
            is_adverse = any(term in condition for term in _RAIN_STORM_TERMS)
            if not is_adverse:
                return

            key = f"weather_{datetime.now().date().isoformat()}"
            if self._already_alerted_today(key):
                return

            msg = (
                f"Weather alert sir. {w['condition']} expected in Cairo today. "
                f"Temperature {w['temp']} degrees."
            )
            await self._interrupt(msg, priority="medium", source="weather",
                                  alert_id=key)
            self._mark_alerted_today(key)

        except Exception as e:
            print(f"[PROACTIVE] Weather check error: {e}")

    # ── Monitor: Missions ──────────────────────────────────────────────────────

    async def _check_missions(self) -> None:
        try:
            from core.mission_board import get_today
            missions = await asyncio.to_thread(get_today)
        except Exception:
            return

        stale_hours = self._config.get("mission_stale_hours", self.MISSION_STALE_HOURS)
        cutoff      = time.time() - (stale_hours * 3600)
        now         = datetime.now()

        for mission in missions:
            if mission.get("status") in ("complete", "deferred"):
                continue
            created = mission.get("created_at", time.time())
            if created > cutoff:
                continue

            key = f"missions_{mission['id']}_{now.date().isoformat()}"
            if self._already_alerted_today(key):
                continue

            hours_stale = (time.time() - created) / 3600
            msg = (
                f"Sir, mission {mission['title']} "
                f"has had no update in {int(hours_stale)} hours."
            )
            await self._interrupt(msg, priority="medium", source="missions",
                                  alert_id=key)
            self._mark_alerted_today(key)

    # ── Monitor: WhatsApp ──────────────────────────────────────────────────────

    async def _check_whatsapp(self) -> None:
        try:
            from sensors.whatsapp_sensor import whatsapp
            status_data = await whatsapp.get_status()
            if status_data.get("status") != "connected":
                return

            unread = whatsapp.get_unread_count()
            if unread == 0:
                return

            key = f"whatsapp_{datetime.now().date().isoformat()}"
            if self._already_alerted_today(key):
                return

            msgs  = await whatsapp.poll_incoming(limit=10, unread_only=True)
            names = list({m.get("from_name", "Unknown") for m in msgs[:5]})
            names_str = ", ".join(names[:3])
            msg = (
                f"Sir, you have {unread} unread WhatsApp "
                f"message{'s' if unread != 1 else ''}. "
                f"From {names_str}."
            )
            await self._interrupt(msg, priority="medium", source="whatsapp",
                                  alert_id=key)
            self._mark_alerted_today(key)

        except Exception as e:
            print(f"[PROACTIVE] WhatsApp check error: {e}")


# ── Singleton ──────────────────────────────────────────────────────────────────
agent = ProactiveAgent()
