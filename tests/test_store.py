import json
from datetime import date, datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from scraper.adapters.telegram import TelegramAdapter
from scraper.parser import parse
from scraper.store import expire, load_existing, merge, write_outputs

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schema" / "kajian.schema.json").read_text())


@pytest.fixture
def items(fixture_text):
    a = TelegramAdapter({"id": "jks", "channel": "jadwalkajiansunnah"}, fetcher=None)
    raw, _, _ = a.parse_page(fixture_text("telegram_jadwalkajiansunnah.html"))
    return [p for p in (parse(r) for r in raw) if p]


def test_merge_dedupe_dan_sumber(items):
    t1 = datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)
    a = merge({}, items, t1)
    dup = dict(items[0])
    dup["sumber"] = [{**items[0]["sumber"][0], "url": "https://contoh.id/lain"}]
    b = merge(a, [dup], t2)
    assert len(b) == len(a)
    k = b[items[0]["id"]]
    assert len(k["sumber"]) == 2
    assert k["pertama_dilihat"] < k["terakhir_dilihat"]


def test_expire(items):
    m = merge({}, items, datetime(2026, 10, 11, tzinfo=timezone.utc))
    sisa = expire(m, date(2026, 10, 12))
    assert all(k["tanggal"] is None or k["tanggal"] >= "2026-10-12" for k in sisa.values())
    assert any(k["tanggal"] is None for k in sisa.values())  # kajian rutin tetap
    assert not expire(m, date(2027, 1, 1), rutin_ttl_days=45)


def test_tulis_output_dan_validasi_skema(items, tmp_path):
    now = datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc)
    m = merge({}, items, now)
    meta = write_outputs(tmp_path, m, now, [{"id": "jks", "status": "ok"}])
    data = json.loads((tmp_path / "kajian.json").read_text())
    jsonschema.validate(data, SCHEMA)
    assert data["jumlah"] == meta["jumlah_kajian"] == len(items)
    index = json.loads((tmp_path / "kota" / "index.json").read_text())
    slugs = {k["slug"] for k in index["kota"]}
    assert {"kota-bekasi", "kota-depok", "kota-makassar", "online"} <= slugs
    for k in index["kota"]:
        f = json.loads((tmp_path / k["file"]).read_text())
        assert f["jumlah"] == k["jumlah"]
    assert set(load_existing(tmp_path)) == set(m)
