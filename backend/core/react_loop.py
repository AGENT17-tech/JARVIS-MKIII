"""
JARVIS-MKIII — react_loop.py
Observe → Think → Act reasoning loop for tool-using tasks.

Usage:
    result = await react(prompt, tools=sandbox, llm_call=_call_groq_fn)

The loop drives the LLM to emit structured Action lines which the loop
executes via the Sandbox, feeding results back as Observations.  It
terminates when the LLM emits "Final Answer:" or MAX_ITERATIONS is hit.
"""

from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

_ACTION_RE     = re.compile(r"Action:\s*(\w+)\[(.+?)\]", re.DOTALL)
_FINAL_RE      = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)


async def react(
    prompt:   str,
    tools,              # Sandbox instance (has .run())
    llm_call,           # async callable(messages: list[dict]) -> str
) -> str:
    """
    Run the ReAct loop.

    `llm_call` receives the full message history and must return a string.
    `tools` is a Sandbox; tool names are parsed from Action lines.
    Returns the final answer string.
    """
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are a reasoning agent. For each step, think, then emit exactly one of:\n"
                "  Action: tool_name[{\"arg\": \"value\"}]\n"
                "  Final Answer: your answer here\n"
                "Never skip the Final Answer once you have enough information."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    last_response = ""
    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.debug("[REACT] Iteration %d/%d", iteration, MAX_ITERATIONS)
        response = await llm_call(messages)
        last_response = response
        logger.debug("[REACT] LLM response: %s", response[:200])

        # Check for final answer first
        final_match = _FINAL_RE.search(response)
        if final_match:
            answer = final_match.group(1).strip()
            logger.debug("[REACT] Final answer on iteration %d: %s", iteration, answer[:120])
            return answer

        # Check for action call
        action_match = _ACTION_RE.search(response)
        if action_match:
            tool_name = action_match.group(1).strip()
            args_raw  = action_match.group(2).strip()
            try:
                import json as _json
                args = _json.loads(args_raw)
            except Exception:
                args = {"input": args_raw}

            logger.debug("[REACT] Action: %s | args: %s", tool_name, args)
            result = await tools.run(tool_name, args, auto_confirm=True)
            observation = result.output if result.success else f"Error: {result.error}"
            logger.debug("[REACT] Observation: %s", observation[:200])

            # Append assistant turn + observation turn
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"Observation: {observation}"})
        else:
            # No action, no final answer — treat whole response as final
            logger.debug("[REACT] No structured output on iteration %d — returning as-is", iteration)
            return response

    logger.warning("[REACT] Max iterations (%d) reached without Final Answer", MAX_ITERATIONS)
    return last_response
