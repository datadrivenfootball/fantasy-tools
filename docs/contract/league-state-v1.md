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
    `as_of` a strict ISO 8601 date-time with zone (`2026-11-16T12:00:00Z`; calendar-checked, so `2026-02-30` fails), `reason` null.
  - A known cell must have `reason: null`. A missing cell must have `source` and `as_of` null and a non-blank `reason`.
  - Missing: `value` null, `reason` says why (not entered, provider does not expose it, paste drops it). Never zero,
    never an empty string, never a default. A 0-0-0 record is a real value (preseason) and needs a source.
- `version` is `"league-state/1"`. A shape change that breaks readers bumps the number; the validator rejects others.

## Shape

| Path | Type | Notes |
| --- | --- | --- |
| `version` | string | `league-state/1` |
| `league` | `{id, provider, capture, season}` | provider (where the league lives): sleeper, espn, yahoo, other. capture (how the data arrived): import, manual, paste, mcp |
| `captured_at` | ISO string | When the document was assembled |
| `my_team_id` | team id or null | Null needs `my_team_missing_reason` |
| `teams[]` | list | At least one |
| `teams[].id` | string | Stable within the league, unique; Sleeper `roster_id` as a string |
| `teams[].name` | string | Display only |
| `teams[].record` | cell `{w, l, t}` | Whole numbers >= 0 |
| `teams[].points_for`, `points_against` | cell number | >= 0 |
| `teams[].division` | cell string | |
| `record_through_week` | cell int 0-21 | Last week whose result is in the records; 0 = none played. Cannot exceed `last_regular_week` |
| `schedule` | cell of weeks | Remaining games: `[{week 1-21, median_game bool, games:[{home, away}]}]`; team ids must exist, no team twice in a week, unique weeks, each week after `record_through_week` and no later than `last_regular_week` (when known). `median_game` marks the extra vs-league-median result |
| `playoff_rules.spots` | cell int | 1 to team count |
| `playoff_rules.start_week` | cell int | 2-22 |
| `playoff_rules.last_regular_week` | cell int | Must equal `start_week - 1` when both known |
| `playoff_rules.byes` | cell int | 0 to `spots` |
| `playoff_rules.seeding_rule` | cell | `record` or `division_winners_first`. `division_winners_first` needs at least one known team division |
| `playoff_rules.tiebreak` | cell | `points_for`, `head_to_head`, `points_against`, `other` |
| `trade_deadline_week` | cell int or `"none"` | 1-22, or `"none"` when the league has no deadline (Sleeper `trade_deadline` 99 maps to `"none"`) |

Home and away carry no meaning for fantasy matchups; the pair is just the two teams.

## Sleeper mapping (verified 2026-11-16, JEG-1656)

Importer: `DDF.sleeper.load(id, {leagueState: true})` returns `leagueState` (pure builder `DDF.sleeper.buildLeagueState`).
Without the option the import is unchanged. Tests: `node tests/test_sleeper_league_state.js`; fixtures
`tests/fixtures/sleeper-live/` are recorded live public responses (ids and names anonymized, players and matchups trimmed).

Verified on live 2026 leagues and 2025 completed brackets (about 80 divisional and 1000 other leagues crawled from public user lists):

- Rosters: `settings.wins/losses/ties`, `fpts` + `fpts_decimal`, `fpts_against` + `fpts_against_decimal`, `division` (1-based, count in `league.settings.divisions`, names in `league.metadata.division_N`). Before the draft `fpts_against` is absent: points against is null with a reason, while 0-0-0 and `fpts` 0 are kept as real values.
- `record_through_week` = `league.settings.last_scored_leg` (6-3-0 teams have `last_scored_leg` 9). Absent before the draft; a pre-draft league with every record 0-0-0 gives 0 (derived). Capped at `last_regular_week` once the regular season is over.
- `playoff_week_start` is `start_week`; `last_regular_week` = start - 1. `playoff_teams` is `spots`.
- Byes derive from `playoff_teams` (bracket fills to a power of two): 4 teams 0, 5 teams 3, 6 teams 2, 7 teams 1, 8 teams 0, matching 2025 winners brackets. Other sizes are null with a reason.
- `trade_deadline` 99 means no deadline: 2025 leagues with 99 completed trades after week 14, leagues with a deadline of 13 or 14 did not. Maps to `"none"`. 0 and other non-week values are null with a reason.
- `league_average_match` 1 marks the median game.
- Schedule: `GET league/{id}/matchups/{week}` is public and Sleeper pre-generates every regular and playoff week once the league has a schedule (rows `{roster_id, matchup_id, points}`, pairs by `matchup_id`, `points` 0 for future weeks). Before the draft it returns `[]`, so the schedule is null with a reason. The importer asks only for weeks `last_scored_leg + 1` through `last_regular_week` (the in-progress week counts as remaining); the first week is fetched alone and an empty answer stops there.
- `playoff_seed_type` (0 or 1) does not map to `seeding_rule`. In 2025 brackets of leagues with divisions, division winners were seeded first and took the byes under both values (all but one of the leagues where it mattered); without divisions record decided it under both. The importer therefore sets `division_winners_first` when `divisions` > 0 and `record` otherwise, and ignores `playoff_seed_type`. What it does control (possibly a tiebreak) is not verified, so `tiebreak` is null with a reason.
- ESPN and Yahoo have no unauthenticated source: manual entry or null with reason.

## Errors

`validate` returns `{ok, errors:[{path, code, message}]}`. Codes: `shape`, `version`, `cell`, `null_without_reason`,
`no_source`, `no_as_of`, `value`, `reference`, `duplicate`, `cross`.

## Not in v1

Waiver budget, keeper or dynasty rules, weekly player projections (separate warehouse), per-week scores of played games.
