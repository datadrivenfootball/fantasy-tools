## 2026-11-10 - Week 10 held: view invariants counted lagging charts as missing / JEG-1614

Related: JEG-1512 (week-held alerts; JEG-1614 is its auto-opened sub-issue, GitHub #1418), JEG-1485 (weekly
rollover), JEG-1176 (no carry-forward: a lagging chart is left out of the newer week view), JEG-1612 (same
class: a test clock on the Tuesday flip).

### What failed
Every main `rebuild-chain.yml` run from 2026-11-10 03:25 UTC to at least 23:00 UTC failed closed in
post-rebuild validation, so the site kept the 2026-11-10 01:13 UTC build (every source Week 9). The failing
check changed during the day as other fixes landed and sources moved:

| Runs (UTC) | Failing check |
|---|---|
| 03:25 to about 04:00 | `value-check-compare` (engine vs reference) |
| about 05:00 to 08:00 | `tests.test_rank_guard.TestEngineKeepsOrderInTransition.test_lagging_charts_keep_order_in_their_own_week` |
| about 10:00 to 14:00 | `tests.test_seeded_hold_build.SourceScenarioRenderTest.test_fantasycalc_lagging` |
| 15:05 onward | `tests.test_view_invariants ... test_every_view_holds_its_invariant`: `150 not greater than or equal to 225`, then `195` |

The first three pass in the later runs, once more sources had moved to Week 10. They were not
diagnosed here; they can recur at the next flip (follow-up on JEG-1614).

### Root cause (the test's expected count, not the data or the page)
- On the Tuesday flip the page's default view moves to Week 10 once most DDF Value sources serve it.
  CBS (Week 9, publishes mid-week) and Razzball (2026-11-09 content, Week 9) still serve Week 9, so by
  design they are left out of the Week 10 view (JEG-1176: no carry-forward).
- `test_view_invariants` expected every chart without a `validationHold` to be measured in the default view.
  It never got the JEG-1176 lagging-chart handling that the rank guard, superflex, bench-budget and week
  history tests got in #1027 (`tests/_week_view.py`).
- 22:11 run: held razzball and usatoday, so the test expected 3 charts x 3 tabs + 2 + 2 = 13 checks per
  setting; the page measured 10 (CBS absent). Earlier runs: one chart held, expected 15, Razzball and CBS
  absent, 10 measured. 0 invariant problems in every run.

### Fix
- `_sweep` reads a chart absent from the default view in its own week's view with
  `tests._week_view.own_week_reads`, all three tabs, keeping only the lagging charts' maps. These reads are
  measured under `<setting>/week<N>` labels by the same `verify`, including the page's `gatedHold`.
- The expected count leaves out only a chart whose week has no view (lagging, noted on stderr). A chart
  absent for any other reason is still a failure.
- No value math, engine, page or fixture change.

### Checks
- Local, Python 3.12, Google Chrome headless:
  - committed main fixture (Week 9, no lagging): `tests.test_view_invariants` 2 tests OK, 270 checks.
  - candidate from failed run 42907611452 (its `candidate-evidence` tree; only data files copied onto this
    branch): before the fix `150 not greater than or equal to 195`; with the fix 2 tests OK, 270 checks,
    0 problems (CBS, Razzball and USA Today measured in the Week 9 view).
  - the 16 `data-gate` modules after `test_view_invariants` (which the failed runs never reached): all
    pass on the same candidate.
- Branch proof: `rebuild-chain.yml` dispatched on this branch (publication disabled on branches),
  run 42925501505.
