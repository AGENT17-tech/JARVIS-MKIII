"""
JARVIS-MKIII — core/proactive_engine.py
Proactive intelligence engine.

Monitors system state and speaks without being asked — based on time,
mission state, system health, GitHub activity, and user idle time.

Delivery model:
  1. Push alert to HUD via WebSocket immediately
  2. Wait 10 seconds
  3. If user interacted since alert fired, or alert dismissed → cancel TTS
  4. Otherwise → speak via TTS
"""
from __future__ import annotations
import asyncio, datetime, time
from typing import Any


class ProactiveEngine:

    def __init__(self):
        self.last_user_interaction: float = time.time()
        self._spoken_today: set[str] = set()
        self._spoken_date:  str      = ""
        self._pending_alerts: dict[str, dict] = {}
        self._github_last_shas: dict[str, str] = {}
        self._running = False
        self._tasks:   list[asyncio.Task] = []

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        loop = asyncio.get_event_loop()
        self._tasks = [
            loop.create_task(self._main_loop(),     name="proactive_main"),
            loop.create_task(self._calendar_loop(), name="proactive_calendar"),
            loop.create_task(self._github_loop(),   name="proactive_github"),
            loop.create_task(self._timed_loop(),    name="proactive_timed"),
        ]
        print("[PROACTIVE] Engine started.")

    def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()

    # ── Public API ─────────────────────────────────────────────────────────────

    def note_interaction(self) -> None:
        """Call on every user interaction to reset idle/TTS-cancel timer."""
        self.last_user_interaction = time.time()

    def dismiss_alert(self, alert_id: str) -> None:
        """Mark an alert dismissed so pending TTS is cancelled."""
        if alert_id in self._pending_alerts:
            self._pending_alerts[alert_id]["dismissed"] = True

    # ── Daily dedup ────────────────────────────────────────────────────────────

    def _reset_daily(self) -> None:
        today = datetime.date.today().isoformat()
        if today != self._spoken_date:
            self._spoken_date  = today
            self._spoken_today = set()

    def _already_spoken(self, alert_id: str) -> bool:
        self._reset_daily()
        return alert_id in self._spoken_today

    def _mark_spoken(self, alert_id: str) -> None:
        self._reset_daily()
        self._spoken_today.add(alert_id)

    # ── Alert construction ─────────────────────────────────────────────────────

    def _make_alert(
        self,
        alert_id:    str,
        alert_type:  str,
        priority:    str,
        title:       str,
        message:     str,
        hud_message: str,
    ) -> dict:
        return {
            "id":          alert_id,
            "type":        alert_type,
            "priority":    priority,
            "title":       title,
            "message":     message,
            "hud_message": hud_message,
            "timestamp":   datetime.datetime.now().isoformat(),
            "spoken":      False,
            "dismissed":   False,
        }

    # ── Alert firing ──────────────────────────────────────────────────────────

    async def fire_alert(self, alert: dict) -> None:
        """
        1. Mark spoken immediately (prevents duplicates from concurrent checks)
        2. Push to HUD via WebSocket
        3. Sleep 10 seconds
        4. If user interacted or dismissed → cancel TTS
        5. Otherwise → speak
        """
        alert_id = alert["id"]
        if self._already_spoken(alert_id):
            return

        self._mark_spoken(alert_id)
        alert["spoken"]    = False
        alert["dismissed"] = False
        fired_at = time.time()
        self._pending_alerts[alert_id] = alert

        # 1. Push to HUD
        try:
            from api.voice_bridge import broadcast_to_hud
            await broadcast_to_hud({"type": "proactive_alert", "data": alert})
        except Exception as e:
            print(f"[PROACTIVE] HUD push failed for '{alert_id}': {e}")

        # 2. Wait 10 seconds
        await asyncio.sleep(10)

        # 3. Cancel if dismissed or user interacted since alert fired
        entry = self._pending_alerts.get(alert_id, {})
        if entry.get("dismissed", False) or self.last_user_interaction > fired_at:
            print(f"[PROACTIVE] TTS cancelled for '{alert_id}' (user active / dismissed).")
            self._pending_alerts.pop(alert_id, None)
            return

        # 4. Speak — wait if TTS is already playing (up to 30 s)
        try:
            from api.voice_bridge import request_speak, is_speaking
            for _ in range(30):
                if not is_speaking():
                    break
                await asyncio.sleep(1)
            await request_speak(alert["message"])
            print(f"[PROACTIVE] Spoke: '{alert_id}'")
        except Exception as e:
            print(f"[PROACTIVE] TTS failed for '{alert_id}': {e}")

        alert["spoken"] = True

        # Cleanup after another 60 seconds
        await asyncio.sleep(60)
        self._pending_alerts.pop(alert_id, None)

    # ── Background loops ──────────────────────────────────────────────────────

    async def _main_loop(self) -> None:
        """Runs every 30 seconds: mission reminders, anomalies, idle, morning briefing."""
        await asyncio.sleep(20)   # let backend fully start
        while self._running:
            try:
                await self.check_morning_briefing()
                await self.check_mission_deadlines()
                await self.check_system_anomalies()
                await self.check_idle()
            except Exception as e:
                print(f"[PROACTIVE] Main loop error: {e}")
            await asyncio.sleep(30)

    async def _calendar_loop(self) -> None:
        """Runs every 5 minutes: calendar event alerts."""
        await asyncio.sleep(30)
        while self._running:
            try:
                await self.check_calendar_events()
            except Exception as e:
                print(f"[PROACTIVE] Calendar loop error: {e}")
            await asyncio.sleep(300)

    async def _github_loop(self) -> None:
        """Runs every 10 minutes: GitHub activity."""
        await asyncio.sleep(45)
        while self._running:
            try:
                await self.check_github_activity()
            except Exception as e:
                print(f"[PROACTIVE] GitHub loop error: {e}")
            await asyncio.sleep(600)

    async def _timed_loop(self) -> None:
        """Checks every minute for time-triggered events (23:00 EOD)."""
        await asyncio.sleep(10)
        while self._running:
            try:
                now = datetime.datetime.now()
                # EOD at 23:00
                if now.hour == 23 and now.minute == 0:
                    asyncio.create_task(self.check_end_of_day())
            except Exception as e:
                print(f"[PROACTIVE] Timed loop error: {e}")
            await asyncio.sleep(60)

    # ══ TRIGGER IMPLEMENTATIONS ═══════════════════════════════════════════════

    # 1. MORNING BRIEFING ──────────────────────────────────────────────────────

    async def check_morning_briefing(self) -> None:
        now  = datetime.datetime.now()
        hour = now.hour
        if not (5 <= hour <= 11):
            return

        today    = now.date().isoformat()
        alert_id = f"morning_briefing_{today}"
        if self._already_spoken(alert_id):
            return

        # Collect mission data
        mission_text = ""
        try:
            from core.mission_board import get_today
            missions = await asyncio.to_thread(get_today)
            if missions:
                top = next(
                    (m for m in missions if m["priority"] in ("critical", "high")),
                    missions[0],
                )
                n = len(missions)
                mission_text = (
                    f"You have {n} mission{'s' if n != 1 else ''} today. "
                    f"Priority: {top['title']}."
                )
            else:
                mission_text = "No missions logged yet today."
        except Exception:
            pass

        # Collect weather data
        weather_text = ""
        try:
            from api.weather_calendar import get_weather
            w = await get_weather()
            if w.get("temp") is not None:
                weather_text = (
                    f"Weather in {w.get('city', 'Cairo')}: "
                    f"{w.get('condition', '')}, {w.get('temp', '')}°C."
                )
        except Exception:
            pass

        # GitHub status
        github_text = ""
        try:
            from api.weather_calendar import _github_last_ok
            github_text = "GitHub: connected." if _github_last_ok else ""
        except Exception:
            pass

        # Calendar events
        calendar_text = ""
        try:
            from config.google_calendar import get_today_events, is_configured
            if is_configured():
                events = await asyncio.to_thread(get_today_events)
                if events:
                    n = len(events)
                    first = events[0]
                    calendar_text = (
                        f"You have {n} calendar event{'s' if n != 1 else ''} today. "
                        f"First up: {first['title']} at {first['time']}."
                    )
                else:
                    calendar_text = "No calendar events today."
        except Exception:
            pass

        greeting = (
            "Good morning" if hour < 12
            else ("Good afternoon" if hour < 18 else "Good evening")
        )
        date_str = now.strftime("%A, %d %B %Y")
        time_str = now.strftime("%H:%M")

        message = " ".join(filter(None, [
            f"{greeting}, sir. It is {time_str} on {date_str}.",
            mission_text,
            calendar_text,
            weather_text,
            github_text,
            "All systems nominal. Awaiting your orders.",
        ]))

        alert = self._make_alert(
            alert_id    = alert_id,
            alert_type  = "briefing",
            priority    = "high",
            title       = "MORNING BRIEFING",
            message     = message,
            hud_message = " ".join(filter(None, [mission_text, calendar_text, weather_text])) or "Good morning, sir.",
        )
        asyncio.create_task(self.fire_alert(alert))

    # 2. MISSION DEADLINE REMINDERS ────────────────────────────────────────────

    async def check_mission_deadlines(self) -> None:
        now = datetime.datetime.now()

        # 20:00 evening reminder: fire for any incomplete missions
        if now.hour == 20 and now.minute < 30:
            await self._check_evening_mission_reminder(now)
            return

        # Ongoing: missions pending for 4+ hours
        try:
            from core.mission_board import get_today
            missions = await asyncio.to_thread(get_today)
        except Exception:
            return

        cutoff = time.time() - (4 * 3600)
        for m in missions:
            if m["status"] in ("complete", "deferred"):
                continue
            if m.get("created_at", time.time()) > cutoff:
                continue

            date_str = now.date().isoformat()
            hour_str = str(now.hour)
            alert_id = f"mission_reminder_{m['id']}_{date_str}_{hour_str}"
            if self._already_spoken(alert_id):
                continue

            msg = (
                f"Sir, '{m['title']}' remains pending. "
                "Shall I add it to tomorrow's board?"
            )
            alert = self._make_alert(
                alert_id    = alert_id,
                alert_type  = "mission",
                priority    = "medium",
                title       = f"PENDING — {m['title'][:28].upper()}",
                message     = msg,
                hud_message = f"'{m['title']}' — pending 4+ hours.",
            )
            asyncio.create_task(self.fire_alert(alert))
            break   # one reminder per 30s cycle

    async def _check_evening_mission_reminder(self, now: datetime.datetime) -> None:
        try:
            from core.mission_board import get_today
            missions = await asyncio.to_thread(get_today)
        except Exception:
            return

        incomplete = [m for m in missions if m["status"] not in ("complete", "deferred")]
        if not incomplete:
            return

        date_str = now.date().isoformat()
        alert_id = f"evening_mission_reminder_{date_str}"
        if self._already_spoken(alert_id):
            return

        titles = ", ".join(m["title"] for m in incomplete[:3])
        n = len(incomplete)
        msg = (
            f"Sir, end of evening check. "
            f"{n} mission{'s' if n != 1 else ''} still incomplete: {titles}."
        )
        alert = self._make_alert(
            alert_id    = alert_id,
            alert_type  = "mission",
            priority    = "high",
            title       = f"{n} MISSIONS INCOMPLETE",
            message     = msg,
            hud_message = f"{n} missions incomplete at 20:00.",
        )
        asyncio.create_task(self.fire_alert(alert))

    # 3. CALENDAR EVENT ALERTS ─────────────────────────────────────────────────

    async def check_calendar_events(self) -> None:
        """
        Fetch upcoming events from Google Calendar and fire alerts 15 minutes
        before each event starts. Alert ID includes the event ID and the
        15-min slot, so each event only gets one reminder per day.
        """
        try:
            from config.google_calendar import get_upcoming_events, is_configured
        except ImportError:
            return

        if not is_configured():
            return

        try:
            # Look 16 minutes ahead — the loop runs every 5 min, so we catch
            # events whose start time falls in the 0–15 minute window.
            events = await asyncio.to_thread(get_upcoming_events, minutes_ahead=16)
        except Exception as e:
            print(f"[PROACTIVE] Calendar fetch failed: {e}")
            return

        now = datetime.datetime.now()

        for event in events:
            start_dt = event.get("_start_dt")
            if start_dt is None:
                continue

            # Make start_dt offset-naive for comparison if needed
            if hasattr(start_dt, "tzinfo") and start_dt.tzinfo is not None:
                try:
                    import zoneinfo
                    local_tz  = zoneinfo.ZoneInfo("Africa/Cairo")
                    start_dt  = start_dt.astimezone(local_tz).replace(tzinfo=None)
                except Exception:
                    start_dt = start_dt.replace(tzinfo=None)

            minutes_until = (start_dt - now).total_seconds() / 60

            if not (0 < minutes_until <= 15):
                continue

            event_id = event.get("id", event.get("title", "unknown"))
            alert_id = f"calendar_15min_{event_id}_{now.date().isoformat()}"
            if self._already_spoken(alert_id):
                continue

            title     = event.get("title", "Untitled Event")
            time_str  = event.get("time", "")
            location  = event.get("location", "")
            mins_int  = max(1, int(minutes_until))

            location_text = f" at {location}" if location else ""
            msg = (
                f"Sir, you have '{title}'{location_text} starting in {mins_int} "
                f"minute{'s' if mins_int != 1 else ''}."
            )
            hud_msg = f"{title} — in {mins_int} min{'' if mins_int == 1 else 's'} ({time_str})"

            asyncio.create_task(self.fire_alert(self._make_alert(
                alert_id    = alert_id,
                alert_type  = "calendar",
                priority    = "high",
                title       = f"UPCOMING — {title[:28].upper()}",
                message     = msg,
                hud_message = hud_msg,
            )))

    # 4. SYSTEM ANOMALY ALERTS ─────────────────────────────────────────────────

    async def check_system_anomalies(self) -> None:
        try:
            import psutil
            now      = datetime.datetime.now()
            date_str = now.date().isoformat()
            hour_str = str(now.hour)

            # CPU
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu > 85:
                alert_id = f"anomaly_cpu_{date_str}_{hour_str}"
                if not self._already_spoken(alert_id):
                    msg = (
                        f"Sir, CPU usage is at {round(cpu)}%. "
                        "System is under heavy load. Shall I investigate?"
                    )
                    asyncio.create_task(self.fire_alert(self._make_alert(
                        alert_id    = alert_id,
                        alert_type  = "system",
                        priority    = "critical",
                        title       = f"HIGH CPU — {round(cpu)}%",
                        message     = msg,
                        hud_message = f"CPU at {round(cpu)}% — possible overload.",
                    )))

            # RAM
            ram = psutil.virtual_memory().percent
            if ram > 80:
                alert_id = f"anomaly_ram_{date_str}_{hour_str}"
                if not self._already_spoken(alert_id):
                    msg = (
                        f"Sir, memory usage is at {round(ram)}%. "
                        "Shall I identify the heaviest processes?"
                    )
                    asyncio.create_task(self.fire_alert(self._make_alert(
                        alert_id    = alert_id,
                        alert_type  = "system",
                        priority    = "critical",
                        title       = f"HIGH RAM — {round(ram)}%",
                        message     = msg,
                        hud_message = f"Memory at {round(ram)}% — running low.",
                    )))

            # Disk (real partitions only)
            _SKIP_PREFIXES = ("/snap/", "/boot/efi")
            _SKIP_FSTYPES  = {"squashfs", "tmpfs", "devtmpfs"}
            for part in psutil.disk_partitions(all=False):
                mp = part.mountpoint
                if any(mp.startswith(p) for p in _SKIP_PREFIXES):
                    continue
                if part.fstype in _SKIP_FSTYPES:
                    continue
                try:
                    pct = psutil.disk_usage(mp).percent
                    if pct > 85:
                        safe_mp  = mp.replace("/", "_")
                        alert_id = f"anomaly_disk_{safe_mp}_{date_str}_{hour_str}"
                        if not self._already_spoken(alert_id):
                            msg = (
                                f"Sir, disk {mp} is at {round(pct)}% capacity. "
                                "Recommend freeing space soon."
                            )
                            asyncio.create_task(self.fire_alert(self._make_alert(
                                alert_id    = alert_id,
                                alert_type  = "system",
                                priority    = "high",
                                title       = f"DISK {mp.upper()} — {round(pct)}%",
                                message     = msg,
                                hud_message = f"Disk {mp} at {round(pct)}% — low space.",
                            )))
                except Exception:
                    continue

            # GPU VRAM (optional, nvidia-smi)
            try:
                import subprocess
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2,
                )
                if r.returncode == 0:
                    parts    = r.stdout.strip().split(",")
                    used, total = int(parts[0]), int(parts[1])
                    vram_pct = round(used / total * 100)
                    if vram_pct > 90:
                        alert_id = f"anomaly_vram_{date_str}_{hour_str}"
                        if not self._already_spoken(alert_id):
                            msg = (
                                f"Sir, GPU VRAM is at {vram_pct}%. "
                                f"{used} of {total} MB in use."
                            )
                            asyncio.create_task(self.fire_alert(self._make_alert(
                                alert_id    = alert_id,
                                alert_type  = "system",
                                priority    = "critical",
                                title       = f"HIGH VRAM — {vram_pct}%",
                                message     = msg,
                                hud_message = f"GPU VRAM at {vram_pct}% — almost full.",
                            )))
            except Exception:
                pass

        except Exception as e:
            print(f"[PROACTIVE] Anomaly check error: {e}")

    # 5. GITHUB ACTIVITY ALERTS ────────────────────────────────────────────────

    async def check_github_activity(self) -> None:
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
                # First run — seed, no alert
                self._github_last_shas[name] = latest_sha
                continue

            if latest_sha == last_known:
                continue

            # New commits since last check
            self._github_last_shas[name] = latest_sha
            alert_id = f"github_{name}_{latest_sha}"
            if self._already_spoken(alert_id):
                continue

            raw_msg   = commits[0].get("message", "")
            truncated = " ".join(raw_msg.split()[:8])
            if len(raw_msg.split()) > 8:
                truncated += "..."

            n   = len(commits)
            msg = (
                f"Sir, new activity on {name}. "
                f"{n} commit{'s' if n != 1 else ''} pushed. "
                f"Latest: '{truncated}'."
            )
            asyncio.create_task(self.fire_alert(self._make_alert(
                alert_id    = alert_id,
                alert_type  = "github",
                priority    = "low",
                title       = f"NEW COMMIT — {name.upper()}",
                message     = msg,
                hud_message = f"{name}: {truncated}",
            )))

    # 6. IDLE CHECK-INS ────────────────────────────────────────────────────────

    async def check_idle(self) -> None:
        now  = datetime.datetime.now()
        hour = now.hour

        # Active hours only: 08:00–02:00
        if not (hour >= 8 or hour < 2):
            return

        idle_seconds = time.time() - self.last_user_interaction
        if idle_seconds < 2700:   # 45 minutes
            return

        date_str = now.date().isoformat()
        hour_str = str(hour)
        alert_id = f"idle_{date_str}_{hour_str}"
        if self._already_spoken(alert_id):
            return

        pending_count = 0
        try:
            from core.mission_board import get_today
            missions      = await asyncio.to_thread(get_today)
            pending_count = sum(1 for m in missions if m["status"] == "pending")
        except Exception:
            pass

        idle_min = int(idle_seconds // 60)
        msg = (
            f"Sir, you have been inactive for {idle_min} minutes. "
            f"{pending_count} mission{'s' if pending_count != 1 else ''} pending. "
            "Shall I run a status report?"
        )
        asyncio.create_task(self.fire_alert(self._make_alert(
            alert_id    = alert_id,
            alert_type  = "idle",
            priority    = "low",
            title       = f"IDLE — {idle_min} MIN",
            message     = msg,
            hud_message = f"Inactive {idle_min} min — {pending_count} missions pending.",
        )))

    # 7. END OF DAY ────────────────────────────────────────────────────────────

    async def check_end_of_day(self) -> None:
        today    = datetime.date.today().isoformat()
        alert_id = f"eod_{today}"
        if self._already_spoken(alert_id):
            return

        briefing = "End of day report unavailable, sir."
        n_completed, n_pending = 0, 0
        try:
            from core.mission_board import end_of_day_summary
            result      = await asyncio.to_thread(end_of_day_summary)
            briefing    = result.get("briefing", briefing)
            n_completed = len(result.get("completed", []))
            n_pending   = len(result.get("pending",   []))
        except Exception:
            pass

        msg = f"Sir, {briefing} Shall I carry incomplete missions over to tomorrow?"
        asyncio.create_task(self.fire_alert(self._make_alert(
            alert_id    = alert_id,
            alert_type  = "eod",
            priority    = "medium",
            title       = "END OF DAY REPORT",
            message     = msg,
            hud_message = f"{n_completed} done, {n_pending} pending.",
        )))

    # ── External hook: called by monitor_agent ─────────────────────────────────

    async def handle_monitor_alert(self, message: str, key: str, critical: bool = False) -> None:
        """Wire in from agents/monitor_agent.py _alert() method."""
        now      = datetime.datetime.now()
        date_str = now.date().isoformat()
        hour_str = str(now.hour)
        alert_id = f"anomaly_{key}_{date_str}_{hour_str}"
        if self._already_spoken(alert_id):
            return

        priority   = "critical" if critical else "high"
        spoken_msg = f"Sir, {message} Shall I investigate?"
        asyncio.create_task(self.fire_alert(self._make_alert(
            alert_id    = alert_id,
            alert_type  = "system",
            priority    = priority,
            title       = f"SYSTEM — {key.upper().replace('_', ' ')}",
            message     = spoken_msg,
            hud_message = message,
        )))


# ── Singleton ─────────────────────────────────────────────────────────────────
engine = ProactiveEngine()
