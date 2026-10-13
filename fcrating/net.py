"""Polite HTTP fetching: obeys robots.txt, waits between requests per host,
identifies itself, and stops on HTTP 429/403 instead of hammering a site."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
import urllib.robotparser
from typing import Dict, Optional
from urllib.parse import urlparse

DEFAULT_UA = "fc27-rating/0.2 (personlig bruk)"


class Blocked(RuntimeError):
    pass


class PoliteFetcher:
    def __init__(self, user_agent: str = DEFAULT_UA, delay_seconds: float = 2.0, timeout: int = 30,
                 respect_robots: bool = True, log=print):
        self.ua = user_agent
        self.delay = delay_seconds
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.log = log
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._last: Dict[str, float] = {}

    def _robots_for(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": self.ua})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    rp.parse(resp.read().decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    rp.parse(["User-agent: *", "Disallow: /"])
                else:  # 404 etc.: no robots.txt means no restrictions
                    rp.parse([])
            except Exception:
                rp = None  # network trouble: decide per request below
            self._robots[host] = rp
        return self._robots[host]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self._robots_for(url)
        return True if rp is None else rp.can_fetch(self.ua, url)

    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise Blocked(f"robots.txt tillater ikke henting av {url}")
        host = urlparse(url).netloc
        wait = self.delay - (time.time() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "text/html,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                body = resp.read().decode(charset, "replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise Blocked(f"{host} svarte {exc.code}. Stopper for å ikke belaste siden.") from exc
            raise
        finally:
            self._last[host] = time.time()
        return body
