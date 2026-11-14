# Weekly projection warehouse (JEG-1641)

Jeremy, 2026-11-14: "Run a process to warehouse everything that projects out
weeks." His decision the same day (A): daily full copies, no deletion; revisit
retention in the offseason. For these tables, that replaces the 2026-10-23 choice
of two copies a week. Source survey: JEG-1640 (`06-audit/weekly-projection-sources-2026-11-14.md`
in the handoff folder).

Storage only. No value, page, view or API reads these tables. Nothing is blended
with ROS (Jeremy 2026-10-29), and a missing number is null, never 0.
Migration: `supabase/migrations/jeg1641_weekly_projection_warehouse_20261114.sql`
(project `iskiybsimubiujwuchsl`). All four tables are append-only: a trigger
rejects UPDATE and DELETE, RLS is on, and only the service role can access them.

## What is stored

| Table | Grain | Written by |
|---|---|---|
| `source_weekly_projections` | run x source x player x target week | ESPN: `save_espn_weekly.py` (espn-weekly-store.yml). Sleeper, CBS, FantasyPros: `save_projection_warehouse.py` (weekly-projection-warehouse.yml) |
| `source_projection_runs` | run x source: `as_of`, content week, target weeks, rows written, detail (unresolved count, CBS weeks not offered, FantasyPros pages skipped, byes) | the same savers, after that source's rows |
| `nflverse_schedule_snapshots` | run x game: the season's nflverse `games.csv` rows (week, gameday, teams, scores, spread, total) | `save_projection_warehouse.py` |
| `nflverse_injury_snapshots` | run x player: the latest week of nflverse's official injury report, QB/RB/WR/TE | `save_projection_warehouse.py` |
| `player_status_history` (existing, JEG-521) | day x Sleeper player: Sleeper `status`, `injury_status`, depth chart | `save_player_status_history.py` (unchanged) |

Per source in `source_weekly_projections`:

| Source | `coverage` | Target weeks | Points | Stat line (`stats`) |
|---|---|---|---|---|
| espn | every_week | content week to 18 | `points_*` = ESPN's projected stat line rescored with the `v_player_game_actuals` formula; `source_points` = ESPN `appliedTotal` (leaguedefaults/3 scoring). 0 for a bye or out (MR-20, as ESPN gives it) | 9 mapped stat keys (passing/rushing/receiving yards and TDs, interceptions, receptions, targets) |
| sleeper | every_week | content week to 18 (Sleeper offers no skill-position weeks 19+) | `pts_std / pts_half_ppr / pts_ppr` as given (RotoWire) | Sleeper's full stat dict as given (about 56 keys), plus `_company` |
| cbs | current_week | the weeks CBS really serves (current and sometimes next) | non-PPR page total; half/PPR = plus 0.5/1 per reception (the existing puller) | none |
| fantasypros | current_week | content week only, when the page heading names it | FPTS copied to `points_std` (QB page) or `points_half_ppr` (RB/WR/TE pages say Half-PPR), also in `source_points`; the other formats null | the page's stat columns |

`scoring_basis` on every row says the same thing. Identity: `source_player_id`
is always the source's own id (ESPN id, Sleeper id, CBS normalized name,
FantasyPros id). `player_key` comes from `PlayerIndex` (ids first, names last)
and is null when unresolved; the row is still kept. `sleeper_id` is filled where
an id crosswalk gives exactly one.

Limits found on 2026-11-14 (not fixed here):
- FantasyPros without a login embeds only about the top 10 per position (40 rows
  a run). The Muse signed-in feed (`weekly_fantasypros_*`) has no rows.
- Sleeper status (`player_status_history`): the Sunday 16:30 UTC run overwrites
  that day's morning row (upsert on date and player), so the morning status of
  a Sunday is not kept.
- nflverse injuries list only the latest report week. A future week's status is
  unknown until that week's report.

## Schedule

All times are UTC, set by pg_cron through `public.dispatch_gha_workflow`.

| Job | When | Writes |
|---|---|---|
| `espn-weekly-store-live` / `-sunday` (existing) | 12:40 daily, 16:20 Sunday | espn rows |
| `weekly-projection-warehouse-daily` | 13:30 daily | sleeper, cbs, fantasypros, nflverse_schedule, nflverse_injuries |
| `weekly-projection-warehouse-sunday` | 16:40 Sunday (before the 12:00 CT kickoffs) | the same |

A run is about 36 Sleeper requests (0.5 s apart), up to 12 CBS pages, 4
FantasyPros pages 5 s apart (robots.txt Crawl-delay 5; no disallowed path is
used) and 2 nflverse release files. No login. A failed source writes no run row
and does not stop the other sources. The run then exits 1, and
`record_monitor_check` marks `weekly_projection_warehouse` not ok.

## Freshness and size

`pipelines/check_projection_warehouse.py` reads the newest `as_of` per source
from `source_projection_runs`:

- A source is **stale** when its newest run is more than 26 h old, or when it has
  never run. FantasyPros only warns. Nothing is due after 2027-01-05 (offseason).
- It runs as a step in weekly-projection-warehouse.yml, where a stale source
  fails the run. It also runs hourly in source-lateness.yml (`--alert`), which
  has its own schedule. There it opens, updates and closes one GitHub issue,
  "Weekly projection warehouse is stale" (label `warehouse-stale`), the same way
  the source-late issue works.
- Size alert: the same check flags a problem when the **database passes 6 GiB**
  (75% of the Pro plan's 8 GB included disk; the database was 1,150 MB on
  2026-11-14) or when **the four warehouse tables pass 1 GiB** (the point to
  revisit retention). It reads sizes through `public.source_weekly_warehouse_size()`.

When the issue opens: check the newest runs of the two workflows. A source with
an `error` or `problems` entry in the run log failed its pull or its row floor,
and a 403 means the site turned the pull away. A source with no run at all
means the pg_cron job did not dispatch (`select jobname, active from cron.job`).
Pausing or editing a job is a production change, so ask Jeremy.

Size projection (estimate made 2026-11-14 from measured row counts, not yet a
measured size): one daily run is about 5,500 ESPN rows, 3,700 Sleeper rows, 700
CBS rows, 40 FantasyPros rows, 272 schedule rows and about 110 injury rows,
roughly 4 to 5 MB with indexes. The count shrinks as weeks pass, because fewer
future weeks remain. That comes to about 150 MB through week 18 of 2026, and
about 1 GB for a full season captured daily from August. Replace this with
measured numbers after a week of runs:

```sql
select relation, pg_size_pretty(bytes) from public.source_weekly_warehouse_size();
```

## Example queries

A player's latest projection for next week, one row per source:

```sql
with latest as (
  select distinct on (source) source, run_id
    from public.source_projection_runs
   where source in ('espn', 'sleeper', 'cbs', 'fantasypros')
   order by source, as_of desc)
select p.source, p.as_of, p.target_week, p.points_std, p.points_half_ppr, p.points_ppr,
       p.source_points, p.scoring_basis, p.stats
  from public.source_weekly_projections p
  join latest l using (source, run_id)
 where p.player_key = :player_key
   and p.target_week = public.nfl_content_week((now() at time zone 'America/New_York')::date) + 1;
```

All future weeks for a player from the latest ESPN and Sleeper runs, with bye
weeks from the latest schedule:

```sql
with latest as (
  select distinct on (source) source, run_id
    from public.source_projection_runs
   where source in ('espn', 'sleeper')
   order by source, as_of desc),
sched as (
  select s.* from public.nflverse_schedule_snapshots s
   where s.run_id = (select run_id from public.source_projection_runs
                      where source = 'nflverse_schedule' order by as_of desc limit 1))
select p.target_week, p.source, p.team, p.points_half_ppr,
       not exists (select 1 from sched g where g.week = p.target_week
                     and p.team in (g.home_team, g.away_team)) as team_has_no_game
  from public.source_weekly_projections p
  join latest l using (source, run_id)
 where p.player_key = :player_key
 order by p.target_week, p.source;
```

The same projection as it stood on an earlier date (point in time), and its history:

```sql
-- as of a moment: the newest run at or before it
select p.* from public.source_weekly_projections p
 where p.run_id = (select run_id from public.source_projection_runs
                    where source = 'sleeper' and as_of <= :as_of_ts order by as_of desc limit 1)
   and p.source = 'sleeper' and p.player_key = :player_key;

-- how one week's projection moved, run by run
select as_of, source, points_half_ppr from public.source_weekly_projections
 where player_key = :player_key and target_week = :week
 order by source, as_of;
```

Latest injury and status inputs for a player:

```sql
select * from public.nflverse_injury_snapshots
 where player_key = :player_key order by as_of desc limit 1;
select * from public.player_status_history
 where player_key = :player_key order by snapshot_date desc limit 1;
```

Row counts per source and week for one run (the run check):

```sql
select source, target_week, count(*) from public.source_weekly_projections
 where as_of > now() - interval '1 day' group by 1, 2 order by 1, 2;
```

## Relation to JEG-944

`source_projection_captures` (two copies a week, first one wins, three rows per
player for the three formats) is unchanged. Its gate (`check_projection_captures.py`)
and the JEG-945 scoring read it. The warehouse covers the same ESPN and CBS
weeks every day. Retiring the JEG-944 ESPN and CBS rows is a later decision, for
the offseason retention review.
