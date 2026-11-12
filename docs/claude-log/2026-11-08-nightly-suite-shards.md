## 2026-11-08 - Nightly suite sharding / JEG-1547

Contract: split the complete nightly command list deterministically without changing assertions, skipping coverage, or changing the default unsharded invocation. Preserve the make baseline wrapper and exactly one baseline-history writer. Local preparation only; no push, dispatch or deployment.

### Verified (check named)
- `python3.12 -m unittest tests.test_run_suite tests.test_baseline_reds tests.test_no_real_clock tests.test_preview_workflow_matches_pages tests.test_ci_speedup_workflows tests.test_workflow_no_event_interpolation tests.test_org_cutover`: 97 tests passed. Also passed on system Python 3.9.
- `actionlint .github/workflows/full-suite.yml` and `git diff --check`: passed.
- Real Makefile expansion plus suite guards yields 392 commands, partitioned into 66/66/65/65/65/65. Tests check exact occurrence coverage, order, duplicate preservation, the clock guard, Node and pytest commands, invalid shard arguments, failure continuation and child environment isolation.
- Every command emits START and END with exit code and duration. Shard logs are uploaded with unique names. Matrix fail-fast is false; the existing 120-minute and non-blocking settings remain. Shard 1 alone restores, observes and saves baseline history.
- `make validate` through baseline attribution failed before tests on system Python 3.9 because its ISO timestamp parser rejected an existing fixture timestamp. Retried with the workflow's Python 3.12: sync failed because the installed Playwright headless-shell executable is absent. These are local validation limits, not a passing aggregate gate. Generated build outputs remain uncommitted and preserved in the isolated worktree.

### Claimed, not confirmed
- Six shards should reduce elapsed time, but no timing-based balance or completed nightly run has been demonstrated. No per-module deadline is invented.
- Baseline observation remains on shard 1 and can still be interrupted if that shard hits its job bound. It is not an independent recovery job.
- No independent review, remote CI, current-main integration or live acceptance run. The work starts from locally cached origin/main e2e3c7e15176a9f3f9b37e402bd38e5de24be8f2; later main must be integrated before publication.
