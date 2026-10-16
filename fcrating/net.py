"""Polite HTTP fetching: obeys robots.txt, waits between requests per host,
identifies itself, and stops on HTTP 429/403 instead of hammering a site."""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

DEFAULT_UA = "fc27-rating/0.2 (personlig bruk)"


class Blocked(RuntimeError):
    pass


class Robots:
    """robots.txt with the wildcards Python's robotparser ignores ("Disallow: /api/*", "$").
    The group for our user agent is used if there is one, otherwise "*". Longest matching rule
    wins; Allow wins a tie (as Google and RFC 9309 do)."""

    def __init__(self, text: str):
        self.groups: List[Tuple[List[str], List[Tuple[bool, str]]]] = []
        agents: List[str] = []
        rules: List[Tuple[bool, str]] = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and (agents or rules):
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(val.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if val or key == "allow":
                    rules.append((key == "allow", val))
        if agents or rules:
            self.groups.append((agents, rules))

    @staticmethod
    def _match(pattern: str, path: str) -> bool:
        rx = "^" + re.escape(pattern).replace(r"\*", ".*")
        if rx.endswith(r"\$"):
            rx = rx[:-2] + "$"
        return re.match(rx, path) is not None

    def can_fetch(self, user_agent: str, url: str) -> bool:
        ua = user_agent.lower()
        token = ua.split("/")[0].split()[0] if ua else ""
        mine = [r for a, r in self.groups if any(x != "*" and x in ua for x in a) or (token and token in a)]
        rules = [x for r in mine for x in r] or [x for a, r in self.groups if "*" in a for x in r]
        parts = urlparse(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: Optional[Tuple[int, bool]] = None
        for allow, pat in rules:
            if pat and self._match(pat, path):
                cand = (len(pat), allow)
                if best is None or cand > best:
                    best = cand
        return True if best is None else best[1]


class PoliteFetcher:
    def __init__(self, user_agent: str = DEFAULT_UA, delay_seconds: float = 2.0, timeout: int = 30,
                 respect_robots: bool = True, log=print):
        self.ua = user_agent
        self.delay = delay_seconds
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.log = log
        self._robots: Dict[str, Optional[Robots]] = {}
        self._last: Dict[str, float] = {}

    def _robots_for(self, url: str) -> Optional["Robots"]:
        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp: Optional[Robots]
            try:
                req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": self.ua})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    rp = Robots(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                rp = Robots("User-agent: *\nDisallow: /") if exc.code in (401, 403) else Robots("")
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
