# Retailer outreach: request for official price data

Six companies own the nine brands BasketWise covers or wants to cover. Send **one email per company**,
naming all of its brands. Fill in every `[placeholder]` first, and send from a business address
(not a personal Gmail) with a registered company name. That is the single biggest factor in whether
anyone takes it seriously.

## Who to send it to

Confidence: **[Official]** = published on the company's own site; **[3rd-party]** = listed by a directory,
verify before relying on it. None of these is a dedicated "data partnerships" inbox: no SA retailer
publishes one, so the email asks to be forwarded to the e-commerce / digital team.

| Company | Brands | Send to | Also do this |
|---|---|---|---|
| **Shoprite Holdings** | Checkers (Sixty60), Shoprite, Usave, OK Foods | `cosec@shoprite.co.za` *(company secretary, [3rd-party])* | **Phone 021 980 4000** and ask for the Sixty60 / e-commerce partnerships team; then email the named person. No media or partnerships address is published. Don't use `privacy@` (that's for POPIA/PAIA requests only). |
| **Pick n Pay Stores** | Pick n Pay (incl. asap!), Boxer | `CompanySecretary@pnp.co.za` *[Official, investor site]*; cc `customercare@pnp.co.za` *[Official]* | Head office: +27 21 658 1000 |
| **The SPAR Group** | SPAR, SUPERSPAR, KWIKSPAR, SPAR2U | `intcontact@spar.co.za` *[Official]*; cc `Nonganga@spar.co.za` (Group Executive: Investor Relations & Communications) *[Official]* | SPAR stores are franchises, so ask specifically about SPAR2U and national price data |
| **Woolworths Holdings** | Woolworths Food, Woolies Dash | `pressoffice@woolworths.co.za` *[Official]* | |
| **Food Lover's Market** | Food Lover's Market | `care@fnv.co.za` *[3rd-party]* | Tel +27 21 140 9600; check foodloversmarket.co.za first |
| **Massmart (Walmart)** | Makro | `media.enquiries@massmart.co.za` *[Official]*; cc `info@makro.co.za` *[Official]* | Tel +27 11 517 0000 |

Sources: [Shoprite PAIA manual](https://cdn.prod.website-files.com/61108ec55659c1a2772586b6/63fc1250b9bb1020f918e05d_shoprite-group-paia-manual.pdf), [Shoprite supplier portal](https://supplier.shopriteholdings.co.za/ContactUs/), [Moneyweb SHP](https://www.moneyweb.co.za/tools-and-data/click-a-company/SHP/), [Pick n Pay investor contacts](https://www.picknpayinvestor.co.za/contact-us.php), [Pick n Pay corporate info](https://www.picknpayinvestor.co.za/corporate-information.php), [SPAR Group contact](https://thespargroup.com/contact-us/), [Woolworths Holdings media](https://www.woolworthsholdings.co.za/contacts/media/), [PotatoPro: Food Lover's](https://www.potatopro.com/companies/food-lovers-market-pty-limited), [Massmart contact](https://www.massmart.co.za/about-us/contact), [Makro contact](https://www.makro.co.za/pages/contactus)

## The email

**Subject:** Request for an official product & price feed for [BRANDS]: BasketWise price comparison

> Dear [Company] team,
>
> Please could you forward this to the person responsible for e-commerce, digital partnerships or
> product data?
>
> I run BasketWise (https://skarrd001.github.io/basketwise/), a free South African tool that shows shoppers
> which nearby supermarket is cheapest for their whole basket, including the cost of driving there or
> having it delivered. Every price links straight to the retailer's own product page.
>
> I'm writing to ask for official access to up-to-date product and price data for **[BRANDS]**. Ideally:
>
> - product name, barcode (EAN) and pack size
> - current selling price, and loyalty-card / promotional price where applicable
> - regional or store-level pricing where it differs
> - updated daily, via an API, a data feed or a file. Whatever suits your systems.
>
> **[Use one of the two paragraphs below]**
>
> *[For Shoprite Holdings, Pick n Pay]:* To be transparent: BasketWise currently reads prices from your
> public website. It identifies itself as "BasketWiseBot", follows your robots.txt (including crawl
> delays and visiting hours), makes a small number of requests per day, and stores only product names,
> barcodes, prices and promotion text. No images or descriptions. An official feed would be more
> accurate for your customers and lighter on your systems, and I'd switch to it immediately.
>
> *[For SPAR, Woolworths, Food Lover's Market, Makro]:* BasketWise does not currently include
> [BRANDS] prices, because they aren't available in a form we can use and we don't access sites that
> block automated tools. Shoppers using BasketWise near your stores currently see only a link to your
> specials. With a feed, your prices would appear alongside the other chains.
>
> In return BasketWise would:
>
> - credit [Company] as the source and follow any attribution or display rules you set
> - link every price to your own site, sending shoppers who choose you directly to you
> - never present prices as endorsed by you, and correct any error within one business day
>
> If you'd prefer that BasketWise not include [BRANDS] at all, please just reply and I'll remove them
> within one business day.
>
> I'd welcome a short call at your convenience.
>
> Kind regards,
> [Your full name]
> [Company name] (Pty) Ltd, Reg. no. [number]
> [Business email] · [Phone]
> https://skarrd001.github.io/basketwise/

## Before you send

1. **Register the company and use a business email.** A message from a personal address about scraping
   prices is likely to be read as a threat or ignored.
2. **Fill in the placeholders** in `site/terms.html`, `site/privacy.html` and `docs/BOT.md` first. Retailers
   will click through, and the bot page should list the same contact address as your email.
3. **Send to Shoprite and Pick n Pay last**, after the other four, and only once you're ready for a "please
   stop" reply. They are the two whose data the app depends on today.
4. **If anyone asks you to stop**, follow `docs/LEGAL.md` §4: stop collecting that retailer within 24
   hours, confirm in writing, and keep the correspondence.
5. **Follow up once after 10 working days**, then leave it. Log every send and reply below.

## Log

| Company | Sent | To | Reply | Outcome |
|---|---|---|---|---|
| Shoprite Holdings | | | | |
| Pick n Pay Stores | | | | |
| The SPAR Group | | | | |
| Woolworths Holdings | | | | |
| Food Lover's Market | | | | |
| Massmart (Makro) | | | | |
