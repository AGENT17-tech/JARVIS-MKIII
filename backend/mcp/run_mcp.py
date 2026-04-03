"""
JARVIS-MKIII — mcp/run_mcp.py
Standalone launcher for the JARVIS MCP server (stdio transport).

Usage:
  python backend/mcp/run_mcp.py

Claude Code integration: see .mcp.json in repo root.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Ensure backend is on sys.path when run as: python backend/mcp/run_mcp.py
_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logging.basicConfig(level=logging.WARNING)


async def _main():
    try:
        from mcp.server.stdio import stdio_server
        from mcp.server import app  # noqa: F401  — triggers build_app()
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Run: pip install mcp", file=sys.stderr)
        sys.exit(1)

    from mcp.server import app as jarvis_app  # type: ignore[attr-defined]
    if jarvis_app is None:
        print("ERROR: mcp package not installed.", file=sys.stderr)
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await jarvis_app.run(
            read_stream,
            write_stream,
            jarvis_app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_main())
