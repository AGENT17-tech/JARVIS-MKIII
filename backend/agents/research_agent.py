"""
JARVIS-MKIII — agents/research_agent.py
Deep web research agent: searches, reads full page content, synthesises
a structured intelligence briefing.
"""
from __future__ import annotations
import re
from agents.agent_base import AgentBase

# Domains that return no useful readable content
_SKIP_DOMAINS = {"reddit.com", "quora.com", "pinterest.com", "youtube.com"}

_SYNTHESIS_SYSTEM = (
    "You are JARVIS, an elite intelligence analyst. "
    "Synthesize the following sources into a precise intelligence briefing. "
    "Structure your response as:\n\n"
    "SUMMARY: One sentence bottom line up front.\n\n"
    "KEY FINDINGS:\n"
    "- Finding 1 (cite source number)\n"
    "- Finding 2 (cite source number)\n"
    "- Finding 3 (cite source number)\n"
    "[3-5 bullet points max]\n\n"
    "ASSESSMENT: 2-3 sentences of analytical judgment — "
    "what this means, what to watch, what is uncertain.\n\n"
    "SOURCES: List URLs used.\n\n"
    "Be precise. No filler. No hedging. Speak like a cleared analyst."
)


def _extract_urls(text: str) -> list[str]:
    raw = re.findall(r"https?://[^\s,)\"'>]+", text)
    return [u.rstrip(".,)\"'") for u in raw]


def _is_skip_domain(url: str) -> bool:
    for domain in _SKIP_DOMAINS:
        if domain in url:
            return True
    return False


def _voice_summary(briefing: str) -> str:
    """Extract SUMMARY line + first 2 KEY FINDINGS, keep under 40 words."""
    summary_line = ""
    m = re.search(r"SUMMARY:\s*(.+)", briefing)
    if m:
        summary_line = m.group(1).strip()

    findings = re.findall(r"-\s+(.+)", briefing)
    parts = [summary_line] + findings[:2]
    text = " ".join(p.rstrip(".") for p in parts if p)

    # Hard cap at 40 words
    words = text.split()
    if len(words) > 40:
        text = " ".join(words[:40]) + "."
    return text


class ResearchAgent(AgentBase):
    def __init__(self):
        super().__init__("RESEARCH")

    async def run_task(self, task: str) -> str:
        from system.browser_agent import browser

        # ── Step 1: Search ────────────────────────────────────────────────────
        await self.push_update(f"Searching: {task}")
        search_result = await browser.search_web(task)

        # Fallback to DuckDuckGo if browser search fails
        if not search_result["success"]:
            await self.push_update("Browser search unavailable — falling back to DuckDuckGo...")
            try:
                from mcp.mcp_hub import ddg_search
                ddg_text = await ddg_search(task, count=8)
                search_result = {"success": True, "result": ddg_text}
            except Exception as e:
                raise RuntimeError(f"All search methods failed: {e}")

        # Extract and filter URLs
        all_urls  = _extract_urls(search_result["result"])
        filtered  = [u for u in all_urls if not _is_skip_domain(u)]
        urls      = filtered[:3] if filtered else all_urls[:3]

        if not urls:
            raise RuntimeError("No usable URLs found in search results.")

        await self.push_update(f"Found {len(urls)} source(s) to analyse...")

        # ── Step 2: Extract full page content ─────────────────────────────────
        sources: list[str] = []
        for i, url in enumerate(urls, 1):
            await self.push_update(f"Reading source {i}/{len(urls)}: {url[:60]}...")
            page = await browser.get_page_content(url)
            if not page["success"]:
                continue
            content = page["result"].strip()
            if len(content) < 200:
                continue                         # skip stub/redirect pages
            content = content[:3000]
            sources.append(f"SOURCE {i}: {url}\n{content}")

        if not sources:
            raise RuntimeError("All sources returned insufficient content.")

        await self.push_update(f"Synthesising briefing from {len(sources)} source(s)...")

        # ── Step 3: Synthesise ─────────────────────────────────────────────────
        combined = "\n\n---\n\n".join(sources)
        prompt   = f'Research query: "{task}"\n\n{combined}'

        briefing = await self._llm(
            prompt=prompt,
            system=_SYNTHESIS_SYSTEM,
            max_tokens=900,
        )

        # ── Step 4: Voice summary (SUMMARY + first 2 findings, ≤40 words) ─────
        self.summary = _voice_summary(briefing)

        return briefing
