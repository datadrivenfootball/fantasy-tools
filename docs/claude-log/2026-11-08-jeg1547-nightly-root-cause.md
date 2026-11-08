## 2026-11-08 - Nightly full suite: root cause and shard bound / JEG-1547 (Claude, CI health lane)

Builds on Codex's sharding in this branch (PR #1372; see 2026-11-08-nightly-suite-shards.md and
2026-11-08-nightly-shards-qualification.md). Main merged in normally, with no rebase.

### Root cause (verified from the complete job logs)
- `gh run view --job N --log` cuts these logs off at about 12 minutes. It made every cancelled night look as if
  it stopped inside tests.test_v2_assist. The complete log comes from
  `gh api --allow-escape-sequences repos/datadrivenfootball/fantasy-tools/actions/jobs/N/logs`.
- No hang. Run 42489313245 (2026-11-08) ran 191 of 391 commands in 110.6 minutes and was cancelled inside
  tests.test_waiver_band_line.
- The suite outgrew its 120-minute bound. The last green run (41087666788, 2026-10-30) had 325 commands and took
  92 minutes. The commands both runs share are 1.21x slower now. Projected sequential total: about 148 minutes.
- Slowest modules on 2026-11-08: test_v2_panels_render 12.2 min, test_v2_targets_render 8.5,
  test_v2_contract_render 7.9, test_v2_phone_tap_targets_render 5.7, test_waivers_render 4.6,
  test_v2_share_links_render 4.2, test_v2_weight_render 4.1.

### Change on top of #1372
- `full-suite.yml` timeout is now 60 minutes per shard (it was 120 for the single job). The six round-robin shards
  come to about 29/19/23/25/27/25 minutes by that run's per-command times, plus 40 s for each command with no
  history, so 60 leaves 2x headroom. The pin in tests/test_run_suite.py moved from 120 to 60. This is a
  config pin, not a behavior assertion.

### Checks
- `python3 -m unittest tests.test_run_suite tests.test_ci_speedup_workflows tests.test_baseline_reds tests.test_validate_runner`: OK.
- `actionlint .github/workflows/full-suite.yml`: OK. Shard partition: 392 commands, 66/66/65/65/65/65, union exact.

### Claimed, not confirmed
- The shard times are estimates. The first dispatched run after merge measures them (one run only).
- About 40 modules were already red on the 2026-11-08 night. Sharding makes them visible. It does not fix them
  (the JEG-1546 lane and separate tickets do).
