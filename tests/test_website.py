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


BLOK_CFG = {
    "id": "istiqlal-rutin",
    "nama": "Masjid Istiqlal - Jadwal Rutin",
    "list_url": "https://www.istiqlal.or.id/artikel/kategori/keislaman",
    "link_pattern": "(?!)",
    "blok_jadwal": {"item": ".timeline-step", "waktu": ".time-tag", "judul": "h6",
                    "pemateri": ".ustadz-name", "tema": ".kitab-name"},
    "hints": {"tempat": "Masjid Istiqlal", "wilayah": "31.71"},
}


def test_blok_jadwal_hari_ini(fixture_text):
    a = WebsiteAdapter(BLOK_CFG, fetcher=None)
    items = a.parse_blok(fixture_text("website_istiqlal_blok.html"), BLOK_CFG["list_url"],
                         datetime(2026, 10, 11, 3, tzinfo=timezone.utc))
    ks = [parse(i) for i in items]
    assert len(ks) == 4
    zuhur = ks[1]
    assert zuhur["tanggal"] == "2026-10-11" and zuhur["waktu"]["acuan_shalat"] == "Dzuhur"
    assert zuhur["ustadz"] == ["KH Bukhori Sail Attahiri, Lc, MA."]
    assert zuhur["wilayah"]["kode"] == "31.71"
    jumat = ks[3]  # "Khusus Jumat": hari terdekat, bukan hari ini
    assert jumat["hari"] == "Jumat" and jumat["tanggal"] == "2026-10-16" and jumat["tanggal_perkiraan"]
