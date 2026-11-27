# Flaim league snapshot: import schema (JEG-1732)

Jeremy, 2026-11-27: "I want to try out the new features and iterate on them by having flaim populate
the data while we are waiting for yahoo to allow the developer permissions."

Flaim stands in for DDF's own Yahoo connection until Yahoo approves DDF's app. A snapshot lands in the
same `ddf_accounts.leagues` row and the same `summary` shape (`ddf-connected-league/0`) a direct Yahoo
pull writes, so every feature reads one shape and doesn't care where it came from.
`leagues.source` = `flaim`. `leagues.platform` stays where the league lives (`yahoo`). A later direct
Yahoo pull of the same league overwrites the row and sets `source = 'direct'`.

## How to load one (admin only)

The user must have signed in on staging once (their `auth.users` row must exist). Then, as the
service role or postgres (for example the Supabase MCP `execute_sql`):

```sql
select ddf_accounts.import_flaim_snapshot('<user email>', '<snapshot JSON>'::jsonb);  -- returns the league id
```

The function refuses a bad snapshot with a plain message. Signed-in and anonymous roles can't call it.
Loading the same league again replaces the snapshot. It keeps the user's chosen team and confirmed
settings. The staging page shows "League data via Flaim (stand-in until Yahoo is approved) · pulled
<time>" and hides Refresh for these leagues.

Worked example: `supabase/functions/ddf-account/test/flaim-snapshot.example.json`.

## Shape

Missing is never 0: a value Flaim or Yahoo did not give is `null`, plus a row in `missing` with the
reason.

| Path | Type | Required | Notes |
| --- | --- | --- | --- |
| `shape` | `"ddf-connected-league/0"` | yes | |
| `source` | `{kind: "flaim", note?}` | yes | `kind` must be `flaim` |
| `platform` | `"yahoo"` (or `espn`, `sleeper`) | yes | where the league lives |
| `league_key` | string | yes | Yahoo `470.l.848938` |
| `season` | int | yes | 4-digit year |
| `name` | string | yes | |
| `pulled_at` | ISO 8601 with zone | yes | when Flaim read it; refused if more than 5 minutes in the future |
| `current_week` | int or null | | |
| `my_team_key` | string or null | | e.g. `470.l.848938.t.2` (Tiny Hands) |
| `settings` | object | yes | below |
| `teams[]` | non-empty array | yes | below |
| `schedule[]` | array | yes | may be empty; weeks 12-17 wanted |
| `free_agents[]` | array | | top N by position, K and DEF included |
| `transactions[]` | array | | recent first |
| `missing[]` | `{path, reason}` | yes | may be empty |
| `sources[]` | strings | | e.g. `flaim:get_roster` |

`settings`:
- `num_teams` int.
- `ddf` is the site's settings shape: `{scoring: "ppr"|"half_ppr"|"standard", superflex: bool, superflexSlots?: 2, teams: 8|10|12|14, roster: {QB, RB, WR, TE, FLEX, BENCH, K, DST}}`.
- `fit`: object or null.
- `roster_positions[]`: Yahoo slot names (`QB`, `WR`, `RB`, `TE`, `W/R/T`, `Q/W/R/T`, `K`, `DEF`, `BN`, `IR`).
- `scoring_raw`: anything.
- `playoff_start_week`, `playoff_teams`, `last_regular_week`: int or null.
- `trade_deadline`: `{week: int|null, date: "YYYY-MM-DD"|null, none: bool, source: string|null}`.
- `waiver_type`: `"faab"`, `"rolling"`, `"reverse_standings"`, `"continual"` or null.
- `faab_budget`: int or null.

`teams[]`:
- `team_key`, `name`.
- `managers[]`: `{id, name}`.
- `standings`: `{wins, losses, ties, points_for, points_against, rank, rank_source}`.
- `faab_remaining`: int or null.
- `waiver_priority`: int or null.
- `roster[]`: `{player_id, name, position, nfl_team, slot, status, eligible_positions[]}`. `slot` is the current lineup slot or `BN`/`IR`. `status` is the injury designation (`Q`, `O`, `IR`…) or null.

`schedule[]`: `{week, matchups[]}`. Each matchup is:
- `team_keys[2]`.
- `points[2]`: null when not played.
- `projected_points[2]`: Yahoo's team projection.
- `win_probability[2]`: Yahoo's win probability, 0-1.
- `is_playoffs`: bool.
- `status`: `"final"`, `"live"` or `"not_started"`.

`free_agents[]`: `{player_id, name, position, nfl_team, status, eligible_positions[], percent_owned, projected_points?: [{week, points}]}`.

`transactions[]`: `{at (ISO), type, team_keys[], adds[] (player_id), drops[] (player_id), note}`.

## Weekly projections

Yahoo's public API has no per-player weekly projections. Features use Yahoo's team projections and
win probability from `schedule` where present. Player-level weekly values come from the ESPN/Sleeper
weekly projection warehouse (JEG-1641), labelled with their source.
