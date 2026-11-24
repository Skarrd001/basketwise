# Turning on optional sign-in (about 15 minutes, all free)

The app already contains sign-in, saved baskets, price-drop alerts and the weekly-email signup.
They stay hidden until you do the three steps below. **Never paste a password, secret key or SMTP
key into a chat**; the only two values Claude needs (step 1.4) are designed to be public.

## 1. Supabase (accounts and database)
1. Go to https://supabase.com → **Start your project** → sign up (free).
2. **New project**: name `basketwise`, a strong database password (keep it in your password manager,
   nobody else needs it), region **closest to South Africa** (e.g. *West EU (Ireland)*), plan **Free**.
3. When it's ready: left menu **SQL Editor** → **New query** → paste the whole of `supabase/schema.sql`
   from the repo → **Run**. It should say "Success. No rows returned".
4. Left menu **Project Settings → API** (or **Data API**). Copy these two and send them to Claude:
   - **Project URL** (looks like `https://abcdxyz.supabase.co`)
   - **anon / public** key (a long text starting `eyJ…`, or `sb_publishable_…`)
   ⚠️ Do **not** send the `service_role` / secret key.
5. **Authentication → URL Configuration**: set **Site URL** to `https://skarrd001.github.io/basketwise/`
   and add the same address under **Redirect URLs**.

## 2. Brevo (sends the sign-in links and, later, the weekly email)
Supabase's own email only reaches your team, not the public, so it needs a sender.
1. https://www.brevo.com → sign up (free: 300 emails/day).
2. **Senders, domains & dedicated IPs → Senders**: add and verify the address emails should come from.
   Best: a BasketWise address (e.g. a free `basketwise.za@gmail.com`), not your Bluestone address.
3. **SMTP & API → SMTP**: note the **SMTP server** (`smtp-relay.brevo.com`), **port** (587), **login**, and
   **generate an SMTP key**.
4. Back in Supabase: **Authentication → Emails → SMTP Settings** → enable custom SMTP and enter those
   details, with your verified sender address and sender name `BasketWise`. Save.
   (Type the SMTP key straight into Supabase. Never share it.)
5. Optional, nicer emails: **Authentication → Emails → Templates → Magic Link**, subject
   `Your BasketWise sign-in link`.

## 3. Google sign-in (optional, can be done later)
Supabase → **Authentication → Providers → Google** shows the exact steps (create an OAuth client in
Google Cloud Console, paste its ID and secret into Supabase). When it's on, tell Claude to set
`googleSignIn: true` in `site/config.js`.

## What happens next
Claude puts the two values from step 1.4 into `site/config.js` and publishes. The **Sign in** button,
the 🔔 alerts and the weekly-email box then appear. Before you promote the weekly email or alerts:
fill in the placeholders in `site/privacy.html` (company, Information Officer, email provider), and
register an Information Officer with the Information Regulator (POPIA).

Sending the weekly email and the price-drop alert emails is the next build step: a scheduled GitHub
Action that reads the subscriber and alert lists with the service key stored as a GitHub secret
(never in the website).
