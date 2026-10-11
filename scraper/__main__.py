"""CLI.

  python -m scraper run  --config sources.yaml --out data          # ambil semua sumber
  python -m scraper run  --config sources.yaml --source jks --dry-run
  python -m scraper coba < pengumuman.txt                           # uji parser pada satu teks
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .adapters import ADAPTERS
from .http import DEFAULT_UA, Fetcher
from .parser import RawItem, parse
from .store import WIB, expire, load_existing, merge, write_outputs
from .text import normalize

log = logging.getLogger("scraper")


def run(args) -> int:
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    settings = cfg.get("pengaturan", {})
    fetcher = Fetcher(user_agent=settings.get("user_agent") or DEFAULT_UA,
                      delay=float(settings.get("jeda_detik", 2)))
    now = datetime.now(timezone.utc)
    hasil, meta_sumber = [], []
    for src in cfg["sumber"]:
        if args.source and src["id"] != args.source:
            continue
        if src.get("aktif", True) is False:
            continue
        adapter = ADAPTERS[src["tipe"]](src, fetcher)
        try:
            raw = adapter.fetch(now)
            parsed = [p for p in (parse(r) for r in raw) if p]
            hasil.extend(parsed)
            status = "ok"
        except Exception as e:  # satu sumber gagal tidak boleh menghentikan yang lain
            log.exception("Sumber %s gagal", src["id"])
            raw, parsed, status = [], [], f"gagal: {e.__class__.__name__}"
        log.info("[%s] %d pengumuman, %d jadwal terbaca", src["id"], len(raw), len(parsed))
        url = f"https://t.me/s/{src['channel']}" if src["tipe"] == "telegram" else src.get("list_url")
        meta_sumber.append({"id": src["id"], "nama": adapter.name, "tipe": src["tipe"], "url": url,
                            "status": status, "pengumuman": len(raw), "jadwal": len(parsed)})

    if args.dry_run:
        json.dump(hasil, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    out = Path(args.out)
    items = merge(load_existing(out), hasil, now)
    items = expire(items, now.astimezone(WIB).date(), int(settings.get("rutin_ttl_hari", 45)))
    meta = write_outputs(out, items, now, meta_sumber)
    log.info("Selesai: %d kajian di %d kota", meta["jumlah_kajian"], meta["jumlah_kota"])
    return 0


def coba(args) -> int:
    teks = normalize(sys.stdin.read())
    item = RawItem(source_id="coba", source_name="uji manual", url="", text=teks,
                   posted_at=datetime.now(timezone.utc))
    print(json.dumps(parse(item), ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m scraper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="ambil semua sumber dan tulis JSON")
    r.add_argument("--config", default="sources.yaml")
    r.add_argument("--out", default="data")
    r.add_argument("--source", help="hanya jalankan satu sumber (id)")
    r.add_argument("--dry-run", action="store_true", help="cetak hasil, jangan tulis file")
    r.set_defaults(func=run)
    c = sub.add_parser("coba", help="uji parser pada teks dari stdin")
    c.set_defaults(func=coba)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
