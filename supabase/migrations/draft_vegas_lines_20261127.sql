-- JEG-1667: pasted Vegas season player props, one dated snapshot shared by
-- every league (Jeremy, 2026-11-27: "I'll paste the lines.").
-- NOT APPLIED: needs Jeremy's named yes (AGENTS.md: every Supabase
-- migration; the 2026-11-27 yes covered the draft-pull deploy only). Until
-- then snapshots are files written by tools/draft_vegas_paste.mjs.
-- New object only; public.vegas_season_totals (the 2026-09-12 snapshot) is
-- not touched. Same row shape, so both feed ours the same way.
-- Idempotent.
begin;

create table if not exists public.draft_vegas_lines (
  snapshot_date date not null,
  season integer not null,
  source text not null default 'paste' check (source in ('paste')),
  player_key bigint not null,
  player_name text not null,
  team text,
  market text not null check (market in ('season_pass_yds', 'season_pass_tds', 'season_rush_yds',
    'season_rush_tds', 'season_receptions', 'season_rec_yds', 'season_rec_tds')),
  line numeric not null,
  created_at timestamptz not null default now(),
  primary key (snapshot_date, player_key, market)
);
comment on table public.draft_vegas_lines is
  'JEG-1667 draft tool: Vegas season player prop lines pasted from a sportsbook page, one snapshot per date.';

alter table public.draft_vegas_lines enable row level security;
drop policy if exists draft_vegas_lines_read on public.draft_vegas_lines;
create policy draft_vegas_lines_read on public.draft_vegas_lines
  for select to anon, authenticated using (true);
grant select on public.draft_vegas_lines to anon, authenticated;
revoke insert, update, delete, truncate on public.draft_vegas_lines from anon, authenticated;

commit;
