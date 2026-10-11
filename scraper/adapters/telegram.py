"""Adapter kanal Telegram publik lewat pratinjau web https://t.me/s/<kanal>.

Hanya kanal publik yang punya pratinjau web. Tidak memakai akun, API, atau login.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from ..parser import RawItem
from ..text import html_to_text

log = logging.getLogger(__name__)

# Pengumuman yang melarang isinya diubah atau dipakai ulang tanpa izin dilewati.
DEFAULT_DENY = [
    r"dilarang\s+mengubah",
    r"tanpa\s+se-?\s*izin",
    r"tanpa\s+izin\s+(dari\s+)?(tim|admin|penyelenggara)",
    r"dilarang\s+(meng)?copy",
]


class TelegramAdapter:
    def __init__(self, config: dict, fetcher):
        self.id = config["id"]
        self.channel = config["channel"]
        self.name = config.get("nama") or f"Telegram @{self.channel}"
        self.max_pages = int(config.get("max_pages", 10))
        self.lookback_days = int(config.get("lookback_days", 10))
        self.deny = [re.compile(p, re.I) for p in DEFAULT_DENY + list(config.get("deny_patterns", []))]
        self.hints = config.get("hints", {})
        self.fetcher = fetcher

    def page_url(self, before: int | None = None) -> str:
        url = f"https://t.me/s/{self.channel}"
        return f"{url}?before={before}" if before else url

    def fetch(self, now: datetime | None = None) -> list[RawItem]:
        now = now or datetime.now(timezone.utc)
        batas = now - timedelta(days=self.lookback_days)
        items: list[RawItem] = []
        before = None
        for _ in range(self.max_pages):
            html = self.fetcher.get(self.page_url(before))
            page_items, oldest_id, oldest_time = self.parse_page(html)
            items.extend(page_items)
            if not oldest_id or (oldest_time and oldest_time < batas):
                break
            before = oldest_id
        return items

    def parse_page(self, html: str) -> tuple[list[RawItem], int | None, datetime | None]:
        soup = BeautifulSoup(html, "html.parser")
        msgs = []
        for m in soup.select(".tgme_widget_message[data-post]"):
            post = m["data-post"]
            t = m.select_one("time[datetime]")
            posted = datetime.fromisoformat(t["datetime"]) if t else None
            fwd = m.select_one(".tgme_widget_message_forwarded_from_name")
            body = m.select_one(".tgme_widget_message_text")
            msgs.append({
                "post": post,
                "id": int(post.rsplit("/", 1)[1]),
                "posted": posted,
                "fwd": fwd.get_text(" ", strip=True) if fwd else None,
                "html": body.decode_contents() if body else None,
            })
        if not msgs:
            return [], None, None

        # Pesan yang melarang pengubahan isi, beserta pesan lanjutan dalam batch yang sama
        # (dikirim dalam rentang beberapa detik), dilewati seluruhnya.
        denied_times = []
        for m in msgs:
            raw = BeautifulSoup(m["html"] or "", "html.parser").get_text(" ")
            if any(p.search(raw) for p in self.deny):
                m["denied"] = True
                if m["posted"]:
                    denied_times.append(m["posted"])

        items = []
        for m in msgs:
            if m.get("denied") or not m["html"]:
                continue
            if m["posted"] and any(abs((m["posted"] - d).total_seconds()) <= 5 for d in denied_times):
                continue
            text, links = html_to_text(m["html"])
            items.append(RawItem(
                source_id=self.id,
                source_name=self.name,
                url=f"https://t.me/{m['post']}",
                text=text,
                links=links,
                posted_at=m["posted"],
                forwarded_from=m["fwd"],
                hints=dict(self.hints),
            ))
        oldest = min(msgs, key=lambda x: x["id"])
        return items, oldest["id"], oldest["posted"]
