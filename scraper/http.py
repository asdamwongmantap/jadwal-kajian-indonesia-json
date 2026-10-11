"""HTTP yang sopan: patuh robots.txt, jeda antar-permintaan per host, retry, dan User-Agent jelas."""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

DEFAULT_UA = "KajianScraper/0.1 (+https://github.com/USERNAME/jadwal-kajian; jadwal kajian publik)"


class RobotsDisallowed(Exception):
    pass


class Fetcher:
    def __init__(self, user_agent: str = DEFAULT_UA, delay: float = 2.0, timeout: float = 20.0, retries: int = 3):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "id,en;q=0.8"})
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(base + "/robots.txt", timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                else:
                    rp = None  # 404 dsb.: tidak ada aturan, boleh diambil
            except requests.RequestException:
                rp = None
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        host = urlparse(url).netloc
        wait = self.delay - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        err: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, timeout=self.timeout)
                self._last[host] = time.monotonic()
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                r.encoding = r.encoding or "utf-8"
                return r.text
            except requests.RequestException as e:
                err = e
                backoff = self.delay * (2 ** attempt) * 2
                log.warning("Gagal %s (%s), coba lagi dalam %.0fs", url, e, backoff)
                time.sleep(backoff)
        raise err  # type: ignore[misc]
