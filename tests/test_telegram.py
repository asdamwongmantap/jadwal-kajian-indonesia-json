from datetime import datetime, timezone

import pytest

from scraper.adapters.telegram import TelegramAdapter
from scraper.parser import parse


@pytest.fixture
def hasil(fixture_text):
    adapter = TelegramAdapter({"id": "jks", "channel": "jadwalkajiansunnah"}, fetcher=None)
    items, oldest, oldest_time = adapter.parse_page(fixture_text("telegram_jadwalkajiansunnah.html"))
    parsed = {it.url.rsplit("/", 1)[1]: parse(it) for it in items}
    return items, oldest, oldest_time, parsed


def test_paginasi_dan_pesan(hasil):
    items, oldest, oldest_time, _ = hasil
    assert oldest == 11564
    assert oldest_time == datetime(2026, 10, 10, 22, 20, 1, tzinfo=timezone.utc)
    urls = [i.url for i in items]
    assert "https://t.me/jadwalkajiansunnah/11564" not in urls  # hanya foto, tanpa teks


def test_rekapan_yang_melarang_diubah_dilewati_beserta_batchnya(hasil):
    items = hasil[0]
    ids = {i.url.rsplit("/", 1)[1] for i in items}
    assert "11590" not in ids  # memuat "Dilarang Mengubah ... Tanpa se-Izin"
    assert "11591" not in ids and "11596" not in ids  # lanjutan rekap di detik yang sama


def test_caption_kota_saja_tidak_dianggap_jadwal(hasil):
    assert hasil[3]["11584"] is None


def test_label_lengkap_tangerang_selatan(hasil):
    k = hasil[3]["11565"]
    assert k["tanggal"] == "2026-10-11" and k["hari"] == "Ahad"
    assert k["ustadz"] == ["Ustadz Ruslan Nuryadin, Lc."]
    assert k["waktu"]["acuan_shalat"] == "Maghrib" and k["waktu"]["relasi"] == "setelah"
    assert k["tempat"]["nama"] == "Masjid Jami' Utsman bin Affan"
    assert k["wilayah"]["kabkota"] == "Kota Tangerang Selatan"
    assert k["tempat"]["peta"] == "https://bit.ly/mapsMUBA"
    assert k["peserta"] == "umum"


def test_huruf_fancy_dan_rentang_jam(hasil):
    k = hasil[3]["11566"]
    assert k["ustadz"] == ["Ustadz Abdurrahman Dani"]
    assert (k["waktu"]["mulai"], k["waktu"]["selesai"]) == ("09:00", "11:00")
    assert k["mulai_iso"] == "2026-10-11T09:00:00+07:00"
    assert k["tempat"]["nama"] == "Masjid Baitul Haq"
    assert k["wilayah"]["kabkota"] == "Kota Bekasi"


def test_caption_rutin_tanpa_tanggal_diperkirakan_dari_hari(hasil):
    k = hasil[3]["11568"]
    assert k["hari"] == "Ahad" and k["tanggal"] == "2026-10-11" and k["tanggal_perkiraan"] is True
    assert k["mulai_iso"] is None
    assert k["wilayah"]["kabkota"] == "Kabupaten Bekasi"  # "Kab. Bekasi" eksplisit


def test_tema_label_tanpa_ustadz_bukan_penulis_kitab(hasil):
    k = hasil[3]["11611"]
    assert k["ustadz"] == ["Ustadz Riza Afrizal, Lc., M.Ag."]  # bukan "Syaikh Abdurrazaq" (penulis kitab)
    assert k["kitab"] == "Ahaditsul Akhlak"
    assert k["wilayah"]["kabkota"] == "Kota Administrasi Jakarta Selatan"  # dari "Kalibata City"
    assert k["mode"] == "hybrid"


def test_jam_pada_baris_tanggal_dan_kajian_online(hasil):
    k = hasil[3]["11625"]
    assert k["tanggal"] == "2026-10-12" and k["hari"] == "Senin"
    assert (k["waktu"]["mulai"], k["waktu"]["selesai"]) == ("12:30", "13:30")
    assert k["mode"] == "online" and k["tempat"]["nama"] is None and k["wilayah"] is None
    assert k["kitab"] == "62 Amalan Pembuka Pintu Surga"
    assert k["ustadz"] == ["Ustadz Khalid Basalamah"]


def test_wita_dan_kajian_rutin_makassar(hasil):
    k = hasil[3]["11613"]
    assert k["tanggal"] is None and k["hari"] == "Ahad"
    assert k["rutin"] and "Setiap Ahad" in k["rutin"]
    assert k["zona_waktu"] == "WITA" and k["wilayah"]["kabkota"] == "Kota Makassar"


def test_lokasi_tidak_terkecoh_daftar_siaran(hasil):
    # Baris "LIVE: ... Payakumbuh Mengaji" tidak boleh membuat lokasi jadi Payakumbuh.
    assert hasil[3]["11618"]["wilayah"]["kabkota"] == "Kabupaten Kampar"
    assert hasil[3]["11620"]["wilayah"]["kabkota"] == "Kota Pekanbaru"


def test_kota_lain(hasil):
    p = hasil[3]
    assert p["11599"]["wilayah"]["kabkota"] == "Kota Depok" and p["11599"]["peserta"] == "akhwat"
    assert p["11603"]["wilayah"]["kabkota"] == "Kabupaten Sleman" and p["11603"]["tema"] == "Mindful Activities"
    assert p["11605"]["wilayah"]["kabkota"] == "Kota Tasikmalaya"
    assert (p["11605"]["waktu"]["mulai"], p["11605"]["waktu"]["selesai"]) == ("16:00", "17:10")
    assert p["11607"]["wilayah"]["kabkota"] == "Kota Pematangsiantar"
    assert p["11622"]["wilayah"]["kabkota"] == "Kota Cilegon" and p["11622"]["tanggal"] == "2026-10-11"
    assert p["11624"]["wilayah"]["kabkota"] == "Kota Administrasi Jakarta Selatan"


def test_tidak_ada_data_pribadi_di_hasil(hasil):
    import json
    blob = json.dumps(list(hasil[3].values()), ensure_ascii=False)
    assert "wa.me" not in blob and "0800" not in blob
