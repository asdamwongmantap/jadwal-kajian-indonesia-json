"""Mengubah HTML pengumuman menjadi teks bersih yang mudah diparse."""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup, NavigableString

_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote", "section", "article"}
_ZERO_WIDTH = re.compile("[​-‏⁠-⁤﻿­⁦-⁩]")
_MARKDOWN = re.compile(r"[*_`~]+")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]+")


def html_to_text(html: str) -> tuple[str, list[str]]:
    """Kembalikan (teks, daftar_tautan). <br> menjadi baris baru, blok menjadi paragraf."""
    soup = BeautifulSoup(html or "", "html.parser")
    links: list[str] = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href and not href.startswith("?"):
            links.append(_clean_url(href))
    for br in soup.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before(NavigableString("\n\n"))
        tag.insert_after(NavigableString("\n\n"))
    return normalize(soup.get_text()), links


def _clean_url(url: str) -> str:
    url = url.replace("%60", "").rstrip("`'\".,)")
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    elif url.startswith("//"):
        url = "https:" + url
    elif not re.match(r"^[a-z]+://", url, re.I):
        url = "https://" + url
    return url


def strip_symbols(s: str) -> str:
    """Buang emoji dan simbol dekoratif, pertahankan huruf, angka, dan tanda baca."""
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat in ("So", "Sk", "Cs", "Co") or ch in "️⃣":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    """NFKC (huruf "fancy" menjadi ASCII), buang markdown/emoji, rapikan spasi per baris."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _ZERO_WIDTH.sub("", text)
    text = text.replace("\r", "")
    lines = []
    for line in text.split("\n"):
        line = strip_symbols(line)
        line = _MARKDOWN.sub("", line)
        line = line.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
        line = re.sub(r"[ \t ]+", " ", line).strip()
        if re.fullmatch(r"[.\-–—=•●○《》()\[\]:|>]*", line):
            line = ""
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def remove_arabic(s: str) -> str:
    return re.sub(r"\s{2,}", " ", _ARABIC.sub(" ", s)).strip()


def smart_title(s: str) -> str:
    """Ubah teks HURUF BESAR SEMUA menjadi Judul Kapital, biarkan yang sudah campuran."""
    letters = [c for c in s if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        small = {"bin", "binti", "dan", "di", "ke", "dari"}
        words = []
        for i, w in enumerate(s.lower().split(" ")):
            if i > 0 and w in small:
                words.append(w)
            else:
                words.append("-".join(p[:1].upper() + p[1:] for p in w.split("-")))
        s = " ".join(words)
        # Gelar akademik yang lazim ditulis kapital.
        s = re.sub(r"\b(Ma|Mm|Mh|Phd)\b(?=[.,]|$)", lambda m: {"Phd": "PhD"}.get(m.group(1), m.group(1).upper()), s)
    return s
