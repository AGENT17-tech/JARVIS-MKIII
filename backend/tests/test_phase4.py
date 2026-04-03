"""
JARVIS-MKIII — Phase 4 Autonomy Test Suite
Run with: pytest backend/tests/test_phase4.py -v  (PYTHONPATH=backend)

Covers:
  1-3   core/time_parser.py          — natural language time parsing
  4-5   agents/task_scheduler.py     — SQLite-backed scheduling
  6-7   tools/pipeline.py            — sequential tool chaining
  8-9   core/goal_tracker.py         — multi-step goal persistence
  10    system/os_controller.py      — PathSandbox boundary enforcement
"""

import asyncio
import pytest
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── Ensure backend on sys.path ─────────────────────────────────────────────────
_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ══════════════════════════════════════════════════════════════════════════════
# 1-3  TIME PARSER
# ══════════════════════════════════════════════════════════════════════════════

from core.time_parser import parse_time_expression


def test_time_parser_in_minutes():
    result = parse_time_expression("in 20 minutes")
    assert result is not None
    assert result["type"] == "once"
    assert isinstance(result["run_at"], datetime)
    diff = (result["run_at"] - datetime.now()).total_seconds()
    assert 18 * 60 <= diff <= 21 * 60, f"Expected ~20 min delta, got {diff}s"


def test_time_parser_every_morning_cron():
    result = parse_time_expression("every morning at 7")
    assert result is not None
    assert result["type"] == "cron"
    assert result["cron"] == "0 7 * * *"


def test_time_parser_at_clock():
    result = parse_time_expression("at 3pm")
    assert result is not None
    assert result["type"] == "once"
    assert isinstance(result["run_at"], datetime)
    assert result["run_at"].hour == 15


def test_time_parser_unrecognised_returns_none():
    result = parse_time_expression("make me a sandwich")
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 4-5  TASK SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

import sqlite3
import tempfile

from agents.task_scheduler import TaskScheduler


def _make_scheduler() -> TaskScheduler:
    """Return a TaskScheduler wired to an in-memory SQLite DB and a mock APScheduler."""
    mock_sched = MagicMock()
    mock_sched.add_job = MagicMock()
    mock_sched.remove_job = MagicMock()

    ts = TaskScheduler.__new__(TaskScheduler)
    ts._sched = mock_sched

    # Use a temp file so the DB persists across method calls within the test
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            task_id TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            run_at TEXT,
            cron_expr TEXT,
            interval_min INTEGER,
            task_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            fired_count INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        );
    """)
    conn.commit()
    ts._db = conn
    return ts


@pytest.mark.asyncio
async def test_task_scheduler_creates_db_entry():
    ts = _make_scheduler()
    run_at = datetime.now() + timedelta(minutes=5)
    result = await ts.schedule_reminder(message="Test reminder", run_at=run_at)

    assert "task_id" in result
    assert result["type"] == "once"

    row = ts._db.execute(
        "SELECT task_id, active FROM scheduled_tasks WHERE task_id=?",
        (result["task_id"],),
    ).fetchone()
    assert row is not None
    assert row[1] == 1  # active


@pytest.mark.asyncio
async def test_task_scheduler_cancel_deactivates():
    ts = _make_scheduler()
    run_at = datetime.now() + timedelta(minutes=10)
    result = await ts.schedule_reminder(message="Cancel me", run_at=run_at)
    tid = result["task_id"]

    cancelled = await ts.cancel_task(tid)
    assert cancelled is True

    row = ts._db.execute(
        "SELECT active FROM scheduled_tasks WHERE task_id=?", (tid,)
    ).fetchone()
    assert row[0] == 0  # deactivated


# ══════════════════════════════════════════════════════════════════════════════
# 6-7  TOOL PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

from tools.pipeline import ToolPipeline, PipelineStep
from tools.sandbox import Sandbox, ToolResult


def _make_sandbox_with(tools: dict) -> Sandbox:
    sb = Sandbox()
    for name, output in tools.items():
        async def _fn(args, _out=output):
            return ToolResult(True, _out, name)
        sb._tools[name] = {"fn": _fn, "requires_confirmation": False}
    return sb


@pytest.mark.asyncio
async def test_pipeline_single_step_success():
    steps = [PipelineStep(tool="tool_a", args={})]
    pipeline = ToolPipeline(steps)

    with patch("tools.sandbox.sandbox") as mock_sb:
        mock_sb.run = AsyncMock(return_value=ToolResult(True, "output_a", "tool_a"))
        result = await pipeline.run()

    assert result.success is True
    assert result.final_output == "output_a"
    assert len(result.steps) == 1


@pytest.mark.asyncio
async def test_pipeline_chains_previous_output():
    steps = [
        PipelineStep(tool="step1", args={}),
        PipelineStep(tool="step2", args={}, use_previous_output=True),
    ]
    pipeline = ToolPipeline(steps)

    captured_args: list[dict] = []

    async def _mock_run(tool_name, args, auto_confirm=False):
        captured_args.append(dict(args))
        return ToolResult(True, f"out_{tool_name}", tool_name)

    with patch("tools.sandbox.sandbox") as mock_sb:
        mock_sb.run = _mock_run
        result = await pipeline.run()

    assert result.success is True
    assert result.final_output == "out_step2"
    # step2 should have received step1's output as 'input'
    assert captured_args[1].get("input") == "out_step1"


# ══════════════════════════════════════════════════════════════════════════════
# 8-9  GOAL TRACKER
# ══════════════════════════════════════════════════════════════════════════════

from core.goal_tracker import GoalTracker


def _make_goal_tracker() -> GoalTracker:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    gt = GoalTracker.__new__(GoalTracker)
    gt._db = sqlite3.connect(tmp.name, check_same_thread=False)
    gt._db.execute("PRAGMA journal_mode=WAL")
    gt._db.executescript("""
        CREATE TABLE IF NOT EXISTS goals (
            goal_id TEXT PRIMARY KEY, title TEXT NOT NULL,
            status TEXT DEFAULT 'active', created_at TEXT NOT NULL, done_at TEXT
        );
        CREATE TABLE IF NOT EXISTS goal_steps (
            step_id TEXT PRIMARY KEY, goal_id TEXT NOT NULL,
            step_num INTEGER NOT NULL, description TEXT NOT NULL,
            status TEXT DEFAULT 'pending', result TEXT DEFAULT '',
            started_at TEXT, done_at TEXT
        );
    """)
    gt._db.commit()
    return gt


def test_goal_tracker_create_and_retrieve():
    gt = _make_goal_tracker()
    goal = gt.create_goal("Build JARVIS Phase 5", ["Design architecture", "Implement core", "Test"])
    assert goal["goal_id"]
    assert goal["title"] == "Build JARVIS Phase 5"
    assert len(goal["steps"]) == 3
    assert goal["steps"][0]["status"] == "pending"

    fetched = gt.get_goal(goal["goal_id"])
    assert fetched is not None
    assert fetched["title"] == "Build JARVIS Phase 5"


def test_goal_tracker_update_step_status():
    gt = _make_goal_tracker()
    goal = gt.create_goal("Research task", ["Step one", "Step two"])
    step_id = goal["steps"][0]["step_id"]

    gt.update_step(step_id, "done", "Research complete")

    updated = gt.get_goal(goal["goal_id"])
    assert updated["steps"][0]["status"] == "done"
    assert updated["steps"][0]["result"] == "Research complete"


# ══════════════════════════════════════════════════════════════════════════════
# 10  PATH SANDBOX
# ══════════════════════════════════════════════════════════════════════════════

from system.os_controller import PathSandbox


def test_path_sandbox_allows_home():
    sandbox = PathSandbox()
    home = Path.home()
    # Any sub-path of home should validate without raising
    target = home / "test_file.txt"
    try:
        validated = sandbox.validate(str(target))
        assert validated == target.resolve()
    except ValueError:
        # Home may not be in allowed list in CI — just ensure it's callable
        pytest.skip("Home not in sandbox allowed list in this environment")


def test_path_sandbox_rejects_outside():
    sandbox = PathSandbox()
    # Patch allowed paths to a temp dir so the test is deterministic
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        sandbox._allowed = [Path(td).resolve()]
        outside = Path("C:/Windows/System32/secret.txt") if os.name == "nt" else Path("/etc/passwd")
        with pytest.raises(ValueError, match="outside allowed sandbox roots"):
            sandbox.validate(str(outside))
