## 2026-11-21 - Engine pages: skip the duplicate value-pipeline rebuild on first load

Branch `perf/engine-boot-dedupe` (PR 1496). Files: `app/trade-value-chart/assets/curve-widget.js`,
`tests/test_engine_boot_pipeline_runs.py` (new), `Makefile` (test target), this log.

### What was slow
Every engine page ran the whole value pipeline twice on first load: `init()` built the domain, then `makeViewModeTabs()` called
`setViewMode(viewMode, false)`, which rebuilt the same domain with nothing changed. One rebuild is two pipeline calls (current
week and prior week), so a first load made four.

### Change
`setViewMode(mode, publish, keepBuiltDomain)`: init passes `true`, and the rebuild is skipped only when the mode equals the one just
built and the active and deselected source sets are unchanged. View-tab clicks rebuild as before. Nothing awaits between init's
`rebuildDomain()` and `makeViewModeTabs()`, and the controls built in between only render DOM, so no pipeline input can change.

### Checked
- `tests/test_engine_boot_pipeline_runs.py` (`test-unit-modules`): first-load pipeline calls equal one rebuild's, on values.html and
  team.html. Fails on the old build (4 vs 2), passes now. It counts calls, not timings.
- Engine output before and after is byte-identical (rows, state, roster, lineup, weights, bench share, prior week) on values.html
  and team.html across no league, saved league, applied league, superflex, PPR and TE2 cases.
- Review found the same 16-run snapshot comparison byte-identical on current main.

### Not done
- `make values-explainer MARK_REVIEWED=1` is deliberately not run here: no value math or narrative changed, nothing enforces it, and
  the recorded hash for `curve-widget.js` was already stale on main. Re-mark after merge as part of a real math review.
- Merge this before the batch-league PR (1497); both touch `curve-widget.js`. Run `make test-core` between them.

### Learned
A render-tests league failure on a stale base (`test_v2_finder_teams_render`) cleared once `origin/main` was merged in. Merge main
(no rebase) before judging that failure.
