/* Optional sign-in (Supabase): saved basket across devices + price-drop alerts.
   Nothing here runs, and nothing extra is downloaded, until config.js is filled in.
   No passwords: sign-in is by an emailed one-tap link (or Google, if enabled). */
"use strict";
(function () {
  const cfg = window.BW_CONFIG || {};
  const SDK = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.min.js";
  const A = { sb: null, user: null, alerts: new Map(), saveTimer: null, lastSaved: null };
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) return;   // accounts not set up yet: stay invisible, add no hooks

  // Public hooks app.js calls; harmless no-ops until signed in.
  window.BWAccount = {
    get signedIn() { return !!A.user; },
    basketChanged() { if (A.user) scheduleSave(); },
    decorate() { if (A.sb) decorateBreakdown(); },
  };

  function loadSdk() {
    return new Promise((ok, fail) => {
      if (window.supabase) return ok();
      const s = document.createElement("script");
      s.src = SDK; s.async = true; s.onload = ok; s.onerror = () => fail(new Error("sign-in library failed to load"));
      document.head.appendChild(s);
    });
  }

  async function init() {
    const btn = $("account-btn");
    if (btn) { btn.hidden = false; btn.addEventListener("click", openDialog); }
    try { await loadSdk(); } catch { if (btn) btn.hidden = true; return; }
    A.sb = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey, {
      auth: { persistSession: true, detectSessionInUrl: true, flowType: "pkce" },
    });
    A.sb.auth.onAuthStateChange((_evt, session) => { setUser(session?.user || null); });
    const { data } = await A.sb.auth.getSession();
    await setUser(data.session?.user || null);
  }

  async function setUser(user) {
    const was = A.user?.id;
    A.user = user;
    const btn = $("account-btn");
    if (btn) btn.textContent = user ? "👤 My account" : "Sign in";
    if (user && user.id !== was) {
      await syncBasketDown();
      await loadAlerts();
    }
    if (!user) A.alerts.clear();
    // app.js redraws (adds or removes the alert bells) once its prices have loaded
    if (typeof render === "function" && typeof S !== "undefined" && S.prices) render();
    if ($("account-dlg")?.open) fillDialog();
  }

  // ---------------------------------------------------------------- saved basket
  async function syncBasketDown() {
    const { data, error } = await A.sb.from("baskets").select("items, updated_at").maybeSingle();
    if (error) return;
    const remote = (data && data.items) || {};
    const local = (typeof S !== "undefined" && S.basket) || {};
    // merge: keep everything from both, the larger quantity wins; drop products no longer listed
    const merged = { ...remote };
    for (const [id, q] of Object.entries(local)) merged[id] = Math.max(q, merged[id] || 0);
    if (typeof S !== "undefined") {
      S.basket = Object.fromEntries(Object.entries(merged).filter(([id]) => !S.byId || S.byId.has(id)));
      if (typeof store !== "undefined") store.set("basket", S.basket);
      if (typeof renderItems === "function") renderItems();
    }
    A.lastSaved = data?.updated_at || null;
    await saveNow();
  }

  function scheduleSave() {
    clearTimeout(A.saveTimer);
    A.saveTimer = setTimeout(saveNow, 1200);
  }

  async function saveNow() {
    if (!A.user || typeof S === "undefined") return;
    const updated_at = new Date().toISOString();
    const { error } = await A.sb.from("baskets").upsert({ user_id: A.user.id, items: S.basket, updated_at });
    if (!error) { A.lastSaved = updated_at; if ($("account-dlg")?.open) fillDialog(); }
  }

  // ---------------------------------------------------------------- price-drop alerts
  async function loadAlerts() {
    const { data } = await A.sb.from("alerts").select("product_id, product_name, price_at_set");
    A.alerts = new Map((data || []).map((a) => [a.product_id, a]));
  }

  function lowestPrice(it) {
    return Math.min(...Object.values(it.prices || {}).map((p) => p.price));
  }

  async function toggleAlert(id) {
    if (!A.user) { openDialog(); return; }
    if (A.alerts.has(id)) {
      await A.sb.from("alerts").delete().eq("product_id", id);
      A.alerts.delete(id);
    } else {
      const it = S.byId.get(id);
      const row = { user_id: A.user.id, product_id: id, product_name: it ? it.name.slice(0, 200) : null,
                    price_at_set: it ? lowestPrice(it) : null };
      const { error } = await A.sb.from("alerts").upsert(row, { onConflict: "user_id,product_id" });
      if (!error) A.alerts.set(id, row);
    }
    decorateBreakdown();
    if ($("account-dlg")?.open) fillDialog();
  }

  // Adds a bell to every row of the "Price by item" table. Shown to everyone; signing in is asked on tap.
  function decorateBreakdown() {
    document.querySelectorAll("#breakdown tr[data-id]").forEach((tr) => {
      const id = tr.dataset.id;
      let b = tr.querySelector(".bell");
      if (!b) {
        b = document.createElement("button");
        b.className = "bell";
        b.type = "button";
        b.addEventListener("click", () => toggleAlert(id));
        tr.firstElementChild.appendChild(b);
      }
      const on = A.alerts.has(id);
      b.textContent = on ? "🔔 Alert on" : "🔕 Alert me";
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.title = on ? "We'll email you when this gets cheaper. Tap to turn off." : "Email me when this gets cheaper";
    });
  }

  // ---------------------------------------------------------------- the account dialog
  function openDialog() {
    let d = $("account-dlg");
    if (!d) {
      d = document.createElement("dialog");
      d.id = "account-dlg";
      d.className = "acct";
      document.body.appendChild(d);
      d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
    }
    fillDialog();
    d.showModal();
  }

  function fillDialog() {
    const d = $("account-dlg");
    if (!d) return;
    if (!A.user) {
      d.innerHTML = `<form method="dialog" class="acct-close"><button aria-label="Close">✕</button></form>
        <h2>Sign in (optional)</h2>
        <p class="hint">Save your basket on all your devices and get an email when prices drop. No password: we email you a sign-in link.</p>
        <form id="acct-email" novalidate>
          <input type="email" id="acct-addr" required autocomplete="email" placeholder="you@example.com" aria-label="Email address">
          <button class="btn primary" type="submit">Email me a sign-in link</button>
        </form>
        ${cfg.googleSignIn ? `<p class="acct-or">or</p><button class="btn" id="acct-google" type="button">Continue with Google</button>` : ""}
        <p class="hint" id="acct-msg" role="status"></p>
        <p class="hint small">By signing in you agree to our <a href="terms.html">terms</a> and <a href="privacy.html">privacy policy</a>. You can delete your account at any time.</p>`;
      d.querySelector("#acct-email").addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = d.querySelector("#acct-addr").value.trim();
        const msg = d.querySelector("#acct-msg");
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { msg.textContent = "Please enter a valid email address."; return; }
        msg.textContent = "Sending…";
        const { error } = await A.sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + location.pathname } });
        msg.textContent = error ? "Sorry, that didn't work. Please try again in a few minutes."
          : `Check ${email} for a sign-in link. Open it on this device.`;
      });
      const g = d.querySelector("#acct-google");
      if (g) g.addEventListener("click", () => A.sb.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + location.pathname } }));
      return;
    }
    const alerts = [...A.alerts.values()];
    d.innerHTML = `<form method="dialog" class="acct-close"><button aria-label="Close">✕</button></form>
      <h2>Your account</h2>
      <p>Signed in as <b>${esc(A.user.email || "")}</b></p>
      <p class="hint">✅ Your basket (${Object.keys(S.basket).length} item${Object.keys(S.basket).length === 1 ? "" : "s"}) is saved to your account${A.lastSaved ? `, last saved ${new Date(A.lastSaved).toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" })}` : ""}.</p>
      <h3>Price-drop alerts (${alerts.length})</h3>
      ${alerts.length ? `<ul class="acct-alerts">${alerts.map((a) => `<li>${esc(a.product_name || a.product_id)}${a.price_at_set ? ` <span class="hint">(from R${Number(a.price_at_set).toFixed(2).replace(".", ",")})</span>` : ""} <button class="btn ghost" data-off="${esc(a.product_id)}">Remove</button></li>`).join("")}</ul>`
        : `<p class="hint">None yet. Tap "🔕 Alert me" next to any item in the <b>Price by item</b> table.</p>`}
      <div class="acct-actions">
        <button class="btn" id="acct-out" type="button">Sign out</button>
        <button class="btn ghost danger" id="acct-del" type="button">Delete my account</button>
      </div>
      <p class="hint" id="acct-msg" role="status"></p>`;
    d.querySelectorAll("button[data-off]").forEach((b) => b.addEventListener("click", () => toggleAlert(b.dataset.off)));
    d.querySelector("#acct-out").addEventListener("click", async () => { await A.sb.auth.signOut(); d.close(); });
    d.querySelector("#acct-del").addEventListener("click", async () => {
      if (!confirm("Delete your BasketWise account, saved basket and alerts? This can't be undone.")) return;
      const { error } = await A.sb.rpc("delete_my_account");
      if (error) { d.querySelector("#acct-msg").textContent = "Sorry, that didn't work. Please try again or email us."; return; }
      await A.sb.auth.signOut();
      d.innerHTML = `<h2>Account deleted</h2><p>Your account, saved basket and alerts have been deleted. Your basket is still on this device until you clear it.</p><form method="dialog"><button class="btn primary">Close</button></form>`;
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
