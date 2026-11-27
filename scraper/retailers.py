"""Per-retailer price fetchers. Each returns a normalised dict or None.

Normalised price record:
  {retailer, product_id, name, brand, barcode, price, regular_price, promo, url, region, fetched_at}
`price` is what a shopper pays today without a loyalty card; `promo` describes card/multibuy deals.
"""
from __future__ import annotations

import base64
from html import unescape
import json
import re
from datetime import datetime, timezone

from common import Fetcher, extract_json_script

RETAILERS = {
    "checkers": {"name": "Checkers", "domain": "www.checkers.co.za"},
    "shoprite": {"name": "Shoprite", "domain": "www.shoprite.co.za"},
    "pnp": {"name": "Pick n Pay", "domain": "www.pnp.co.za"},
    "woolworths": {"name": "Woolworths", "domain": "www.woolworths.co.za"},
    "spar": {"name": "SPAR", "domain": "www.spar.co.za"},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Home-delivery fees, captured live where a site exposes them, else sensible editable defaults (ZAR).
# The app lets the shopper override these. "free_over" = order value above which delivery is free.
DELIVERY_FEES: dict[str, dict] = {
    "checkers": {"service": "Sixty60", "fee": 37, "min_order": 150, "free_over": None},
    "shoprite": {"service": "Sixty60/Checkers", "fee": 37, "min_order": 150, "free_over": None},
    "pnp": {"service": "PnP asap!/online", "fee": 35, "min_order": 150, "free_over": None},
    "woolworths": {"service": "Woolies Dash", "fee": 35, "min_order": 250, "free_over": None},
    "spar": {"service": "SPAR2U", "fee": 40, "min_order": 150, "free_over": None},
}


# ---------------------------------------------------------------- Checkers / Shoprite (same platform)
def fetch_shoprite_group(f: Fetcher, retailer: str, product_path: str) -> dict | None:
    url = f"https://{RETAILERS[retailer]['domain']}/product/{product_path}"
    r = f.get(url)
    if not r:
        return None
    data = extract_json_script(r.text, "__NEXT_DATA__")
    pp = (data or {}).get("props", {}).get("pageProps", {})
    # Opportunistically capture live delivery fees (same on every page); run.py reads this.
    fees = pp.get("serverDeliveryFees") or {}
    sixty = fees.get("sixty-min-delivery") or fees.get("one-day-delivery")
    if sixty and sixty.get("deliveryFee") is not None:
        DELIVERY_FEES[retailer].update(fee=sixty["deliveryFee"], min_order=sixty.get("minimumOrderValue"))
    p = pp.get("serverProduct")
    # price 0 = not ranged/sold online at the site's default store: treat as unavailable, never as R0
    if not p or not p.get("price") or float(p["price"]) <= 0:
        return None
    promo = None
    bb = p.get("bonusBuy") or {}
    if bb.get("name"):
        promo = bb["name"].strip()  # e.g. "Now R29.99" (usually an Xtra Savings card deal)
    price = float(p.get("discountedPrice") or p["price"])
    return {
        "retailer": retailer,
        "product_id": p.get("articleNumber"),
        "name": (p.get("displayName") or p.get("name") or "").strip(),
        "brand": p.get("brand"),
        "barcode": (p.get("barcodes") or [None])[0],
        "price": price,
        "regular_price": float(p.get("oldPrice", 0)) / 100 if p.get("oldPrice") else float(p["price"]),
        "promo": promo,
        "promo_price": _promo_price(promo),
        "in_stock": not p.get("outOfStock", False),
        "url": url,
        "region": "national-online",
        "fetched_at": now(),
    }


def _promo_price(text: str | None) -> float | None:
    if not text:
        return None
    m = re.fullmatch(r"\s*Now\s*R\s*(\d+(?:[.,]\d{2})?)\s*", text, re.I)
    return float(m.group(1).replace(",", ".")) if m else None


# ---------------------------------------------------------------- Pick n Pay
PNP_API = "https://www.pnp.co.za/pnphybris/v2/pnp-spa/products/{code}?fields=FULL&storeCode={store}&lang=en&curr=ZAR"
PNP_DEFAULT_STORE = "WC21"  # the store the PnP site prices anonymous visitors against


def fetch_pnp(f: Fetcher, code: str, store: str = PNP_DEFAULT_STORE) -> dict | None:
    # This is the same JSON endpoint pnp.co.za's own product page loads in every visitor's browser.
    r = f.get(PNP_API.format(code=code, store=store), accept_json=True)
    if not r:
        return None
    try:
        d = r.json()
    except json.JSONDecodeError:
        return None
    price = (d.get("price") or {}).get("value")
    if not price or float(price) <= 0:
        return None
    barcode = None
    for c in d.get("classifications", []):
        for feat in c.get("features", []):
            if feat.get("name") == "unit_barcode":
                vals = feat.get("featureValues") or []
                barcode = vals[0].get("value") if vals else None
    old = (d.get("price") or {}).get("oldPrice") or 0
    promos = [p.get("description") or p.get("title") for p in d.get("potentialPromotions", []) if p]
    slug = re.sub(r"[^a-z0-9]+", "-", d.get("name", "").lower()).strip("-")
    return {
        "retailer": "pnp",
        "product_id": code,
        "name": d.get("name"),
        "brand": d.get("brand"),
        "barcode": barcode,
        "price": float(price),
        "regular_price": float(old) if old else float(price),
        "promo": "; ".join(x for x in promos if x) or None,
        "promo_price": None,
        "in_stock": (d.get("stock") or {}).get("stockLevelStatus") != "outOfStock",
        "url": f"https://www.pnp.co.za/{slug}/p/{code}",
        "region": f"store:{store}",
        "fetched_at": now(),
    }


# ---------------------------------------------------------------- Woolworths
def fetch_woolworths_category(f: Fetcher, browse_path: str) -> list[dict]:
    """One category page returns every product in it with 3 regional price zones (p10/p30/p60).

    NOTE: woolworths.co.za currently answers self-identified bots with a block page. We do not
    disguise our crawler, so this returns [] until Woolworths allows BasketWiseBot or grants a feed.
    """
    url = f"https://www.woolworths.co.za/{browse_path.lstrip('/')}"
    r = f.get(url)
    if not r or "/400" in r.url:
        return []
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", r.text, re.S)
    if not m:
        return []
    out = []
    for m2 in re.finditer(r'"data":\{("id":"\d+".*?|"bu":\d+,"id":"\d+".*?)"stockAvailable":\d+\}', r.text):
        try:
            d = json.loads("{" + m2.group(1) + '"stockAvailable":0}')
        except json.JSONDecodeError:
            continue
        if not d.get("p10"):
            continue
        out.append({
            "retailer": "woolworths",
            "product_id": d["id"],
            "name": d.get("description"),
            "brand": d.get("brand"),
            "barcode": d["id"] if len(d["id"]) >= 12 else None,
            "price": float(d["p10"]),
            "regular_price": float(d.get("p10_wp") or d["p10"]),
            "zone_prices": {"p10": d.get("p10"), "p30": d.get("p30"), "p60": d.get("p60")},
            "promo": None,
            "promo_price": None,
            "in_stock": True,
            "url": "https://www.woolworths.co.za/" + d.get("url", ""),
            "region": "zone:p10",
            "fetched_at": now(),
        })
    return out


# ---------------------------------------------------------------- SPAR (specials only)
# SPAR distribution regions (EC, KZN, Lowveld, North Rand, South Rand, Western Cape). NAM/SWZ are outside SA.
SPAR_PAGES = {"national": "national-specials", "EC": "regional-specials/EC", "KZN": "regional-specials/KZN",
              "LV": "regional-specials/LV", "NR": "regional-specials/NR", "SR": "regional-specials/SR",
              "WC": "regional-specials/WC"}


def fetch_spar_specials(f: Fetcher) -> list[dict]:
    """SPAR stores are independent owners who set their own shelf prices, and there is no online catalogue.
    The only public prices are the national and regional promotions on spar.co.za, keyed by barcode."""
    out: dict[tuple, dict] = {}
    for region, path in SPAR_PAGES.items():
        r = f.get(f"https://www.spar.co.za/{path}")
        if not r:
            continue
        recs = parse_spar_cards(r.text) or _parse_spar_flight(r.text)
        for rec in recs:
            rec["region"] = region
            rec["url"] = f"https://www.spar.co.za/{path}"
            out[(rec["barcode"], rec["region"])] = rec
    return list(out.values())


_SPAR_IMG = re.compile(r'src="[^"]*/images/([A-Za-z0-9+/=_-]{16,})"')
_SPAR_VALID = re.compile(r"valid until\s*\[?([0-9]{1,2}\s+[A-Za-z]{3,9})\]?", re.I)


def _cls_text(html: str, name: str) -> str | None:
    """Text inside the first element whose CSS-module class starts with _<name>_ (the hash suffix changes)."""
    m = re.search(r'class="_' + name + r'_[A-Za-z0-9]+_\d+[^"]*"[^>]*>(.*?)</(?:span|div)>', html, re.S)
    if not m:
        return None
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split()) or None


def parse_spar_cards(html: str) -> list[dict]:
    """Read the promotion cards SPAR's pages render as HTML. The product image path carries the barcode
    (base64 of 'product_images/<EAN>/...'); we read only that path, never the image."""
    valid = _SPAR_VALID.search(html)
    valid_until = valid.group(1) if valid else None
    out = []
    for chunk in re.split(r'<a class="_card_', html)[1:]:
        chunk = chunk.split("</a>", 1)[0]
        m = _SPAR_IMG.search(chunk)
        barcode = None
        if m:
            try:
                path = base64.b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4), altchars=b"-_").decode("ascii", "ignore")
                bm = re.match(r"product_images/(\d{8,14})/", path)
                barcode = bm.group(1) if bm else None
            except (ValueError, UnicodeDecodeError):
                barcode = None
        title = _cls_text(chunk, "title")
        size = _cls_text(chunk, "bodyCopy")
        price_txt = _cls_text(chunk, "price")
        label = _cls_text(chunk, "priceLabel") or ""
        save = _cls_text(chunk, "label") or ""
        pm = re.search(r"R\s?(\d+(?:[.,]\d{2})?)", price_txt or "")
        if not (barcode and title and pm):
            continue
        total = float(pm.group(1).replace(",", "."))
        qm = re.search(r"(?:any|buy)\s*(\d+)", label, re.I)
        qty = int(qm.group(1)) if qm else 1
        per_unit = round(total / qty, 2)
        rewards = "rewards.png" in chunk
        sm = re.search(r"R\s?(\d+(?:[.,]\d{2})?)", save)
        saving = float(sm.group(1).replace(",", ".")) if sm else 0.0
        name = f"{title} {size}".strip() if size else title
        promo = (f"Buy any {qty} for R{total:.2f}" if qty > 1 else f"Special R{total:.2f}")
        if saving:
            promo += f", save R{saving:.2f}"
        if rewards:
            promo += " with SPAR Rewards"
        # SPAR's 'Save R X' tags carry the Rewards logo: without the card you pay the usual price, which we
        # take as special + saving (SPAR's own figure; each store sets its own shelf price).
        card_unit = round(total / qty, 2)
        shelf_unit = round((total + saving) / qty, 2) if (rewards and saving) else card_unit
        out.append({
            "retailer": "spar", "product_id": barcode, "barcode": barcode,
            "name": name, "title": title, "size": size, "brand": None,
            "price": shelf_unit, "regular_price": round((total + saving) / qty, 2) if saving else None,
            "promo": promo, "promo_price": card_unit,
            "multibuy_qty": qty, "multibuy_total": total, "rewards": rewards,
            "in_store_only": "in store only" in chunk.lower(),
            "valid_until": valid_until, "in_stock": True, "fetched_at": now(),
        })
    return out


def _parse_spar_flight(html: str) -> list[dict]:
    """Decode React Router 'turbo-stream' payload and pull out the 'promotions' blocks."""
    out = []
    for m in re.finditer(r'streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)', html):
        try:
            table = json.loads(json.loads(m.group(1)))
        except (json.JSONDecodeError, TypeError):
            continue
        out.extend(_walk_spar_table(table))
    return out


def _walk_spar_table(table) -> list[dict]:
    """turbo-stream: a flat list; dict keys '_N' name table[N], int values point at table[value]."""
    if not isinstance(table, list):
        return []

    def val(i, depth=0):
        if not isinstance(i, int) or i < 0 or i >= len(table) or depth > 15:
            return None
        o = table[i]
        if isinstance(o, dict):
            return {table[int(k[1:])]: val(v, depth + 1) for k, v in o.items() if k.startswith("_")}
        if isinstance(o, list):
            return [val(x, depth + 1) for x in o]
        return o

    out = []
    for i, item in enumerate(table):
        if not (isinstance(item, dict)):
            continue
        keys = {table[int(k[1:])] for k in item if k.startswith("_") and k[1:].isdigit() and int(k[1:]) < len(table)}
        if "product_information" not in keys or "amount_total" not in keys:
            continue
        p = val(i)
        info = p.get("product_information") or {}
        barcode = info.get("barcode")
        total = p.get("amount_total")
        if not barcode or total is None:
            continue
        qty = p.get("multibuy_quantity") or 1
        flashes = json.dumps(p.get("flashes"))
        per_unit = round(float(total) / float(qty), 2)
        out.append({
            "retailer": "spar",
            "product_id": str(barcode),
            "name": info.get("product_title"),
            "brand": p.get("brand"),
            "barcode": str(barcode),
            "price": per_unit,
            "regular_price": None,
            "promo": (f"{p.get('multibuy_type') or 'Buy'} {qty} for R{total}" if qty > 1 else f"Special R{total}")
                     + (" (SPAR Rewards)" if "Rewards" in flashes else ""),
            "promo_price": per_unit,
            "in_stock": True,
            "url": "https://www.spar.co.za/specials-2026",
            "fetched_at": now(),
        })
    return out


# ---------------------------------------------------------------- Checkers / Shoprite: bulk catalogue
# The category listing on checkers.co.za / shoprite.co.za loads its products from this endpoint in every
# visitor's browser: 100 products per request, each with barcode and price. Far gentler than one request
# per product page.
GROCERY_DEPARTMENTS = {
    "baby", "bakery", "beverages-juices-and-cordials", "coffee-tea-and-hot-drinks", "deli-and-chilled-meats",
    "fish-and-seafood", "food-cupboard", "frozen-foods", "fruit-veg-and-salads", "household-and-cleaning",
    "meat-and-poultry", "milk-dairy-and-eggs", "ready-meals-and-desserts", "sweets-and-snacks", "toiletries", "pets",
}
BULK_PAGE = 100


def list_departments(f: Fetcher, retailer: str) -> list[tuple[str, str]]:
    """(slug, id) of the grocery level-1 departments, read fresh from the public category sitemap."""
    dom = RETAILERS[retailer]["domain"]
    r = f.get(f"https://{dom}/api/sitemaps/display-category-sitemap_{retailer}.xml")
    if not r:
        return []
    out = []
    for u in re.findall(r"<loc>([^<]+)</loc>", r.text):
        m = re.search(r"/department/([a-z0-9-]+)-1-([0-9a-f]{24})$", u.strip())
        if m and m.group(1) in GROCERY_DEPARTMENTS:
            out.append((m.group(1), m.group(2)))
    return out


def _bulk_body(dept_id: str, page: int) -> dict:
    return {"storeContexts": [], "forYouBonusBuyIds": [], "filterData": {
        "displayOptions": {"includeDisplayCategoryTree": False},
        "filter": {"showAllDisplayVariants": False, "showNotRangedProducts": False, "sortOptions": None,
                   "productListSource": {"displayCategory": {"id": dept_id, "level": 1, "name": ""}},
                   "paginationOptions": {"page": page, "pageSize": BULK_PAGE},
                   "filterOptions": {"dealsOnly": False, "brandOptions": [], "departmentOptions": [],
                                     "serviceOptions": [], "facetOptions": []}}}}


def product_slug(name: str) -> str:
    s = name.lower().replace("&", " and ").replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def fetch_catalogue_bulk(f: Fetcher, retailer: str, log=None) -> tuple[list[dict], dict]:
    """Every grocery product at Checkers/Shoprite. Returns (records, stats)."""
    dom = RETAILERS[retailer]["domain"]
    url = f"https://{dom}/api/catalogue/get-products-filter"
    recs: dict[str, dict] = {}
    stats = {"departments": 0, "requests": 0, "expected": 0}
    for slug, dept_id in list_departments(f, retailer):
        stats["departments"] += 1
        page, total = 0, None
        while total is None or page * BULK_PAGE < total:
            r = f.post_json(url, _bulk_body(dept_id, page))
            stats["requests"] += 1
            if not r:
                break
            try:
                j = r.json()
            except ValueError:
                break
            total = j.get("totalCount") or 0
            if page == 0:
                stats["expected"] += total
            for p in j.get("products") or []:
                rec = _bulk_record(retailer, p, slug)
                if rec:
                    recs.setdefault(rec["barcode"], rec)
            if not j.get("products"):
                break
            page += 1
        if log:
            log.info("%s %s: %s products so far", retailer, slug, len(recs))
    return list(recs.values()), stats


def _bulk_record(retailer: str, p: dict, dept: str) -> dict | None:
    bcs = p.get("barcodes") or []
    price = p.get("discountedPrice") or p.get("price")
    # Keep out-of-stock items: a temporary gap at the online store doesn't change the shelf price.
    if not bcs or not price or float(price) <= 0:
        return None
    name = (p.get("displayName") or p.get("name") or "").strip()
    promo = ((p.get("bonusBuy") or {}).get("name") or "").strip() or None
    art, uom = p.get("articleNumber") or "", p.get("unitOfMeasure") or "EA"
    return {
        "retailer": retailer, "barcode": str(bcs[0]), "barcodes": [str(b) for b in bcs], "name": name,
        "brand": p.get("brand"), "department": dept, "product_id": art,
        "price": float(price), "promo": promo, "promo_price": _promo_price(promo),
        **({"in_stock": False} if p.get("outOfStock") else {}),
        "url": f"https://{RETAILERS[retailer]['domain']}/product/{product_slug(name)}-{art}{uom}",
        "fetched_at": now(),
    }
