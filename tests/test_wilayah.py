import pytest

from scraper.wilayah import default_gazetteer


@pytest.mark.parametrize("teks,harapan", [
    ("Jl. Murjaya, Jurangmangu Barat, Pd. Aren, Tangerang Selatan", "Kota Tangerang Selatan"),
    ("Kp. Selang Jati, Kec. Cibitung, Kab. Bekasi, Jawa Barat", "Kabupaten Bekasi"),
    ("Masjid Baitul Haq, Purigading, Jatimelati, Bekasi", "Kota Bekasi"),
    ("Ds. Karangsari Kec. Cikarang Timur, Bekasi", "Kabupaten Bekasi"),
    ("Jl. Kolintang 2, Sukmajaya, Depok 2 Tengah", "Kota Depok"),
    ("Pogung Kidul, Sinduadi, Mlati, Sleman, DIY", "Kabupaten Sleman"),
    ("Jl. RS. Fatmawati, Cilandak - JakSel", "Kota Administrasi Jakarta Selatan"),
    ("Apartemen Kalibata City Basement Tower Cendana", "Kota Administrasi Jakarta Selatan"),
    ("Di Kawasan CPI Makassar", "Kota Makassar"),
    ("Kota Bandung", "Kota Bandung"),
    ("Kabupaten Bandung", "Kabupaten Bandung"),
    ("Jayapura Utara, Kota Jayapura", "Kota Jayapura"),
])
def test_deteksi(teks, harapan):
    assert default_gazetteer().detect(teks).kabkota == harapan


def test_zona_waktu():
    g = default_gazetteer()
    assert g.detect("Kota Makassar").zona == "WITA"
    assert g.detect("Kota Jayapura").zona == "WIT"
    assert g.detect("Kota Medan").zona == "WIB"


def test_tidak_ditemukan():
    assert default_gazetteer().detect("Basement lantai dua") is None
