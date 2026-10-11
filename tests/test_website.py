from datetime import datetime, timezone

from scraper.adapters.website import WebsiteAdapter
from scraper.parser import parse

CFG = {
    "id": "attaqwa-jatibening",
    "nama": "Masjid At-Taqwa Jatibening Satu",
    "list_url": "https://attaqwajatibening.com/berita",
    "link_pattern": "/berita/(kajian|talim|ta-lim|tabligh)",
    "content_selector": "article",
    "title_selector": "h3.my-4",
    "hints": {"tempat": "Masjid At-Taqwa Jatibening Satu", "wilayah": "32.75"},
}


def test_tautan_artikel_disaring_dan_unik(fixture_text):
    a = WebsiteAdapter(CFG, fetcher=None)
    links = a.article_links(fixture_text("website_attaqwa_daftar.html"), CFG["list_url"])
    assert len(links) == 3
    assert not any("info-shalat-jumat" in u for u in links)


def test_artikel_menjadi_jadwal(fixture_text):
    a = WebsiteAdapter(CFG, fetcher=None)
    item = a.parse_article(fixture_text("website_attaqwa_artikel.html"), "https://attaqwajatibening.com/berita/x",
                           datetime(2026, 10, 6, tzinfo=timezone.utc))
    k = parse(item)
    assert k["tanggal"] == "2026-10-07" and k["hari"] == "Rabu"
    assert k["ustadz"] == ["Ustadz Varian Ghani, Lc."]
    assert k["waktu"]["acuan_shalat"] == "Maghrib" and k["waktu"]["mulai"] is None  # jam adzan diabaikan
    assert k["tema"].startswith("Kitab Bulughul Maram")
    assert k["tempat"]["nama"] == "Masjid At-Taqwa Jatibening Satu"
    assert k["wilayah"]["kabkota"] == "Kota Bekasi"
