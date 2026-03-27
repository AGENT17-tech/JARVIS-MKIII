"""
JARVIS-MKIII — tunnel/tunnel_manager.py
Manages a Cloudflare Quick Tunnel (no account required).
Starts cloudflared and parses the public trycloudflare.com URL from its output.
"""
from __future__ import annotations
import os, re, subprocess, threading, time

CLOUDFLARED_PATH = "/home/k/.local/bin/cloudflared"
URL_FILE         = "/home/k/JARVIS-MKIII/backend/data/tunnel_url.txt"
TOKEN            = os.getenv("MOBILE_ACCESS_TOKEN", "phantom-zero-2026")


class TunnelManager:
    def __init__(self, port: int = 8000):
        self.port    = port
        self.url:    str | None = None
        self.process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> str | None:
        """Start the Cloudflare quick tunnel. Returns the public URL (or None on failure)."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="cloudflare-tunnel")
        self._thread.start()
        # Block up to 20s waiting for the URL to appear in cloudflared output
        for _ in range(40):
            if self.url:
                return self.url
            time.sleep(0.5)
        print("[TUNNEL] Timed out waiting for public URL.")
        return None

    def stop(self) -> None:
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass

    def get_url(self) -> str | None:
        return self.url

    # ── Internal ───────────────────────────────────────────────────────────────

    def _run(self) -> None:
        cmd = [CLOUDFLARED_PATH, "tunnel", "--url", f"http://localhost:{self.port}"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in self.process.stdout:
                stripped = line.strip()
                if stripped:
                    print(f"[TUNNEL] {stripped}")
                match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', stripped)
                if match and not self.url:
                    self.url = match.group(0)
                    print("=" * 60)
                    print(f"  JARVIS PUBLIC URL:")
                    print(f"  {self.url}")
                    print(f"  MOBILE: {self.url}/mobile")
                    print(f"  TOKEN:  {TOKEN}")
                    print("=" * 60)
                    try:
                        os.makedirs(os.path.dirname(URL_FILE), exist_ok=True)
                        with open(URL_FILE, "w") as f:
                            f.write(self.url)
                    except Exception as e:
                        print(f"[TUNNEL] Could not save URL to file: {e}")
        except FileNotFoundError:
            print(f"[TUNNEL] cloudflared not found at {CLOUDFLARED_PATH} — tunnel disabled.")
        except Exception as e:
            print(f"[TUNNEL] Error: {e}")


# ── Singleton ──────────────────────────────────────────────────────────────────
tunnel = TunnelManager(port=8000)
