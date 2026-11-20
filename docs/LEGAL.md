# BasketWise: legal risk memo

**Status: working analysis, not legal advice.** Written by an AI assistant to brief a South African
attorney (budget about R3,000–R8,000 for a one-hour review). Confidence tags: **[Certain]** = from the
statute or the retailer's own published files; **[Likely]** = strong inference; **[Guessing]** = needs
counsel.

## 1. What the system actually does

| Retailer | What we read | How | Their robots.txt | Status |
|---|---|---|---|---|
| Checkers | ~40 product pages/day | Public product page, embedded JSON | Allows all crawlers except /login, /my-profile **[Certain]** | Collected |
| Shoprite | ~40 product pages/day | Same as Checkers | Same as Checkers **[Certain]** | Collected |
| Pick n Pay | ~40 product records/day | The JSON endpoint the public product page loads in every visitor's browser | 10 s between requests, 04:00–08:45 UTC only, no `/search/` **[Certain]** | Collected, inside those limits |
| SPAR | Specials pages (national + 9 provinces) | Public HTML | Allows all except store-finder **[Certain]** | Collected (specials only) |
| Woolworths | Nothing | n/a | Allows category pages, but its firewall blocks self-identified bots **[Certain]** | **Not collected. We do not disguise the bot.** |

Controls built into the code (`scraper/common.py`):
- Honest User-Agent `BasketWiseBot/1.0` with a contact URL. We never pretend to be a browser.
- robots.txt checked on every URL. PnP's crawl-delay and visit window are enforced.
- At least 3 s between requests per site (10 s for PnP). Hard back-off on 403/429/503. Any block page stops all requests to that site.
- Low volume: about 200 requests a day in total. A single human shopper browsing generates more.
- We store only: product name, brand, barcode, price, promo text and the product URL. **No images, descriptions or reviews.**

## 2. South African law that applies

### 2.1 Cybercrimes Act 19 of 2020, s2 (unlawful access), formerly ECT Act s86
- **[Likely]** Reading pages the owner serves to the public, at the rate and times their robots.txt asks for, is not "unlawful access": the owner has made the data available to anyone.
- **[Likely]** Bypassing a technical block, such as spoofing a browser after a firewall rejects you, rotating IPs to dodge a ban, or solving CAPTCHAs, is where criminal exposure starts. This is why Woolworths is switched off and the code stops on block pages.
- **Rule: if any retailer blocks us, we stop collecting from that retailer. We never work around a block.**

### 2.2 Copyright Act 98 of 1978
- **[Certain]** Copyright protects expression, not facts. A price is a fact.
- **[Likely]** Product photos and marketing descriptions are protected, so we do not copy them.
- **[Guessing]** A retailer could argue its product database is a protected compilation. Our extract (about 40 items out of 100k+) is a small, non-substantial part, and the comparison is a different use.

### 2.3 Website terms of use (contract)
- **[Likely]** Most retailer terms ban automated access.
- **[Guessing]** Whether "browsewrap" terms (terms nobody clicks to accept) bind a visitor is unsettled in SA law. Even if they do, damages are hard to show for low-volume reading.
- This is the most likely basis for a **cease-and-desist letter**. See the response plan in §4.

### 2.4 Unlawful competition (common law)
- **[Likely]** This is the realistic civil claim in SA: "misappropriating another's performance".
- Our defences:
  - we do not compete with retailers (we sell no groceries)
  - every price links back to the retailer's own page, sending them customers
  - we copy almost nothing of their database
  - the travel-cost layer is our own work

### 2.5 Trade Marks Act 194 of 1993
- **[Likely]** Using retailer *names* to say truthfully whose price is shown is honest descriptive use.
- **Do not** use their logos, colours as branding, or anything that suggests endorsement. The app states it is independent.
- Pick a product name that doesn't contain a retailer's mark.

### 2.6 Consumer Protection Act 68 of 2008 (s41) and the ARB Code (comparative advertising)
- **[Certain]** Comparisons must not be misleading.
- **[Likely]** The ARB code expects like-for-like, verifiable comparisons.
- What the app does:
  - matches products by **barcode** (identical product), so comparisons are like-for-like
  - shows the date of each price and links to its source
  - marks old prices as stale
  - says online prices may differ from shelf prices
  - shows loyalty-card prices separately
- **Risk:** stating "X is cheapest" from stale or wrong data. Keep the daily health checks running.

### 2.7 POPIA (Protection of Personal Information Act 4 of 2013)
- **[Certain]** A user's location is personal information.
- How the app handles it:
  - All distance maths runs in the user's browser, and location is never sent to our servers.
  - A typed suburb is sent to the OpenStreetMap geocoder.
  - The app has no accounts, no cookies of its own and no analytics.
- **When you add accounts, analytics, ads or e-mail, the privacy policy must be updated first.** You will also need an Information Officer registered with the Information Regulator.

### 2.8 Data licences we use
- **[Certain]** Store locations come from OpenStreetMap under the ODbL. Attribution is required and is shown in the app.
- **[Certain]** OSM's public tile server and Nominatim have usage policies meant for light use. At real traffic you must switch to a paid tile and geocoding provider (e.g. MapTiler, Stadia, or self-hosting).

## 3. What to do before public launch
1. Register a (Pty) Ltd so personal assets are shielded.
2. Spend one hour with an IT/IP attorney on §2.3–2.6. Bring this memo.
3. **Write to each retailer's e-commerce or partnerships team** (template in `docs/RETAILER_LETTER.md`). Say what we collect, how politely, that we send them traffic, and offer to use an official feed. A written "no objection" removes most of this risk; a "please stop" costs you one retailer instead of a lawsuit.
4. Ask Woolworths for permission or a feed. Until then the app says Woolworths is unavailable.
5. Publish `docs/BOT.md` at the URL in the User-Agent so site admins can contact you.

## 4. If a cease-and-desist arrives
1. Within 24 h, stop that retailer: set it to skip in `scraper/run.py` and push. The daily job picks it up.
2. Reply politely confirming you've stopped, and propose an official feed.
3. Keep the letter and send it to your attorney. Don't argue the law in your reply.
4. Mark the retailer "unavailable" in the app with a neutral note. Don't badmouth them.
