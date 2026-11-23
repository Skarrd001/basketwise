# BasketWise

**Which supermarket is cheapest for *your* basket, once you count the drive there?**

BasketWise compares a core basket of everyday groceries across Checkers, Shoprite, Pick n Pay and
SPAR. It finds your nearest store of each chain and adds the fuel (and, optionally, time) cost of
getting there. It also suggests a two-store "split shop" when that comes out cheaper.

## How it runs (no servers)

```
GitHub Actions, daily 04:20 UTC (06:20 SAST)
  ├─ Mondays:  scraper/stores.py    → data/stores.json     (OpenStreetMap, ~3,000 stores)
  ├─ daily:    scraper/run.py       → data/prices.json (thousands of products), data/pnp_map.json
  │             Checkers + Shoprite: whole grocery range, 100 products/request (~15 min)
  │             Pick n Pay: rolling refresh + new barcode matches inside its robots.txt window
  ├─ tests
  ├─ commit data back to the repo   (the price history is the long-term asset)
  └─ deploy site/ + data to GitHub Pages
```

- **Cost:** R0. A public repo gets unlimited Actions minutes and free Pages.
- **If a retailer changes its site:** `run.py` exits non-zero, the workflow fails, and GitHub e-mails
  the repo owner. Prices from the last 3 days are carried forward, marked stale, so the app keeps
  working meanwhile.
- **Scheduled workflows** are disabled by GitHub after 60 days without repo activity. The daily data
  commit counts as activity, so this never triggers.

## Coverage

| Retailer | Source | Notes |
|---|---|---|
| Checkers | Public product pages | Online price (Checkers says it matches in-store), plus Xtra Savings deals |
| Shoprite | Public product pages | Same platform as Checkers |
| Pick n Pay | The product JSON its own pages load | Default pricing region; crawled only in the robots.txt window (04:00–08:45 UTC, 10 s apart) |
| SPAR | Public specials pages | SPAR stores set their own prices, so only specials are available |
| Woolworths | **Not collected** | Their firewall blocks self-identified bots, and we don't disguise ours. See `docs/LEGAL.md` |

## Run locally

```bash
pip install -r scraper/requirements.txt
cd scraper
python discover.py   # ~15 min (PnP asks for 10 s between requests); only within 04:00–08:45 UTC for PnP
python run.py        # ~10 min
python stores.py     # needs access to overpass-api.de
cd ..
python -m unittest discover -s tests
ln -sfn ../data site/data && python -m http.server -d site 8000
```

## How the catalogue grows

Products are matched across retailers by **barcode**. Checkers and Shoprite are fully refreshed every
day. Pick n Pay only allows one request every 10 seconds, early mornings only, so each run spends its
window refreshing the oldest PnP prices and matching new products. PnP coverage grows daily, and
every price that isn't from today is shown with its date. Departments included are listed in
`GROCERY_DEPARTMENTS` in `scraper/retailers.py`. The "Monthly family shop" preset is `scraper/preset.json`.

## Before you launch

Read `docs/LEGAL.md`, then fill in the `[placeholders]` in `site/terms.html`, `site/privacy.html` and
`docs/BOT.md`.
