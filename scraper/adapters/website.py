"""Adapter situs masjid/lembaga: halaman daftar -> tautan artikel -> teks pengumuman.

Setiap situs dikonfigurasi di sources.yaml: URL daftar, pola tautan, dan selector isi.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import RobotsDisallowed
from ..parser import RawItem
from ..text import html_to_text

log = logging.getLogger(__name__)


class WebsiteAdapter:
    def __init__(self, config: dict, fetcher):
        self.id = config["id"]
        self.name = config.get("nama") or self.id
        self.list_urls = config["list_urls"] if "list_urls" in config else [config["list_url"]]
        self.link_pattern = re.compile(config.get("link_pattern", r"kajian"), re.I)
        self.content_selector = config.get("content_selector", "article")
        self.title_selector = config.get("title_selector")
        self.max_articles = int(config.get("max_articles", 15))
        self.hints = config.get("hints", {})
        self.fetcher = fetcher

    def article_links(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        seen, out = set(), []
        for a in soup.find_all("a", href=True):
            url = urljoin(base_url, a["href"]).split("#")[0]
            if self.link_pattern.search(url) and url not in seen:
                seen.add(url)
                out.append(url)
        return out[: self.max_articles]

    def parse_article(self, html: str, url: str, now: datetime) -> RawItem | None:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.select_one(self.content_selector)
        if body is None:
            log.warning("[%s] selector %r tidak ditemukan di %s", self.id, self.content_selector, url)
            return None
        title = soup.select_one(self.title_selector).get_text(" ", strip=True) if self.title_selector and soup.select_one(self.title_selector) else ""
        text, links = html_to_text(body.decode_contents())
        if title:
            text = title + "\n\n" + text
        return RawItem(source_id=self.id, source_name=self.name, url=url, text=text, links=links,
                       posted_at=now, hints=dict(self.hints))

    def fetch(self, now: datetime | None = None) -> list[RawItem]:
        now = now or datetime.now(timezone.utc)
        items: list[RawItem] = []
        for list_url in self.list_urls:
            links = self.article_links(self.fetcher.get(list_url), list_url)
            for url in links:
                try:
                    item = self.parse_article(self.fetcher.get(url), url, now)
                except RobotsDisallowed:
                    log.info("[%s] dilewati karena robots.txt: %s", self.id, url)
                    continue
                if item:
                    items.append(item)
        return items
