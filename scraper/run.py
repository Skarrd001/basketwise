"""Daily: refresh prices for thousands of grocery products.

  Checkers + Shoprite - whole grocery range via the category listing endpoint (100 products/request)
  Pick n Pay          - rolling: refresh oldest prices + match new barcodes, inside its robots.txt window
  SPAR                - national specials, matched by barcode
  Woolworths          - one honest attempt (they block bots; we don't bypass that)

The three big retailers run in parallel threads (different sites, each with its own polite delay).
Prices that couldn't be refreshed today are kept, with their date, for up to KEEP_DAYS.

Outputs: data/prices.json (the app's data), data/history/<date>.json (reference basket), data/trends.json.
Exit code 1 if a retailer that worked last run collapses, so the scheduler e-mails the owner.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from common import Fetcher, in_visit_window
from pnp import load_map, run_pnp
from retailers import (DELIVERY_FEES, RETAILERS, fetch_catalogue_bulk, fetch_spar_specials,
                       fetch_woolworths_category, now)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
log = logging.getLogger("basketwise")
KEEP_DAYS = 21  # show an older price, labelled with its date, for up to this long

RETAILER_NOTES = {
    "checkers": "Online (Sixty60) price, which Checkers states matches in-store. Refreshed daily. Xtra Savings card deals shown separately.",
    "shoprite": "Online price, refreshed daily. Xtra Savings card deals shown separately.",
    "pnp": "Online price for PnP's default pricing region. PnP allows one request every 10 seconds, early mornings only, so prices refresh on a rolling basis and each shows its date. Coverage grows every day.",
    "woolworths": "Not available: woolworths.co.za blocks automated access. We do not bypass this.",
    "spar": "SPAR stores set their own prices; only published national SPAR specials are available.",
}
STAPLES = ["milk-dairy-and-eggs", "bakery", "food-cupboard", "household-and-cleaning", "toiletries",
           "beverages-juices-and-cordials", "coffee-tea-and-hot-drinks", "frozen-foods", "baby",
           "sweets-and-snacks", "deli-and-chilled-meats", "meat-and-poultry", "fruit-veg-and-salads",
           "fish-and-seafood", "ready-meals-and-desserts", "pets"]


def label(dept: str) -> str:
    return dept.replace("-and-", " & ").replace("-", " ").capitalize()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(message)s")
    prev = json.loads((DATA / "prices.json").read_text(encoding="utf-8")) if (DATA / "prices.json").exists() else {}
    prev_items = {i["id"]: i for i in prev.get("items", [])}
    preset = json.loads((Path(__file__).parent / "preset.json").read_text(encoding="utf-8"))
    preset_ids = [p["barcode"] for p in preset]

    # ---- 1. Checkers + Shoprite in parallel
    bulk: dict[str, list] = {}
    bulk_stats: dict[str, dict] = {}

    def do_bulk(r: str) -> None:
        try:
            bulk[r], bulk_stats[r] = fetch_catalogue_bulk(Fetcher(), r, log)
        except Exception as e:  # never let one retailer kill the run
            log.exception("%s bulk failed: %s", r, e)
            bulk[r], bulk_stats[r] = [], {"error": str(e)}

    threads = [threading.Thread(target=do_bulk, args=(r,), name=r) for r in ("checkers", "shoprite")]
    for t in threads:
        t.start()

    # ---- 2. Build the product list from what Checkers/Shoprite returned (falls back to last run's list)
    for t in threads:
        t.join()
    items: dict[str, dict] = {}
    alias: dict[str, str] = {}  # any barcode -> canonical id
    for r in ("checkers", "shoprite"):
        for rec in bulk.get(r, []):
            cid = next((alias[b] for b in rec["barcodes"] if b in alias), rec["barcode"])
            it = items.setdefault(cid, {"id": cid, "name": rec["name"], "brand": rec.get("brand"),
                                        "category": label(rec["department"]), "dept": rec["department"],
                                        "barcodes": set(), "prices": {}})
            it["barcodes"].update(rec["barcodes"])
            for b in rec["barcodes"]:
                alias[b] = cid
            it["prices"][r] = _slim(rec)

    # ---- 3. Pick n Pay: rolling refresh + discovery (needs the product list for its candidates)
    def prio(it):
        both = "checkers" in it["prices"] and "shoprite" in it["prices"]
        d = STAPLES.index(it["dept"]) if it.get("dept") in STAPLES else 99
        return (it["id"] not in preset_ids, not both, d)

    cands = [{"barcode": it["id"], "barcodes": sorted(it["barcodes"]), "name": it["name"], "brand": it.get("brand")}
             for it in sorted(items.values(), key=prio)]
    pnp_budget = float(os.environ.get("BASKETWISE_PNP_BUDGET_MIN", "200"))
    pnp_stats = {}
    try:
        pnp_stats = run_pnp(cands, pnp_budget)
    except Exception as e:
        log.exception("pnp failed: %s", e)
        pnp_stats = {"error": str(e)}

    # ---- 4. SPAR specials + Woolworths check
    f = Fetcher()
    spar = {}
    try:
        for rec in fetch_spar_specials(f):
            # Regional specials only apply in that SPAR region; until regions are mapped to locations,
            # use national specials only so we never show a price the shopper can't get.
            if rec["region"] == "national":
                spar[rec["barcode"]] = rec
    except Exception as e:
        log.exception("spar failed: %s", e)
    ww_ok = bool(fetch_woolworths_category(f, "browse/food-south-africa/milk-dairy-eggs/milk"))

    # ---- 5. Merge PnP + SPAR + carried-forward prices
    pmap = load_map()["products"]
    today = now()[:10]
    for bc, e in pmap.items():
        cid = alias.get(bc, bc)
        if cid not in items and cid in prev_items:  # product not in today's Checkers/Shoprite lists
            old = prev_items[cid]
            items[cid] = {"id": cid, "name": old["name"], "brand": old.get("brand"), "category": old.get("category"),
                          "barcodes": {cid}, "prices": {}}
        if cid in items and e.get("price") and _age_days(e.get("fetched_at")) <= KEEP_DAYS:
            items[cid]["prices"]["pnp"] = {"price": e["price"], "promo": (e.get("promo") or "")[:80] or None,
                                           "url": e.get("url"), "fetched_at": e.get("fetched_at"),
                                           **({"stale": True} if (e.get("fetched_at") or "")[:10] != today else {})}
    for it in items.values():
        hit = next((spar[b] for b in it["barcodes"] if b in spar), None)
        if hit:
            it["prices"]["spar"] = _slim(hit)
    # a retailer whose bulk fetch failed today keeps its previous prices (dated) for a while
    for r in ("checkers", "shoprite"):
        if bulk.get(r):
            continue
        for cid, old in prev_items.items():
            p = (old.get("prices") or {}).get(r)
            if p and _age_days(p.get("fetched_at")) <= KEEP_DAYS:
                it = items.setdefault(cid, {"id": cid, "name": old["name"], "brand": old.get("brand"),
                                            "category": old.get("category"), "barcodes": {cid}, "prices": {}})
                it["prices"].setdefault(r, {**p, "stale": True})

    # Keep products that at least two retailers price (comparable), plus the preset basket.
    out_items = []
    for it in items.values():
        if len(it["prices"]) >= 2 or it["id"] in preset_ids:
            out_items.append({"id": it["id"], "name": it["name"], "brand": it.get("brand"),
                              "category": it.get("category"), "prices": it["prices"]})
    out_items.sort(key=lambda i: (i.get("category") or "", i["name"]))

    # ---- 6. Health
    health = {}
    for r, meta in RETAILERS.items():
        fresh = sum(1 for i in out_items if r in i["prices"] and not i["prices"][r].get("stale"))
        anyp = sum(1 for i in out_items if r in i["prices"])
        if r in ("checkers", "shoprite"):
            got, prev_n = len(bulk.get(r, [])), prev.get("retailers", {}).get(r, {}).get("catalogue_size", 0)
            status = "ok" if got and got >= 0.6 * max(prev_n, 1) else ("partial" if got else "unavailable")
            extra = {"catalogue_size": got, "requests": bulk_stats.get(r, {}).get("requests", 0)}
        elif r == "pnp":
            status = ("paused" if not pnp_stats.get("window") else
                      "ok" if pnp_stats.get("refreshed", 0) + pnp_stats.get("discovered", 0) else "unavailable")
            extra = {k: pnp_stats.get(k) for k in ("refreshed", "discovered", "mapped", "index")}
        elif r == "spar":
            status = "specials-only" if anyp else "unavailable"
            extra = {"specials_found": len(spar)}
        else:
            status = "ok" if ww_ok else "unavailable"
            extra = {}
        health[r] = {"name": meta["name"], "status": status, "items_priced": anyp, "items_fresh": fresh,
                     "note": RETAILER_NOTES[r], "delivery": DELIVERY_FEES.get(r), **extra}

    doc = {"generated_at": now(), "item_count": len(out_items), "retailers": health,
           "preset": [{"id": p["barcode"], "qty": p["qty"]} for p in preset], "items": out_items}
    DATA.mkdir(exist_ok=True)
    (DATA / "prices.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # History: the reference (preset) basket only, so the repo stays small.
    hist = DATA / "history"
    hist.mkdir(exist_ok=True)
    byid = {i["id"]: i for i in out_items}
    snap = {pid: {r: p["price"] for r, p in byid[pid]["prices"].items() if not p.get("stale")}
            for pid in preset_ids if pid in byid}
    (hist / f"{datetime.now(timezone.utc):%Y-%m-%d}.json").write_text(json.dumps(snap, separators=(",", ":")))
    _write_trends(hist, DATA)
    log.info("done: %d items; %s", len(out_items), {r: h["status"] for r, h in health.items()})

    regressions = [r for r, h in health.items()
                   if h["status"] in ("unavailable", "partial")
                   and prev.get("retailers", {}).get(r, {}).get("status") == "ok"]
    if regressions:
        log.error("REGRESSION: %s stopped returning prices - scraper needs attention", regressions)
        return 1
    return 0


def _write_trends(hist, data_dir, days: int = 90) -> None:
    """Cost of the reference basket per retailer over time, for the ops chart."""
    files = sorted(hist.glob("20*.json"))[-days:]
    series: dict[str, list] = {}
    dates = []
    for fp in files:
        snap = json.loads(fp.read_text())
        dates.append(fp.stem)
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for prices in snap.values():
            for r, v in prices.items():
                totals[r] = totals.get(r, 0) + v
                counts[r] = counts.get(r, 0) + 1
        for r, t in totals.items():
            series.setdefault(r, []).append({"date": fp.stem, "total": round(t, 2), "items": counts[r]})
    (data_dir / "trends.json").write_text(json.dumps({"dates": dates, "series": series}, separators=(",", ":")))


def _slim(rec: dict) -> dict:
    out = {k: rec.get(k) for k in ("price", "promo", "promo_price", "url", "fetched_at") if rec.get(k) is not None}
    if out.get("promo"):
        out["promo"] = out["promo"][:80]
    return out


def _age_days(iso: str | None) -> float:
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return 999
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 86400


if __name__ == "__main__":
    sys.exit(main())
