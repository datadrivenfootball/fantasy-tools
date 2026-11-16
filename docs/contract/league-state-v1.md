# league-state contract, version 1

JEG-1655 (part of JEG-1653). Spec: `06-audit/standings-aware-value-spec-2026-11-15.md` section 1.
Validator: `app/next/league-state.js` (`DDF.leagueState.validate`). Fixtures: `tests/fixtures/league-state/`
(`sleeper.json`, `manual.json`, `partial.json`). Test: `node tests/test_league_state.js`.

Status: contract only. Nothing reads or writes it yet; no value math. Planned homes: the league workspace state and
`ddf-state` (MCP `read_state` / `make_state`), next to the ES-12 week settings (`last_regular_week` and
`start_week` fill those when known). Wiring is a later ticket.

## Rules

- One shape for every capture path (Sleeper import, manual entry, paste, MCP state). Consumers read only this shape.
- Every field except identity is a cell: `{value, source, as_of, reason}`.
  - Known: `value` set, `source` a non-empty string (for example `sleeper:rosters`, `manual:entry`, `derived:...`),
    `as_of` an ISO timestamp, `reason` null.
  - Missing: `value` null, `reason` says why (not entered, provider does not expose it, paste drops it). Never zero,
    never an empty string, never a default. A 0-0-0 record is a real value (preseason) and needs a source.
- `version` is `"league-state/1"`. A shape change that breaks readers bumps the number; the validator rejects others.

## Shape

| Path | Type | Notes |
| --- | --- | --- |
| `version` | string | `league-state/1` |
| `league` | `{id, platform, season}` | platform: sleeper, espn, yahoo, manual, mcp, other |
| `captured_at` | ISO string | When the document was assembled |
| `my_team_id` | team id or null | Null needs `my_team_missing_reason` |
| `teams[]` | list | At least one |
| `teams[].id` | string | Stable within the league, unique; Sleeper `roster_id` as a string |
| `teams[].name` | string | Display only |
| `teams[].record` | cell `{w, l, t}` | Whole numbers >= 0 |
| `teams[].points_for`, `points_against` | cell number | >= 0 |
| `teams[].division` | cell string | |
| `schedule` | cell of weeks | Remaining games: `[{week 1-22, median_game bool, games:[{home, away}]}]`; team ids must exist, no team twice in a week, unique weeks. `median_game` marks the extra vs-league-median result |
| `playoff_rules.spots` | cell int | 1 to team count |
| `playoff_rules.start_week` | cell int | 2-22 |
| `playoff_rules.last_regular_week` | cell int | Must equal `start_week - 1` when both known |
| `playoff_rules.byes` | cell int | 0 to `spots` |
| `playoff_rules.seeding_rule` | cell | `record` or `division_winners_first` |
| `playoff_rules.tiebreak` | cell | `points_for`, `head_to_head`, `points_against`, `other` |
| `playoff_rules.division_winners_seeded` | cell bool | |
| `trade_deadline_week` | cell int | 1-22 |

Home and away carry no meaning for fantasy matchups; the pair is just the two teams.

## Sleeper mapping (reported, not re-fetched; verify when the importer is wired)

`rosters[].settings.wins/losses/ties`, `fpts` + `fpts_decimal`, `fpts_against`, `division`; `league/{id}/matchups/{week}`
(`matchup_id` pairs); `settings.league_average_match` (median game), `playoff_teams`, `playoff_week_start`,
`playoff_seed_type`, `trade_deadline`. ESPN and Yahoo have no unauthenticated source: manual entry or null with reason.

## Errors

`validate` returns `{ok, errors:[{path, code, message}]}`. Codes: `shape`, `version`, `cell`, `null_without_reason`,
`no_source`, `no_as_of`, `value`, `reference`, `duplicate`, `cross`.

## Not in v1

Waiver budget, keeper or dynasty rules, weekly player projections (separate warehouse), per-week scores of played games.
