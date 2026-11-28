-- JEG-1667 Phase 0: draft tool daily pull storage. Applied 2026-11-27 via the
-- Supabase MCP on Jeremy's yes (AGENTS.md: every Supabase migration). New objects only,
-- all prefixed draft_; no existing table, view or function is touched.
--
-- draft_pulls: one row per source per UTC day (ok or failed), with the
--   source's own "last updated" time, so a page can show its pull date and a
--   stale warning when the latest ok pull is old.
-- draft_market_values: recurring draft data that is the same for every league
--   (FantasyPros 2026 draft ECR; ESPN 2026 published auction values, AAV,
--   ADP). League-specific math runs client side (app/draft/draft-engine.js).
-- draft_market_latest: the latest ok pull per source.
--
-- RLS is on. Anyone may read (Jeremy, 2026-11-27: show FantasyPros numbers
-- "with attribution"); only the service role (the edge function) writes.
-- Every row carries `credit`, the source credit a page must show with its
-- numbers. No live page reads these objects yet (hold of 2026-11-16).
-- Idempotent.
begin;

create table if not exists public.draft_pulls (
  id bigserial primary key,
  pull_date date not null,
  source text not null check (source in ('fantasypros_ecr', 'espn')),
  season integer not null,
  status text not null check (status in ('ok', 'failed')),
  rows integer not null default 0,
  source_updated_at timestamptz,
  detail jsonb not null default '{}'::jsonb,
  pulled_at timestamptz not null default now(),
  unique (pull_date, source)
);
comment on table public.draft_pulls is
  'JEG-1667 draft tool: one row per source per UTC day; season is the season the source states (2026 data is labeled 2026).';

create table if not exists public.draft_market_values (
  pull_date date not null,
  source text not null check (source in ('fantasypros_ecr', 'espn')),
  season integer not null,
  scoring text not null check (scoring in ('STD', 'HALF', 'PPR')),
  source_player_id text not null,
  player_name text not null,
  pos text not null,
  team text,
  bye integer,
  rank_overall numeric,
  rank_pos text,
  tier integer,
  rank_sd numeric,
  dollars numeric,
  aav numeric,
  adp numeric,
  credit text not null default '',
  created_at timestamptz not null default now(),
  primary key (pull_date, source, scoring, source_player_id)
);
comment on table public.draft_market_values is
  'JEG-1667 draft tool: recurring draft data per pull date. dollars = platform published auction value; aav = average auction price paid; rank_* = consensus rank.';

alter table public.draft_pulls enable row level security;
alter table public.draft_market_values enable row level security;

drop policy if exists draft_pulls_read on public.draft_pulls;
create policy draft_pulls_read on public.draft_pulls
  for select to anon, authenticated using (true);
drop policy if exists draft_market_values_read on public.draft_market_values;
create policy draft_market_values_read on public.draft_market_values
  for select to anon, authenticated using (true);
grant select on public.draft_pulls, public.draft_market_values to anon, authenticated;
revoke insert, update, delete, truncate on public.draft_pulls, public.draft_market_values from anon, authenticated;

create or replace view public.draft_market_latest
with (security_invoker = true) as
select v.*
from public.draft_market_values v
join (
  select source, max(pull_date) as pull_date
  from public.draft_pulls
  where status = 'ok'
  group by source
) l on l.source = v.source and l.pull_date = v.pull_date;
grant select on public.draft_market_latest to anon, authenticated;
comment on view public.draft_market_latest is
  'JEG-1667 draft tool: rows from the latest ok pull of each source; pull_date is on every row.';

commit;
