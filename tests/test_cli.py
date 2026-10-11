import json

import yaml

from scraper import __main__ as cli


class FakeFetcher:
    """Menyajikan fixture alih-alih internet. Halaman Telegram kedua kosong agar paginasi berhenti."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise RuntimeError(f"tidak ada fixture untuk {url}")
        return self.pages[url]


def test_run_end_to_end(tmp_path, fixture_text, monkeypatch):
    cfg = {
        "pengaturan": {"jeda_detik": 0},
        "sumber": [
            {"id": "jks", "tipe": "telegram", "channel": "jadwalkajiansunnah", "max_pages": 3, "lookback_days": 3650},
            {"id": "attaqwa", "tipe": "website", "list_url": "https://attaqwajatibening.com/berita",
             "link_pattern": "/berita/kajian-rutin-rabu", "content_selector": "article", "title_selector": "h3.my-4",
             "hints": {"tempat": "Masjid At-Taqwa Jatibening Satu", "wilayah": "32.75"}},
            {"id": "rusak", "tipe": "telegram", "channel": "tidakada"},
        ],
    }
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    artikel = ("https://attaqwajatibening.com/berita/"
               "kajian-rutin-rabu-malam-pekan-pertama-7-oktober-2026-26-rabiul-akhir-1448-h")
    fake = FakeFetcher({
        "https://t.me/s/jadwalkajiansunnah": fixture_text("telegram_jadwalkajiansunnah.html"),
        "https://t.me/s/jadwalkajiansunnah?before=11564": "<html><body></body></html>",
        "https://attaqwajatibening.com/berita": fixture_text("website_attaqwa_daftar.html"),
        artikel: fixture_text("website_attaqwa_artikel.html"),
    })
    monkeypatch.setattr(cli, "Fetcher", lambda **kw: fake)

    class FixedNow:
        @staticmethod
        def now(tz=None):
            from datetime import datetime, timezone
            return datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cli, "datetime", FixedNow)

    out = tmp_path / "data"
    assert cli.main(["run", "--config", str(tmp_path / "sources.yaml"), "--out", str(out)]) == 0

    meta = json.loads((out / "meta.json").read_text())
    status = {s["id"]: s for s in meta["sumber"]}
    assert status["jks"]["status"] == "ok" and status["jks"]["jadwal"] >= 15
    assert status["attaqwa"]["jadwal"] == 1
    assert status["rusak"]["status"].startswith("gagal")  # satu sumber gagal, yang lain tetap jalan
    data = json.loads((out / "kajian.json").read_text())
    assert data["jumlah"] == meta["jumlah_kajian"] > 0
    assert (out / "kota" / "kota-bekasi.json").exists()
    assert "https://t.me/s/jadwalkajiansunnah?before=11564" in fake.calls
