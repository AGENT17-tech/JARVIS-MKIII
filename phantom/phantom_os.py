"""
JARVIS-MKIII — phantom/phantom_os.py
PHANTOM ZERO OS Layer — Agent 17 domain tracking and daily operational scoring.

Five domains, each with daily activity logging and score computation.
Scores persist in phantom/scores.json across restarts.
"""
from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

# ── Domain definitions ─────────────────────────────────────────────────────────

DOMAINS: dict[str, dict] = {
    "engineering": {
        "label":  "ENGINEERING & ROBOTICS",
        "color":  "#00d4ff",
        "target": 80,
    },
    "programming": {
        "label":  "PROGRAMMING & CYBER",
        "color":  "#00ffc8",
        "target": 85,
    },
    "combat": {
        "label":  "COMBAT & PHYSICAL",
        "color":  "#ff6644",
        "target": 75,
    },
    "strategy": {
        "label":  "STRATEGIC THINKING",
        "color":  "#ffb900",
        "target": 70,
    },
    "neuro": {
        "label":  "NEURO-PERFORMANCE",
        "color":  "#a78bfa",
        "target": 75,
    },
}

_BASELINE = 25   # score for domains with zero logged activity today

SCORES_PATH = Path(__file__).parent / "scores.json"


# ── Score formula helpers ──────────────────────────────────────────────────────

def _clip(value: float) -> int:
    return max(0, min(100, int(value)))


def _score_engineering(acts: list[dict]) -> int:
    github_commits  = sum(a["value"] for a in acts if a["activity_type"] == "commit")
    code_sessions   = sum(a["value"] for a in acts if a["activity_type"] == "session")
    build_runs      = sum(a["value"] for a in acts if a["activity_type"] == "build")
    return _clip(github_commits * 15 + code_sessions * 20 + build_runs * 10)


def _score_programming(acts: list[dict]) -> int:
    dsa_problems       = sum(a["value"] for a in acts if a["activity_type"] == "dsa")
    teaching_sessions  = sum(a["value"] for a in acts if a["activity_type"] == "teaching_session")
    claude_code_hrs    = sum(a["value"] for a in acts if a["activity_type"] == "claude_code")
    # also count generic "session" and "study" contributions
    study              = sum(a["value"] for a in acts if a["activity_type"] == "study")
    return _clip(dsa_problems * 20 + teaching_sessions * 25 + claude_code_hrs * 15 + study * 10)


def _score_combat(acts: list[dict]) -> int:
    workout_logged  = sum(a["value"] for a in acts if a["activity_type"] == "workout")
    sparring_logged = sum(a["value"] for a in acts if a["activity_type"] == "sparring")
    streak_bonus    = 1 if acts else 0   # any activity = streak day
    return _clip(workout_logged * 40 + sparring_logged * 30 + streak_bonus * 10)


def _score_strategy(acts: list[dict]) -> int:
    chess_games            = sum(a["value"] for a in acts if a["activity_type"] == "game")
    missions_completed_pct = sum(a["value"] for a in acts if a["activity_type"] == "mission_pct")
    decisions_logged       = sum(a["value"] for a in acts if a["activity_type"] == "decision")
    return _clip(chess_games * 20 + missions_completed_pct * 50 + decisions_logged * 10)


def _score_neuro(acts: list[dict]) -> int:
    sleep_hrs    = sum(a["value"] for a in acts if a["activity_type"] == "sleep")
    reading_mins = sum(a["value"] for a in acts if a["activity_type"] == "reading")
    lang_mins    = sum(a["value"] for a in acts if a["activity_type"] == "language")
    study_mins   = sum(a["value"] for a in acts if a["activity_type"] == "study") * 5
    return _clip(sleep_hrs * 12 + reading_mins / 3 + lang_mins / 2 + study_mins)


_SCORERS = {
    "engineering": _score_engineering,
    "programming": _score_programming,
    "combat":      _score_combat,
    "strategy":    _score_strategy,
    "neuro":       _score_neuro,
}


# ── PhantomOS ──────────────────────────────────────────────────────────────────

class PhantomOS:
    def __init__(self) -> None:
        SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._path = SCORES_PATH
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:
                pass
        return {"activities": []}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    # ── Write ─────────────────────────────────────────────────────────────────

    def log_activity(
        self,
        domain:        str,
        activity_type: str,
        value:         float,
        notes:         str = "",
    ) -> None:
        """Append a timestamped activity record to scores.json."""
        if domain not in DOMAINS:
            raise ValueError(f"Unknown domain: {domain!r}. Valid: {list(DOMAINS)}")
        record = {
            "domain":        domain,
            "activity_type": activity_type,
            "value":         value,
            "notes":         notes,
            "timestamp":     datetime.now().isoformat(),
            "date":          date.today().isoformat(),
        }
        self._data.setdefault("activities", []).append(record)
        self._save()

    # ── Score computation ─────────────────────────────────────────────────────

    def _activities_for(self, domain: str, target_date: str) -> list[dict]:
        return [
            a for a in self._data.get("activities", [])
            if a["domain"] == domain and a.get("date") == target_date
        ]

    def _compute_score(self, domain: str, target_date: str) -> int:
        acts = self._activities_for(domain, target_date)
        if not acts:
            return _BASELINE
        raw = _SCORERS[domain](acts)
        return max(_BASELINE, raw)   # never below baseline even if formula gives 0

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_today_scores(self) -> dict:
        """Return dict of domain → { score, label, color, target } for today."""
        today = date.today().isoformat()
        return {
            domain: {
                "score":  self._compute_score(domain, today),
                "label":  DOMAINS[domain]["label"],
                "color":  DOMAINS[domain]["color"],
                "target": DOMAINS[domain]["target"],
            }
            for domain in DOMAINS
        }

    def get_weekly_trend(self) -> dict:
        """Return last 7 days of scores per domain. Keys are ISO date strings."""
        trend: dict[str, dict] = {}
        today = date.today()
        for offset in range(6, -1, -1):
            d = (today - timedelta(days=offset)).isoformat()
            trend[d] = {domain: self._compute_score(domain, d) for domain in DOMAINS}
        return trend

    def get_priority_recommendation(self) -> str:
        """Return a specific action for the domain furthest below its target."""
        today  = date.today().isoformat()
        worst_domain  = None
        worst_gap     = -1
        for domain, cfg in DOMAINS.items():
            score = self._compute_score(domain, today)
            gap   = cfg["target"] - score
            if gap > worst_gap:
                worst_gap    = gap
                worst_domain = domain

        if worst_domain is None or worst_gap <= 0:
            return "All domains meeting targets. Maintain momentum, Agent 17."

        _actions = {
            "engineering": "Log a build session or push a commit to close the gap.",
            "programming": "Solve one DSA problem or run a 30-min Claude Code session.",
            "combat":      "Log a workout — even 20 minutes of sparring or conditioning counts.",
            "strategy":    "Play a chess game or log one key decision made today.",
            "neuro":       "Log reading time or a language study block to boost neuro score.",
        }
        label  = DOMAINS[worst_domain]["label"]
        action = _actions.get(worst_domain, "Log any activity for this domain.")
        return f"PRIORITY: {label} is {worst_gap}pts below target. {action}"

    def generate_daily_brief_addendum(self) -> str:
        """Two-sentence domain summary for morning briefing injection."""
        scores = self.get_today_scores()
        priority = self.get_priority_recommendation()

        above = [d for d, v in scores.items() if v["score"] >= v["target"]]
        below = [d for d, v in scores.items() if v["score"] < v["target"]]

        above_labels = ", ".join(DOMAINS[d]["label"].split()[0] for d in above) if above else "none"
        below_labels = ", ".join(DOMAINS[d]["label"].split()[0] for d in below) if below else "none"

        line1 = (
            f"PHANTOM ZERO status: {len(above)} of 5 domains meeting targets "
            f"({above_labels})."
        )
        line2 = priority
        return f"{line1} {line2}"


# ── Singleton ──────────────────────────────────────────────────────────────────

_phantom: PhantomOS | None = None


def get_phantom() -> PhantomOS:
    global _phantom
    if _phantom is None:
        _phantom = PhantomOS()
    return _phantom
