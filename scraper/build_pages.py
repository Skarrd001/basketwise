"""Static page generator, run at publish time:  python scraper/build_pages.py _site

Writes into the site folder:
  p/<slug>.html        one SEO page per product ("cheapest X in South Africa")
  c/<slug>.html        one page per category
  products.html        index of all categories
  weekly/index.html    this week's specials post (+ weekly/<date>.html archive copy)
  weekly/latest.txt    the same post as copy-paste text for Facebook / WhatsApp / X
  weekly/latest.png    a 1080x1080 share image (if Pillow is available)
  sitemap.xml          every page, for Google Search Console
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BASE = "https://skarrd001.github.io/basketwise/"
NAMES = {"checkers": "Checkers", "shoprite": "Shoprite", "pnp": "Pick n Pay", "spar": "SPAR", "woolworths": "Woolworths"}
ORDER = ["checkers", "shoprite", "pnp", "spar", "woolworths"]
DISCLAIMER = ("Prices are the most recent on record and may not be 100% up to date at the time of publishing. "
              "They come from each retailer's public website and may differ from the shelf price in your store. "
              "Always check at the till. BasketWise is independent and not affiliated with any retailer.")

e = html.escape


def R(x: float) -> str:
    return "R" + f"{x:,.2f}".replace(",", " ").replace(".", ",")


def slugify(s: str) -> str:
    s = s.lower().replace("&", " and ").replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def pslug(it: dict) -> str:
    return f"{slugify(it['name'])[:70].strip('-')}-{it['id'][-5:]}"


def fmt_date(iso: str | None) -> str:
    try:
        t = datetime.fromisoformat(iso)
        return f"{t.day} {t:%b %Y}"  # portable: Windows strftime has no day-without-zero flag
    except (TypeError, ValueError):
        return ""


def page(title: str, desc: str, canonical: str, body: str, depth: int, extra_head: str = "") -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en-ZA"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{canonical}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{canonical}">
<meta name="theme-color" content="#0b7a55"><link rel="icon" href="{up}icon-192.png"><link rel="stylesheet" href="{up}styles.css">{extra_head}
</head><body>
<header class="top"><div class="wrap"><p class="fresh"><a href="{up}">BasketWise</a> · <a href="{up}products.html">All products</a> · <a href="{up}weekly/">This week's prices</a></p></div></header>
<main class="wrap" style="max-width:860px;padding-bottom:40px">{body}
<p class="disclaimer">{e(DISCLAIMER)}</p></main></body></html>"""


def offers_table(it: dict) -> tuple[str, list]:
    rows, vals = [], []
    for r in ORDER:
        p = it["prices"].get(r)
        if not p:
            continue
        vals.append((r, p))
    if not vals:
        return "", []
    lo = min(p["price"] for _, p in vals)
    for r, p in sorted(vals, key=lambda v: v[1]["price"]):
        promo = f'<span class="promo">{e(p["promo"])}</span>' if p.get("promo") else ""
        when = fmt_date(p.get("fetched_at"))
        rows.append(f'<tr><td>{NAMES[r]}</td><td class="{"cheap" if p["price"] == lo else ""}">'
                    f'<a href="{e(p.get("url") or "#")}" rel="nofollow noopener" target="_blank">{R(p["price"])}</a>{promo}</td>'
                    f'<td>{e(when)}</td></tr>')
    return ("<table><thead><tr><th>Store</th><th>Price</th><th>Price checked</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>"), vals


def product_page(it: dict, related: list[dict]) -> str:
    table, vals = offers_table(it)
    lo_r, lo = min(vals, key=lambda v: v[1]["price"])
    hi_r, hi = max(vals, key=lambda v: v[1]["price"])
    gap = hi["price"] - lo["price"]
    stores = ", ".join(NAMES[r] for r, _ in vals)
    title = f"{it['name']}: cheapest price at {stores}"
    desc = (f"{it['name']} costs from {R(lo['price'])} at {NAMES[lo_r]}. "
            f"Compare {stores}, and see which store is cheapest once you add the drive there.")
    summary = (f"<p><b>Cheapest: {NAMES[lo_r]} at {R(lo['price'])}</b>"
               + (f", {R(gap)} less than {NAMES[hi_r]}." if gap >= 0.01 else ", the same price at every store we track.")
               + "</p>")
    rel = "".join(f'<li><a href="{pslug(r)}.html">{e(r["name"])}</a></li>' for r in related)
    ld = {"@context": "https://schema.org", "@type": "Product", "name": it["name"],
          **({"brand": {"@type": "Brand", "name": it["brand"]}} if it.get("brand") else {}),
          **({"gtin13": it["id"]} if len(it["id"]) == 13 and it["id"].isdigit() else {}),
          "offers": {"@type": "AggregateOffer", "priceCurrency": "ZAR", "lowPrice": f"{lo['price']:.2f}",
                     "highPrice": f"{hi['price']:.2f}", "offerCount": len(vals)}}
    body = f"""
<p class="hint"><a href="../c/{slugify(it.get('category') or 'other')}.html">{e(it.get('category') or '')}</a></p>
<h1 style="font-size:1.5rem;margin:6px 0 10px">{e(it['name'])}</h1>
<section class="card">{summary}{table}
<p style="margin-top:14px"><a class="btn primary" href="../?add={it['id']}">Add to my basket: compare whole shop incl. travel →</a></p></section>
<section class="card" style="margin-top:16px"><h2>Similar products</h2><ul>{rel}</ul></section>"""
    head = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    return page(title, desc, f"{BASE}p/{pslug(it)}.html", body, 1, head)


def category_page(cat: str, items: list[dict]) -> str:
    rows = []
    for it in sorted(items, key=lambda i: i["name"]):
        r, p = min(it["prices"].items(), key=lambda kv: kv[1]["price"])
        rows.append(f'<tr><td><a href="../p/{pslug(it)}.html">{e(it["name"])}</a></td><td>{R(p["price"])}</td><td>{NAMES[r]}</td></tr>')
    body = (f'<h1 style="font-size:1.5rem">{e(cat)}: cheapest prices in South Africa</h1>'
            f'<p class="hint">{len(items)} products compared across Checkers, Shoprite and Pick n Pay.</p>'
            '<section class="card scroll"><table><thead><tr><th>Product</th><th>From</th><th>Cheapest at</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></section>")
    return page(f"{cat}: cheapest grocery prices | BasketWise",
                f"Compare {len(items)} {cat.lower()} prices at Checkers, Shoprite and Pick n Pay.",
                f"{BASE}c/{slugify(cat)}.html", body, 1)


# ------------------------------------------------------------------ weekly post
def weekly(doc: dict) -> dict:
    items = doc["items"]
    fresh = lambda it: {r: p for r, p in it["prices"].items() if not p.get("stale")}  # noqa: E731
    # 1. reference basket (the "monthly family shop" preset), like-for-like on items every chain prices
    byid = {i["id"]: i for i in items}
    basket_def = doc.get("index") or doc.get("preset", [])  # the 15-item standard basket
    lines = [(byid[p["id"]], p.get("qty", 1)) for p in basket_def if p["id"] in byid]
    chains = [r for r in ("checkers", "shoprite", "pnp")
              if sum(1 for it, _ in lines if r in it["prices"]) >= max(1, 0.6 * len(lines))]
    common = [(it, q) for it, q in lines if all(r in it["prices"] for r in chains)]
    basket = sorted(((r, sum(it["prices"][r]["price"] * q for it, q in common)) for r in chains), key=lambda x: x[1])
    # 2. same product, different price (fresh prices only, at least R5 apart)
    gaps = []
    for it in items:
        f = fresh(it)
        if len(f) < 2:
            continue
        (lr, lp), (hr, hp) = min(f.items(), key=lambda kv: kv[1]["price"]), max(f.items(), key=lambda kv: kv[1]["price"])
        d = hp["price"] - lp["price"]
        # everyday items (under R250) at least R5 apart, ranked by % difference: what a shopper feels
        if d >= 5 and hp["price"] <= 250:
            gaps.append((d / hp["price"], d, it, lr, lp["price"], hr, hp["price"]))
    gaps.sort(key=lambda g: (-g[0], -g[1]))
    # 3. best loyalty-card deals
    deals = []
    for it in items:
        for r, p in fresh(it).items():
            if p.get("promo_price") and p["promo_price"] < p["price"]:
                deals.append(((p["price"] - p["promo_price"]) / p["price"], it, r, p))
    deals.sort(key=lambda d: -d[0])
    # 4. changes since last week
    changes = []
    snaps = sorted((DATA / "weekly").glob("*-W*.json"))
    y, w, _ = datetime.now(timezone.utc).isocalendar()
    prev = [s for s in snaps if s.stem < f"{y}-W{w:02d}"]
    if prev:
        old = json.loads(prev[-1].read_text(encoding="utf-8"))
        for it in items:
            for r, p in fresh(it).items():
                o = (old.get(it["id"]) or {}).get(r)
                if o and abs(p["price"] - o) >= 2:
                    changes.append((p["price"] - o, it, r, o, p["price"]))
        changes.sort(key=lambda c: c[0])
    return {"basket": basket, "basket_n": len(common), "basket_total_n": len(lines), "gaps": gaps[:10],
            "deals": deals[:10], "drops": [c for c in changes if c[0] < 0][:10],
            "rises": sorted([c for c in changes if c[0] > 0], key=lambda c: -c[0])[:5], "has_prev": bool(prev)}


def weekly_page(wk: dict, date: str) -> tuple[str, str]:
    li = lambda xs: "<ol>" + "".join(f"<li>{x}</li>" for x in xs) + "</ol>"  # noqa: E731
    link = lambda it: f'<a href="../p/{pslug(it)}.html">{e(it["name"])}</a>'  # noqa: E731
    parts = [f'<h1 style="font-size:1.5rem">Grocery prices this week: {e(date)}</h1>']
    txt = [f"🛒 BasketWise grocery prices: week of {date}", ""]
    if wk["basket"]:
        best_r, best_t = wk["basket"][0]
        worst_r, worst_t = wk["basket"][-1]
        parts.append(f'<section class="card"><h2>Cheapest standard basket</h2><p>On the {wk["basket_n"]} everyday items '
                     f'every store prices online, the cheapest basket is at <b>{NAMES[best_r]}: {R(best_t)}</b>.</p>'
                     + li([f"{NAMES[r]}: {R(t)}" for r, t in wk["basket"]]) + "</section>")
        txt += [f"Cheapest standard basket ({wk['basket_n']} items): {NAMES[best_r]} {R(best_t)}"
                + (f", {R(worst_t - best_t)} less than {NAMES[worst_r]}" if worst_t - best_t >= 1 else ""), ""]
    if wk["gaps"]:
        parts.append('<section class="card"><h2>Same product, different price</h2>' + li(
            [f"{link(g[2])}: {R(g[4])} at {NAMES[g[3]]} vs {R(g[6])} at {NAMES[g[5]]} (save {R(g[1])}, {g[0]:.0%})" for g in wk["gaps"]]) + "</section>")
        txt += ["Same product, different price:"] + [
            f"• {g[2]['name']}: {R(g[4])} at {NAMES[g[3]]} vs {R(g[6])} at {NAMES[g[5]]}" for g in wk["gaps"][:5]] + [""]
    if wk["deals"]:
        parts.append('<section class="card"><h2>Best loyalty-card deals</h2>' + li(
            [f"{link(d[1])} at {NAMES[d[2]]}: {R(d[3]['promo_price'])} with the card (normally {R(d[3]['price'])}, {d[0]:.0%} off)"
             for d in wk["deals"]]) + "</section>")
        txt += ["Best card deals:"] + [
            f"• {d[1]['name']} at {NAMES[d[2]]}: {R(d[3]['promo_price'])} (normally {R(d[3]['price'])})" for d in wk["deals"][:5]] + [""]
    if wk["has_prev"] and (wk["drops"] or wk["rises"]):
        if wk["drops"]:
            parts.append('<section class="card"><h2>Biggest price drops since last week</h2>' + li(
                [f"{link(c[1])} at {NAMES[c[2]]}: {R(c[3])} → {R(c[4])}" for c in wk["drops"]]) + "</section>")
            txt += ["Biggest price drops since last week:"] + [
                f"• {c[1]['name']} at {NAMES[c[2]]}: {R(c[3])} → {R(c[4])}" for c in wk["drops"][:5]] + [""]
        if wk["rises"]:
            parts.append('<section class="card"><h2>Biggest increases since last week</h2>' + li(
                [f"{link(c[1])} at {NAMES[c[2]]}: {R(c[3])} → {R(c[4])}" for c in wk["rises"]]) + "</section>")
    parts.append('<p><a class="btn primary" href="../">Find the cheapest shop for your basket, incl. travel →</a></p>')
    txt += [f"Compare your whole basket, including the petrol to get there: {BASE}",
            "Prices are the most recent on record from each store's website and may change. Always check at the till."]
    return "".join(parts), "\n".join(txt)


def share_image(wk: dict, date: str, out: Path) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    W = H = 1080
    img = Image.new("RGB", (W, H), "#0b7a55")
    d = ImageDraw.Draw(img)

    def font(size, bold=False):
        for p in (f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
                  "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        return ImageFont.load_default()

    d.text((70, 70), "BasketWise", font=font(44, True), fill="#ffd54a")
    d.text((70, 130), f"Grocery prices: week of {date}", font=font(40, True), fill="white")
    y = 230
    if wk["basket"]:
        r, t = wk["basket"][0]
        d.text((70, y), f"Cheapest standard basket ({wk['basket_n']} items)", font=font(32), fill="#d8f3e6")
        d.text((70, y + 44), f"{NAMES[r]}  {R(t)}", font=font(64, True), fill="white")
        y += 160
    d.text((70, y), "Same product, different price:", font=font(32, True), fill="#ffd54a")
    y += 56
    for g in wk["gaps"][:5]:
        name = g[2]["name"] if len(g[2]["name"]) <= 34 else g[2]["name"][:33] + "…"
        d.text((70, y), name, font=font(30, True), fill="white")
        d.text((70, y + 38), f"{R(g[4])} {NAMES[g[3]]}  vs  {R(g[6])} {NAMES[g[5]]}", font=font(28), fill="#d8f3e6")
        y += 92
    d.text((70, H - 90), "skarrd001.github.io/basketwise", font=font(32, True), fill="#ffd54a")
    img.save(out)
    return True


def main(out_dir: str) -> int:
    out = Path(out_dir)
    doc = json.loads((DATA / "prices.json").read_text(encoding="utf-8"))
    # SEO pages only for products we can actually compare (2+ stores): single-store pages would be thin.
    items = [i for i in doc["items"] if len(i["prices"]) >= 2]
    gen = doc["generated_at"][:10]
    urls = [(BASE, gen), (BASE + "products.html", gen), (BASE + "weekly/", gen)]
    by_cat: dict[str, list] = {}
    for it in items:
        by_cat.setdefault(it.get("category") or "Other", []).append(it)

    (out / "p").mkdir(parents=True, exist_ok=True)
    for cat, its in by_cat.items():
        its_sorted = sorted(its, key=lambda i: i["name"])
        for k, it in enumerate(its_sorted):
            related = [r for r in its_sorted[max(0, k - 3):k + 4] if r is not it][:6]
            (out / "p" / f"{pslug(it)}.html").write_text(product_page(it, related), encoding="utf-8")
            urls.append((f"{BASE}p/{pslug(it)}.html", gen))
    (out / "c").mkdir(exist_ok=True)
    for cat, its in by_cat.items():
        (out / "c" / f"{slugify(cat)}.html").write_text(category_page(cat, its), encoding="utf-8")
        urls.append((f"{BASE}c/{slugify(cat)}.html", gen))
    idx = "".join(f'<li><a href="c/{slugify(c)}.html">{e(c)}</a> ({len(v)})</li>'
                  for c, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1])))
    (out / "products.html").write_text(page(
        "All products: compare grocery prices in South Africa | BasketWise",
        f"Compare {len(items)} grocery prices at Checkers, Shoprite and Pick n Pay, by category.",
        BASE + "products.html",
        f'<h1 style="font-size:1.5rem">Compare {len(items):,} grocery prices</h1><section class="card"><ul>{idx}</ul></section>'.replace(",", " "),
        0), encoding="utf-8")

    wk = weekly(doc)
    t = datetime.now(timezone.utc)
    date = f"{t.day} {t:%B %Y}"
    body, text = weekly_page(wk, date)
    (out / "weekly").mkdir(exist_ok=True)
    wpage = page(f"Grocery prices this week ({date}) | BasketWise",
                 "This week's cheapest grocery basket, biggest price gaps and best card deals at Checkers, Shoprite and Pick n Pay.",
                 BASE + "weekly/", body, 1,
                 f'<meta property="og:image" content="{BASE}weekly/latest.png">')
    (out / "weekly" / "index.html").write_text(wpage, encoding="utf-8")
    (out / "weekly" / f"{datetime.now(timezone.utc):%Y-%m-%d}.html").write_text(wpage, encoding="utf-8")
    (out / "weekly" / "latest.txt").write_text(text, encoding="utf-8")
    img = share_image(wk, date, out / "weekly" / "latest.png")

    sm = "".join(f"<url><loc>{u}</loc><lastmod>{d}</lastmod></url>" for u, d in urls)
    (out / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>',
        encoding="utf-8")
    print(f"built {len(items)} product pages, {len(by_cat)} category pages, weekly post (image: {img}), sitemap with {len(urls)} URLs")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "_site"))
