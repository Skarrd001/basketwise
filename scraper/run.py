"""Daily: fetch today's price for every catalogue item at every retailer.

Outputs (all static JSON, served straight to the web app):
  data/prices.json            latest prices + per-retailer health
  data/history/YYYY-MM-DD.json compact daily snapshot (price history = future data product)
Exit code 1 if a retailer that worked yesterday collapses, so the scheduler e-mails the owner.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import Fetcher
from retailers import (DELIVERY_FEES, RETAILERS, fetch_pnp, fetch_shoprite_group,
                       fetch_spar_specials, fetch_woolworths_category, now)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
log = logging.getLogger("basketwise")

RETAILER_NOTES = {
    "checkers": "Online (Sixty60) price, which Checkers states matches in-store. Xtra Savings card deals shown separately.",
    "shoprite": "Online price. Xtra Savings card deals shown separately.",
    "pnp": "Online price for PnP's default pricing region. Smart Shopper deals shown where published. Crawled only 04:00-08:45 UTC per PnP's robots.txt; between runs, prices are carried forward.",
    "woolworths": "Not available: woolworths.co.za blocks automated access. We do not bypass this.",
    "spar": "SPAR stores set their own prices; only published SPAR specials are available.",
}
STALE_AFTER_DAYS = 3


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    catalogue = json.loads((DATA / "catalogue.json").read_text())
    prev = json.loads((DATA / "prices.json").read_text()) if (DATA / "prices.json").exists() else {}
    prev_items = {i["id"]: i for i in prev.get("items", [])}
    f = Fetcher()

    ok = {r: 0 for r in RETAILERS}
    tried = {r: 0 for r in RETAILERS}
    items = []

    spar = {}
    try:
        for rec in fetch_spar_specials(f):
            # Regional specials only apply in that SPAR region; until we map regions to locations,
            # use national specials only so we never show a price the shopper can't get.
            if rec["region"] == "national":
                spar[rec["barcode"]] = rec
    except Exception as e:  # never let one retailer kill the run
        log.exception("spar failed: %s", e)

    for entry in catalogue:
        out = {k: entry.get(k) for k in ("id", "name", "category", "barcode", "canonical_name")}
        out["prices"] = {}
        old = (prev_items.get(entry["id"]) or {}).get("prices", {})
        for r, ref in entry.get("products", {}).items():
            tried[r] += 1
            rec = None
            try:
                if r in ("checkers", "shoprite"):
                    rec = fetch_shoprite_group(f, r, ref["path"])
                elif r == "pnp":
                    rec = fetch_pnp(f, ref["code"])
            except Exception as e:
                log.exception("%s %s failed: %s", r, entry["id"], e)
            expected = {entry.get("barcode"), ref.get("barcode")} - {None}
            if rec and (not rec.get("barcode") or rec["barcode"] in expected):
                ok[r] += 1
                out["prices"][r] = _slim(rec)
            elif r in old:
                # carry yesterday's price forward, flagged, until it is too old to trust
                age = _age_days(old[r]["fetched_at"])
                if age <= STALE_AFTER_DAYS:
                    out["prices"][r] = {**old[r], "stale": True}
        if entry.get("barcode") in spar:
            tried["spar"] += 1
            ok["spar"] += 1
            out["prices"]["spar"] = _slim(spar[entry["barcode"]])
        items.append(out)

    # Woolworths: one honest attempt per run so we notice if they ever unblock us.
    tried["woolworths"] = 1
    if fetch_woolworths_category(f, "browse/food-south-africa/milk-dairy-eggs/milk"):
        ok["woolworths"] = 1

    # A retailer skipped for its robots.txt visit window (e.g. PnP outside 04:00-08:45 UTC) is
    # "paused", not broken - carry its last status forward so it doesn't trip the regression alarm.
    from common import in_visit_window
    paused = {r for r, meta in RETAILERS.items()
              if ok[r] == 0 and not in_visit_window(meta["domain"])}
    health = {}
    for r, meta in RETAILERS.items():
        cov = sum(1 for i in items if r in i["prices"] and not i["prices"][r].get("stale"))
        fresh = sum(1 for i in items if r in i["prices"])  # incl. carried-forward
        status = "ok" if cov >= 0.7 * max(1, len(items)) else ("partial" if cov else "unavailable")
        if r in paused:
            status = "paused"  # not crawled this run (robots.txt visit window); prices carried forward
        if r == "spar" and cov:
            status = "specials-only"
        health[r] = {"name": meta["name"], "status": status, "items_priced": cov,
                     "requests_ok": ok[r], "requests_tried": tried[r], "note": RETAILER_NOTES[r],
                     "delivery": DELIVERY_FEES.get(r)}

    doc = {"generated_at": now(), "item_count": len(items), "retailers": health, "items": items}
    DATA.mkdir(exist_ok=True)
    (DATA / "prices.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    hist = DATA / "history"
    hist.mkdir(exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (hist / f"{day}.json").write_text(json.dumps(
        {i["id"]: {r: p["price"] for r, p in i["prices"].items() if not p.get("stale")} for i in items},
        separators=(",", ":")))
    _write_trends(hist, DATA)
    log.info("done: %s, %d requests", {r: h["status"] for r, h in health.items()}, f.requests_made)

    # Alert: a retailer that was fine last run and is now down means their site changed.
    regressions = [r for r, h in health.items()
                   if h["status"] in ("unavailable", "partial")
                   and prev.get("retailers", {}).get(r, {}).get("status") == "ok"]
    if regressions:
        log.error("REGRESSION: %s stopped returning prices - scraper needs attention", regressions)
        return 1
    return 0


def _write_trends(hist, data_dir, days: int = 90) -> None:
    """Summarise history into one small file the ops console charts: the cost of a reference
    basket (one of each item a chain priced that day) per retailer over time."""
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
    keep = ("price", "regular_price", "promo", "promo_price", "in_stock", "url", "region", "name", "fetched_at")
    return {k: rec.get(k) for k in keep if rec.get(k) is not None}


def _age_days(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return 999
    return (datetime.now(timezone.utc) - t).total_seconds() / 86400


if __name__ == "__main__":
    sys.exit(main())
