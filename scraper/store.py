"""Menggabungkan hasil baru dengan data lama, membuang yang kedaluwarsa, lalu menulis JSON."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WIB = timezone(timedelta(hours=7))
SKEMA_VERSI = "1.0"


def load_existing(out_dir: Path) -> dict[str, dict]:
    f = out_dir / "kajian.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    return {k["id"]: k for k in data.get("kajian", [])}


def merge(existing: dict[str, dict], new_items: list[dict], now: datetime) -> dict[str, dict]:
    stamp = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    out = dict(existing)
    for item in new_items:
        old = out.get(item["id"])
        if old:
            urls = {s["url"] for s in old["sumber"]}
            sumber = old["sumber"] + [s for s in item["sumber"] if s["url"] not in urls]
            merged = {**old, **{k: v for k, v in item.items() if v not in (None, [], "")}}
            merged["sumber"] = sumber
            merged["pertama_dilihat"] = old.get("pertama_dilihat", stamp)
            merged["terakhir_dilihat"] = stamp
            out[item["id"]] = merged
        else:
            out[item["id"]] = {**item, "pertama_dilihat": stamp, "terakhir_dilihat": stamp}
    return out


def expire(items: dict[str, dict], today: date, rutin_ttl_days: int = 45) -> dict[str, dict]:
    """Buang kajian yang sudah lewat. Kajian tanpa tanggal (rutin) dibuang bila lama tak terlihat."""
    keep = {}
    for k, it in items.items():
        if it.get("tanggal"):
            if date.fromisoformat(it["tanggal"]) >= today:
                keep[k] = it
        else:
            seen = datetime.fromisoformat(it["terakhir_dilihat"]).date()
            if (today - seen).days <= rutin_ttl_days:
                keep[k] = it
    return keep


def _sort_key(it: dict):
    return (it.get("tanggal") or "9999-12-31", it["waktu"].get("mulai") or "99:99",
            (it.get("wilayah") or {}).get("kabkota", "~"), it["id"])


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(out_dir: Path, items: dict[str, dict], now: datetime, sources_meta: list[dict]) -> dict:
    gen = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    semua = sorted(items.values(), key=_sort_key)
    _dump(out_dir / "kajian.json", {"skema": SKEMA_VERSI, "dibuat": gen, "jumlah": len(semua), "kajian": semua})

    per_kota: dict[str, list[dict]] = {}
    for it in semua:
        slug = (it.get("wilayah") or {}).get("slug") or ("online" if it.get("mode") == "online" else "tanpa-wilayah")
        per_kota.setdefault(slug, []).append(it)

    kota_dir = out_dir / "kota"
    if kota_dir.exists():
        for f in kota_dir.glob("*.json"):
            f.unlink()
    index = []
    for slug, lst in sorted(per_kota.items()):
        w = lst[0].get("wilayah") or {}
        _dump(kota_dir / f"{slug}.json", {"skema": SKEMA_VERSI, "dibuat": gen, "wilayah": w or None,
                                           "jumlah": len(lst), "kajian": lst})
        index.append({"slug": slug, "kabkota": w.get("kabkota"), "provinsi": w.get("provinsi"),
                      "kode": w.get("kode"), "jumlah": len(lst), "file": f"kota/{slug}.json"})
    _dump(kota_dir / "index.json", {"skema": SKEMA_VERSI, "dibuat": gen, "kota": index})

    meta = {"skema": SKEMA_VERSI, "dibuat": gen, "jumlah_kajian": len(semua), "jumlah_kota": len(index),
            "sumber": sources_meta,
            "catatan": "Data diambil otomatis dari pengumuman publik. Selalu cek sumber asli sebelum berangkat."}
    _dump(out_dir / "meta.json", meta)
    return meta
