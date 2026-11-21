## 2026-11-21 - JEG-1685: wire league-state into workspace, ddf-state, ES-12 weeks (PR #1473)

Contract: Wire the league-state/1 contract into the app — workspace persistence,
Sleeper import, ddf-state envelope, and ES-12 weekFill — without touching any
value formula.

### Verified (check named)

- `test_refused_fill_records_null_weeksFilled_when_plan_matches_reader_weeks`
  (new, `tests.test_jeg1685_league_state_render`): failed on ceb9ebc, passes
  on 883fd7d. Confirms connect-entry.js P2: `fillWeeks` returns null when
  `weekFill` refuses because weeks belong to the reader.
- `V2SettingsSaveMarker.test_v2_settings_save_keeps_weeksFilled_marker`
  (new, `tests.test_jeg1685_league_state_render`): failed on 5badd37, passes
  on c8369a0. Confirms v2.js P2: `saveLeagueSettings` carries `weeksFilled`
  forward so a v2 scoring change does not erase the import-filled marker.
- Full `tests.test_jeg1685_league_state_render` suite (12 tests after both new
  tests): all pass on c8369a0.
- Gate: `node tests/test_league_state_wiring.js` (21 pass), `test_league_state`
  (ok), `test_sleeper_league_state` (15), `test_sleeper_import` (6),
  `test_paste_settings` (22), `test_entry_league_paste` (32),
  `test_v2_league_paste` (12). `python3.12 -m unittest
  tests.test_jeg1685_league_state_render tests.test_entry_pages
  tests.test_ddf_state` — 24 tests OK on c8369a0.

### Fixes

**connect-entry.js P2** (883fd7d): `fillWeeks` last return guarded with
`!fill.why`, then simplified to plain `return null` (c8369a0). `weekFill`
always sets `why` on any refusal; the conditional was dead code. Bug trigger:
reader sets non-default weeks, import plan matches reader's `regularEnd` and
`playoffLo` — old code saved the reader's tuple as a filled marker; a later
paste then called `releaseWeeks()` and reset to defaults.

**v2.js P2** (c8369a0): `saveLeagueSettings()` reads `weeksFilled` from the
existing stored record and carries it forward. `ddf-engine.js` is not loaded
on v2 pages, so `weeksFilled` could only come from the existing record. Bug
trigger: any v2 settings change after a Sleeper import erased the marker from
`ddf.v2.league-settings`; next-page-load `applySaved` saw no `weeksFilled` and
a subsequent Sleeper import was refused ("set by the reader").

### Claimed, not confirmed

- Linear status for JEG-1685 not updated: Linear was unavailable during this
  session (tool auth not connected). Status should be In Progress / In Review;
  PR #1473 is open, not merged.
- clear-league P3 (`ops.clearLeague` in workspace.js keeps `leagueState` /
  `weeksFilled`): nothing on the site uses it today and no value math reads
  it. Follow-up ticket needed before standings-aware math ships.
- MCP edge function (`supabase/**`) does not pass `leagueState` through
  `read_state`/`make_state` yet — noted as "Not done" in the original PR
  description. No change made here.
- Known CI failures on main: `test_v2_waterfall_render` and preview-shard 5
  timeout — not introduced by this PR. CI on c8369a0 pending.
