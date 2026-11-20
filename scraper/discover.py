"""Weekly: map each basket item to a concrete product at each retailer, matched by barcode.

1. Pull the public product sitemaps (allowed by every retailer's robots.txt).
2. Shortlist URLs whose slug contains all the item's tokens.
3. Fetch the Checkers candidate -> canonical barcode.
4. Confirm the same barcode at Shoprite and PnP (fetching only a few candidates each).
Writes data/catalogue.json. Items that need a human eye go into data/catalogue_review.json.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from common import Fetcher, parse_size
from retailers import fetch_pnp, fetch_shoprite_group

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
log = logging.getLogger("basketwise")

SITEMAPS = {
    "checkers": "https://www.checkers.co.za/sitemap.xml",
    "shoprite": "https://www.shoprite.co.za/sitemap.xml",
    "pnp": "https://www.pnp.co.za/sitemap.xml",
}
MAX_CANDIDATES = 4


def load_sitemap_urls(f: Fetcher, index_url: str) -> list[str]:
    r = f.get(index_url)
    if not r:
        return []
    urls: list[str] = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", r.text):
        if "product" not in loc.lower() and "PRODUCT" not in loc:
            continue
        sub = f.get(loc.strip())
        if sub:
            urls += [u.strip() for u in re.findall(r"<loc>([^<]+)</loc>", sub.text)]
    return urls


def slug_of(url: str) -> str:
    if "/product/" in url:
        return url.split("/product/")[1].lower()
    if "/p/" in url:
        return url.split("/")[-3].lower()
    return url.lower()


def candidates(urls: list[str], item: dict, retailer: str = "checkers") -> list[str]:
    key = "pnp" if retailer == "pnp" else "ck"
    tokens = item.get(key) or item["tokens"]
    out = []
    for u in urls:
        s = slug_of(u)
        parts = set(s.split("-"))
        if all((t in parts) if "-" not in t else (t in s) for t in tokens) and not any(x in parts for x in item.get("exclude", [])):
            out.append(u)
    # prefer the shortest slug (least extra words = the plain variant)
    return sorted(out, key=lambda u: len(slug_of(u)))[:MAX_CANDIDATES]


def same_product(a: str, b: str) -> bool:
    """Fallback when barcodes differ (e.g. eggs packed by different packhouses)."""
    if not a or not b or parse_size(a) != parse_size(b):
        return False
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(wa & wb) / max(1, len(wa | wb)) >= 0.6


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    f = Fetcher()
    basket = json.loads((Path(__file__).parent / "basket.json").read_text())
    only = set(sys.argv[1:])
    prev = {}
    cat_path = DATA / "catalogue.json"
    if cat_path.exists():
        prev = {c["id"]: c for c in json.loads(cat_path.read_text())}

    urls = {r: load_sitemap_urls(f, sm) for r, sm in SITEMAPS.items()}
    for r, u in urls.items():
        log.info("%s: %d product URLs", r, len(u))

    catalogue, review = [], []
    for item in basket:
        if only and item["id"] not in only:
            if item["id"] in prev:
                catalogue.append(prev[item["id"]])
            continue
        entry = {k: item[k] for k in ("id", "name", "category")}
        entry["products"] = {}
        barcode = None
        ck_paths = [u.split("/product/")[1] for u in candidates(urls["checkers"], item, "checkers")]
        sr_paths = [u.split("/product/")[1] for u in candidates(urls["shoprite"], item, "shoprite")]
        pnp_codes = [u.rstrip("/").split("/p/")[-1] for u in candidates(urls["pnp"], item, "pnp")]
        pnp_seen: dict[str, dict] = {}

        want = parse_size(item["name"])

        def size_ok(rec) -> bool:
            # never let a multipack or other size stand in for the basket item
            return bool(rec) and (want is None or parse_size(rec.get("name") or "") == want)

        def set_canon(rec):
            entry["barcode"] = rec["barcode"]
            entry["canonical_name"] = rec["name"]
            return rec["barcode"]

        # 1) canonical barcode: Checkers, else Shoprite, else PnP (whoever sells it online)
        for path in ck_paths:
            rec = fetch_shoprite_group(f, "checkers", path)
            if size_ok(rec) and rec.get("barcode"):
                barcode = set_canon(rec)
                entry["products"]["checkers"] = {"path": path, "name": rec["name"], "match": "barcode"}
                # Shoprite usually shares the article number
                art = path.rsplit("-", 1)[-1]
                sr_paths = [u.split("/product/")[1] for u in urls["shoprite"] if u.endswith(art)] + sr_paths
                break
        if not barcode:
            for path in sr_paths:
                rec = fetch_shoprite_group(f, "shoprite", path)
                if size_ok(rec) and rec.get("barcode"):
                    barcode = set_canon(rec)
                    break
        if not barcode:
            for code in pnp_codes:
                rec = pnp_seen[code] = fetch_pnp(f, code) or {}
                if size_ok(rec) and rec.get("barcode"):
                    barcode = set_canon(rec)
                    break
        if not barcode:
            review.append({"id": item["id"], "reason": "not sold online at any retailer (or tokens wrong)"})
            if item["id"] in prev:
                catalogue.append(prev[item["id"]])
            continue
        # 2) Shoprite
        for path in list(dict.fromkeys(sr_paths))[:MAX_CANDIDATES]:
            rec = fetch_shoprite_group(f, "shoprite", path)
            if rec and rec.get("barcode") == barcode:
                entry["products"]["shoprite"] = {"path": path, "name": rec["name"], "match": "barcode"}
                break
        # 3) PnP: barcode first; otherwise same size + near-identical name
        fallback = None
        for code in pnp_codes:
            rec = pnp_seen.get(code)
            if rec is None:
                rec = fetch_pnp(f, code) or {}
            if not rec:
                continue
            if rec.get("barcode") == barcode:
                entry["products"]["pnp"] = {"code": code, "name": rec["name"], "match": "barcode"}
                break
            if fallback is None and size_ok(rec) and same_product(entry["canonical_name"], rec["name"]):
                fallback = {"code": code, "name": rec["name"], "match": "name+size", "barcode": rec.get("barcode")}
        if "pnp" not in entry["products"] and fallback:
            entry["products"]["pnp"] = fallback
        for r in ("checkers", "shoprite", "pnp"):
            if r not in entry["products"]:
                review.append({"id": item["id"], "reason": f"not matched at {r}", "barcode": barcode})
        catalogue.append(entry)
        log.info("%s -> %s at %s", item["id"], barcode, ", ".join(entry["products"]))

    DATA.mkdir(exist_ok=True)
    cat_path.write_text(json.dumps(catalogue, indent=1, ensure_ascii=False))
    (DATA / "catalogue_review.json").write_text(json.dumps(review, indent=1))
    log.info("catalogue: %d items, %d need review, %d requests", len(catalogue), len(review), f.requests_made)
    return 0


if __name__ == "__main__":
    sys.exit(main())
