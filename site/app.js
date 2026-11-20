/* BasketWise front end: no build step, no tracking, location never leaves the browser
   (except a typed suburb, which is sent to OpenStreetMap's geocoder to find it on the map). */
"use strict";

const CHAINS = {
  checkers:   { name: "Checkers",   color: "var(--checkers)" },
  shoprite:   { name: "Shoprite",   color: "var(--shoprite)" },
  pnp:        { name: "Pick n Pay", color: "var(--pnp)" },
  spar:       { name: "SPAR",       color: "var(--spar)" },
  woolworths: { name: "Woolworths", color: "var(--woolworths)" },
};
const ROAD_FACTOR = 1.3;      // straight line -> typical road distance
const AVG_SPEED_KMH = 35;     // urban driving, for the time-cost option
const PRESET = ["milk-2l", "eggs-18", "brown-bread", "white-bread", "maize-meal-10kg", "rice-2kg",
  "sugar-2_5kg", "cake-flour-2_5kg", "sunflower-oil-2l", "pasta-500g", "baked-beans-410g",
  "pilchards-400g", "peanut-butter-400g", "tomato-sauce-700ml", "tea-100", "coffee-200g",
  "oats-1kg", "chicken-portions", "toilet-paper-9", "dishwashing-750ml", "washing-powder-2kg",
  "bath-soap", "toothpaste-100ml", "butter-500g"];
const PRESET_QTY = { "milk-2l": 4, "brown-bread": 4, "white-bread": 2, "baked-beans-410g": 3, "pilchards-400g": 2, "bath-soap": 3 };

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
  S.stores = stores.stores || [];
  S.basket = store.get("basket", {});
  for (const id of ["fuel", "cons", "time", "maxkm"]) {
    const v = store.get(id, null);
    if (v !== null) $(id).value = v;
    $(id).addEventListener("input", () => { store.set(id, $(id).value); render(); });
  }
  $("loyalty").checked = store.get("loyalty", true);
  $("loyalty").addEventListener("change", () => { store.set("loyalty", $("loyalty").checked); render(); });
  renderFreshness();
  renderItems();
  initMap();
  const loc = store.get("loc", null);
  if (loc) setLoc(loc.lat, loc.lon, false);
  $("filter").addEventListener("input", renderItems);
  $("preset").addEventListener("click", () => {
    S.basket = {};
    for (const id of PRESET) if (S.prices.items.some((i) => i.id === id)) S.basket[id] = PRESET_QTY[id] || 1;
    saveBasket();
  });
  $("clear").addEventListener("click", () => { S.basket = {}; saveBasket(); });
  $("geo").addEventListener("click", useGeolocation);
  $("addr-form").addEventListener("submit", geocode);
  render();
}

function renderFreshness() {
  const p = S.prices;
  const when = new Date(p.generated_at);
  const ago = Math.round((Date.now() - when) / 36e5);
  const chips = [`<span class="chip">Prices updated ${ago < 1 ? "within the hour" : ago < 48 ? ago + "h ago" : when.toLocaleDateString("en-ZA")}</span>`];
  for (const [id, h] of Object.entries(p.retailers)) {
    const good = h.status === "ok";
    const label = h.status === "ok" ? `${h.items_priced} items` : h.status === "specials-only" ? "specials only" : "unavailable";
    chips.push(`<span class="chip ${good ? "ok" : "bad"}" title="${esc(h.note)}">${esc(h.name)}: ${label}</span>`);
  }
  $("freshness").innerHTML = chips.join("");
  $("coverage").innerHTML = Object.values(p.retailers).map((h) => `<b>${esc(h.name)}:</b> ${esc(h.note)}`).join("<br>");
}

function renderItems() {
  const q = $("filter").value.trim().toLowerCase();
  const byCat = {};
  for (const it of S.prices.items) {
    if (!Object.keys(it.prices).length) continue;
    const hay = (it.name + " " + (it.canonical_name || "") + " " + it.category).toLowerCase();
    if (q && !hay.includes(q)) continue;
    (byCat[it.category] ||= []).push(it);
  }
  let html = "";
  for (const [cat, items] of Object.entries(byCat)) {
    html += `<div class="cat">${esc(cat)}</div>`;
    for (const it of items) {
      const n = S.basket[it.id] || 0;
      const lo = Math.min(...Object.values(it.prices).map((p) => p.price));
      html += `<div class="item ${n ? "on" : ""}">
        <div class="nm">${esc(it.name)}<small>${esc(it.canonical_name || "")} · from ${R(lo)}</small></div>
        <div class="qty"><button data-id="${it.id}" data-d="-1" aria-label="Remove one">−</button><span>${n}</span><button data-id="${it.id}" data-d="1" aria-label="Add one">+</button></div>
      </div>`;
    }
  }
  $("items").innerHTML = html || `<p class="hint">No items match.</p>`;
  $("items").querySelectorAll("button[data-id]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.id;
    S.basket[id] = Math.max(0, (S.basket[id] || 0) + Number(b.dataset.d));
    if (!S.basket[id]) delete S.basket[id];
    saveBasket();
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

function nearestStores() {
  const out = {};
  if (!S.loc) return out;
  const max = Number($("maxkm").value) || 20;
  for (const s of S.stores) {
    const d = km(S.loc, s);
    if (d > max) continue;
    if (!out[s.chain] || d < out[s.chain].d) out[s.chain] = { ...s, d };
  }
  return out;
}

function tripCost(roadKm) {
  const fuel = Number($("fuel").value) || 0, cons = Number($("cons").value) || 0, t = Number($("time").value) || 0;
  return roadKm * (cons / 100) * fuel + (roadKm / AVG_SPEED_KMH) * t;
}

/* ------------------------------------------------------------------ pricing */
function unitPrice(p) {
  if ($("loyalty").checked && p.promo_price && p.promo_price < p.price) return { v: p.promo_price, promo: true };
  return { v: p.price, promo: false };
}

function render() {
  const lines = Object.entries(S.basket).map(([id, qty]) => ({ it: S.prices.items.find((i) => i.id === id), qty })).filter((l) => l.it);
  renderBreakdown(lines);
  const res = $("results");
  if (!lines.length) { res.innerHTML = `<p class="hint">Add items to your basket to see where to shop.</p>`; drawStores({}); return; }

  const near = nearestStores();
  drawStores(near);
  const haveStores = S.stores.length > 0 && S.loc;
  const chains = Object.keys(CHAINS).filter((c) => lines.some((l) => l.it.prices[c]));

  // Like-for-like: compare chains only on items EVERY compared chain prices. A chain is compared if it
  // has a store nearby and prices at least 60% of the basket; items outside the common set are listed.
  const eligible = chains.filter((c) => (!haveStores || near[c]) &&
    lines.filter((l) => l.it.prices[c]).length >= Math.max(1, Math.ceil(lines.length * 0.6)));
  const common = lines.filter((l) => eligible.every((c) => l.it.prices[c]));
  const excluded = lines.filter((l) => !common.includes(l));
  const others = chains.filter((c) => !eligible.includes(c) && (!haveStores || near[c]));

  const opts = [];
  for (const c of eligible) {
    const st = near[c];
    let total = 0; let promos = 0;
    for (const { it, qty } of common) {
      const u = unitPrice(it.prices[c]); total += u.v * qty; if (u.promo) promos++;
    }
    const road = st ? st.d * ROAD_FACTOR * 2 : 0;
    const travel = st ? tripCost(road) : 0;
    opts.push({ kind: "single", chains: [c], stores: st ? [st] : [], goods: total, travel, road, missing: [], promos });
  }
  // Two-store split over the same common items: buy each where it's cheaper, home -> A -> B -> home.
  if (haveStores) {
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

  let html = "";
  if (!S.loc) html += `<p class="hint warn">Set your location in step 1 to include travel costs. Showing basket prices only.</p>`;
  else if (!S.stores.length) html += `<p class="hint warn">Store locations are still loading on the server. Showing basket prices only.</p>`;
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
  res.innerHTML = html;
}

function optCard(o, best, top) {
  const names = o.chains.map((c) => `<span class="dot" style="background:${CHAINS[c].color}"></span>${CHAINS[c].name}`).join(" + ");
  const where = o.stores.map((s) => `${esc(s.name || "")}${s.suburb ? ", " + esc(s.suburb) : ""} (${s.d.toFixed(1)} km)`).join(" → ");
  const extra = top && !best ? `<div class="save">+${R(o.total - top.total)}</div>` : best ? `<div class="save">Cheapest</div>` : "<div></div>";
  const travel = o.stores.length ? `Groceries ${R(o.goods)} + travel ${R(o.travel)} (${o.road.toFixed(0)} km)` : `Groceries only. Set location for travel cost`;
  return `<div class="opt ${best ? "best" : ""}">
    <div class="title">${names} ${best ? '<span class="badge">Best</span>' : ""} ${o.kind === "split" ? '<span class="chip">Split shop</span>' : ""}</div>
    <div class="total">${R(o.total)}</div>
    <div class="sub">${travel}${where ? "<br>" + where : ""}${o.split ? `<br>${o.split[0]} items at ${CHAINS[o.chains[0]].name}, ${o.split[1]} at ${CHAINS[o.chains[1]].name}` : ""}${o.missing.length ? `<br><span class="warn">Missing: ${o.missing.map(esc).join(", ")}</span>` : ""}</div>
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
    h += `<tr><td>${esc(it.canonical_name || it.name)}</td><td>${qty}</td>` + chains.map((c, k) => {
      const v = vals[k]; const p = it.prices[c];
      if (!v) return `<td class="na">–</td>`;
      const stale = p.stale ? ` title="Price from ${new Date(p.fetched_at).toLocaleDateString("en-ZA")}"` : "";
      return `<td class="${v.v === lo ? "cheap" : ""}"${stale}><a href="${esc(p.url)}" target="_blank" rel="noopener nofollow">${R(v.v)}</a>${p.promo ? `<span class="promo" title="${esc(p.promo)}">${esc(p.promo.length > 40 ? p.promo.slice(0, 38) + "…" : p.promo)}</span>` : ""}</td>`;
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
