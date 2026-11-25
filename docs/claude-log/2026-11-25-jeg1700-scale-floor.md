## 2026-11-25 - Week 12 held by the overall-scale floor / JEG-1700

Contract: find why the chain kept Week 11 on the site after the Week 12 rollover and fix it with the smallest
change that keeps the gate honest. PR #1530, branch `claude/project-thread-n8nb42`.

### What failed
Every main `rebuild-chain.yml` run from 2026-11-23 06:44 UTC (still Week 11) failed closed in post-rebuild
validation on one data-gate test, `tests.test_static_export ... test_top_indexed_values_preserve_high_overall_scale`
(every chart's top full_12 Indexed value >= 38). The value it reported: 37.41 (Nov 23), 37.68, 37.56, then
36.59 from the Week 12 rollover (2026-11-24 05:04 UTC) and 35.78 from 18:45 UTC. JEG-1700's alert named cbsros
only because cbsros was the one source with a newer week waiting when it fired (cbsros was held 2026-11-23 12:48
to 2026-11-24 00:04 UTC, while this test was already failing).

### Root cause (the test's floor, not the data)
USA Today's board is unchanged since 2026-11-17 (top native 81, native total 4710). JEG-482 indexes it by one
factor so its total equals ESPN's total over the same players. That anchor total fell 2242.7 -> 2175.4 -> 2127.4
-> 2080.8, so its top fell 38.6 -> 35.8 with its pie still exact. The 38 floor (last lowered 45 -> 38 for JEG-667)
was a heuristic for scale collapse; for one-factor charts the anchor-pie test already pins scale exactly.
The assertion was wrong for that chart type; the JEG-482 rule (Jeremy, 2026-10-08) is what sets their scale.

### Fix
`overall_scale_problems()` in `tests/test_static_export.py`: the 38 floor applies to anchor-scale charts (ESPN,
CBS ROS, Razzball); a chart with an `order_preserving_rescale` fit, held or not, must reproduce its top as top
native x factor. Overall max >= 68 unchanged. New test `test_scale_floor_follows_chart_type_not_hold_or_drift`.
Codex review on 8d4f8ab4 found a held one-factor chart still fell under the floor; fixed by classifying on the fit.

### Verified (check named)
- Source of the failing value is USA Today: anchor totals implied by 4710 x top / 81 come out at one-decimal
  ESPN sums (2175.4, 2127.4, 2080.8); fixture factor 0.476157 x 81 = 38.569 matches the published top.
- `python3 -m pytest tests/test_static_export.py`: 36 pass; `test_inline_players_match_fixture` fails the same
  way on origin/main locally (no build in this sandbox), not this change.
- Simulated USA Today at 35.78: main's test fails, 8d4f8ab4 fails when USA Today is also held, the new head passes.
- Simulated USA Today factor halved: `test_published_indexed_is_one_factor_on_the_anchor_pie` fails.
- Simulated ESPN, CBS ROS, Razzball x 0.4: the new floor fails (28.0 < 38).

### Claimed, not confirmed
- No other data-gate test fails on the Week 12 candidate: tests after `test_static_export` never ran on the held
  candidate. Branch proof run 45528274289 (8d4f8ab4) is the check; see the PR.
- Week 12 publishes on the first main chain run after merge.
