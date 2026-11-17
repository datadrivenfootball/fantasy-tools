# Weekly team projection (JEG-1658, part of JEG-1653)

Module: `app/next/weekly-team-projection.js` (`DDF.weeklyTeamProjection.project`). Test:
`node tests/test_weekly_team_projection.js` (in `make test-core` and `test-core-shard-2`). Fixtures:
`tests/fixtures/weekly-team-projection/small.json` (regenerate with `generate_small.js` in the same folder) and the
Sleeper producer fixture `tests/fixtures/sleeper-live/full.json`.

Status: pure module only. No page loads it and no data path feeds it yet (see "Data path"). UI is JEG-1660 (My Season).
It reads nothing from, and feeds nothing into, DDF Value, rest-of-season values, charts or the pipeline.

## What it returns

For each team in a `league-state/1` document and each week from `fromWeek` (default `record_through_week + 1`; the
spec's W+1 is passed by the caller) to the last playoff week: the points of the best legal lineup for the league's
starter slots, from that week's Sleeper projections, with ESPN's figure for the same rules beside it.

- Last playoff week: `opts.lastWeek`, otherwise `start_week + rounds - 1`, rounds = log2 of the bracket (2 spots 1
  round, 3-4 2, 5-8 3, 9-16 4), one week per round. Two-week rounds (Sleeper `playoff_round_type` 1 or 2) are not in
  league-state/1, so such a league must pass `lastWeek`. Capped at week 18.
- Lineup: exact assignment (Hungarian method) over the projected slots QB, RB, WR, TE, FLEX, WRRB_FLEX, REC_FLEX,
  SUPER_FLEX. Greedy filling is wrong when flex sets overlap without nesting. K, DEF and IDP slots are listed in
  `basis.slots_not_projected` and add nothing (the warehouse has QB/RB/WR/TE only). An unfillable slot is a real 0 and
  is listed in `flags.empty_slots`.
- Points: one function, `opts.points(row, {scoring, source, week})`, default `providerPoints` = the stored
  `points_<format>` column. Per-league rescoring from `row.stats` (JEG-1688, Jeremy 2026-11-16 decision C on
  JEG-1682) replaces only this function.

## Availability rules (Jeremy 2026-11-16)

| Case | Rule |
| --- | --- |
| Bye | nflverse schedule (REG games): the player's team has no game. Team codes normalised to nflverse (`LAR` to `LA`, `JAC` to `JAX`, `WSH` to `WAS`). The team comes from that week's row, else the player's newest row in any source and week (Sleeper has no row in a bye week), else `players`. A week with no schedule rows is `bye_unknown`. |
| Out with an expected return week | Out (excluded) before it; counted from it, flagged `uncertain_return` |
| Weekly `Out` (injury report), no return week | Out for the report week only; counted after it, flagged |
| IR, PUP, NFI, suspended, no return week | The provider's weeks as given (its 0 is out), flagged |
| Questionable, Doubtful | Counted, no flag |
| No row for the player that week | Excluded with `points: null` and a reason; the next player fills in |
| Source has no rows for the week | The team week is `null` with a reason (never 0) |
| Week 18 | `flags.rest_starters_risk` |

No source gives an expected return week. nflverse injuries carry only the latest report week; Sleeper
`player_status_history` carries status only. So `return_week` has to come from the user or a later source.

## Join keys (checked on the warehouse, 2026-11-16, latest runs)

- Rosters are Sleeper player ids. Sleeper rows: `sleeper_id` always set (3,715 rows, weeks 10-18).
- ESPN rows: 4,104 of 5,517 have no `sleeper_id`, but all have `player_key`. The module maps `player_key` to the
  Sleeper id through the Sleeper rows; every ESPN row above 5 half-PPR points joins that way.
- Team codes: ESPN rows already use nflverse codes; Sleeper writes `LAR` (the only mismatch, 118 rows).
- Sleeper has no row for a player on bye; ESPN has a 0 row (MR-20).

## Data path (finding, 2026-11-16)

The browser cannot read the warehouse. `source_weekly_projections`, `nflverse_schedule_snapshots` and
`nflverse_injury_snapshots` have RLS on with all privileges revoked from `anon` and `authenticated`
(migration `jeg1641_weekly_projection_warehouse_20261114.sql`). The site reads only static files built with it
(`players-table-1.json`, `sleeper-players.json`) and Sleeper's public API; `get-values` and `mcp` are edge functions
for the MCP connector and read no warehouse table. Options (each a pipeline or infra change that ships alone):

- A (recommended): a pipeline step writes a static `weekly-projections.json` with the site build (latest Sleeper and
  ESPN run, weeks W+1..18, the module's row columns only, plus the schedule and injury rows). Same pattern as
  `players-table-1.json`; no new public database surface; about 9,000 rows a day, so trim columns.
- B: a read-only edge function that returns the latest run's rows for a list of Sleeper ids. Live, but a new public
  endpoint with its own egress and rate limits.
- C: a `security definer` RPC granted to `anon`. Smallest code, but opens a database path from the browser.

## Not in v1

Team score spread and the season simulator (later JEG-1653 tickets), median games, two-week playoff rounds read
from Sleeper, per-league rescoring (JEG-1688), Sleeper vs ESPN gap flags per player.
