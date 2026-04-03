"""
JARVIS-MKIII — tools/pipeline.py
Sequential tool chaining: each step can consume the previous step's output.

Preset pipelines are defined in config.settings.PIPELINES.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PipelineStep:
    tool:                str
    args:                dict = field(default_factory=dict)
    use_previous_output: bool = False


@dataclass
class PipelineResult:
    success:      bool
    steps:        list[dict]
    final_output: str
    error:        str = ""


class ToolPipeline:
    """Run a sequence of sandbox tools, optionally chaining outputs between steps."""

    def __init__(self, steps: list[PipelineStep]):
        self.steps = steps

    async def run(self) -> PipelineResult:
        from tools.sandbox import sandbox

        step_results: list[dict] = []
        last_output = ""

        for i, step in enumerate(self.steps):
            args = dict(step.args)
            if step.use_previous_output and last_output:
                args["input"] = last_output

            logger.info(
                "[PIPELINE] Step %d/%d: %s | use_prev=%s",
                i + 1, len(self.steps), step.tool, step.use_previous_output,
            )
            result = await sandbox.run(step.tool, args, auto_confirm=True)

            step_results.append({
                "step":    i + 1,
                "tool":    step.tool,
                "success": result.success,
                "output":  result.output,
                "error":   result.error,
            })

            if not result.success:
                logger.warning("[PIPELINE] Step %d failed: %s", i + 1, result.error)
                return PipelineResult(
                    success=False,
                    steps=step_results,
                    final_output=last_output,
                    error=f"Step {i + 1} ({step.tool}) failed: {result.error}",
                )

            last_output = result.output

        return PipelineResult(success=True, steps=step_results, final_output=last_output)


def pipeline_from_config(name: str) -> ToolPipeline | None:
    """Build a ToolPipeline from a named preset in settings.PIPELINES."""
    try:
        from config.settings import PIPELINES
        cfg = PIPELINES.get(name)
        if not cfg:
            return None
        steps = [
            PipelineStep(
                tool=s["tool"],
                args=s.get("args", {}),
                use_previous_output=s.get("use_previous_output", False),
            )
            for s in cfg
        ]
        return ToolPipeline(steps)
    except Exception as exc:
        logger.warning("[PIPELINE] Could not load pipeline %r: %s", name, exc)
        return None
