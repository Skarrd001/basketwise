# BasketWise: marketing & go-to-market strategy

Written to be executed solo, on near-zero budget, because you've said you won't spend before there's
proof. Every tactic below is free or cheap, and ordered so the cheapest proof comes first.
Confidence: **[Certain]** grounded, **[Likely]** strong inference, **[Guessing]** needs testing.

## 0. The one-line pitch
> "BasketWise tells you which shop is actually cheapest for *your* trolley — once you count the petrol
> to get there."

The petrol angle is the hook. [Likely] Nobody else in SA leads with total cost including travel, and
in a country where fuel is a monthly shock, "cheapest including the drive" is a sharper promise than
"compare prices", which shoppers have heard before.

## 1. Who you're actually for (pick one to start)
Don't launch "for everyone". [Likely] A narrow first audience is cheaper to reach and gives cleaner
feedback. Candidates, best first:

1. **Budget-stretched family shoppers** doing a monthly bulk shop (the basket is already built for
   them). High motivation, high basket value, they feel R100 saved.
2. **Stokvels and bulk-buying groups.** One organiser decides where the group buys; saving the group
   R500 makes you a hero. [Guessing] Word of mouth here is strong.
3. **"One-grand-a-month" / frugal-living followers** on TikTok and Facebook. They *perform* saving
   money, so they'll share a tool that proves it.

**Decision:** start with (1), seed through (3). Ignore (2) until the app has a share feature.

## 2. Positioning — what makes you different
| Everyone else | BasketWise |
|---|---|
| Lists specials | Compares *your whole basket* |
| Price only | Price **+ travel cost** |
| One retailer's app | All the big chains at once |
| "With your card" prices only | Shows card price **and** no-card price |
| Assumes you'll drive | Compares **driving vs delivery** |

Lead every piece of content with the travel-cost or the delivery-vs-drive angle. Those are the two
things only you do.

## 3. The content engine (free, and it doubles as SEO)
Your daily scraper is a content machine. Each day it knows real prices. Turn that into posts:

- **"Cheapest basic basket this week: R___ at [chain]"** — a weekly number, posted every Monday.
- **"Milk costs R___ at Checkers vs R___ at PnP right now."** — single-item shock posts.
- **"Is Sixty60 delivery worth it? We did the maths on a R600 basket."** — delivery-vs-drive.
- **Monthly "grocery inflation" post** once you have history: "A basic basket is up R__ since [month]."
  [Likely] This is the one that gets press pickup — local news loves a cost-of-living number with data.

Automate it: a weekly GitHub Action can generate the numbers and even draft the post text from
`data/trends.json`. You approve and paste. **Build the audience before you need it.**

### SEO pages (do this once, compounds forever)
Generate a public page per item: "Cheapest [product] in South Africa" with today's prices and a
30-day chart. [Likely] People google exactly this. These pages are free to generate from data you
already have, and they bring in search traffic with no ad spend. This is the highest-leverage
free channel; prioritise it.

## 4. Launch sequence (first 60 days, R0)
**Weeks 1–2 — proof, no audience.**
- Ship the site. Post it in 3–4 SA Facebook groups (frugal living, couponing, your town's community
  group) with a specific claim: "I built a free thing that found R__ difference on my monthly shop."
- Post once on r/southafrica and r/PersonalFinanceZA with the story, not a pitch. [Guessing] Reddit
  punishes promotion; lead with "I scraped the prices and here's what I found", link second.
- Goal: 100 visitors, 5 pieces of feedback. Not revenue.

**Weeks 3–6 — the weekly number.**
- Start the Monday "cheapest basket" post on one channel you'll actually maintain (pick TikTok *or*
  Facebook, not both).
- DM 5 local frugal-living/finance micro-influencers (5–50k followers). Offer nothing but the free
  tool and the weekly data. [Likely] Some will post it unpaid because the data is genuinely useful.

**Weeks 7–8 — press the inflation angle.**
- Once you have ~4 weeks of history, email the number to 2–3 personal-finance journalists
  (Moneyweb, BusinessTech, News24 personal finance, Fin24). A clean "grocery basket up R__ this
  month, here's the chart" is the kind of free data they publish. One pickup = thousands of visitors.

## 5. Channels, ranked by cost-to-return
1. **SEO per-item pages** — free, compounding, intent-driven. Best long-term. Start now.
2. **Your own weekly data posts** — free, builds a owned audience. Start now.
3. **PR via the inflation number** — free, spiky, high-reach. Start week 7.
4. **Micro-influencer gifting** — free-ish, needs the app to be share-worthy first.
5. **WhatsApp/community groups** — free, high-trust, hard to scale.
6. **Paid ads** — last. [Likely] Don't pay for traffic until you know what a visitor is worth to you.

## 6. The viral loop to build next (not now)
The share feature is the growth engine: after a comparison, a **"Share my saving"** image —
"I saved R137 on my monthly shop with BasketWise" with the basket total and your URL. [Likely] People
share wins, not tools. This turns every happy user into a free ad. Build it once retention is proven.

## 7. What NOT to do
- Don't buy ads yet. You have no measured value-per-user. [Certain] You'd be guessing.
- Don't market Woolworths coverage you don't have.
- Don't claim "always cheapest" or name a chain as "most expensive" — that invites both a defamation
  argument and an accuracy fight. Say "cheapest *for this basket, today*".
- Don't build a mobile app for stores yet. The web app is the cheapest way to test demand. [Likely]
  App-store presence matters only once the web version shows people come back.

## 8. The numbers to watch (free analytics)
Use a privacy-light, free analytics tool (Plausible self-hosted, or Cloudflare Web Analytics — both
free, both POPIA-friendlier than Google Analytics). Watch three things only:
- **Return visits** — the single best signal that this is useful, not just a novelty.
- **Baskets completed** — did they actually get an answer?
- **Share clicks** (once built) — your growth coefficient.

Ignore vanity metrics (page views, "likes"). [Likely] Retention is the only number that tells you
whether to invest more.

## 9. When to spend money (your trigger, not a date)
Spend only when **one** of these is true:
- Return-visit rate is clearly positive (people come back monthly), **or**
- A brand/researcher has said they'd pay for the price data (see `docs/LEGAL.md` §3 and the
  monetisation notes), **or**
- An unpaid post drove a spike you can't keep up with for free.

Until then, every hour goes into the free content engine and the SEO pages. That's the plan that
respects "no money until there's a return".
