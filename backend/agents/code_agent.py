"""
JARVIS-MKIII — agents/code_agent.py
Writes and optionally executes Python code. Iterates up to 3 times on failure.
"""
from __future__ import annotations
import asyncio, pathlib, re, subprocess, time

_WORKSPACE = pathlib.Path.home() / "JARVIS_MKIII" / "agent_workspace"
_WORKSPACE.mkdir(parents=True, exist_ok=True)

from agents.agent_base import AgentBase


class CodeAgent(AgentBase):
    def __init__(self):
        super().__init__("CODE")

    async def run_task(self, task: str) -> str:
        execute_code = "run it" in task.lower() or "execute it" in task.lower()

        await self.push_update("Writing code...")

        # ── Step 1: Generate code ─────────────────────────────────────────────
        code_prompt = (
            f"Task: {task}\n\n"
            "Write complete, working Python 3 code for this task. "
            "Return ONLY the code inside a single ```python ... ``` block. "
            "No explanation outside the code block."
        )
        response = await self._llm(
            prompt=code_prompt,
            system=(
                "You are a JARVIS code-writing engine. "
                "Write clean, complete, executable Python 3. "
                "Always include all necessary imports. "
                "Return code in a single ```python block."
            ),
            max_tokens=1200,
        )
        code = self._extract_code(response)
        if not code:
            raise RuntimeError("LLM did not return a code block.")

        # ── Step 2: Save to workspace ─────────────────────────────────────────
        safe_name = re.sub(r"[^\w]", "_", task[:40]).strip("_")
        fname     = _WORKSPACE / f"{safe_name}_{int(time.time())}.py"
        fname.write_text(code)
        await self.push_update(f"Saved to {fname}")

        if not execute_code:
            self.summary = f"Code written and saved to {fname.name}, sir."
            return f"```python\n{code}\n```\n\nSaved to: {fname}"

        # ── Step 3: Execute (up to 3 attempts) ───────────────────────────────
        output, error = "", ""
        for attempt in range(1, 4):
            await self.push_update(f"Executing (attempt {attempt}/3)...")
            proc = await asyncio.create_subprocess_exec(
                "python3", str(fname),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_WORKSPACE),
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                error = "Execution timed out after 30 seconds."
                break

            output = stdout_b.decode(errors="replace")[:1000]
            error  = stderr_b.decode(errors="replace")[:500]

            if proc.returncode == 0:
                self.summary = f"Code written and executed successfully, sir. Output: {output[:80]}"
                return (
                    f"```python\n{code}\n```\n\n"
                    f"**Execution output:**\n```\n{output}\n```\n"
                    f"Saved to: {fname}"
                )

            if attempt < 3:
                await self.push_update(f"Attempt {attempt} failed. Debugging...")
                debug_prompt = (
                    f"This Python code failed with the following error:\n\n"
                    f"```\n{error}\n```\n\n"
                    f"Original code:\n```python\n{code}\n```\n\n"
                    "Fix the bug and return the corrected code in a ```python block."
                )
                debug_response = await self._llm(
                    prompt=debug_prompt,
                    system="You are a Python debugger. Fix the code and return it in a ```python block.",
                    max_tokens=1200,
                )
                new_code = self._extract_code(debug_response)
                if new_code:
                    code = new_code
                    fname.write_text(code)

        raise RuntimeError(
            f"Execution failed after 3 attempts.\n"
            f"Last error:\n{error}\n\n"
            f"Code:\n```python\n{code}\n```"
        )

    @staticmethod
    def _extract_code(text: str) -> str:
        m = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Fallback: any code block
        m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        return m.group(1).strip() if m else ""
