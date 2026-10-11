# Jadwal Kajian Indonesia (JSON)

Kumpulan jadwal kajian Islam dari berbagai kota di Indonesia dalam bentuk JSON,
diperbarui otomatis dua kali sehari lewat GitHub Actions.

Data diambil dari pengumuman publik (kanal Telegram publik dan situs masjid/lembaga),
dibaca dengan parser teks, lalu dikelompokkan per kabupaten/kota memakai kode wilayah Kemendagri.

> Data dibaca otomatis dari teks bebas, jadi bisa keliru. Selalu cek tautan `sumber`
> sebelum berangkat.

## Pakai datanya

Setelah repo publik, file bisa diambil langsung (ganti `USERNAME/REPO`):

```
https://raw.githubusercontent.com/USERNAME/REPO/main/data/kajian.json        # semua kajian
https://raw.githubusercontent.com/USERNAME/REPO/main/data/kota/index.json    # daftar kota + jumlah
https://raw.githubusercontent.com/USERNAME/REPO/main/data/kota/kota-bekasi.json
https://raw.githubusercontent.com/USERNAME/REPO/main/data/kota/online.json   # kajian online/live
https://raw.githubusercontent.com/USERNAME/REPO/main/data/meta.json          # status tiap sumber
```

Contoh hasil dari postingan asli ada di folder [`contoh-data/`](contoh-data/).
Skema lengkap: [`schema/kajian.schema.json`](schema/kajian.schema.json).

### Bentuk satu kajian

```json
{
  "id": "b1e1ced5d1a4",
  "judul": null,
  "tema": "MAHA INDAH (Al-Jamil) (Fiqih Asmaul Husna)",
  "kitab": null,
  "ustadz": ["Ustadz Luthfi Abdul Jabbar, Lc."],
  "tanggal": "2026-10-12",
  "tanggal_perkiraan": false,
  "hari": "Senin",
  "rutin": null,
  "waktu": {"mulai": "09:30", "selesai": null, "acuan_shalat": null, "relasi": null},
  "zona_waktu": "WIB",
  "mulai_iso": "2026-10-12T09:30:00+07:00",
  "tempat": {
    "nama": "Masjid Jami' Al-Husna Admiralty Residence",
    "alamat": "Jl. RS. Fatmawati, Cilandak - JakSel",
    "peta": "https://maps.app.goo.gl/yfBwHz5jZgF6M9H88"
  },
  "wilayah": {
    "kode": "31.74",
    "kabkota": "Kota Administrasi Jakarta Selatan",
    "provinsi": "Daerah Khusus Ibukota Jakarta",
    "slug": "kota-administrasi-jakarta-selatan",
    "zona_waktu": "WIB"
  },
  "mode": "offline",
  "streaming": null,
  "peserta": null,
  "sumber": [{"id": "jadwalkajiansunnah", "nama": "Telegram @jadwalkajiansunnah",
              "url": "https://t.me/jadwalkajiansunnah/11624", "diteruskan_dari": null,
              "diposting": "2026-10-11T09:47:23+00:00"}],
  "pertama_dilihat": "2026-10-11T10:00:00+00:00",
  "terakhir_dilihat": "2026-10-11T10:00:00+00:00"
}
```

Catatan field:

| Field | Arti |
|---|---|
| `waktu.mulai` / `selesai` | Jam `HH:MM` bila tertulis. |
| `waktu.acuan_shalat` + `relasi` | Untuk "Ba'da Maghrib" → `Maghrib` + `setelah`. Aplikasi bisa menghitung jamnya dari jadwal shalat lokasi. |
| `tanggal_perkiraan` | `true` bila poster hanya menulis hari ("Ahad, Maghrib"); tanggal diambil dari hari terdekat sejak waktu posting. |
| `rutin` | Keterangan kajian rutin tanpa tanggal, mis. "Setiap Ahad 2 Pekan Sekali". `tanggal` bernilai `null`. |
| `mode` | `offline`, `online` (live saja), atau `hybrid` (di masjid + live). |
| `wilayah.kode` | Kode kab/kota Kemendagri, cocok untuk digabung dengan data wilayah lain. |
| `sumber` | Bisa lebih dari satu bila kajian yang sama diumumkan di beberapa tempat. |

Kajian yang sudah lewat dibuang otomatis. Kajian rutin dibuang bila 45 hari tidak muncul lagi.

## Menjalankan sendiri

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                                   # 32 test
python -m scraper run --config sources.yaml --out data
python -m scraper run --source jadwalkajiansunnah --dry-run   # lihat hasil tanpa menulis file
```

Uji parser pada satu teks pengumuman (salin dari poster/caption):

```bash
python -m scraper coba < pengumuman.txt
```

## Otomatis di GitHub

1. Buat repo baru, unggah semua isi folder ini.
2. Ganti `USERNAME/jadwal-kajian` di `sources.yaml` (bagian `user_agent`) dengan alamat repo Anda.
3. Buka **Settings → Actions → General → Workflow permissions**, pilih **Read and write permissions**.
4. Buka tab **Actions**, pilih **Perbarui jadwal kajian**, klik **Run workflow** untuk percobaan pertama.

Setelah itu workflow berjalan sendiri pukul 04:17 dan 16:17 WIB dan meng-commit folder `data/` bila ada perubahan.
Status tiap sumber bisa dilihat di `data/meta.json`.

## Menambah sumber

Edit `sources.yaml`.

**Kanal Telegram publik** (harus punya pratinjau di `https://t.me/s/<kanal>`):

```yaml
- id: kajian-kotaku
  tipe: telegram
  channel: nama_kanal
  lookback_days: 7
  hints:
    wilayah: "32.71"      # opsional: kode kab/kota bila alamat di poster sering tidak lengkap
```

**Situs masjid/lembaga** yang memuat pengumuman kajian sebagai artikel:

```yaml
- id: masjid-contoh
  tipe: website
  list_url: "https://masjid-contoh.id/berita"
  link_pattern: "/berita/.*kajian"   # regex untuk memilih tautan artikel kajian
  content_selector: "article"        # CSS selector isi artikel
  title_selector: "h1"
  hints:
    tempat: "Masjid Contoh"
    wilayah: "32.71"
```

Cara mencari kode wilayah: buka `scraper/wilayah.json`, cari nama kab/kota di bagian `kabkota`.

Cara mencari selector: buka satu artikel di browser, klik kanan pada isi pengumuman → **Inspect**,
lihat elemen pembungkusnya (`article`, `.post-content`, `.entry-content`, dst.).

## Etika dan batasan

- **Patuh robots.txt.** Halaman yang dilarang robots.txt tidak diambil. Jeda minimal 2 detik per host.
- **Menghormati larangan penulis.** Pesan yang memuat larangan seperti "dilarang mengubah ... tanpa izin"
  dilewati beserta pesan lanjutannya. Tambahkan pola lain di `deny_patterns`.
- **Tanpa data pribadi.** Yang disimpan hanya informasi acara (tema, ustadz, waktu, tempat, tautan peta/streaming).
  Nomor HP, nomor rekening, dan nama narahubung tidak ikut disimpan.
- **Selalu menautkan sumber.** Setiap kajian menyertakan tautan ke pengumuman aslinya.
- **Sebaiknya minta izin.** Untuk sumber yang dipakai rutin, hubungi admin kanal/pengelola situs, dan
  hapus sumber bila mereka keberatan.
- Poster yang hanya berupa gambar (tanpa caption teks) tidak terbaca. Parser memakai pola teks
  dan bisa salah membaca format yang tidak lazim.

## Struktur

```
scraper/
  adapters/telegram.py   pratinjau kanal t.me/s/<kanal>, paginasi ?before=
  adapters/website.py    halaman daftar -> artikel -> teks
  parser.py              teks pengumuman -> data kajian
  wilayah.py             deteksi kab/kota dari alamat (514 kab/kota, 7.285 kecamatan)
  text.py                HTML -> teks bersih (emoji, huruf "fancy", markdown)
  http.py                robots.txt, jeda, retry
  store.py               gabung, buang kedaluwarsa, tulis JSON per kota
schema/                  JSON Schema
tests/                   test dengan cuplikan halaman asli (data pribadi disamarkan)
sources.yaml             daftar sumber
data/                    hasil (diisi GitHub Actions)
contoh-data/             contoh hasil dari 25 postingan asli
```

## Lisensi data wilayah

`scraper/wilayah.json` diolah dari [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah)
(MIT License, rujukan Kepmendagri No. 300.2.2-2430 Tahun 2025). Lihat `scraper/WILAYAH_LICENSE.txt`.

Hak atas isi pengumuman kajian tetap milik penyelenggara masing-masing.
