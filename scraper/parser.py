"""Parser teks pengumuman kajian (poster/caption) menjadi data terstruktur.

Pengumuman kajian ditulis bebas, jadi parser memakai dua lapis:
1. Label yang lazim ("Tema:", "Pemateri:", "Tempat:", "Waktu:", ...).
2. Pola cadangan (tanggal Masehi, jam, "Ba'da Maghrib", baris "Masjid ...").
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .text import remove_arabic, smart_title
from .wilayah import Gazetteer, Wilayah, default_gazetteer

BULAN = {
    "januari": 1, "jan": 1, "februari": 2, "pebruari": 2, "feb": 2, "maret": 3, "mar": 3,
    "april": 4, "apr": 4, "mei": 5, "may": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "agt": 8, "aug": 8, "august": 8, "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10, "november": 11, "nov": 11, "nopember": 11,
    "desember": 12, "des": 12, "december": 12, "dec": 12,
    "january": 1, "february": 2, "march": 3, "june": 6, "july": 7,
}
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Ahad"]
_HARI_RE = re.compile(r"\b(senin|selasa|rabu|kamis|jum'?at|sabtu|ahad|minggu)\b", re.I)
_TANGGAL_RE = re.compile(
    r"\b(\d{1,2})\s*(" + "|".join(sorted(BULAN, key=len, reverse=True)) + r")\.?\s*,?\s*(20\d{2})\b", re.I)
_JAM_RE = re.compile(r"(?<![\d/])([01]?\d|2[0-3])[.:]([0-5]\d)(?![\d/])\s*(wib|wita|wit)?", re.I)
_SHALAT = {
    "subuh": "Subuh", "shubuh": "Subuh", "shubh": "Subuh", "fajar": "Subuh",
    "dzuhur": "Dzuhur", "zhuhur": "Dzuhur", "zuhur": "Dzuhur", "dhuhur": "Dzuhur", "duhur": "Dzuhur",
    "ashar": "Ashar", "asar": "Ashar", "maghrib": "Maghrib", "magrib": "Maghrib",
    "isya": "Isya", "'isya": "Isya", "isya'": "Isya", "dhuha": "Dhuha", "duha": "Dhuha",
}
_SHALAT_RE = re.compile(
    r"\b(ba'?da|bakda|ba'da|setelah|sesudah|menjelang|sebelum)?\s*(?:shalat|sholat|salat)?\s*"
    r"('?(?:shubuh|subuh|shubh|fajar|dzuhur|zhuhur|zuhur|dhuhur|duhur|ashar|asar|maghrib|magrib|isya|dhuha|duha)'?)\b",
    re.I)

LABELS = {
    "ustadz": r"pemateri|penceramah|pembicara|narasumber|nara sumber|pengisi(?: kajian)?|"
              r"(?:insya+ ?allah )?bersama(?: ustadz)?|oleh",
    "tema": r"tema(?: kajian)?|dengan tema|judul|topik|materi|pembahasan|bahasan|dengan pembahasan",
    "kitab": r"kitab|pembahasan kitab|kajian kitab",
    "tanggal": r"hari ?/ ?tanggal|hari ?/ ?tgl|hari,? tanggal|hari|tanggal|tgl",
    "waktu": r"waktu|pukul|jam",
    "tempat": r"tempat|lokasi|alamat|venue",
}
_LABEL_RE = {k: re.compile(r"^(?:[-•●》>\[]\s*)?(?:" + v + r")\b\s*(?::|-|=|,)?\s*(.*)$", re.I) for k, v in LABELS.items()}
_ANY_LABEL = re.compile(r"^(?:[-•●》>\[]\s*)?(?:" + "|".join(LABELS.values()) + r")\s*(?::|-|=)\s*", re.I)
_TEMPAT_AWAL = re.compile(
    r"^(masjid|mesjid|musholl?a|mushola|musala|musalla|surau|langgar|ma'?had|pondok pesantren|ponpes|"
    r"pesantren|rumah (?:al-?)?qur'?an|islamic cent(?:er|re)|aula|gedung|balai|graha|auditorium)\b", re.I)
_MAPS_RE = re.compile(r"(maps\.app\.goo\.gl|goo\.gl/maps|g\.co/kgs|share\.google|maps\.google|google\.[a-z.]+/maps|"
                      r"bit\.ly/\S*map|s\.id/\S*peta|s\.id/\S*map)", re.I)
_STREAM_RE = re.compile(r"(youtube\.com|youtu\.be|siar\.us|facebook\.com/.*/live|instagram\.com/.*/live)", re.I)
_ONLINE_RE = re.compile(r"live\s*streaming|simaklah\s+live|disiarkan\s+(?:secara\s+)?live|\blive\s*:|via\s+zoom|kajian\s+online|daring", re.I)
_HONORIFIK = re.compile(
    r"[-–(]*\s*\b(hafi[dz]h?[oa]?hull?ah\w*|hafi[dz]ahull?ah\w*|hafidzahullah\w*|hafizhohullah\w*|hafizhahull?ah\w*|"
    r"rahimahull?ah\w*|ta'?ala)\b\s*[-–)]*", re.I)
_SAMPAH_URL = re.compile(r"(wa\.me|whatsapp\.com|chat\.whatsapp|t\.me/|instagram\.com|bit\.ly/grup|linktr\.ee)", re.I)


@dataclass
class RawItem:
    """Satu pengumuman mentah dari sebuah adapter."""
    source_id: str
    source_name: str
    url: str
    text: str
    links: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    forwarded_from: str | None = None
    hints: dict = field(default_factory=dict)


def _blocks(text: str) -> list[list[str]]:
    blocks, cur = [], []
    for line in text.split("\n"):
        if line.strip():
            cur.append(line.strip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def _label_value(lines: list[str], key: str) -> tuple[str | None, int | None]:
    """Nilai label: sisa baris setelah pemisah, atau baris-baris berikutnya dalam paragraf.

    Label dianggap sah bila diikuti pemisah (: - = ,), berdiri sendiri di barisnya,
    atau (khusus ustadz) berupa "Bersama Ustadz ...". Ini mencegah "Tematik" terbaca
    sebagai label "Tema", atau "Hadirilah" sebagai "Hari".
    """
    rx = _LABEL_RE[key]
    for i, line in enumerate(lines):
        m = rx.match(line)
        if not m:
            continue
        rest = m.group(1)
        head = line[: len(line) - len(rest)] if rest else line
        has_sep = bool(re.search(r"[:\-=,]\s*$", head))
        if rest and not has_sep:
            if not (key == "ustadz" and re.match(r"(?i)(ustad|syaikh|syekh|kak|dr\.)", rest)):
                continue
        val = rest.strip(" :-=,")
        nxt = []
        for line2 in lines[i + 1:]:
            if not line2 or _ANY_LABEL.match(line2):
                break
            nxt.append(line2)
        if val:
            if key == "tempat":
                extra = nxt[:3]
            elif key in ("tema", "kitab"):
                extra = [x for x in nxt[:2] if x.startswith("(")]
            else:
                extra = []
            return "\n".join([val] + extra), i
        if nxt:
            return "\n".join(nxt[:4]), i
    return None, None


def _clean_person(s: str) -> str:
    s = remove_arabic(s)
    s = re.sub(r"\(.*?\)", "", s)
    s = _HONORIFIK.sub(" ", s)
    s = re.sub(r"^(insya+ ?allah\s+)?(bersama|oleh)\s*:?\s*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -–:.,")
    m = re.match(r"(?i)^(ustadzah|ustadz|ustads|ustad|ust\.?|syaikh|syeikh|syekh|kak)\s+", s)
    prefix, rest = ("", s) if not m else (m.group(1), s[m.end():])
    prefix = {"ustadzah": "Ustadzah", "ustads": "Ustadz", "ustad": "Ustadz", "ust.": "Ustadz", "ust": "Ustadz"}.get(
        prefix.lower(), prefix.capitalize())
    s = (prefix + " " + smart_title(rest)).strip()
    if not s.endswith(".") and (re.search(r"(?i)\b(lc|ma|mm|phd)$", s) or re.search(r"\b[A-Za-z]{1,3}\.[A-Za-z]{1,3}$", s)):
        s += "."
    return s


def _find_ustadz(lines: list[str]) -> list[str]:
    val, _ = _label_value(lines, "ustadz")
    cands: list[str] = []
    if val:
        cands = [x for x in val.split("\n") if re.search(r"[A-Za-z]{3}", x)][:2]
    if not cands:
        # Utamakan "Ustadz/Ustadzah"; "Syaikh" sering muncul sebagai penulis kitab ("karya Syaikh ...").
        for pola in (r"\b(ustad[sz](?:ah)?|ust\.)\s+(.{3,80})", r"\b(syaikh|syeikh|syekh|kyai|kh\.|buya)\s+(.{3,80})"):
            for line in lines:
                m = re.search(pola, line, re.I)
                if m and not re.search(r"(channel|official|youtube|karya|kitab)", line, re.I):
                    cands = [m.group(0)]
                    break
            if cands:
                break
    out: list[str] = []
    for c in cands:
        c = re.split(r"(?<=[a-z.])\s*-\s*(?=hafi|ha?fizh)", c, flags=re.I)[0]
        name = _clean_person(c)
        if name and len(name) >= 4 and not re.fullmatch(r"(?i)ustadz(ah)?", name) and name not in out:
            out.append(name)
    return out


def _clean_value(s: str | None, max_len: int = 200) -> str | None:
    if not s:
        return None
    s = remove_arabic(s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"#[A-Za-z]\w*", "", s)
    s = re.sub(r"[\[\]]", "", s)
    s = " ".join(x.strip(" -–:") for x in s.split("\n") if x.strip(" -–:"))
    s = re.sub(r"\s+", " ", s).strip(" -–:\"'.,")
    if s.startswith("(") and s.endswith(")") and s.count("(") == 1:
        s = s[1:-1].strip(" \"'.,")
    s = smart_title(s)
    return (s[: max_len - 1] + "…") if len(s) > max_len else (s or None)


def _find_tanggal(text: str) -> date | None:
    for m in _TANGGAL_RE.finditer(text):
        d, bln, th = int(m.group(1)), BULAN[m.group(2).lower()], int(m.group(3))
        try:
            return date(th, bln, d)
        except ValueError:
            continue
    return None


def _find_hari(text: str) -> str | None:
    m = _HARI_RE.search(text)
    if not m:
        return None
    h = m.group(1).lower().replace("'", "")
    return {"minggu": "Ahad", "jumat": "Jumat"}.get(h, h.capitalize())


def _find_waktu(text: str, waktu_label: str | None) -> dict:
    src_lines = [waktu_label] if waktu_label else []
    src_lines += [ln for ln in text.split("\n") if not re.search(r"adzan|azan|wa\.me|http|\bno\.|\bhal", ln, re.I)]
    mulai = selesai = zona = None
    for ln in src_lines:
        ln = _TANGGAL_RE.sub(" ", ln)
        ln = re.sub(r"\b\d{3,4}\s*H\b|\b(?:19|20)\d{2}\b", " ", ln)
        jams = list(_JAM_RE.finditer(ln))
        if jams:
            mulai = f"{int(jams[0].group(1)):02d}:{jams[0].group(2)}"
            zona = next((j.group(3).upper() for j in jams if j.group(3)), None)
            if len(jams) > 1 and re.search(r"[-–]|s\.?/?d|sampai|hingga", ln, re.I):
                selesai = f"{int(jams[1].group(1)):02d}:{jams[1].group(2)}"
            break
    acuan = relasi = None
    ctx = (waktu_label or "") + "\n" + text
    m = _SHALAT_RE.search(ctx)
    if m:
        acuan = _SHALAT.get(m.group(2).lower().strip("'"), None)
        r = (m.group(1) or "").lower()
        relasi = "sebelum" if r in ("menjelang", "sebelum") else ("setelah" if r else None)
    if mulai and acuan and not (waktu_label and _SHALAT_RE.search(waktu_label)):
        acuan = relasi = None
    return {"mulai": mulai, "selesai": selesai, "acuan_shalat": acuan, "relasi": relasi, "zona": zona}


def _find_tempat(lines: list[str], blocks: list[list[str]]) -> tuple[str | None, str | None, list[str]]:
    val, idx = _label_value(lines, "tempat")
    parts: list[str] = []
    if val:
        parts = [p for p in val.split("\n") if p]
    else:
        for i, line in enumerate(lines):
            if _TEMPAT_AWAL.match(line) and not re.search(r"(official|channel|youtube|kajian rutin:)", line, re.I):
                parts = [line]
                for nxt in lines[i + 1:i + 4]:
                    if not nxt or _ANY_LABEL.match(nxt) or re.match(r"(?i)(https?://|live|terbuka|ikhwan|akhwat)", nxt):
                        break
                    parts.append(nxt)
                break
    parts = [p for p in parts if not p.lower().startswith(("http", "maps", "g-maps", "peta", "link"))]
    if not parts:
        return None, None, []
    first = remove_arabic(parts[0]).strip(" :")
    nama, alamat_first = (first.split(",", 1) + [""])[:2] if "," in first and _TEMPAT_AWAL.match(first) else (first, "")
    alamat_parts = [x.strip() for x in [alamat_first] + parts[1:] if x and x.strip()]
    alamat = ", ".join(alamat_parts) or None
    nama = _clean_value(nama, 120)
    alamat = _clean_value(alamat, 250) if alamat else None
    return nama, alamat, parts


def _peserta(text: str) -> str | None:
    t = text.lower()
    if re.search(r"khusus\s+(akhwat|akhawat|muslimah|wanita|perempuan)|spesial muslimah|ibu-ibu|kajian muslimah", t):
        return "akhwat"
    if re.search(r"khusus\s+(ikhwan|laki|pria)", t):
        return "ikhwan"
    if re.search(r"kajian\s+anak|\(kajian anak\)|khusus anak", t):
        return "anak"
    if re.search(r"umum|ikhwan\s*(&|dan|maupun)\s*akh", t):
        return "umum"
    return None


def _judul(lines: list[str]) -> str | None:
    for line in lines[:8]:
        if _ANY_LABEL.match(line):
            continue
        if len(line) > 90 or re.search(r"(?i)insya|akan |perhatian|link|http", line):
            continue
        bersih = re.sub(r"^[\[(]+|^(hadirilah|ikutilah)\s*:?\s*", "", line, flags=re.I).strip()
        if re.match(r"(?i)^(info\s+)?(kajian|ta'?lim|majelis|majlis|tabligh|dauroh|daurah|pengajian)\b", bersih):
            j = _clean_value(bersih, 140)
            if j and len(j) > 6 and j.lower() not in ("info kajian", "kajian rutin", "kajian islam ilmiah",
                                                       "info kajian rutin", "kajian islami"):
                return j
    return None


def _kitab(lines: list[str], tema: str | None) -> str | None:
    val, _ = _label_value(lines, "kitab")
    if val:
        return _clean_value(val.split("\n")[0], 160)
    for line in lines:
        m = re.search(r"\bkitab\b\s*:?\s*(.{3,120})", line, re.I)
        if m:
            k = _clean_value(re.split(r"\s+karya\s+|\(", m.group(1), flags=re.I)[0], 160)
            if k and (not tema or k.lower() not in tema.lower()):
                return k
    return None


def _make_id(tanggal: str | None, hari: str | None, waktu: dict, tempat: str | None,
             ustadz: list[str], wilayah: dict | None) -> str:
    def n(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    key = "|".join([tanggal or (hari or ""), waktu.get("mulai") or waktu.get("acuan_shalat") or "",
                    n(tempat) or "online", n(ustadz[0] if ustadz else ""), (wilayah or {}).get("kode", "")])
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def parse(item: RawItem, gaz: Gazetteer | None = None) -> dict | None:
    """Ubah satu pengumuman menjadi dict kajian, atau None bila bukan jadwal kajian."""
    gaz = gaz or default_gazetteer()
    text = item.text
    if len(text) < 25:
        return None
    lines = [re.sub(r"^[\s:;]+", "", ln) for ln in text.split("\n")]
    nonblank = [ln for ln in lines if ln.strip()]
    blocks = _blocks(text)

    ustadz = _find_ustadz(lines)
    tema_val = None
    for i, ln in enumerate(lines[:-1]):
        if re.search(r"(?i)\btema\s*:\s*$", ln) and not _LABEL_RE["tema"].match(ln) and lines[i + 1]:
            tema_val = lines[i + 1]
            break
    if not tema_val:
        tema_val, _ = _label_value(lines, "tema")
    if not tema_val:
        tema_val = next((ln for ln in lines if len(ln) <= 100 and re.search(
            r"(?i)\b(syarah|syarh|kitabul|tafsir|hadits|fiqih|fikih|aqidah|akidah|sirah|siroh|tazkiyah)\b", ln)
            and not re.search(r"(?i)https?://|karya", ln)), None)
    tema = _clean_value(tema_val)
    kitab = _kitab(lines, tema)
    tanggal_val, _ = _label_value(lines, "tanggal")
    waktu_val, _ = _label_value(lines, "waktu")

    tgl = _find_tanggal((tanggal_val or "") + "\n" + (waktu_val or "") + "\n" + text)
    hari = _find_hari((tanggal_val or "") + "\n" + (waktu_val or "")) or _find_hari(text)
    waktu = _find_waktu(text, waktu_val)

    nama_tempat, alamat, tempat_lines = _find_tempat(lines, blocks)
    header = " ".join(re.findall(r"\(\(\s*(.+?)\s*\)\)", text))
    lokasi_text = " ".join(filter(None, [" ".join(tempat_lines), header]))
    wil = item.hints.get("wilayah")
    if isinstance(wil, str):
        wil = gaz.wilayah(wil)
    teks_lokasi_luas = "\n".join(ln for ln in lines if not re.search(
        r"(?i)live|\btv\b|channel|radio|\bfm\b|youtube|mengaji|saluran|instagram|facebook|telegram", ln))
    wil = gaz.detect(lokasi_text) or wil or gaz.detect(teks_lokasi_luas)
    if item.hints.get("tempat") and not nama_tempat:
        nama_tempat = item.hints["tempat"]

    online = bool(_ONLINE_RE.search(text))
    streaming = next((u for u in item.links if _STREAM_RE.search(u)), None) if online else None
    mode = ("hybrid" if nama_tempat else "online") if online else "offline"
    peta = next((u for u in item.links if _MAPS_RE.search(u)), None) or item.hints.get("peta")

    rutin = None
    m_rutin = re.search(r"^.*\b(setiap|tiap)\b.*$", text, re.I | re.M)
    if m_rutin and not tgl:
        rutin = _clean_value(re.sub(r"(?i)^insya+ ?allah\s*", "", m_rutin.group(0)) + " " + " ".join(re.findall(r"\((\d+ pekan[^)]*)\)", text, re.I)), 120)

    tanggal_perkiraan = False
    if not tgl and hari and not rutin and item.posted_at:
        # Caption seperti "🗓 Ahad ⏰ Maghrib": hari terdekat sejak tanggal posting.
        tz_h = (wil.tz if wil and wil.tz else 7)
        lokal = item.posted_at.astimezone(timezone(timedelta(hours=tz_h))).date()
        target = HARI.index(hari)
        tgl = lokal + timedelta(days=(target - lokal.weekday()) % 7)
        tanggal_perkiraan = True
    if tgl and not hari:
        hari = HARI[tgl.weekday()]

    # Syarat minimal: ada kapan, ada di mana (atau online), dan ada isi kajian.
    if not (tgl or hari or rutin):
        return None
    if not (nama_tempat or mode == "online"):
        return None
    if not (ustadz or tema or kitab or nama_tempat):
        return None
    if not re.search(r"kajian|ta'?lim|majelis|pengajian|tabligh|dauroh|daurah|ustad|pemateri|kitab|tema|masjid|halaqah", text, re.I):
        return None

    zona = waktu.pop("zona") or (wil.zona if wil else None) or "WIB"
    mulai_iso = None
    if tgl and waktu["mulai"] and not tanggal_perkiraan:
        off = {"WIB": 7, "WITA": 8, "WIT": 9}[zona]
        h, mi = map(int, waktu["mulai"].split(":"))
        mulai_iso = datetime(tgl.year, tgl.month, tgl.day, h, mi, tzinfo=timezone(timedelta(hours=off))).isoformat()

    wil_d = wil.as_dict() if isinstance(wil, Wilayah) else None
    tanggal_s = tgl.isoformat() if tgl else None
    return {
        "id": _make_id(tanggal_s, hari, waktu, nama_tempat, ustadz, wil_d),
        "judul": _judul(nonblank),
        "tema": tema,
        "kitab": kitab,
        "ustadz": ustadz,
        "tanggal": tanggal_s,
        "tanggal_perkiraan": tanggal_perkiraan,
        "hari": hari,
        "rutin": rutin,
        "waktu": waktu,
        "zona_waktu": zona,
        "mulai_iso": mulai_iso,
        "tempat": {"nama": nama_tempat, "alamat": alamat, "peta": peta},
        "wilayah": wil_d,
        "mode": mode,
        "streaming": streaming,
        "peserta": _peserta(text),
        "sumber": [{
            "id": item.source_id,
            "nama": item.source_name,
            "url": item.url,
            "diteruskan_dari": item.forwarded_from,
            "diposting": item.posted_at.isoformat() if item.posted_at else None,
        }],
    }
