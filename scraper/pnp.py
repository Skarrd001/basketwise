"""Pick n Pay: grows coverage a little every morning, inside PnP's robots.txt rules.

PnP only allows one request per 10 s, 04:00-08:45 UTC, so there is no bulk option. Instead:
  * data/pnp_map.json remembers every PnP product we've matched to a barcode, with its last price.
  * Each run alternates two jobs until PnP's window closes or the time budget runs out:
      refresh  - re-price the mapped products with the OLDEST prices first
      discover - take an unmatched barcode, find the most similar PnP product name in PnP's public
                 sitemap (no request), fetch it once, and keep it only if the barcode (or brand +
                 size + near-identical name) matches.
  * Old prices stay in the app, labelled with their date, until their turn to refresh comes round.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import Fetcher, in_visit_window, parse_size
from retailers import fetch_pnp, now

log = logging.getLogger("basketwise")
ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "data" / "pnp_map.json"
STOP = {"and", "the", "with", "in", "of", "for", "a", "pnp", "x", "pack", "ea"}
RETRY_MISS_DAYS = 30


def _tokens(text: str) -> set[str]:
    t = re.sub(r"(\d+)[.,](\d+)", r"\1\2", text.lower())  # 2.5kg -> 25kg (matches how slugs drop the dot)
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP}


def _slug_size(slug: str):
    s = re.sub(r"(\d+)-(\d+)(kg|g|ml|l)\b", r"\1.\2\3", slug)  # 2-5kg -> 2.5kg
    return parse_size(s.replace("-", " "))


class PnpIndex:
    """All PnP product URLs from the public sitemap, indexed for name matching."""

    def __init__(self, f: Fetcher):
        self.by_first: dict[str, list] = {}
        self.count = 0
        r = f.get("https://www.pnp.co.za/sitemap.xml")
        if not r:
            return
        for loc in re.findall(r"<loc>([^<]+)</loc>", r.text):
            if "PRODUCT" not in loc:
                continue
            sub = f.get(loc.strip())
            if not sub:
                continue
            for u in re.findall(r"<loc>([^<]+)</loc>", sub.text):
                if "/p/" not in u:
                    continue
                slug = u.strip().rstrip("/").split("/")[-3].lower()
                code = u.strip().rstrip("/").split("/p/")[-1]
                toks = _tokens(slug.replace("-", " "))
                first = slug.split("-")[0]
                self.by_first.setdefault(first, []).append((toks, _slug_size(slug), code, slug))
                self.count += 1

    def best(self, name: str, brand: str | None):
        want = parse_size(name)
        toks = _tokens(name)
        keys = {w for w in re.findall(r"[a-z0-9]+", (brand or name).lower())[:1]}
        keys |= {re.findall(r"[a-z0-9]+", name.lower())[0]} if re.findall(r"[a-z0-9]+", name.lower()) else set()
        best, best_score = None, 0.0
        for k in keys:
            for ptoks, psize, code, slug in self.by_first.get(k, []):
                if want and psize != want:
                    continue
                score = len(toks & ptoks) / max(1, len(toks | ptoks))
                if score > best_score:
                    best, best_score = (code, slug), score
        return (best, best_score) if best_score >= 0.5 else (None, best_score)


def load_map() -> dict:
    if MAP_PATH.exists():
        return json.loads(MAP_PATH.read_text(encoding="utf-8"))
    return {"products": {}, "misses": {}}


def save_map(m: dict) -> None:
    MAP_PATH.write_text(json.dumps(m, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def _same_product(a: str, b: str) -> bool:
    if not a or not b or parse_size(a) != parse_size(b):
        return False
    wa, wb = _tokens(a), _tokens(b)
    return len(wa & wb) / max(1, len(wa | wb)) >= 0.6


def run_pnp(candidates: list[dict], budget_min: float) -> dict:
    """candidates: [{barcode, barcodes, name, brand}] in priority order. Returns stats; updates the map file."""
    f = Fetcher()
    f.deadline = time.time() + budget_min * 60
    pmap = load_map()
    products, misses = pmap["products"], pmap["misses"]
    stats = {"refreshed": 0, "discovered": 0, "tried": 0, "index": 0, "window": in_visit_window("www.pnp.co.za")}
    if not stats["window"]:
        log.info("pnp: outside robots.txt visit window - keeping last prices")
        return stats | {"mapped": len(products)}

    index = PnpIndex(f)
    stats["index"] = index.count
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETRY_MISS_DAYS)).strftime("%Y-%m-%d")
    todo_discover = [c for c in candidates if c["barcode"] not in products and misses.get(c["barcode"], "") < cutoff]
    todo_refresh = sorted(products.items(), key=lambda kv: kv[1].get("fetched_at", ""))
    today = now()[:10]
    di = ri = 0
    turn = 0
    last_save = time.time()
    while time.time() < f.deadline and in_visit_window("www.pnp.co.za") and "www.pnp.co.za" not in f.blocked_hosts:
        do_refresh = (turn % 2 == 0 and ri < len(todo_refresh)) or di >= len(todo_discover)
        turn += 1
        if do_refresh:
            if ri >= len(todo_refresh):
                break
            bc, ref = todo_refresh[ri]
            ri += 1
            if ref.get("fetched_at", "")[:10] == today:
                continue
            rec = fetch_pnp(f, ref["code"])
            if rec:
                ref.update(price=rec["price"], promo=rec.get("promo"), url=rec["url"], name=rec["name"], fetched_at=rec["fetched_at"])
                stats["refreshed"] += 1
        else:
            c = todo_discover[di]
            di += 1
            hit, _ = index.best(c["name"], c.get("brand"))
            if not hit:
                misses[c["barcode"]] = today
                continue
            code, _slug = hit
            stats["tried"] += 1
            rec = fetch_pnp(f, code)
            if not rec:
                misses[c["barcode"]] = today
                continue
            match = "barcode" if rec.get("barcode") in set(c["barcodes"]) else (
                "name+size" if _same_product(c["name"], rec["name"]) else None)
            if match:
                products[c["barcode"]] = {"code": code, "match": match, "name": rec["name"], "price": rec["price"],
                                          "promo": rec.get("promo"), "url": rec["url"], "fetched_at": rec["fetched_at"]}
                stats["discovered"] += 1
            else:
                misses[c["barcode"]] = today
        if time.time() - last_save > 300:  # save progress every 5 min, so an interrupted run keeps its work
            save_map(pmap)
            last_save = time.time()
    save_map(pmap)
    stats["mapped"] = len(products)
    log.info("pnp: %s", stats)
    return stats
