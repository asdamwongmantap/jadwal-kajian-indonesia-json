"""Adapter situs masjid/lembaga: halaman daftar -> tautan artikel -> teks pengumuman.

Setiap situs dikonfigurasi di sources.yaml: URL daftar, pola tautan, dan selector isi.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import RobotsDisallowed
from ..parser import RawItem
from ..text import html_to_text

log = logging.getLogger(__name__)

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Ahad"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
         "Oktober", "November", "Desember"]


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
        self.blok = config.get("blok_jadwal")
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

    def parse_blok(self, html: str, url: str, now: datetime) -> list[RawItem]:
        """Blok "Kajian Hari Ini" di halaman daftar: satu elemen per sesi, tanpa halaman artikel.

        Sesi biasa diberi tanggal hari ini (WIB). Sesi yang waktunya berbunyi "Khusus <hari>" hanya diberi
        nama hari, supaya parser memakai hari tersebut yang terdekat.
        """
        cfg = self.blok
        soup = BeautifulSoup(html, "html.parser")
        lokal = now.astimezone(timezone(timedelta(hours=7))).date()

        def teks(el, sel):
            found = el.select_one(sel) if sel else None
            return found.get_text(" ", strip=True) if found else ""

        items = []
        for el in soup.select(cfg["item"]):
            judul, waktu = teks(el, cfg.get("judul")), teks(el, cfg.get("waktu"))
            pemateri, tema = teks(el, cfg.get("pemateri")), teks(el, cfg.get("tema"))
            if not judul:
                continue
            khusus = re.search(r"(?i)khusus\s+(\w+)", waktu)
            if khusus:
                kapan = f"Hari: {khusus.group(1).capitalize()}"
            else:
                kapan = f"Tanggal: {HARI[lokal.weekday()]}, {lokal.day} {BULAN[lokal.month - 1]} {lokal.year}"
            baris = [f"Kajian {judul}", kapan]
            if waktu and not khusus:
                baris.append(f"Waktu: {waktu}")
            if pemateri:
                baris.append(f"Pemateri: {pemateri}")
            if tema:
                baris.append(f"Tema: {tema}")
            if self.hints.get("tempat"):
                baris.append(f"Tempat: {self.hints['tempat']}")
            items.append(RawItem(source_id=self.id, source_name=self.name, url=url, text="\n".join(baris),
                                 posted_at=now, hints=dict(self.hints)))
        return items

    def fetch(self, now: datetime | None = None) -> list[RawItem]:
        now = now or datetime.now(timezone.utc)
        items: list[RawItem] = []
        for list_url in self.list_urls:
            html = self.fetcher.get(list_url)
            if self.blok:
                items.extend(self.parse_blok(html, list_url, now))
            links = self.article_links(html, list_url)
            for url in links:
                try:
                    item = self.parse_article(self.fetcher.get(url), url, now)
                except RobotsDisallowed:
                    log.info("[%s] dilewati karena robots.txt: %s", self.id, url)
                    continue
                if item:
                    items.append(item)
        return items
