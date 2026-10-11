"""Mendeteksi kabupaten/kota dari teks alamat memakai data wilayah Kemendagri."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).with_name("wilayah.json")

TZ_NAMA = {7: "WIB", 8: "WITA", 9: "WIT"}

# Singkatan dan sebutan populer -> nama kab/kota (tanpa awalan Kota/Kabupaten).
ALIAS_KABKOTA = {
    "jaksel": "jakarta selatan", "jakpus": "jakarta pusat", "jakbar": "jakarta barat",
    "jaktim": "jakarta timur", "jakut": "jakarta utara", "tangsel": "tangerang selatan",
    "tang-sel": "tangerang selatan", "tang sel": "tangerang selatan", "bks": "bekasi",
    "jogja": "yogyakarta", "jogjakarta": "yogyakarta", "yogya": "yogyakarta",
    "solo": "surakarta", "makasar": "makassar", "siantar": "pematangsiantar",
    "pematang siantar": "pematangsiantar", "bandar lampung": "bandar lampung",
}
# Nama tempat populer yang bukan nama kecamatan -> kode kab/kota.
ALIAS_TEMPAT = {
    "kalibata": "31.74", "kalibata city": "31.74", "cikarang": "32.16", "tebet": "31.74",
    "bintaro": "36.74", "serpong": "36.74", "bsd": "36.74", "gading serpong": "36.03",
    "jatibening": "32.75", "kemang pratama": "32.75", "sentul": "32.01", "cibubur": "31.75",
}
_STOP_KECAMATAN = {
    "masjid", "tengah", "barat", "timur", "utara", "selatan", "kota", "baru", "raya",
    "pusat", "sunnah", "mekar", "sukamaju", "kampung", "ilmu", "islam", "taqwa", "wanita",
}


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'")
    s = re.sub(r"\bpd\.\s*", "pondok ", s)
    s = re.sub(r"\bkec\.\s*", "kecamatan ", s)
    s = re.sub(r"\bkab\.\s*", "kabupaten ", s)
    s = re.sub(r"\bsel\.(?=\s|,|$)", "selatan", s)
    s = re.sub(r"\btim\.(?=\s|,|$)", "timur", s)
    s = re.sub(r"\bbar\.(?=\s|,|$)", "barat", s)
    s = re.sub(r"\butr\.(?=\s|,|$)", "utara", s)
    s = re.sub(r"[^a-z0-9' -]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_prefix(nama: str) -> tuple[str, str]:
    n = nama.strip()
    for pre, jenis in (("Kabupaten Administrasi ", "kabupaten"), ("Kota Administrasi ", "kota"),
                       ("Kabupaten ", "kabupaten"), ("Kota ", "kota")):
        if n.startswith(pre):
            return n[len(pre):], jenis
    return n, "kota"


@dataclass(frozen=True)
class Wilayah:
    kode: str
    kabkota: str
    provinsi: str
    tz: int | None

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.kabkota.lower()).strip("-")

    @property
    def zona(self) -> str | None:
        return TZ_NAMA.get(self.tz) if self.tz else None

    def as_dict(self) -> dict:
        return {"kode": self.kode, "kabkota": self.kabkota, "provinsi": self.provinsi,
                "slug": self.slug, "zona_waktu": self.zona}


class Gazetteer:
    def __init__(self, data: dict):
        self.prov = {p["kode"]: p for p in data["provinsi"]}
        self.reg = {r["kode"]: r for r in data["kabkota"]}
        self.by_name: dict[str, list[tuple[str, str]]] = {}
        for r in data["kabkota"]:
            base, jenis = _strip_prefix(r["nama"])
            self.by_name.setdefault(_norm(base), []).append((r["kode"], jenis))
        counts: dict[str, list[str]] = {}
        for d in data["kecamatan"]:
            counts.setdefault(_norm(d["nama"]), []).append(d["reg"])
        self.kec_by_name = counts
        self._reg_pattern = self._compile(list(self.by_name) + list(ALIAS_KABKOTA))
        kec_unique = [k for k, v in counts.items()
                      if len(set(v)) == 1 and len(k) >= 5 and k not in _STOP_KECAMATAN]
        self._kec_pattern = self._compile(kec_unique + list(ALIAS_TEMPAT))

    @staticmethod
    def _compile(names: list[str]) -> re.Pattern:
        names = sorted(set(names), key=len, reverse=True)
        return re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(n) for n in names) + r")(?![a-z0-9])")

    def wilayah(self, kode: str) -> Wilayah:
        r = self.reg[kode]
        p = self.prov[r["prov"]]
        return Wilayah(kode=kode, kabkota=r["nama"], provinsi=p["nama"], tz=r.get("tz") or p.get("tz"))

    def detect(self, *texts: str) -> Wilayah | None:
        """Cari kab/kota dari teks lokasi. Teks pertama yang menghasilkan kecocokan dipakai."""
        for text in texts:
            if text:
                kode = self._detect_one(_norm(text))
                if kode:
                    return self.wilayah(kode)
        return None

    def _detect_one(self, t: str) -> str | None:
        kec_hits = [m.group(1) for m in self._kec_pattern.finditer(t)]
        alias_regs = [ALIAS_TEMPAT[h] for h in kec_hits if h in ALIAS_TEMPAT]
        kec_regs: list[str] = list(alias_regs)
        for h in kec_hits:
            if h not in ALIAS_TEMPAT:
                kec_regs.extend(self.kec_by_name.get(h, []))

        # 1) Awalan eksplisit: "Kota Bekasi", "Kabupaten Bekasi".
        for m in re.finditer(r"\b(kota|kabupaten)\s+(?:administrasi\s+)?([a-z' -]+)", t):
            jenis, rest = m.group(1), m.group(2)
            words = rest.split()
            for n in range(min(4, len(words)), 0, -1):
                key = " ".join(words[:n])
                key = ALIAS_KABKOTA.get(key, key)
                for kode, j in self.by_name.get(key, []):
                    if j == jenis:
                        return kode

        # 2) Nama kab/kota tanpa awalan, ambil kemunculan terakhir (alamat biasanya diakhiri kota).
        hits = [m.group(1) for m in self._reg_pattern.finditer(t)]
        for key in reversed(hits):
            key = ALIAS_KABKOTA.get(key, key)
            cands = self.by_name.get(key, [])
            if not cands:
                continue
            if len(cands) == 1:
                return cands[0][0]
            # Ambigu (mis. Kota/Kab. Bekasi): pakai petunjuk kecamatan, lalu default "kota".
            for kode, _ in cands:
                if kode in kec_regs:
                    return kode
            for kode, jenis in cands:
                if jenis == "kota":
                    return kode
            return cands[0][0]

        # 3) Tempat populer, lalu kecamatan unik yang paling sering disebut.
        if alias_regs:
            return alias_regs[0]
        if kec_regs:
            return max(kec_regs, key=lambda k: (kec_regs.count(k), -kec_regs.index(k)))
        return None


@lru_cache(maxsize=1)
def default_gazetteer() -> Gazetteer:
    return Gazetteer(json.loads(DATA_FILE.read_text(encoding="utf-8")))
