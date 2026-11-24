-- BasketWise accounts: paste this whole file into Supabase -> SQL Editor -> New query -> Run.
-- Safe to run more than once.
--
-- Security model (Row Level Security on every table):
--   * a signed-in user can read and change ONLY their own basket and alerts
--   * anyone can ADD an email to the weekly-update list, but nobody can read the list from the app;
--     only the owner (Supabase dashboard / service key in GitHub Actions) can read it
--   * no passwords are stored: sign-in is by emailed link (or Google)

-- ---------------------------------------------------------------- saved baskets
create table if not exists public.baskets (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  items      jsonb not null default '{}'::jsonb,      -- { "<barcode>": qty, ... }
  updated_at timestamptz not null default now()
);
alter table public.baskets enable row level security;
drop policy if exists "own basket" on public.baskets;
create policy "own basket" on public.baskets
  for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------- price-drop alerts
create table if not exists public.alerts (
  id            bigint generated always as identity primary key,
  user_id       uuid not null references auth.users (id) on delete cascade,
  product_id    text not null check (length(product_id) between 6 and 20),
  product_name  text check (length(product_name) <= 200),
  price_at_set  numeric(10, 2),                       -- the lowest price when the alert was set
  last_notified timestamptz,
  created_at    timestamptz not null default now(),
  unique (user_id, product_id)
);
alter table public.alerts enable row level security;
drop policy if exists "own alerts" on public.alerts;
create policy "own alerts" on public.alerts
  for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------- weekly update subscribers
create table if not exists public.subscribers (
  id                bigint generated always as identity primary key,
  email             text not null unique check (email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' and length(email) <= 254),
  consent_text      text not null check (length(consent_text) <= 500),   -- exactly what they agreed to (POPIA s69)
  consent_at        timestamptz not null default now(),
  confirmed_at      timestamptz,                                         -- set when they click the confirmation email
  unsubscribe_token uuid not null default gen_random_uuid(),
  source            text check (length(source) <= 40)
);
alter table public.subscribers enable row level security;
drop policy if exists "anyone can subscribe" on public.subscribers;
create policy "anyone can subscribe" on public.subscribers
  for insert to anon, authenticated
  with check (confirmed_at is null);
-- (no select/update/delete policy: the list can't be read or changed from the app)

-- One-click unsubscribe from a link in any email: needs only the secret token in that link.
create or replace function public.unsubscribe(token uuid)
returns boolean language sql security definer set search_path = public as $$
  with d as (delete from public.subscribers where unsubscribe_token = token returning 1)
  select exists (select 1 from d);
$$;
revoke all on function public.unsubscribe(uuid) from public;
grant execute on function public.unsubscribe(uuid) to anon, authenticated;

-- Confirm a weekly-update subscription (double opt-in) from the link in the confirmation email.
create or replace function public.confirm_subscription(token uuid)
returns boolean language sql security definer set search_path = public as $$
  with u as (update public.subscribers set confirmed_at = coalesce(confirmed_at, now())
             where unsubscribe_token = token returning 1)
  select exists (select 1 from u);
$$;
revoke all on function public.confirm_subscription(uuid) from public;
grant execute on function public.confirm_subscription(uuid) to anon, authenticated;

-- "Delete my account": removes the user and, by cascade, their basket and alerts.
create or replace function public.delete_my_account()
returns void language plpgsql security definer set search_path = public, auth as $$
begin
  if auth.uid() is null then
    raise exception 'not signed in';
  end if;
  delete from auth.users where id = auth.uid();
end;
$$;
revoke all on function public.delete_my_account() from public;
grant execute on function public.delete_my_account() to authenticated;
