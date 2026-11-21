## 2026-11-21 - JEG-1658 weekly team projection: Codex review findings on PR #1474

Contract: resolve the two Codex findings on PR #1474 (P1 missing team projections shown as 0; P2 a later injury
report applied to earlier weeks), each with a failing test first. Hold rule (Jeremy, 2026-11-16): "Nothing about
playoffs or draft publishes until I see the concepts." No merge, no ready-for-review, no deploy, no page wiring.

Linear was unavailable this session. Status to set when it is back: JEG-1658 stays In Progress (PR held, not merged).

### What changed
- P1: `teamWeek` returned `points: 0, reason: null` when the week had source rows but none of the team's players had
  usable points. Now the team week is `null` with a reason when the missing players would fill a starter slot that no
  real player can (exact-assignment slot count with and without them). A slot emptied by bye/out stays a real 0; a
  provider 0 stays a value; a partly missing roster still uses the next player. An empty roster is `null`.
  The test "scoring format picks the stored column" asserted the ESPN cross-check was `0` when every ESPN row had
  null points: that assertion pinned the bug and was wrong under AGENTS.md "missing values never shown as zero"; it
  now expects `null` with a reason.
- P2: raised on db04be3 (`week <= inj.week`). d7f7bd1 no longer read `inj.week` at all, but the problem remained in
  another form: a report dated week 13 still excluded the player from week 12 (ESPN 0 that week, or "every ESPN week
  at 0, out every week"). Now weeks before the report week ignore the report. This does not contradict Jeremy's
  2026-11-16 rules: they describe a player "listed out now", which covers the report week and later; inside that
  range they run unchanged (all-zero weekly Out is still out every week from the report on). Codex's wording
  ("applies only to its report week") was the db04be3 rule that Jeremy's ESPN rule replaced, so it is not adopted.

### Verified (check named)
- `node tests/test_weekly_team_projection.js`: the two new tests failed before the fix (team 1 week 12 points 0;
  wr4 excluded in week 12), and 18 of 18 pass after.
- `node tests/test_league_state.js`, `node tests/test_sleeper_league_state.js` (15 passed),
  `node tests/test_sleeper_import.js` (6 passed): pass.
- `make test-core-shard-2` (python3.12, CHROMIUM_PATH set): the node and first python groups pass (26 tests OK);
  in the second group 28 of 29 pass and `test_value_pipeline_engine ... test_python_reference_flag_on_equals_baseline`
  errors because its `sync_dashboard_artifacts.py` build timed out after 600 s on this machine. That test does not
  touch this module. Under python3.9 the same build fails earlier on `fromisoformat('...+00')`, so use 3.12.

### Claimed, not confirmed
- The live data rarely hits P1 (it needs a roster whose players all lack rows in a week that has rows); not measured
  on the warehouse.
- `test_python_reference_flag_on_equals_baseline` passes when its build has time: left to CI on the new head.
