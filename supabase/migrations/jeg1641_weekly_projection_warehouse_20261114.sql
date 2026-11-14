-- JEG-1641: daily, append-only warehouse of per-player per-week projections for
-- every future week (QB/RB/WR/TE), plus the daily expected-to-play inputs.
-- Jeremy 2026-11-14: "Run a process to warehouse everything that projects out weeks."
-- Sources surveyed in JEG-1640 (06-audit/weekly-projection-sources-2026-11-14.md):
-- only ESPN and Sleeper (RotoWire) project every remaining week; CBS and
-- FantasyPros publish the current week only and are stored tagged with that week.
--
-- Decision (Jeremy, 2026-11-14, relayed by the coordinator): "A. Yes, apply the
-- migration with daily full copies as designed, no deletion, revisit retention in
-- the offseason." Applied only after an independent review of this file.
--
-- Storage only. No view, function or published output reads these tables; no
-- value logic; no ROS rows (Jeremy 2026-10-29: never blend weekly with ROS).
-- What is reused instead of duplicated:
--   * Sleeper injury/roster status: public.player_status_history (JEG-521, daily).
--   * ESPN fetch: the daily espn-weekly-store run (one ESPN pull per run; the
--     saver also writes these rows). public.source_projection_captures (JEG-944,
--     twice weekly, first-one-wins) is left unchanged for its gate and JEG-945.
--   * Calendar: public.nfl_content_week(date) (JEG-432).
--
-- Naming: <subproject>_<entity> (docs/supabase-naming-conventions.md).

-- ---------------------------------------------------------------- run log
-- One row per source per run, written after that source's rows land. The
-- freshness check reads max(as_of) per source from here.
create table if not exists public.source_projection_runs (
    run_id         uuid        not null,
    source         text        not null check (source in
                       ('espn', 'sleeper', 'cbs', 'fantasypros', 'nflverse_schedule', 'nflverse_injuries')),
    as_of          timestamptz not null,
    season         smallint    not null,
    -- content week at as_of (public.nfl_content_week, Tuesday flip)
    content_week   smallint    not null check (content_week between 1 and 22),
    target_weeks   smallint[]  not null default '{}',
    rows_written   integer     not null check (rows_written >= 0),
    workflow_run   text,
    detail         jsonb       not null default '{}'::jsonb,
    primary key (run_id, source)
);
create index if not exists source_projection_runs_latest_idx
    on public.source_projection_runs (source, as_of desc);

-- ---------------------------------------------------------------- projections
create table if not exists public.source_weekly_projections (
    id               bigint generated always as identity primary key,
    run_id           uuid        not null,
    source           text        not null check (source in ('espn', 'sleeper', 'cbs', 'fantasypros')),
    -- every_week: the source projects each remaining week (espn, sleeper);
    -- current_week: the source publishes only the week it is on (cbs, fantasypros)
    coverage         text        not null check (coverage in ('every_week', 'current_week')),
    as_of            timestamptz not null,
    season           smallint    not null,
    content_week     smallint    not null check (content_week between 1 and 22),
    target_week      smallint    not null check (target_week between 1 and 22),
    -- identity: the source's own id always; ours when resolved (null = unresolved,
    -- the row is still kept, as player_status_history does)
    source_player_id text        not null,
    player_key       bigint      references public.players (player_key),
    sleeper_id       text,
    full_name        text,
    position         text        not null check (position in ('QB', 'RB', 'WR', 'TE')),
    team             text,
    opponent         text,
    -- points in the three standard formats; null when the source does not give
    -- (or we cannot derive) that format. Never 0 for "missing".
    points_std       numeric(7,2),
    points_half_ppr  numeric(7,2),
    points_ppr       numeric(7,2),
    -- the source's own headline number and the scoring it assumes
    source_points    numeric(7,2),
    scoring_basis    text        not null,
    -- the raw projected stat line exactly as the source gives it (keys are the
    -- source's own); null when the source gives points only
    stats            jsonb,
    source_updated_at timestamptz,
    constraint source_weekly_projections_week_ok check (target_week >= content_week),
    constraint source_weekly_projections_has_value check (
        points_std is not null or points_half_ppr is not null or points_ppr is not null
        or source_points is not null or stats is not null),
    constraint source_weekly_projections_key unique (run_id, source, source_player_id, target_week)
);
comment on table public.source_weekly_projections is
    'JEG-1641: append-only daily copy of each source''s per-player projection for every future week (espn, sleeper) or the current week (cbs, fantasypros). as_of = capture time, run_id joins source_projection_runs. Not read by any published output. Service role only.';
create index if not exists source_weekly_projections_player_idx
    on public.source_weekly_projections (player_key, season, target_week, as_of desc);
create index if not exists source_weekly_projections_run_idx
    on public.source_weekly_projections (source, season, as_of desc);

-- ---------------------------------------------------------------- schedule and byes
create table if not exists public.nflverse_schedule_snapshots (
    run_id      uuid        not null,
    as_of       timestamptz not null,
    season      smallint    not null,
    game_id     text        not null,
    game_type   text,
    week        smallint    not null,
    gameday     date,
    gametime    text,
    away_team   text        not null,
    home_team   text        not null,
    away_score  smallint,
    home_score  smallint,
    spread_line numeric(5,1),
    total_line  numeric(5,1),
    primary key (run_id, game_id)
);
create index if not exists nflverse_schedule_snapshots_latest_idx
    on public.nflverse_schedule_snapshots (season, as_of desc);

-- ---------------------------------------------------------------- injury reports
-- nflverse injuries (CC-BY-4.0): the official weekly report. Stored daily for the
-- latest report week in the file (earlier weeks are final and already stored).
create table if not exists public.nflverse_injury_snapshots (
    run_id                  uuid        not null,
    as_of                   timestamptz not null,
    season                  smallint    not null,
    week                    smallint    not null,
    gsis_id                 text        not null,
    player_key              bigint      references public.players (player_key),
    sleeper_id              text,
    full_name               text,
    position                text        not null check (position in ('QB', 'RB', 'WR', 'TE')),
    team                    text,
    report_status           text,
    report_primary_injury   text,
    practice_status         text,
    practice_primary_injury text,
    primary key (run_id, season, week, gsis_id)
);
create index if not exists nflverse_injury_snapshots_player_idx
    on public.nflverse_injury_snapshots (player_key, season, week, as_of desc);

-- ---------------------------------------------------------------- append-only
create or replace function public.source_weekly_warehouse_append_only()
returns trigger language plpgsql set search_path = '' as $$
begin
    raise exception '% is append-only (%).', tg_table_name, tg_op;
end;
$$;

do $$
declare t text;
begin
    foreach t in array array['source_projection_runs', 'source_weekly_projections',
                             'nflverse_schedule_snapshots', 'nflverse_injury_snapshots'] loop
        execute format('drop trigger if exists %I on public.%I', t || '_no_change', t);
        execute format('create trigger %I before update or delete on public.%I '
                       'for each row execute function public.source_weekly_warehouse_append_only()',
                       t || '_no_change', t);
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
    end loop;
end;
$$;

-- ---------------------------------------------------------------- size
-- Read by pipelines/check_projection_warehouse.py for the size alert (the
-- thresholds live there and in docs/weekly-projection-warehouse.md).
create or replace function public.source_weekly_warehouse_size()
returns table (relation text, bytes bigint)
language sql stable security definer set search_path = '' as $$
    select 'database', pg_catalog.pg_database_size(pg_catalog.current_database())
    union all
    select c.relname::text, pg_catalog.pg_total_relation_size(c.oid)
      from pg_catalog.pg_class c
      join pg_catalog.pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relname in ('source_projection_runs', 'source_weekly_projections',
                         'nflverse_schedule_snapshots', 'nflverse_injury_snapshots')
$$;
revoke all on function public.source_weekly_warehouse_size() from public, anon, authenticated;
grant execute on function public.source_weekly_warehouse_size() to service_role;

-- ---------------------------------------------------------------- schedule
-- Daily 13:30 UTC (07:30 CST), after espn-weekly-store-live (12:40) and
-- player-status-history-live (13:10); Sunday 16:40 UTC (10:40 CST) game-day copy,
-- before the 12:00 CT kickoffs. ESPN rows come from espn-weekly-store itself.
select cron.schedule(
    'weekly-projection-warehouse-daily',
    '30 13 * * *',
    $$SELECT public.dispatch_gha_workflow('weekly-projection-warehouse.yml', '{"mode": "write"}'::jsonb)$$
);
select cron.schedule(
    'weekly-projection-warehouse-sunday',
    '40 16 * * 0',
    $$SELECT public.dispatch_gha_workflow('weekly-projection-warehouse.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('weekly_projection_warehouse', 'http_status_and_content', 86400, 7200,
     'github_actions', 'weekly-projection-warehouse.yml',
     '{"severity": "warn", "what": "Daily append-only weekly projections (sleeper, cbs, fantasypros) and nflverse schedule/injury snapshots, plus the per-source freshness check over source_projection_runs (13:30 UTC via pg_cron weekly-projection-warehouse-daily; JEG-1641)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();

notify pgrst, 'reload schema';
