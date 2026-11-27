# Signed-in DDF features on stored league data (JEG-1736, staging only)

Spec: `06-audit/ddf-unified-framework-2026-11-27.md` revisions 3 and 4 (handoff folder). Built up from the live
site's pages; **Games left** is the one new page. Weekly planning uses weekly scoring data only, never DDF Value.
Missing is never 0: a value nothing gave is `null` with a reason.

## Data path

1. `GET /leagues/:id` (ddf-account) returns the league row; `league.summary` is `ddf-connected-league/0`
   (`docs/flaim-snapshot-schema.md`).
2. `GET /leagues/:id/weekly` (new) returns player weekly projections for every rostered player and free agent in
   that league, for the current week through the last playoff week (`ddf-league-weekly/0`, below).
3. `staging/account/weekly.js` (`DDFWeekly`, pure, no DOM; also loaded by `deno test`) turns the two into the
   planner: best legal lineups, win chances, the season simulation, goals and moves.
4. Pages render that output.

### `ddf-league-weekly/0`

```
{
  shape: "ddf-league-weekly/0",
  season: 2026, scoring: "half_ppr", weeks: [12, 13, ...],
  as_of: {espn: ISO|null, sleeper: ISO|null, schedule: ISO|null, kdef: ISO|null},
  players: {
    "<platform player_id>": {
      name, pos, nfl_team, sleeper_id|null, espn_id|null,
      weeks: { "13": {points: number|null, source: "espn"|"sleeper"|"espn_live"|null, bye: bool, note: string|null} }
    }
  },
  unmatched: [{player_id, name, reason}],
  byes: {"<NFL team>": [week, ...]}
}
```

- Player identity: Yahoo `player_id` (`470.p.33536` -> `33536`) -> Sleeper player DB `yahoo_id` -> `sleeper_id`,
  `espn_id`. IDs only; a name is never the join.
- QB/RB/WR/TE: the weekly projection warehouse (JEG-1641), latest run per source, ESPN first (rescored to the
  league's scoring), Sleeper where ESPN has no row. Source on every cell.
- K and DEF: the warehouse has none, so ESPN's own weekly projection is read live, one week at a time by
  `scoringPeriodId`, by ESPN id (DEF: ESPN's D/ST id for the team). Labelled `espn_live` (ESPN default scoring).
- Bye from the nflverse schedule: `bye: true`, `points: 0`, shown as BYE.

### `DDFWeekly.plan(summary, weekly, opts)`

```
{
  league: {name, season, current_week, last_regular_week, playoff_start_week, playoff_teams, num_teams,
           trade_deadline, scoring, pulled_at},
  me: {team_key, name, wins, losses, ties, rank, points_for},
  standings: [{team_key, name, wins, losses, ties, rank, points_for, playoff_p, seed_p: [p1..pN]}],
  spread: {sd, basis},                    // weekly spread of one team's score and where it came from
  wins: {dist: [{wins, p}], expected, games},     // remaining regular-season games, DDF win chances
  sim: {runs, playoff_p, top_seed_p, bye_p|null, expected_seed, by_final_wins: [{wins, p_reach, playoff_p}],
        clinch_wins|null, safe_wins|null},
  need: [string],                          // header sentences: record and need
  goals: [{id, label, detail}],            // high_score | record | seed | playoffs
  games: [{
    week, phase: "regular"|"playoffs", status,
    opp: {team_key, name, wins, losses, ties, rank, playoff_p} | null, opp_note|null,
    mine: Lineup, theirs: Lineup|null,
    margin|null,
    win: {ddf: p|null, yahoo: p|null}, yahoo_proj: {mine, theirs}|null,
    high_score: {chance, my_rank, of, top: {name, total}},
    stake: {playoffs: dp|null, seed: dp|null}, type: "must_win"|"bankable"|"seed_game"|"free"|"playoff",
    goals: [goal ids touched],
    moves: [{kind: "start"|"add"|"watch"|"bye", text, gain|null, when|null}]
  }],
  sources: [string], missing: [{what, reason}]
}
Lineup = {team_key, name, total|null, starters: [Player & {slot}], bench: [Player], empty_slots: [slot],
          unscored: [{name, reason}]}
Player = {player_id, name, pos, nfl_team, points|null, source, status|null, bye, note|null}
```
