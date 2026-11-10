## 2026-11-08 - test-core shard 3 rebalance / JEG-1580 (Claude, CI health lane)

- Problem: `test-core-shard-3` (preview-shard 3 on PRs, validate-shard 3 on deploys, 30-minute job timeout) took
  29.6 minutes on pages run 42520541617, 29.1 of them tests. It was cancelled at 30 minutes on PR #1372, run
  42521576491, inside tests.test_view_switch_hidden_defaults. New modules kept going to the end of shard 3.
- Change: the 13 lines from test_espn_listed_rows to test_razzball_outlier_guard (9.6 minutes measured) moved. The
  first three (about 4.8 min) went to shard 2 and the rest (about 4.8 min) to shard 4. Each went in at its test-core
  position, so every shard still keeps test-core order. Expected: 2 = 19.7, 3 = 19.5, 4 = 19.6 minutes.
- No test, assertion or timeout changed. The test-core union is unchanged (tests.test_validate_shards).
- Checks: `python3 -m unittest tests.test_validate_shards tests.test_preview_workflow_matches_pages tests.test_ci_speedup_workflows`: 70 OK.
- Not confirmed until this PR's own preview run shows the shard times.
