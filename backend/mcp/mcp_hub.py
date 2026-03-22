"""
JARVIS-MKIII — mcp/mcp_hub.py
Pre-configured MCPClient instances + high-level helper functions.

Each function returns a plain string suitable for TTS and HUD display.
"""
from __future__ import annotations
import asyncio, os, re
from mcp.mcp_bridge import MCPClient

# ── Binary paths ──────────────────────────────────────────────────────────────
_NPM_BIN = os.path.expanduser("~/.npm-global/bin")
_FS_BIN  = f"{_NPM_BIN}/mcp-server-filesystem"
_GH_BIN  = f"{_NPM_BIN}/mcp-server-github"

# ── Allowed root for filesystem access ───────────────────────────────────────
_HOME = os.path.expanduser("~")

# ── Lazy singleton clients (created on first use) ─────────────────────────────
_clients: dict[str, MCPClient] = {}


def _get_client(name: str) -> MCPClient:
    """Return (and lazily create) a persistent MCP client by name."""
    if name not in _clients:
        from core.vault import Vault
        v = Vault()

        if name == "filesystem":
            _clients[name] = MCPClient([_FS_BIN, _HOME])

        elif name == "github":
            token = v.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
            _clients[name] = MCPClient(
                [_GH_BIN],
                env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
            )

        else:
            raise ValueError(f"Unknown MCP client: {name!r}")

    return _clients[name]


# ── Filesystem helpers ────────────────────────────────────────────────────────

async def fs_read(path: str) -> str:
    """Read a file and return its content (truncated to 3000 chars for TTS)."""
    client = _get_client("filesystem")
    result = await client.call_tool("read_file", {"path": path})
    if len(result) > 3000:
        result = result[:3000] + "\n… (truncated)"
    return result


async def fs_write(path: str, content: str) -> str:
    """Write content to a file."""
    client = _get_client("filesystem")
    return await client.call_tool("write_file", {"path": path, "content": content})


async def fs_list(path: str) -> str:
    """List directory contents."""
    client = _get_client("filesystem")
    return await client.call_tool("list_directory", {"path": path})


async def fs_search(path: str, pattern: str) -> str:
    """Search files matching a pattern under a path."""
    client = _get_client("filesystem")
    return await client.call_tool("search_files", {"path": path, "pattern": pattern})


async def fs_tree(path: str) -> str:
    """Return a directory tree."""
    client = _get_client("filesystem")
    return await client.call_tool("directory_tree", {"path": path})


# ── DuckDuckGo Search helpers ─────────────────────────────────────────────────

def _ddg_html_scrape(query: str, count: int = 5, news: bool = False) -> list[dict]:
    """
    Scrape DuckDuckGo HTML endpoint — no API key, no package dependency.
    Returns list of {title, snippet, url} dicts.
    """
    import urllib.request
    from bs4 import BeautifulSoup

    search_query = (query + " news") if news else query
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(search_query)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
    )
    html = urllib.request.urlopen(req, timeout=12).read()
    soup = BeautifulSoup(html, "lxml")

    results = []
    for block in soup.select(".result__body")[:count]:
        a     = block.select_one(".result__a")
        snip  = block.select_one(".result__snippet")
        title = a.get_text(separator=" ", strip=True) if a else ""
        href  = a["href"] if a and a.get("href") else ""
        body  = snip.get_text(separator=" ", strip=True) if snip else ""
        # DDG wraps real URLs in a redirect — unwrap uddg= param
        try:
            parsed = urllib.parse.urlparse(href)
            uddg = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            real_url = urllib.parse.unquote(uddg) if uddg else href
            host = urllib.parse.urlparse(real_url).netloc.removeprefix("www.")
        except Exception:
            host = ""
        if title:
            results.append({"title": title, "snippet": body, "source": host, "url": href})
    return results


import urllib.parse   # needed by _ddg_html_scrape


async def ddg_raw(query: str, count: int = 5, news: bool = False) -> list[dict]:
    """Return raw list of {title, snippet, source, url} dicts."""
    try:
        return await asyncio.to_thread(_ddg_html_scrape, query, count, news)
    except Exception:
        return []


async def ddg_search(query: str, count: int = 5) -> str:
    """
    Web search via DuckDuckGo HTML (no API key required).
    Returns a concise summary of top results suitable for TTS.
    """
    try:
        results = await asyncio.to_thread(_ddg_html_scrape, query, count, False)
    except Exception as e:
        return f"Search failed: {e}"

    if not results:
        return "No results found."

    lines = []
    for r in results:
        entry = r["title"]
        if r["snippet"]:
            entry += f": {r['snippet']}"
        lines.append(entry)
    return "\n".join(lines)


async def ddg_news(query: str, count: int = 5) -> str:
    """Latest news headlines via DuckDuckGo News (no API key required)."""
    try:
        results = await asyncio.to_thread(_ddg_html_scrape, query, count, True)
    except Exception as e:
        return f"News search failed: {e}"

    if not results:
        return "No news found."

    lines = []
    for r in results:
        entry = r["title"]
        if r["snippet"]:
            entry += f": {r['snippet'][:120]}"
        lines.append(entry)
    return "\n".join(lines)


# ── GitHub helpers ────────────────────────────────────────────────────────────

async def github_commits(owner: str, repo: str, branch: str = "main", limit: int = 5) -> str:
    """List recent commits on a repo."""
    client = _get_client("github")
    result = await client.call_tool(
        "list_commits",
        {"owner": owner, "repo": repo, "sha": branch, "perPage": limit},
    )
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    return "\n".join(lines[:20]) if lines else "No commits found."


async def github_search_repos(query: str, limit: int = 5) -> str:
    """Search GitHub repositories."""
    client = _get_client("github")
    result = await client.call_tool(
        "search_repositories",
        {"query": query, "perPage": limit},
    )
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    return "\n".join(lines[:20]) if lines else "No repos found."


async def github_get_file(owner: str, repo: str, path: str, branch: str = "main") -> str:
    """Read a file from a GitHub repo."""
    client = _get_client("github")
    result = await client.call_tool(
        "get_file_contents",
        {"owner": owner, "repo": repo, "path": path, "branch": branch},
    )
    return result[:3000] if len(result) > 3000 else result


async def github_list_issues(owner: str, repo: str, state: str = "open", limit: int = 5) -> str:
    """List issues on a GitHub repo."""
    client = _get_client("github")
    return await client.call_tool(
        "list_issues",
        {"owner": owner, "repo": repo, "state": state, "perPage": limit},
    )


async def github_create_issue(owner: str, repo: str, title: str, body: str = "") -> str:
    """Create a GitHub issue."""
    client = _get_client("github")
    return await client.call_tool(
        "create_issue",
        {"owner": owner, "repo": repo, "title": title, "body": body},
    )


# ── Web fetch (httpx-based, replaces server-fetch) ────────────────────────────

async def web_fetch(url: str, max_chars: int = 3000) -> str:
    """
    Fetch a URL and return cleaned text content.
    Uses httpx + BeautifulSoup (same as browser_agent.extract_clean_content).
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                     headers={"User-Agent": "JARVIS-MKIII/3.3"}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        from system.browser_agent import extract_clean_content
        parsed = extract_clean_content(html)
        text   = parsed.get("text", "").strip()
        title  = parsed.get("title", "")

        out = f"# {title}\n\n{text}" if title else text
        return out[:max_chars]
    except Exception as e:
        return f"Fetch failed: {e}"


# ── Shutdown all clients on app exit ─────────────────────────────────────────

async def close_all() -> None:
    """Close all open MCP client processes. Call on app shutdown."""
    for client in list(_clients.values()):
        try:
            await client.close()
        except Exception:
            pass
    _clients.clear()
