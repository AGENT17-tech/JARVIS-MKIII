"""
JARVIS-MKIII — system/browser_agent.py
Dual-engine browser: Playwright (fast, headless) + Selenium (JS-heavy fallback).
BeautifulSoup4 parses all extracted content for clean, readable text.
"""
from __future__ import annotations
import asyncio, pathlib, re, time
import logging

_SCREENSHOT_DIR = pathlib.Path.home() / "JARVIS_MKIII" / "screenshots"
_R = lambda ok, result="", error="": {"success": ok, "result": result, "error": error}


# ── BeautifulSoup content extractor ───────────────────────────────────────────


logger = logging.getLogger(__name__)
def extract_clean_content(html: str) -> dict:
    """
    Parse raw HTML with BS4.
    Removes noise, extracts main text, title, meta description, links, tables.
    Text is capped at 4000 chars.
    Returns: {text, title, description, links, tables}
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Strip non-content tags
    for tag in soup.find_all(["script", "style", "nav", "footer",
                               "header", "aside", "noscript", "form"]):
        tag.decompose()

    # Title
    title = soup.title.get_text(strip=True) if soup.title else ""

    # Meta description
    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    description = (meta.get("content") or "").strip() if meta else ""

    # Main content — prefer semantic containers
    main = (
        soup.find("article") or
        soup.find("main") or
        soup.find(attrs={"role": "main"}) or
        soup.find(class_=re.compile(r"\bcontent\b", re.I)) or
        soup.find(id=re.compile(r"\bcontent\b", re.I)) or
        soup.body
    )

    if main:
        blocks = main.find_all(["p", "h1", "h2", "h3", "h4", "li", "td", "th", "blockquote"])
        text = " ".join(b.get_text(separator=" ", strip=True) for b in blocks)
        if len(text.strip()) < 100:
            text = main.get_text(separator=" ", strip=True)
    else:
        text = soup.get_text(separator=" ", strip=True)

    text = re.sub(r"\s+", " ", text).strip()[:4000]

    # All absolute links
    links = [
        {"text": a.get_text(strip=True)[:80], "href": a["href"]}
        for a in soup.find_all("a", href=True)
        if str(a.get("href", "")).startswith("http")
    ][:50]

    # First data table as list-of-dicts
    tables = []
    for tbl in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
        rows = []
        for tr in tbl.find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cols:
                rows.append(dict(zip(headers, cols)) if headers else cols)
        if rows:
            tables.append(rows)
            break  # first table only

    return {"text": text, "title": title, "description": description,
            "links": links, "tables": tables}


# ── Selenium helper (sync, run in thread) ─────────────────────────────────────

def _selenium_fetch_sync(url: str) -> str:
    """Fetch raw HTML via Selenium headless Chromium. Returns HTML string."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    from config.settings import BROWSER_CFG

    opts = Options()
    if BROWSER_CFG.headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=opts)
    try:
        driver.set_page_load_timeout(BROWSER_CFG.page_load_timeout_s)
        driver.implicitly_wait(BROWSER_CFG.implicit_wait_s)
        logger.info("[BROWSER] Selenium fetching: %s", url)
        driver.get(url)
        time.sleep(1)  # allow JS to settle
        return driver.page_source
    except TimeoutException:
        logger.warning("[BROWSER] Selenium page load timed out for %s", url)
        raise
    except WebDriverException as exc:
        logger.warning("[BROWSER] Selenium WebDriver error for %s: %s", url, exc)
        raise
    finally:
        driver.quit()


# ── BrowserAgent ──────────────────────────────────────────────────────────────

class BrowserAgent:
    """Dual-engine browser session (Playwright primary, Selenium fallback)."""

    def __init__(self):
        self._pw       = None
        self._browser  = None
        self._page     = None
        try:
            from config.settings import BROWSER_CFG
            self._headless = BROWSER_CFG.headless
        except Exception:
            self._headless = True
        self._lock     = asyncio.Lock()

    # ── Playwright init ───────────────────────────────────────────────────────

    async def _ensure(self):
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. "
                "Run: pip install playwright && playwright install chromium"
            )
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()

    async def set_headed(self, headed: bool):
        self._headless = not headed
        if self._browser:
            await self._browser.close()
            self._browser = None
        self._page = None

    # ── Engine B: Selenium ────────────────────────────────────────────────────

    async def fetch_with_selenium(self, url: str) -> dict:
        """Fetch raw HTML via Selenium (async wrapper around sync driver)."""
        try:
            html = await asyncio.to_thread(_selenium_fetch_sync, url)
            return _R(True, html)
        except Exception as e:
            return _R(False, error=f"Selenium: {e}")

    # ── BS4 parsing ───────────────────────────────────────────────────────────

    async def fetch_with_bs4(self, html: str) -> dict:
        """Parse raw HTML string through BS4. Returns _R with clean text."""
        try:
            parsed = await asyncio.to_thread(extract_clean_content, html)
            return _R(True, parsed["text"])
        except Exception as e:
            return _R(False, error=f"BS4: {e}")

    # ── Smart fetch: Playwright → Selenium → BS4 ──────────────────────────────

    async def smart_fetch(self, url: str) -> dict:
        """
        Try Playwright first.
        Fall back to Selenium if content is sparse or JS-blocked.
        Always parse final HTML through BS4.
        Returns dict with text in 'result' and full parsed dict in 'parsed'.
        """
        html = None

        # --- Try Playwright ---
        async with self._lock:
            try:
                await self._ensure()
                await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
                html = await self._page.content()
            except Exception as pw_err:
                logger.error(f"[BROWSER] Playwright failed for {url}: {pw_err}")

        # Check if Playwright gave usable content
        need_selenium = False
        if html:
            snippet = html.lower()
            if len(html) < 1000 or "enable javascript" in snippet or "please enable" in snippet:
                need_selenium = True
        else:
            need_selenium = True

        # --- Selenium fallback ---
        if need_selenium:
            logger.info(f"[BROWSER] Falling back to Selenium for {url}")
            sel = await self.fetch_with_selenium(url)
            if sel["success"]:
                html = sel["result"]
            elif not html:
                return _R(False, error=f"Both engines failed for {url}")

        # --- Parse through BS4 ---
        try:
            parsed = await asyncio.to_thread(extract_clean_content, html)
            return {"success": True, "result": parsed["text"], "parsed": parsed, "error": ""}
        except Exception as e:
            return _R(False, error=f"BS4 parse failed: {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    async def open_url(self, url: str) -> dict:
        async with self._lock:
            try:
                await self._ensure()
                await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
                title = await self._page.title()
                return _R(True, f"Opened: {title}  ({url})")
            except Exception as e:
                return _R(False, error=str(e))

    async def search_web(self, query: str) -> dict:
        async with self._lock:
            try:
                await self._ensure()
                encoded = query.replace(" ", "+")
                await self._page.goto(
                    f"https://www.google.com/search?q={encoded}",
                    wait_until="domcontentloaded", timeout=20000,
                )
                results = await self._page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('div.g');
                        const out = [];
                        for (const item of items) {
                            const a = item.querySelector('a[href]');
                            const h3 = item.querySelector('h3');
                            if (a && h3 && out.length < 8) {
                                out.push({ title: h3.innerText, url: a.href });
                            }
                        }
                        return out;
                    }
                """)
                if not results:
                    return _R(True, "Search returned no results.")
                lines = [f"{i+1}. {r['title']}\n   {r['url']}" for i, r in enumerate(results)]
                return _R(True, "\n".join(lines))
            except Exception as e:
                return _R(False, error=str(e))

    async def get_page_content(self, url: str) -> dict:
        """Fetch page using smart_fetch (Playwright → Selenium → BS4)."""
        result = await self.smart_fetch(url)
        if result["success"]:
            return _R(True, result["result"])
        return _R(False, error=result["error"])

    async def extract_table(self, url: str) -> dict:
        """Return first data table on page as list of dicts (JSON string)."""
        fetched = await self.smart_fetch(url)
        if not fetched["success"]:
            return _R(False, error=fetched["error"])
        tables = fetched.get("parsed", {}).get("tables", [])
        if not tables:
            return _R(True, "No data tables found on this page.")
        import json
        return _R(True, json.dumps(tables[0], ensure_ascii=False))

    async def extract_links(self, url: str) -> dict:
        """Return all absolute href links from page."""
        fetched = await self.smart_fetch(url)
        if not fetched["success"]:
            return _R(False, error=fetched["error"])
        links = fetched.get("parsed", {}).get("links", [])
        if not links:
            return _R(True, "No links found.")
        lines = [f"{lk['href']}  [{lk['text']}]" for lk in links]
        return _R(True, "\n".join(lines))

    async def login_and_fetch(
        self,
        url: str,
        username: str,
        password: str,
        username_selector: str = 'input[type="email"],input[name*="user" i],input[name*="email" i]',
        password_selector: str = 'input[type="password"]',
    ) -> dict:
        """
        Selenium-based login flow.
        Fills credentials, submits, waits for navigation, returns page content.
        """
        def _sync():
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            driver = webdriver.Chrome(options=opts)
            try:
                driver.get(url)
                wait = WebDriverWait(driver, 10)
                u_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, username_selector))
                )
                u_field.clear()
                u_field.send_keys(username)
                p_field = driver.find_element(By.CSS_SELECTOR, password_selector)
                p_field.clear()
                p_field.send_keys(password)
                p_field.submit()
                time.sleep(3)
                return driver.page_source
            finally:
                driver.quit()

        try:
            html   = await asyncio.to_thread(_sync)
            parsed = await asyncio.to_thread(extract_clean_content, html)
            return _R(True, parsed["text"])
        except Exception as e:
            return _R(False, error=str(e))

    async def download_file(self, url: str, dest_path: str) -> dict:
        try:
            import httpx, pathlib as _pl
            dest = _pl.Path(dest_path).expanduser()
            dest.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(url)
                dest.write_bytes(response.content)
            return _R(True, f"Downloaded to {dest} ({len(response.content)} bytes)")
        except Exception as e:
            return _R(False, error=str(e))

    async def fill_form(self, url: str, fields: dict) -> dict:
        async with self._lock:
            try:
                await self._ensure()
                await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
                for label, value in fields.items():
                    selector = (
                        f'input[placeholder*="{label}" i],'
                        f'input[name*="{label}" i],'
                        f'textarea[placeholder*="{label}" i]'
                    )
                    try:
                        el = await self._page.wait_for_selector(selector, timeout=3000)
                        await el.fill(str(value))
                    except Exception:
                        pass
                return _R(True, f"Filled {len(fields)} field(s) on {url}")
            except Exception as e:
                return _R(False, error=str(e))

    async def click_element(self, selector: str) -> dict:
        async with self._lock:
            try:
                await self._ensure()
                await self._page.click(selector, timeout=5000)
                return _R(True, f"Clicked: {selector}")
            except Exception as e:
                return _R(False, error=str(e))

    async def screenshot(self) -> dict:
        async with self._lock:
            try:
                await self._ensure()
                _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                fname = _SCREENSHOT_DIR / f"browser_{int(time.time())}.png"
                await self._page.screenshot(path=str(fname))
                return _R(True, f"Screenshot saved: {fname}")
            except Exception as e:
                return _R(False, error=str(e))

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = None
        self._page    = None
        self._pw      = None


# ── Singleton instance ─────────────────────────────────────────────────────────
browser = BrowserAgent()
