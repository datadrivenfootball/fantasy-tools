## 2026-11-21 - Engine pages: restore a saved league with one value-pipeline rebuild

Branch `perf/engine-batch-league` (PR 1497). Files: `app/next/ddf-engine.js`,
`app/trade-value-chart/assets/curve-widget.js`, `tests/test_engine_saved_league_pipeline_runs.py` (new), `Makefile`, this log.

### What was slow
`ddf-engine.js` restored saved settings with `setScoring`, `setTeams`, then `setRosterSpot` per changed spot, and each call rebuilt
the full value pipeline. A saved Half PPR, 3 WR, 5 bench league cost three extra rebuilds on every engine page load, and
`DDF.engine.apply()` rebuilt once per field.

### Change
New `TradeValueCurveControls.setLeague({scoring, teams, roster}, publish)`: same normalization, clamping and position-weight reset
as the single setters, one rebuild on the final league, and the union of their UI refreshes. A non-default lock order falls back to
one-at-a-time, the only state that could depend on an in-between league. `applySaved`, `apply` and `applyVisit` use it when present.
Roster `SUPERFLEX` still wins over the flag, and `applyVisit` keeps its order (weeks, league, week, advanced, shares).

Review follow-up: `applySaved` makes no `setLeague` call when the saved league already matches the current one, as the old code made
none, so the roster controls are not rebuilt for nothing.

### Checked
- `tests/test_engine_saved_league_pipeline_runs.py` (`test-unit-modules`): passes; fails on main (6 vs 2 calls).
- Engine snapshot before and after is byte-identical on values.html and team.html across 8 cases, per independent review.
- Pipeline calls: saved league load 10 to 6, hash link 18 to 8, `apply()` with several fields 10 to 2.

### Not done
- A manual y-axis now clamps once rather than once per step in `syncYAxis` (legacy chart only, not a value). Left as is.
- `make values-explainer MARK_REVIEWED=1` not run, same reasoning as the boot-dedupe PR. Merge after it, and run `make test-core` between.
- Open PR 1473 conflicts in `apply()`: keep `setLeague(partial, function (fn) { fn(); });` then its weeks lines.
