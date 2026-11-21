## 2026-11-21 - JEG-1685: wire league-state into workspace, ddf-state, ES-12 weeks (PR #1473)

Contract: Wire the league-state/1 contract into the app — workspace persistence,
Sleeper import, ddf-state envelope, and ES-12 weekFill — without touching any
value formula.

### Verified (check named)

- `test_refused_fill_records_null_weeksFilled_when_plan_matches_reader_weeks`
  (new, `tests.test_jeg1685_league_state_render`): failed before fix, passes
  after. Confirms P2 (Codex comment 4594659560): `fillWeeks` now returns null
  when `weekFill` refuses because weeks belong to the reader, so no
  import-filled marker is written and a later paste cannot trigger
  `releaseWeeks()` to overwrite reader-owned weeks.
- Full `tests.test_jeg1685_league_state_render` suite (10 tests): OK.
- Gate: `node tests/test_league_state_wiring.js`, `test_league_state`,
  `test_sleeper_league_state`, `test_sleeper_import`, `test_paste_settings`,
  `test_entry_league_paste`, `test_v2_league_paste`; `python3.12 -m unittest
  tests.test_jeg1685_league_state_render tests.test_entry_pages
  tests.test_ddf_state` — run against the final head; see CI for results.

### Fix

`app/next/connect-entry.js` `fillWeeks`: last return guarded with `!fill.why`.
`weekFill` always sets `why` on a refusal (`patch` null), so this is a
no-op for all currently-reachable paths but prevents the bug if weekFill
gains new paths. The specific P2 trigger was: reader sets non-default weeks,
import plan happens to match reader's `regularEnd`/`playoffLo` — the old code
returned the reader tuple as the weeksFilled marker.

### Claimed, not confirmed

- Linear status for JEG-1685 not updated: Linear was unavailable during this
  session (tool auth not connected). Status should be In Progress / In Review;
  PR #1473 is open, not merged.
- MCP edge function (`supabase/**`) does not pass `leagueState` through
  `read_state`/`make_state` yet — noted as "Not done" in the original PR
  description. No change made here.
- Known CI failures on main: `test_v2_waterfall_render` and preview-shard 5
  timeout — not introduced by this PR.
