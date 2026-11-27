-- JEG-1732 (part of JEG-1653): DDF accounts and league connections, private staging.
-- Jeremy, 2026-11-27: "New schema, same project" — additive schema, RLS on, not
-- exposed to the public API; only the ddf-account edge function (direct Postgres
-- connection, service role) touches it. No existing table, view or row changes.
--
-- Platform tokens (Yahoo OAuth) are stored only as AES-256-GCM ciphertext made in
-- the edge function with the DDF_TOKEN_KEY function secret; the key never reaches
-- the database. Deleting an auth user cascades to everything below.

create schema if not exists ddf_accounts;
revoke all on schema ddf_accounts from public, anon, authenticated;

-- Staging gate: only these emails may use the edge function. Rows are added by
-- hand (never committed: emails are private).
create table if not exists ddf_accounts.allowlist (
  email      text primary key check (email = lower(email)),
  added_at   timestamptz not null default now()
);

create table if not exists ddf_accounts.connections (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users (id) on delete cascade,
  platform          text not null check (platform in ('sleeper', 'yahoo', 'espn')),
  external_id       text not null,          -- Sleeper user_id, Yahoo guid, ESPN league id
  display_name      text,
  secret_ciphertext bytea,                  -- AES-GCM ciphertext of the token JSON; null for public platforms
  secret_iv         bytea,
  token_expires_at  timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (user_id, platform, external_id),
  check ((secret_ciphertext is null) = (secret_iv is null))
);

-- One-time OAuth state (CSRF), 10 minutes.
create table if not exists ddf_accounts.oauth_states (
  state       text primary key,
  user_id     uuid not null references auth.users (id) on delete cascade,
  platform    text not null check (platform in ('yahoo')),
  return_to   text not null,
  expires_at  timestamptz not null default now() + interval '10 minutes'
);

create table if not exists ddf_accounts.leagues (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users (id) on delete cascade,
  connection_id      uuid not null references ddf_accounts.connections (id) on delete cascade,
  platform           text not null check (platform in ('sleeper', 'yahoo', 'espn')),
  league_key         text not null,
  season             int  not null,
  name               text,
  my_team_key        text,
  summary            jsonb not null,        -- ddf-connected-league/0 (settings, teams, rosters, standings, schedule, deadline, FAAB, waivers)
  raw                jsonb not null,        -- platform payloads as returned, for audit
  confirmed_settings jsonb,                 -- what the user confirmed; drives DDF when present
  confirmed_at       timestamptz,
  pulled_at          timestamptz not null,
  created_at         timestamptz not null default now(),
  unique (user_id, platform, league_key)
);
create index if not exists leagues_connection on ddf_accounts.leagues (connection_id);

-- Shared platform reference data (Sleeper player names), refreshed at most daily.
create table if not exists ddf_accounts.platform_cache (
  key         text primary key,
  body        jsonb not null,
  fetched_at  timestamptz not null default now()
);

alter table ddf_accounts.allowlist      enable row level security;
alter table ddf_accounts.connections    enable row level security;
alter table ddf_accounts.oauth_states   enable row level security;
alter table ddf_accounts.leagues        enable row level security;
alter table ddf_accounts.platform_cache enable row level security;
revoke all on all tables in schema ddf_accounts from public, anon, authenticated;
-- No policies: nothing but the service role (edge function) can read or write.

comment on schema ddf_accounts is
  'JEG-1732 signed-in DDF staging: accounts, platform connections and pulled leagues. Not exposed to PostgREST; ddf-account edge function only.';
