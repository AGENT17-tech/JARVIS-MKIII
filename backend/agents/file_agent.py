"""
JARVIS-MKIII — agents/file_agent.py
Organises, searches, or manages files by natural language instruction.
Always previews changes before executing destructive operations.
"""
from __future__ import annotations
import asyncio, json, re
from agents.agent_base import AgentBase


class FileAgent(AgentBase):
    def __init__(self):
        super().__init__("FILE-OPS")
        self._pending_ops: list[dict] | None = None

    async def run_task(self, task: str) -> str:
        await self.push_update(f"Analysing file task: {task}")

        # ── Step 1: Let LLM decide what operations to perform ─────────────────
        plan_prompt = (
            f"File management task: {task}\n\n"
            "Generate a JSON array of file operations to complete this task.\n"
            "Each operation is an object with:\n"
            '  "op": one of: list_directory, search_files, create_file, '
            "create_directory, move, copy, delete, read_file\n"
            '  "args": dict of arguments\n'
            "Use ~ for home directory. Be precise with paths.\n"
            "If the task is read-only (list, search, read), execute immediately.\n"
            "If any operation is destructive (delete, move), mark it "
            'with "destructive": true.\n'
            "Return ONLY a JSON array."
        )
        plan_response = await self._llm(
            prompt=plan_prompt,
            system=(
                "You are a JARVIS file-operation planner. "
                "Output a JSON array of file operations. No explanation."
            ),
            max_tokens=512,
        )
        ops = self._parse_ops(plan_response)
        if not ops:
            raise RuntimeError("Could not parse file operation plan.")

        # ── Step 2: Preview destructive ops ──────────────────────────────────
        destructive = [o for o in ops if o.get("destructive")]
        if destructive:
            preview_lines = []
            for o in destructive:
                args_str = ", ".join(f"{k}={v}" for k, v in o.get("args", {}).items())
                preview_lines.append(f"  {o['op']}({args_str})")
            preview = "\n".join(preview_lines)
            await self.push_update(
                f"Preview — {len(destructive)} destructive operation(s) planned:\n{preview}\n"
                "Awaiting confirmation, sir."
            )
            # Store for confirmation — dispatcher will handle yes/no
            self._pending_ops = ops
            self.summary = f"Previewed {len(ops)} operation(s). Awaiting your confirmation, sir."
            return (
                f"I will perform {len(ops)} operation(s), sir. "
                f"Destructive steps:\n{preview}\n\nShall I proceed?"
            )

        # ── Step 3: Execute read-only ops immediately ─────────────────────────
        return await self._execute_ops(ops)

    async def confirm_and_execute(self) -> str:
        """Called when user confirms destructive preview."""
        if not self._pending_ops:
            return "No pending operations, sir."
        ops = self._pending_ops
        self._pending_ops = None
        return await self._execute_ops(ops)

    async def _execute_ops(self, ops: list[dict]) -> str:
        import system.os_controller as osc
        import asyncio

        log = []
        for op in ops:
            name = op.get("op", "")
            args = op.get("args", {}) or {}
            await self.push_update(f"Executing {name}({', '.join(str(v) for v in args.values())})")
            fn = getattr(osc, name, None)
            if fn is None:
                log.append(f"⚠ Unknown op: {name}")
                continue
            result = await asyncio.to_thread(fn, **args)
            if result["success"]:
                log.append(f"✓ {name}: {result['result']}")
            else:
                log.append(f"✗ {name}: {result['error']}")

        summary = f"Completed {len(ops)} file operation(s)."
        self.summary = summary
        return summary + "\n\n" + "\n".join(log)

    @staticmethod
    def _parse_ops(text: str) -> list[dict]:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return []
        try:
            return json.loads(m.group())
        except Exception:
            return []
