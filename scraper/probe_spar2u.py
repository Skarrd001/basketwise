"""One-off check: does SPAR publish prices online in a form BasketWise may read?

Answers four questions, politely (robots.txt respected, at most ~12 requests, normal delays):
  1. What do spar2u.co.za's and spar.co.za's robots.txt allow?
  2. Do their sitemaps list product pages?
  3. Does a sample product page load without a login?
  4. Does it show a price (in the HTML or in embedded JSON)?

Writes data/spar2u_probe.json. The workflow runs it once, only while that file doesn't exist.
Nothing here collects store contacts: spar.co.za's robots.txt disallows its store finder.
"""
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from common import Fetcher  # noqa: E402

log = logging.getLogger("probe")
OUT = Path(__file__).resolve().parent.parent / "data" / "spar2u_probe.json"
HOSTS = ["https://www.spar2u.co.za", "https://spar2u.co.za", "https://www.spar.co.za"]
PRODUCT_HINT = re.compile(r"/(p|product|products|prod|item)/|/p-\d|-p\d{5,}", re.I)
PRICE_TEXT = re.compile(r"\bR\s?\d{1,4}[.,]\d{2}\b")
PRICE_JSON = re.compile(r'"(price|sellingPrice|salePrice|currentPrice)"\s*:\s*"?\d', re.I)
LOGIN_HINT = re.compile(r"login|signin|sign-in|account/auth", re.I)


def sitemap_urls(f: Fetcher, url: str, depth: int = 0) -> list[str]:
    r = f.get(url, retries=1)
    if r is None:
        return []
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    if "<sitemapindex" in r.text and depth == 0:
        # Prefer a child sitemap that looks like products; read at most two.
        kids = sorted(locs, key=lambda u: 0 if re.search(r"product", u, re.I) else 1)[:2]
        out = []
        for k in kids:
            out += sitemap_urls(f, k, 1)
        return out
    return locs


def check_page(f: Fetcher, url: str) -> dict:
    r = f.get(url, retries=1)
    if r is None:
        return {"url": url, "loaded": False, "note": "blocked by robots.txt, refused, or failed"}
    return {
        "url": url,
        "loaded": True,
        "final_url": r.url,
        "status": r.status_code,
        "bytes": len(r.text),
        "login_redirect": bool(LOGIN_HINT.search(urlparse(r.url).path)),
        "prices_in_text": len(PRICE_TEXT.findall(r.text)),
        "price_fields_in_json": len(PRICE_JSON.findall(r.text)),
        "sample_prices": PRICE_TEXT.findall(r.text)[:5],
    }


def probe_host(f: Fetcher, base: str) -> dict:
    res: dict = {"host": base}
    try:
        rr = f.s.get(base + "/robots.txt", timeout=20)
        res["robots_status"] = rr.status_code
        res["robots_txt"] = rr.text[:3000] if rr.ok else ""
    except Exception as e:  # noqa: BLE001 - record any failure, never crash the run
        res["robots_status"] = f"error: {type(e).__name__}"
        res["robots_txt"] = ""
    sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", res["robots_txt"]) or [base + "/sitemap.xml"]
    res["sitemaps_listed"] = sitemaps
    urls = sitemap_urls(f, sitemaps[0])
    products = [u for u in urls if PRODUCT_HINT.search(u)]
    res["sitemap_urls"] = len(urls)
    res["product_like_urls"] = len(products)
    res["product_url_samples"] = products[:5]
    res["homepage"] = check_page(f, base + "/")
    if products:
        res["product_page"] = check_page(f, products[0])
    return res


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    f = Fetcher()
    hosts = []
    for base in HOSTS:
        try:
            hosts.append(probe_host(f, base))
        except Exception as e:  # noqa: BLE001
            hosts.append({"host": base, "error": f"{type(e).__name__}: {e}"})
    out = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "requests": f.requests_made, "hosts": hosts}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for h in hosts:
        pp = h.get("product_page") or {}
        log.info("spar-probe %s: robots %s, %s sitemap URLs (%s product-like), product page loaded=%s, "
                 "prices=%s/%s", h["host"], h.get("robots_status"), h.get("sitemap_urls"),
                 h.get("product_like_urls"), pp.get("loaded"), pp.get("prices_in_text"),
                 pp.get("price_fields_in_json"))


if __name__ == "__main__":
    main()
