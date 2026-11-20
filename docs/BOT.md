# BasketWiseBot

BasketWiseBot collects a small set of everyday grocery prices once a day so that shoppers can
compare supermarkets, including the cost of travelling to them.

- **User-Agent:** `Mozilla/5.0 (compatible; BasketWiseBot/1.0; +<this page>)`
- **Volume:** about 40 product pages per retailer per day.
- **Politeness:**
  - follows robots.txt (including `Crawl-delay` and `Visit-time`)
  - waits at least 3 s between requests
  - backs off on 403/429/503
  - stops entirely if a site blocks it
- **What we keep:** product name, barcode, price and promotion text. We do not keep images or descriptions.
- **We never disguise this bot.**

**Site owners:** to ask us to slow down or stop, e-mail **[contact e-mail]**. We act within one
business day. You can also add `User-agent: BasketWiseBot` / `Disallow: /` to your robots.txt, which
the bot obeys automatically.
