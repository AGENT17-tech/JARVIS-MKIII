"""
JARVIS-MKIII — core/adaptive_memory.py
Adaptive learning system.

LAYER 1 — Interaction Logger       : records every chat exchange to SQLite
LAYER 2 — Feedback Capture         : detects implicit approval / rejection signals
LAYER 3 — Pattern Extraction       : analyses 7-day window for behavioural patterns
LAYER 4 — User Profile             : persists adaptive profile to JSON
LAYER 5 — Mistake Learning         : extracts lessons from failed exchanges via LLM

Design contract:
  • All public sync functions are cheap SQLite reads/writes.
  • All LLM calls live in async helpers and are fire-and-forget — they NEVER
    block the main chat path.
  • Import side-effects are nil: DB is initialised lazily on first call.
"""
from __future__ import annotations
import asyncio, json, sqlite3, time, datetime
from pathlib import Path

DB_PATH      = Path.home() / "JARVIS_MKIII" / "backend" / "data" / "jarvis.db"
PROFILE_PATH = Path.home() / "JARVIS_MKIII" / "backend" / "data" / "user_profile.json"

# ── DB helpers ────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       TEXT,
                timestamp        REAL NOT NULL,
                user_input       TEXT NOT NULL,
                jarvis_response  TEXT NOT NULL,
                intent_detected  TEXT,
                agent_used       TEXT,
                response_time_ms INTEGER,
                feedback         TEXT
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions(timestamp)
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           REAL NOT NULL,
                original_input      TEXT NOT NULL,
                failed_response     TEXT NOT NULL,
                corrected_response  TEXT,
                lesson              TEXT
            )
        """)
        c.commit()


_init_db()

# ── LAYER 1 — Interaction Logger ─────────────────────────────────────────────

def log_interaction(
    session_id:       str,
    user_input:       str,
    jarvis_response:  str,
    intent_detected:  str | None = None,
    agent_used:       str | None = None,
    response_time_ms: int | None = None,
) -> int:
    """Synchronously insert one interaction row. Returns the row id."""
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO interactions
               (session_id, timestamp, user_input, jarvis_response,
                intent_detected, agent_used, response_time_ms)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, time.time(), user_input, jarvis_response,
             intent_detected, agent_used, response_time_ms),
        )
        c.commit()
        return cur.lastrowid


async def log_interaction_async(
    session_id:      str,
    user_input:      str,
    jarvis_response: str,
    intent:          str | None = None,
    agent:           str | None = None,
    ms:              int | None = None,
) -> None:
    """Fire-and-forget wrapper — never raises, never blocks."""
    try:
        await asyncio.to_thread(
            log_interaction, session_id, user_input, jarvis_response, intent, agent, ms
        )
    except Exception:
        pass


# ── LAYER 2 — Feedback Capture ────────────────────────────────────────────────

_POSITIVE = frozenset({
    "good", "perfect", "exactly", "yes", "great", "correct",
    "well done", "nice", "excellent", "that's right", "brilliant",
})
_NEGATIVE = frozenset({
    "no", "wrong", "not what i meant", "try again", "incorrect",
    "that's wrong", "nope", "not right", "negative", "bad",
})


def detect_feedback(user_input: str) -> str | None:
    """
    Scan a follow-up user utterance for implicit feedback on the prior response.
    Returns 'response_approved' | 'response_failed' | None.
    """
    lower = user_input.strip().lower()
    if any(s in lower for s in _POSITIVE):
        return "response_approved"
    if any(s in lower for s in _NEGATIVE):
        return "response_failed"
    return None


def update_feedback(interaction_id: int, feedback: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE interactions SET feedback=? WHERE id=?",
            (feedback, interaction_id),
        )
        c.commit()


def get_last_interaction_id(session_id: str) -> int | None:
    with _conn() as c:
        row = c.execute(
            "SELECT id FROM interactions WHERE session_id=? ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return row["id"] if row else None


def get_last_interaction(session_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM interactions WHERE session_id=? ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None


# ── LAYER 3 — Pattern Extraction ─────────────────────────────────────────────

def extract_patterns(days: int = 7) -> dict:
    """
    Analyse the last N days of interactions.
    Returns a dict of behavioural signals suitable for profile updating.
    """
    cutoff = time.time() - days * 86400
    with _conn() as c:
        rows = c.execute(
            """SELECT user_input, jarvis_response, intent_detected, agent_used,
                      feedback, timestamp
               FROM interactions WHERE timestamp > ? ORDER BY timestamp""",
            (cutoff,),
        ).fetchall()

    if not rows:
        return {}

    interactions = [dict(r) for r in rows]
    approved = [r for r in interactions if r["feedback"] == "response_approved"]
    failed   = [r for r in interactions if r["feedback"] == "response_failed"]

    # Response-length preference
    def avg_resp_len(lst: list) -> int:
        lens = [len(r["jarvis_response"]) for r in lst if r.get("jarvis_response")]
        return int(sum(lens) / len(lens)) if lens else 0

    approved_avg = avg_resp_len(approved)
    preferred_length = (
        "concise"  if approved_avg < 150 else
        "detailed" if approved_avg > 400 else
        "medium"
    )

    # Time-of-day patterns
    hours = [datetime.datetime.fromtimestamp(r["timestamp"]).hour for r in interactions]
    morning_count = sum(1 for h in hours if 5 <= h < 12)
    night_count   = sum(1 for h in hours if h >= 20 or h < 4)
    total         = len(hours)
    peak_period   = (
        "morning" if total and morning_count > total * 0.5 else
        "night"   if total and night_count   > total * 0.4 else
        "mixed"
    )

    # Agent / intent frequency
    intent_counts: dict[str, int] = {}
    agent_counts:  dict[str, int] = {}
    for r in interactions:
        if r.get("intent_detected"):
            k = r["intent_detected"]
            intent_counts[k] = intent_counts.get(k, 0) + 1
        if r.get("agent_used"):
            k = r["agent_used"]
            agent_counts[k] = agent_counts.get(k, 0) + 1

    top_agents  = sorted(agent_counts,  key=lambda x: -agent_counts[x])[:3]
    top_intents = sorted(intent_counts, key=lambda x: -intent_counts[x])[:5]
    positive_rate = round(len(approved) / len(interactions) * 100) if interactions else 0

    return {
        "preferred_response_length": preferred_length,
        "approved_avg_chars":        approved_avg,
        "peak_period":               peak_period,
        "top_intents":               top_intents,
        "preferred_agents":          top_agents,
        "total_interactions":        len(interactions),
        "positive_feedback_rate":    positive_rate,
    }


# ── LAYER 4 — User Profile ────────────────────────────────────────────────────

_DEFAULT_PROFILE: dict = {
    "name":                      "Khalid",
    "preferred_response_length": "medium",
    "active_hours":              ["09:00-12:00", "21:00-03:00"],
    "frequent_topics":           ["engineering", "JARVIS", "IEEE", "training"],
    "preferred_agents":          ["research", "code"],
    "communication_style":       "direct",
    "last_updated":              None,
}


def load_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text())
        except Exception:
            pass
    return dict(_DEFAULT_PROFILE)


def save_profile(profile: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    profile["last_updated"] = datetime.datetime.now().isoformat()
    PROFILE_PATH.write_text(json.dumps(profile, indent=2))


def update_profile_from_patterns(patterns: dict) -> dict:
    """Merge extracted patterns into the persisted user profile."""
    if not patterns:
        return load_profile()
    profile = load_profile()
    if patterns.get("preferred_response_length"):
        profile["preferred_response_length"] = patterns["preferred_response_length"]
    if patterns.get("preferred_agents"):
        profile["preferred_agents"] = patterns["preferred_agents"]
    save_profile(profile)
    return profile


async def run_daily_analysis() -> None:
    """Scheduled task: extract patterns and update profile. Fire-and-forget."""
    try:
        patterns = await asyncio.to_thread(extract_patterns)
        if patterns:
            await asyncio.to_thread(update_profile_from_patterns, patterns)
    except Exception:
        pass


# ── LAYER 5 — Mistake Learning ────────────────────────────────────────────────

def log_correction(
    original_input:     str,
    failed_response:    str,
    corrected_response: str | None = None,
) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO corrections
               (timestamp, original_input, failed_response, corrected_response)
               VALUES (?,?,?,?)""",
            (time.time(), original_input, failed_response, corrected_response),
        )
        c.commit()
        return cur.lastrowid


async def generate_lesson(
    original_input:     str,
    failed_response:    str,
    corrected_response: str,
    correction_id:      int,
) -> None:
    """
    Ask the LLM to distil a one-sentence lesson from a failed exchange,
    then persist it. Fully async, never blocks the response path.
    """
    try:
        from groq import AsyncGroq
        from core.vault import Vault
        from config.settings import MODEL_CFG
        client = AsyncGroq(api_key=Vault().get("GROQ_API_KEY"))
        prompt = (
            f"Original request: {original_input}\n"
            f"JARVIS response: {failed_response}\n"
            f"User rephrased as: {corrected_response}\n\n"
            "What lesson should JARVIS learn? "
            "Reply in ONE sentence starting with 'When user asks about'"
        )
        resp = await client.chat.completions.create(
            model=MODEL_CFG.groq_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.3,
        )
        lesson = resp.choices[0].message.content.strip()
        with _conn() as c:
            c.execute(
                "UPDATE corrections SET lesson=? WHERE id=?",
                (lesson, correction_id),
            )
            c.commit()
    except Exception:
        pass


def get_recent_lessons(limit: int = 5) -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT lesson FROM corrections WHERE lesson IS NOT NULL"
            " ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["lesson"] for r in rows]


# ── Public stats ──────────────────────────────────────────────────────────────

def get_stats() -> dict:
    week_cutoff = time.time() - 7 * 86400
    with _conn() as c:
        total    = c.execute("SELECT COUNT(*) AS n FROM interactions").fetchone()["n"]
        week     = c.execute("SELECT COUNT(*) AS n FROM interactions WHERE timestamp>?", (week_cutoff,)).fetchone()["n"]
        approved = c.execute("SELECT COUNT(*) AS n FROM interactions WHERE feedback='response_approved'").fetchone()["n"]
        failed   = c.execute("SELECT COUNT(*) AS n FROM interactions WHERE feedback='response_failed'").fetchone()["n"]
        lessons  = c.execute("SELECT COUNT(*) AS n FROM corrections WHERE lesson IS NOT NULL").fetchone()["n"]
    rated = approved + failed
    return {
        "total_interactions": total,
        "last_7_days":        week,
        "approved":           approved,
        "failed":             failed,
        "lessons_learned":    lessons,
        "approval_rate":      round(approved / rated * 100) if rated else 0,
    }
