/* BasketWise front end: no build step, no tracking, location never leaves the browser
   (except a typed suburb, which is sent to OpenStreetMap's geocoder to find it on the map). */
"use strict";

const CHAINS = {
  checkers:   { name: "Checkers",   color: "var(--checkers)" },
  shoprite:   { name: "Shoprite",   color: "var(--shoprite)" },
  pnp:        { name: "Pick n Pay", color: "var(--pnp)" },
  spar:       { name: "SPAR",       color: "var(--spar)" },
  woolworths: { name: "Woolworths", color: "var(--woolworths)" },
  usave:      { name: "Usave",            color: "#e2001a" },
  ok:         { name: "OK Foods",         color: "#d71920" },
  boxer:      { name: "Boxer",            color: "#00843d" },
  foodlovers: { name: "Food Lover's Market", color: "#7ab800" },
  makro:      { name: "Makro",            color: "#003c71" },
};
// Chains that don't publish machine-readable prices: we show the nearest store and their own specials page.
const SPECIALS = {
  spar: "https://www.spar.co.za/national-specials",
  woolworths: "https://www.woolworths.co.za/browse/food/promotions-specials",
  usave: "https://www.usave.co.za/specials.html",
  ok: "https://www.okfoods.co.za/specials.html",
  boxer: "https://www.boxer.co.za/specials/",
  foodlovers: "https://foodloversmarket.co.za/specials/",
  makro: "https://www.makro.co.za/",
};
const ROAD_FACTOR = 1.3;      // straight line -> typical road distance
const AVG_SPEED_KMH = 35;     // urban driving, for the time-cost option
const S = {
  prices: null, stores: [], loc: null, basket: {}, marker: null, storeLayer: null, map: null,
};

const $ = (id) => document.getElementById(id);
const R = (n) => "R" + n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const store = {
  get(k, d) { try { const v = localStorage.getItem("bw:" + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("bw:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

async function boot() {
  const [prices, stores] = await Promise.all([
    fetch("data/prices.json", { cache: "no-cache" }).then((r) => r.json()),
    fetch("data/stores.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : { stores: [] })).catch(() => ({ stores: [] })),
  ]);
  S.prices = prices;
  S.byId = new Map(prices.items.map((i) => [i.id, i]));
  for (const it of prices.items) it._hay = (it.name + " " + (it.brand || "") + " " + (it.category || "")).toLowerCase();
  S.stores = stores.stores || [];
  S.basket = Object.fromEntries(Object.entries(store.get("basket", {})).filter(([id]) => S.byId.has(id)));
  // Links from product pages: ?add=<id> puts that product in the basket, then tidies the address bar.
  const add = new URLSearchParams(location.search).get("add");
  if (add && S.byId.has(add)) {
    S.basket[add] = (S.basket[add] || 0) + 1;
    store.set("basket", S.basket);
    history.replaceState(null, "", location.pathname);
  }
  for (const id of ["fuel", "cons", "time", "maxkm"]) {
    const v = store.get(id, null);
    if (v !== null) $(id).value = v;
    $(id).addEventListener("input", () => { store.set(id, $(id).value); render(); });
  }
  $("loyalty").checked = store.get("loyalty", true);
  $("loyalty").addEventListener("change", () => { store.set("loyalty", $("loyalty").checked); render(); });
  const savedMode = store.get("mode", "drive");
  document.querySelectorAll('input[name="mode"]').forEach((el) => {
    el.checked = el.value === savedMode;
    el.addEventListener("change", () => { store.set("mode", mode()); render(); });
  });
  renderFreshness();
  renderItems();
  initMap();
  const loc = store.get("loc", null);
  if (loc) setLoc(loc.lat, loc.lon, false);
  let t;
  $("filter").addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { S.cat = null; S.limit = 40; renderItems(); }, 120); });
  $("preset").addEventListener("click", () => {
    S.basket = {};
    for (const p of S.prices.preset || []) if (S.byId.has(p.id)) S.basket[p.id] = p.qty || 1;
    saveBasket();
  });
  $("clear").addEventListener("click", () => { S.basket = {}; saveBasket(); });
  $("geo").addEventListener("click", useGeolocation);
  $("addr-form").addEventListener("submit", geocode);
  render();
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([e]) => { document.body.classList.toggle("results-visible", e.isIntersecting); })
      .observe($("step-results"));
  }
}

function renderFreshness() {
  const p = S.prices;
  const when = new Date(p.generated_at);
  const ago = Math.round((Date.now() - when) / 36e5);
  const chips = [`<span class="chip">${p.item_count.toLocaleString("en-ZA")} products</span>`, `<span class="chip">Prices updated ${ago < 1 ? "within the hour" : ago < 48 ? ago + "h ago" : when.toLocaleDateString("en-ZA")}</span>`];
  for (const [id, h] of Object.entries(p.retailers)) {
    const good = h.status === "ok" || h.status === "paused";
    const label = h.status === "ok" ? `${h.items_priced.toLocaleString("en-ZA")} items`
      : h.status === "paused" ? `${(h.items_priced || 0).toLocaleString("en-ZA")} items (refreshing daily)`
      : h.status === "specials-only" ? "specials only" : "unavailable";
    chips.push(`<span class="chip ${good ? "ok" : "bad"}" title="${esc(h.note)}">${esc(h.name)}: ${label}</span>`);
  }
  $("freshness").innerHTML = chips.join("");
  $("coverage").innerHTML = Object.values(p.retailers).map((h) => `<b>${esc(h.name)}:</b> ${esc(h.note)}`).join("<br>");
}

function itemRow(it) {
  const n = S.basket[it.id] || 0;
  const vals = Object.entries(it.prices);
  const lo = Math.min(...vals.map(([, p]) => p.price));
  const where = vals.length + (vals.length === 1 ? " store" : " stores");
  return `<div class="item ${n ? "on" : ""}">
    <div class="nm">${esc(it.name)}<small>${esc(it.category || "")} · from ${R(lo)} · ${where}</small></div>
    <div class="qty"><button data-id="${it.id}" data-d="-1" aria-label="Remove one">−</button><span>${n}</span><button data-id="${it.id}" data-d="1" aria-label="Add one">+</button></div>
  </div>`;
}

function renderItems() {
  const q = $("filter").value.trim().toLowerCase();
  const words = q.split(/\s+/).filter(Boolean);
  const limit = S.limit || 40;
  let html = "";
  const inBasket = Object.keys(S.basket).map((id) => S.byId.get(id)).filter(Boolean);
  if (inBasket.length && !q && !S.cat) {
    html += `<div class="cat">In your basket (${inBasket.length})</div>` + inBasket.map(itemRow).join("");
  }
  if (words.length) {
    const hits = S.prices.items.filter((it) => words.every((w) => it._hay.includes(w)));
    // items whose name starts with the query word rank first, then the most widely stocked
    hits.sort((a, b) => (b.name.toLowerCase().startsWith(words[0]) - a.name.toLowerCase().startsWith(words[0]))
      || (Object.keys(b.prices).length - Object.keys(a.prices).length) || a.name.length - b.name.length);
    html += `<div class="cat">${hits.length.toLocaleString("en-ZA")} match${hits.length === 1 ? "" : "es"}</div>` +
      hits.slice(0, limit).map(itemRow).join("") +
      (hits.length > limit ? `<button class="btn ghost more" data-more="1">Show more</button>` : "");
    if (!hits.length) html += `<p class="hint">Nothing matches "${esc(q)}". Try one word, like "milk" or "sunlight".</p>`;
  } else if (S.cat) {
    const list = S.prices.items.filter((it) => it.category === S.cat);
    html += `<div class="cat"><button class="btn ghost" data-cat="">← All categories</button> ${esc(S.cat)} (${list.length.toLocaleString("en-ZA")})</div>` +
      list.slice(0, limit).map(itemRow).join("") +
      (list.length > limit ? `<button class="btn ghost more" data-more="1">Show more</button>` : "");
  } else {
    const counts = {};
    for (const it of S.prices.items) counts[it.category] = (counts[it.category] || 0) + 1;
    html += `<div class="cat">Browse by category, or search above</div><div class="cats">` +
      Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([c, n]) =>
        `<button class="chip catbtn" data-cat="${esc(c)}">${esc(c)} <b>${n.toLocaleString("en-ZA")}</b></button>`).join("") + `</div>`;
  }
  $("items").innerHTML = html;
  $("items").querySelectorAll("button[data-id]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.id;
    S.basket[id] = Math.max(0, (S.basket[id] || 0) + Number(b.dataset.d));
    if (!S.basket[id]) delete S.basket[id];
    saveBasket();
  }));
  $("items").querySelectorAll("button[data-cat]").forEach((b) => b.addEventListener("click", () => {
    S.cat = b.dataset.cat || null; S.limit = 40; renderItems(); $("items").scrollTop = 0;
  }));
  $("items").querySelectorAll("button[data-more]").forEach((b) => b.addEventListener("click", () => {
    S.limit = (S.limit || 40) + 60; renderItems();
  }));
}

function saveBasket() { store.set("basket", S.basket); renderItems(); render(); }

/* ------------------------------------------------------------------ map & location */
function initMap() {
  if (typeof L === "undefined") {  // map library failed to load: everything else still works
    $("map").style.display = "none";
    $("loc-status").textContent = "Map unavailable right now. Use your location or type a suburb.";
    return;
  }
  S.map = L.map("map", { zoomControl: true }).setView([-29.0, 25.0], 5);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(S.map);
  S.storeLayer = L.layerGroup().addTo(S.map);
  S.map.on("click", (e) => setLoc(e.latlng.lat, e.latlng.lng));
}

function setLoc(lat, lon, pan = true) {
  S.loc = { lat, lon };
  store.set("loc", S.loc);
  if (S.map) {
    if (S.marker) S.marker.setLatLng([lat, lon]);
    else S.marker = L.marker([lat, lon], { title: "You" }).addTo(S.map);
    S.map.setView([lat, lon], 12, { animate: pan });
  }
  $("loc-status").textContent = `Location set (${lat.toFixed(3)}, ${lon.toFixed(3)}).${S.map ? " Tap the map to move it." : ""}`;
  render();
}

function useGeolocation() {
  if (!navigator.geolocation) { $("loc-status").textContent = "Your browser can't share location; type a suburb instead."; return; }
  $("loc-status").textContent = "Finding you…";
  navigator.geolocation.getCurrentPosition(
    (p) => setLoc(p.coords.latitude, p.coords.longitude),
    () => { $("loc-status").textContent = "Location permission denied; type a suburb or tap the map."; },
    { enableHighAccuracy: false, timeout: 10000 },
  );
}

async function geocode(e) {
  e.preventDefault();
  const q = $("addr").value.trim();
  if (!q) return;
  $("loc-status").textContent = "Searching…";
  try {
    const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=za&q=${encodeURIComponent(q)}`);
    const j = await r.json();
    if (!j.length) { $("loc-status").textContent = "Couldn't find that place; try a nearby suburb or tap the map."; return; }
    setLoc(Number(j[0].lat), Number(j[0].lon));
  } catch { $("loc-status").textContent = "Search failed; tap the map instead."; }
}

function km(a, b) {
  const rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

// Nearest branch of every chain. withinMax=false also returns branches beyond the max distance,
// flagged far:true, so a chain that prices your basket is never silently dropped.
function nearestStores(withinMax = true) {
  const out = {};
  if (!S.loc) return out;
  const max = Number($("maxkm").value) || 20;
  for (const s of S.stores) {
    const d = km(S.loc, s);
    if (withinMax && d > max) continue;
    if (!out[s.chain] || d < out[s.chain].d) out[s.chain] = { ...s, d, far: d > max };
  }
  return out;
}

function tripCost(roadKm) {
  const fuel = Number($("fuel").value) || 0, cons = Number($("cons").value) || 0, t = Number($("time").value) || 0;
  return roadKm * (cons / 100) * fuel + (roadKm / AVG_SPEED_KMH) * t;
}

/* ------------------------------------------------------------------ pricing */
function mode() { return document.querySelector('input[name="mode"]:checked')?.value || "drive"; }

function unitPrice(p) {
  // Loyalty price = the card/multibuy price where we have a clean numeric one (mainly Checkers/Shoprite).
  if ($("loyalty").checked && p.promo_price && p.promo_price < p.price) return { v: p.promo_price, promo: true };
  return { v: p.price, promo: false };
}

function deliveryFee(chain, goods) {
  const d = (S.prices.retailers[chain] || {}).delivery || { fee: 40, min_order: 150 };
  const override = store.get("delivery:" + chain, null);
  const fee = override !== null ? Number(override) : Number(d.fee || 0);
  const freeOver = d.free_over ? Number(d.free_over) : null;
  const effective = freeOver && goods >= freeOver ? 0 : fee;
  return { fee: effective, listed: fee, min_order: d.min_order || 0, service: d.service,
           belowMin: goods < (d.min_order || 0) };
}

// ---------------------------------------------------------------- standard basket (15 staples)
function renderStandard() {
  const el = $("std-body");
  const idx = (S.prices.index || []).map((x) => ({ ...x, it: S.byId.get(x.id) })).filter((x) => x.it);
  if (!idx.length) { $("std").hidden = true; return; }
  const priced = (c) => idx.filter((x) => x.it.prices[c]).length;
  const chains = ["checkers", "shoprite", "pnp", "spar", "woolworths"].filter((c) => priced(c) >= Math.ceil(idx.length * 0.6));
  const common = idx.filter((x) => chains.every((c) => x.it.prices[c]));
  const rows = chains.map((c) => ({ c, total: common.reduce((a, x) => a + unitPrice(x.it.prices[c]).v * (x.qty || 1), 0) }))
    .sort((a, b) => a.total - b.total);
  const others = ["checkers", "shoprite", "pnp"].filter((c) => !chains.includes(c));
  const best = rows[0];
  let h = "";
  if (rows.length >= 2 && common.length) {
    const max = rows[rows.length - 1].total;
    h += `<div class="std-rank">` + rows.map((r, k) => `<div class="std-row ${k === 0 ? "win" : ""}">
        <span class="std-name"><span class="dot" style="background:${CHAINS[r.c].color}"></span> ${CHAINS[r.c].name}</span>
        <span class="std-bar"><span style="width:${Math.max(8, Math.round(100 * r.total / max))}%"></span></span>
        <span class="std-total">${R(r.total)}${k === 0 ? ` <span class="badge">Cheapest</span>` : ` <small>+${R(r.total - best.total)}</small>`}</span></div>`).join("") + `</div>`;
    h += `<p class="hint">Compared on the <b>${common.length} of ${idx.length}</b> everyday items that ${rows.map((r) => CHAINS[r.c].name).join(", ")} all price, at ${$("loyalty").checked ? "loyalty-card" : "normal shelf"} prices. Store prices only: build your own basket below to add travel or delivery.` +
      (others.length ? ` ${others.map((c) => CHAINS[c].name).join(", ")}: ${others.map((c) => priced(c)).join(", ")} of ${idx.length} items priced so far (coverage grows daily).` : "") + `</p>`;
  } else {
    h += `<p class="hint">Not enough stores price these items yet to compare fairly. Coverage grows every morning.</p>`;
  }
  const allc = ["checkers", "shoprite", "pnp"].filter((c) => priced(c));
  h += `<details><summary>See the ${idx.length} items and prices</summary><div class="scroll"><table><thead><tr><th>Item</th>${allc.map((c) => `<th>${CHAINS[c].name}</th>`).join("")}</tr></thead><tbody>` +
    idx.map((x) => {
      const vals = allc.map((c) => (x.it.prices[c] ? unitPrice(x.it.prices[c]).v : null));
      const lo = Math.min(...vals.filter((v) => v !== null));
      return `<tr><td>${esc(x.it.name)}</td>` + allc.map((c, k) => {
        const p = x.it.prices[c];
        if (!p) return `<td class="na">–</td>`;
        const when = p.stale && p.fetched_at ? `<span class="dated">from ${new Date(p.fetched_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short" })}</span>` : "";
        return `<td class="${vals[k] === lo ? "cheap" : ""}">${R(vals[k])}${when}</td>`;
      }).join("") + `</tr>`;
    }).join("") + `</tbody></table></div></details>`;
  h += `<p style="margin-top:10px"><button class="btn primary" id="std-use">Use this basket as mine</button> <span class="hint">then add or remove items, and include travel or delivery</span></p>`;
  el.innerHTML = h;
  $("std-use").addEventListener("click", () => {
    S.basket = {};
    for (const x of idx) S.basket[x.id] = x.qty || 1;
    saveBasket();
    $("step-results").scrollIntoView({ behavior: "smooth" });
  });
}

function render() {
  renderStandard();
  const lines = Object.entries(S.basket).map(([id, qty]) => ({ it: S.byId.get(id), qty })).filter((l) => l.it);
  renderBreakdown(lines);
  const res = $("results");
  if (!lines.length) { res.innerHTML = `<p class="hint">Add items to your basket to see where to shop.</p>`; drawStores({}); updateSticky(null); return; }

  const near = nearestStores();
  const nearAll = nearestStores(false);
  drawStores(near);
  const haveStores = S.stores.length > 0 && S.loc;
  const chains = Object.keys(CHAINS).filter((c) => lines.some((l) => l.it.prices[c]));

  // Like-for-like: compare chains only on items EVERY compared chain prices. A chain is compared if it
  // has a store nearby and prices at least 60% of the basket; items outside the common set are listed.
  const enough = (c) => lines.filter((l) => l.it.prices[c]).length >= Math.max(1, Math.ceil(lines.length * 0.6));
  let eligible = chains.filter((c) => (!haveStores || near[c]) && enough(c));
  if (haveStores && eligible.length < 2) {
    for (const c of chains) if (!near[c] && nearAll[c] && enough(c)) near[c] = nearAll[c];
    eligible = chains.filter((c) => near[c] && enough(c));
  }
  const common = lines.filter((l) => eligible.every((c) => l.it.prices[c]));
  const excluded = lines.filter((l) => !common.includes(l));
  const others = chains.filter((c) => !eligible.includes(c) && (!haveStores || near[c]));

  const delivery = mode() === "delivery";
  const opts = [];
  for (const c of eligible) {
    const st = near[c];
    let total = 0; let promos = 0;
    for (const { it, qty } of common) {
      const u = unitPrice(it.prices[c]); total += u.v * qty; if (u.promo) promos++;
    }
    if (delivery) {
      const d = deliveryFee(c, total);
      opts.push({ kind: "single", chains: [c], stores: st ? [st] : [], goods: total, travel: d.fee,
                  road: 0, missing: [], promos, delivery: d });
    } else {
      const road = st ? st.d * ROAD_FACTOR * 2 : 0;
      opts.push({ kind: "single", chains: [c], stores: st ? [st] : [], goods: total, travel: st ? tripCost(road) : 0, road, missing: [], promos });
    }
  }
  // Two-store split: only for driving (two deliveries = two fees, which almost never wins).
  if (haveStores && !delivery) {
    for (let i = 0; i < eligible.length; i++) for (let j = i + 1; j < eligible.length; j++) {
      const a = near[eligible[i]], b = near[eligible[j]];
      let goods = 0, inA = 0, inB = 0;
      for (const { it, qty } of common) {
        const va = unitPrice(it.prices[eligible[i]]).v, vb = unitPrice(it.prices[eligible[j]]).v;
        if (va <= vb) { goods += va * qty; inA++; } else { goods += vb * qty; inB++; }
      }
      if (!inA || !inB) continue;
      const road = (a.d + km(a, b) + b.d) * ROAD_FACTOR;
      opts.push({ kind: "split", chains: [eligible[i], eligible[j]], stores: [a, b], goods, travel: tripCost(road), road, missing: [], split: [inA, inB] });
    }
  }
  for (const o of opts) o.total = o.goods + o.travel;
  const ranked = opts.filter((o) => !o.missing.length).sort((x, y) => x.total - y.total);
  // only show the best split, and only if it beats the best single shop
  const bestSingle = ranked.find((o) => o.kind === "single");
  const bestSplit = ranked.find((o) => o.kind === "split");
  const shown = ranked.filter((o) => o.kind === "single");
  if (bestSplit && bestSingle && bestSplit.total < bestSingle.total - 1) shown.push(bestSplit);
  shown.sort((x, y) => x.total - y.total);

  // "Your basket at each store": every chain that prices any of the basket, full totals, gaps listed.
  const summary = chains.map((c) => {
    const have = lines.filter((l) => l.it.prices[c]);
    const goods = have.reduce((a, { it, qty }) => a + unitPrice(it.prices[c]).v * qty, 0);
    const st = nearAll[c];
    const extra = delivery ? deliveryFee(c, goods).fee : (st ? tripCost(st.d * ROAD_FACTOR * 2) : null);
    return { c, have: have.length, missing: lines.filter((l) => !l.it.prices[c]).map((l) => l.it.name),
             goods, extra, total: goods + (extra || 0), st };
  }).sort((a, b) => a.missing.length - b.missing.length || a.total - b.total);
  S.summary = summary;

  let html = "";
  if (!delivery && !S.loc) {
    html += `<p><button class="btn primary" id="geo2">📍 Use my location to add travel costs</button></p>`;
  }
  if (summary.length) {
    const lo = Math.min(...summary.filter((r) => !r.missing.length).map((r) => r.total));
    html += `<h3 class="sub-h">Your basket at each store</h3><div class="scroll"><table class="sumtab"><thead><tr><th>Store</th><th>Items</th><th>Total</th></tr></thead><tbody>` +
      summary.map((r) => `<tr class="${!r.missing.length && r.total === lo ? "best-row" : ""}"><td><span class="dot" style="background:${CHAINS[r.c].color}"></span> ${CHAINS[r.c].name}${r.st && !delivery ? `<small class="${r.st.far ? "warn" : ""}">${r.st.d.toFixed(1)} km${r.st.far ? " (further than your max distance)" : ""}</small>` : (!r.st && !delivery && S.loc ? `<small class="warn">no branch on our map</small>` : "")}</td>` +
        `<td>${r.have}/${lines.length}</td><td><b>${R(r.total)}</b><small>${R(r.goods)} groceries${r.extra === null ? "" : " + " + (r.extra === 0 && delivery ? "free delivery" : R(r.extra) + (delivery ? " delivery" : " travel"))}</small></td></tr>` +
        (r.missing.length ? `<tr class="miss"><td colspan="3">Not priced at ${CHAINS[r.c].name}: ${r.missing.map(esc).join(", ")}</td></tr>` : "")).join("") +
      `</tbody></table></div>`;
  }
  html += `<h3 class="sub-h">Best option, like-for-like</h3>`;
  const cardOn = $("loyalty").checked;
  html += `<p class="hint">${delivery ? "🚚 <b>Home delivery</b>: groceries + each store's delivery fee." : "🚗 <b>Drive to store</b>: groceries + fuel there and back."} ` +
    `Prices shown ${cardOn ? "<b>with</b> loyalty-card specials (Xtra Savings, Smart Shopper)." : "at <b>normal shelf price</b> (no loyalty card)."}</p>`;
  if (!delivery && !S.loc) html += `<p class="hint warn">Travel costs aren't included yet: tap "Use my location" above, or set it in step 1.</p>`;
  else if (!delivery && !S.stores.length) html += `<p class="hint warn">Store locations are still loading on the server. Showing basket prices only.</p>`;
  if (!shown.length) html += `<p class="hint">No nearby chains to compare. Try increasing the max distance in travel settings, or see the per-item table below.</p>`;
  html += `<div class="rank">` + shown.map((o, k) => optCard(o, k === 0, shown[0])).join("") + `</div>`;
  if (excluded.length && eligible.length) {
    html += `<p class="hint" style="margin-top:12px">Compared on the ${common.length} of your ${lines.length} items that ${eligible.map((c) => CHAINS[c].name).join(", ")} all sell online. ` +
      `Not compared: ${excluded.map((l) => esc(l.it.name) + " (" + (Object.keys(l.it.prices).map((c) => CHAINS[c].name).join(", ") || "none") + ")").join("; ")}.</p>`;
  }
  if (others.length) {
    html += `<p class="hint">${others.map((c) => CHAINS[c].name).join(", ")}: not enough of your basket is priced online to compare fairly (see the table below).</p>`;
  }
  if (bestSingle && S.loc) {
    const worst = shown.filter((o) => o.kind === "single").slice(-1)[0];
    if (worst && worst !== bestSingle) html += `<p class="hint">Shopping at the best option instead of the most expensive saves <b>${R(worst.total - bestSingle.total)}</b> on this basket.</p>`;
  }
  html += otherStoresPanel(near, chains);
  html += `<p class="disclaimer">Prices shown are the most recent we have on record and may not be 100% up to date at the time you shop. Where a price is older than today, its date is shown. Always check the price at the till.</p>`;
  res.innerHTML = html;
  if ($("geo2")) $("geo2").addEventListener("click", useGeolocation);
  updateSticky(shown[0], delivery);
}

function updateSticky(best, delivery) {
  const bar = $("sticky");
  if (!bar) return;
  const n = Object.keys(S.basket).length;
  if (!n || !best) { bar.hidden = true; return; }
  const what = best.delivery ? "incl. delivery" : best.stores.length ? "incl. travel" : "groceries only";
  const name = best.chains.map((c) => CHAINS[c].name).join(" + ");
  bar.innerHTML = `<span><b>${n} item${n === 1 ? "" : "s"}</b> · Cheapest: <b>${name} ${R(best.total)}</b> <small>${what}</small></span><button class="btn primary" id="sticky-go">See comparison</button>`;
  bar.hidden = false;
  $("sticky-go").addEventListener("click", () => $("step-results").scrollIntoView({ behavior: "smooth" }));
}

function otherStoresPanel(near, pricedChains) {
  const rows = Object.keys(SPECIALS).filter((c) => !pricedChains.includes(c) && near[c])
    .sort((a, b) => near[a].d - near[b].d)
    .map((c) => `<li><span class="dot" style="background:${CHAINS[c].color}"></span> <b>${CHAINS[c].name}</b>: ${esc(near[c].name || "")}${near[c].suburb ? ", " + esc(near[c].suburb) : ""} (${near[c].d.toFixed(1)} km) · <a href="${SPECIALS[c]}" target="_blank" rel="noopener nofollow">This week's specials ↗</a></li>`);
  if (!rows.length) return "";
  return `<div class="others"><p class="hint" style="margin:14px 0 6px"><b>Other stores near you</b>. These chains don't publish their prices online, so we can't price your basket there. Check their specials before you go:</p><ul>${rows.join("")}</ul></div>`;
}

function optCard(o, best, top) {
  const names = o.chains.map((c) => `<span class="dot" style="background:${CHAINS[c].color}"></span>${CHAINS[c].name}`).join(" + ");
  const where = o.stores.map((s) => `${esc(s.name || "")}${s.suburb ? ", " + esc(s.suburb) : ""} (${s.d.toFixed(1)} km${s.far ? `, <span class="warn">further than your max distance</span>` : ""})`).join(" → ");
  const extra = top && !best ? `<div class="save">+${R(o.total - top.total)}</div>` : best ? `<div class="save">Cheapest</div>` : "<div></div>";
  let line;
  if (o.delivery) {
    line = `Groceries ${R(o.goods)} + ${o.delivery.service || "delivery"} ${o.delivery.fee === 0 ? "free" : R(o.delivery.fee)}`;
    if (o.delivery.belowMin) line += `<br><span class="warn">Below ${R(o.delivery.min_order)} minimum order — add more or pay a surcharge.</span>`;
  } else {
    line = o.stores.length ? `Groceries ${R(o.goods)} + travel ${R(o.travel)} (${o.road.toFixed(0)} km round trip)` : `Groceries only. Set location for travel cost`;
  }
  return `<div class="opt ${best ? "best" : ""}">
    <div class="title">${names} ${best ? '<span class="badge">Best</span>' : ""} ${o.kind === "split" ? '<span class="chip">Split shop</span>' : ""}</div>
    <div class="total">${R(o.total)}</div>
    <div class="sub">${line}${where && !o.delivery ? "<br>" + where : ""}${o.split ? `<br>${o.split[0]} items at ${CHAINS[o.chains[0]].name}, ${o.split[1]} at ${CHAINS[o.chains[1]].name}` : ""}</div>
    ${extra}
  </div>`;
}

function renderBreakdown(lines) {
  const el = $("breakdown");
  if (!lines.length) { el.innerHTML = `<p class="hint">Your basket is empty.</p>`; return; }
  const chains = Object.keys(CHAINS).filter((c) => lines.some((l) => l.it.prices[c]));
  let h = `<table><thead><tr><th>Item</th><th>Qty</th>${chains.map((c) => `<th>${CHAINS[c].name}</th>`).join("")}</tr></thead><tbody>`;
  for (const { it, qty } of lines) {
    const vals = chains.map((c) => (it.prices[c] ? unitPrice(it.prices[c]) : null));
    const lo = Math.min(...vals.filter(Boolean).map((v) => v.v));
    h += `<tr><td>${esc(it.name)}</td><td>${qty}</td>` + chains.map((c, k) => {
      const v = vals[k]; const p = it.prices[c];
      if (!v) return `<td class="na">–</td>`;
      const when = p.stale && p.fetched_at ? new Date(p.fetched_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short" }) : "";
      return `<td class="${v.v === lo ? "cheap" : ""}"><a href="${esc(p.url || "#")}" target="_blank" rel="noopener nofollow">${R(v.v)}</a>${p.promo ? `<span class="promo" title="${esc(p.promo)}">${esc(p.promo.length > 40 ? p.promo.slice(0, 38) + "…" : p.promo)}</span>` : ""}${when ? `<span class="dated" title="Last checked ${when}; refreshes on a rolling basis">from ${when}</span>` : ""}</td>`;
    }).join("") + `</tr>`;
  }
  h += `</tbody></table>`;
  el.innerHTML = h;
}

function drawStores(near) {
  if (!S.storeLayer) return;
  S.storeLayer.clearLayers();
  for (const [c, s] of Object.entries(near)) {
    L.circleMarker([s.lat, s.lon], { radius: 7, color: getComputedStyle(document.documentElement).getPropertyValue("--" + c).trim() || "#333", weight: 3, fillOpacity: 0.8 })
      .bindTooltip(`${CHAINS[c].name}: ${s.name || ""} (${s.d.toFixed(1)} km)`).addTo(S.storeLayer);
  }
}

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]); }

boot().catch((e) => { document.querySelector("main").insertAdjacentHTML("afterbegin", `<p class="card warn">Couldn't load price data (${esc(e.message)}). Please try again shortly.</p>`); });
