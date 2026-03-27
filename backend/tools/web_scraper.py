"""
JARVIS-MKIII — tools/web_scraper.py
Web scraping: BeautifulSoup (static) and Selenium (dynamic/JS pages).
Registered automatically into sandbox on import.
"""
from __future__ import annotations
import asyncio, json
from tools.sandbox import sandbox, ToolResult


def _clean_text(soup) -> str:
    for tag in soup(["script", "style", "head", "nav", "footer"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())[:8000]


async def scrape_bs4(url: str, selector: str | None = None) -> dict:
    import requests
    from bs4 import BeautifulSoup
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup  = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title else ""
    if selector:
        elements = soup.select(selector)
        content  = " ".join(e.get_text(separator=" ").strip() for e in elements)[:8000]
    else:
        content = _clean_text(soup)
    links = [a.get("href", "") for a in soup.find_all("a", href=True)][:20]
    return {"url": url, "title": title, "content": content, "links": links}


async def scrape_selenium(url: str, selector: str | None = None, wait_seconds: int = 3) -> dict:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.common.by import By
    from bs4 import BeautifulSoup
    import time

    def _run() -> dict:
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        service = Service(ChromeDriverManager().install())
        driver  = webdriver.Chrome(service=service, options=opts)
        try:
            driver.get(url)
            time.sleep(wait_seconds)
            title = driver.title or ""
            if selector:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    content  = " ".join(e.text for e in elements)[:8000]
                except Exception:
                    content = driver.page_source[:4000]
            else:
                soup    = BeautifulSoup(driver.page_source, "html.parser")
                content = _clean_text(soup)
            links = [
                a.get_attribute("href")
                for a in driver.find_elements(By.TAG_NAME, "a")
                if a.get_attribute("href")
            ][:20]
            return {"url": url, "title": title, "content": content, "links": links}
        finally:
            driver.quit()

    return await asyncio.to_thread(_run)


async def scrape(url: str, selector: str | None = None, dynamic: bool = False) -> dict:
    """Auto-select engine. dynamic=True forces Selenium."""
    if dynamic:
        return await scrape_selenium(url, selector)
    try:
        return await scrape_bs4(url, selector)
    except Exception:
        return await scrape_selenium(url, selector)


@sandbox.register(name="scrape_url")
async def tool_scrape_url(args: dict) -> ToolResult:
    url      = args.get("url", "")
    selector = args.get("selector")
    if not url:
        return ToolResult(False, "", "scrape_url", "No URL provided.")
    try:
        data = await scrape(url, selector, dynamic=False)
        return ToolResult(True, json.dumps(data, ensure_ascii=False), "scrape_url")
    except Exception as e:
        return ToolResult(False, "", "scrape_url", str(e))


@sandbox.register(name="scrape_dynamic")
async def tool_scrape_dynamic(args: dict) -> ToolResult:
    url      = args.get("url", "")
    selector = args.get("selector")
    wait     = int(args.get("wait_seconds", 3))
    if not url:
        return ToolResult(False, "", "scrape_dynamic", "No URL provided.")
    try:
        data = await scrape_selenium(url, selector, wait_seconds=wait)
        return ToolResult(True, json.dumps(data, ensure_ascii=False), "scrape_dynamic")
    except Exception as e:
        return ToolResult(False, "", "scrape_dynamic", str(e))
