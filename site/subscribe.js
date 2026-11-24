/* Weekly-update signup: email only, no account. Talks to Supabase's REST API directly (no library),
   so it also works on the static weekly and product pages. Hidden when config.js isn't filled in. */
"use strict";
(function () {
  const cfg = window.BW_CONFIG || {};
  const CONSENT = "Send me the BasketWise weekly grocery prices update by email. I can unsubscribe at any time.";

  function forms() { return document.querySelectorAll("[data-bw-subscribe]"); }

  function render(el) {
    el.innerHTML = `<form class="sub-form" novalidate>
      <p class="sub-title"><b>📬 Get this week's cheapest basket by email</b></p>
      <div class="sub-row">
        <input type="email" name="email" required autocomplete="email" placeholder="you@example.com" aria-label="Email address">
        <button class="btn primary" type="submit">Subscribe</button>
      </div>
      <label class="sub-consent"><input type="checkbox" name="consent" required> ${CONSENT}</label>
      <p class="sub-msg hint" role="status"></p>
    </form>`;
    const f = el.querySelector("form");
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = f.querySelector(".sub-msg");
      const email = f.email.value.trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { msg.textContent = "Please enter a valid email address."; return; }
      if (!f.consent.checked) { msg.textContent = "Please tick the box to agree to receive the email."; return; }
      f.querySelector("button").disabled = true;
      msg.textContent = "Subscribing…";
      try {
        const r = await fetch(`${cfg.supabaseUrl}/rest/v1/subscribers`, {
          method: "POST",
          headers: { apikey: cfg.supabaseAnonKey, Authorization: `Bearer ${cfg.supabaseAnonKey}`,
                     "Content-Type": "application/json", Prefer: "return=minimal" },
          body: JSON.stringify({ email, consent_text: CONSENT, source: el.dataset.bwSubscribe || "app" }),
        });
        // 409 = already on the list: same answer, so the form can't be used to test who is subscribed
        if (r.ok || r.status === 409) {
          msg.textContent = "Thanks! Check your inbox for a confirmation email (it may take a few minutes).";
          f.email.value = "";
        } else {
          msg.textContent = "Sorry, that didn't work. Please try again later.";
        }
      } catch {
        msg.textContent = "Sorry, that didn't work. Please check your connection and try again.";
      }
      f.querySelector("button").disabled = false;
    });
  }

  function init() {
    if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) { forms().forEach((el) => { el.hidden = true; }); return; }
    forms().forEach((el) => { el.hidden = false; render(el); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
