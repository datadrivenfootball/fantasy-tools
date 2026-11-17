## 2026-11-17 - JEG-1691 v5 review round 1 fixes (PR #1472, draft)

Contract: fix the review findings on head 0637e6680. That covers the mechanical outcome, the
ESPN-left-out scope, the outcome-table gaps, a hardened once-only guard, a plain statement of
how hard each test is to fail, per-position T5, the stale-Sleeper correction, and wrong doc
statements. Dev weeks 5-7 only; no week 8-10 value was computed.

### Verified (check named)
- `python3 -m pytest -q tests/test_jeg1691_v5.py tests/test_jeg1611_v4.py tests/test_jeg1611_shrink.py`
  passes. It includes the new checks:
  - `test_outcome_rules_are_mechanical`, among them a FantasyPros T5 failure under the Full anchor
    blocking C;
  - `test_guard_requires_committed_approval`;
  - `test_manifest_covers_the_executed_tree`;
  - `test_espn_left_out_of_step4_keeps_references`.
- The dev rerun `run_v5.py --weeks 5 6 7` completes with the new sensitivity set and writes
  `out/dev/verdict.json` with a `decision` block, which on dev is not a decision.

### Claimed, not confirmed
- The tests ran on Python 3.9 (`python3`, with numpy and scipy). No Python 3.12 environment with
  numpy and scipy exists on this machine (`/Users/botcomp/code/fantasy-tools/.venv` is 3.12 without
  numpy). Building one would need a package download, which was not done without Jeremy's yes.

### Correction to the 2026-11-16 entries
- Amendments 2-9 said no pass threshold was loosened. T2(iii) went from 1e-9 to 1e-4 after the dev
  run showed 1e-6, and the first dev files (21:32 CST) were written on code committed only at 21:53.
  Both are now recorded in the pre-registration's amendment 16.

### Re-review fix (2026-11-17)
- Verified: `--no-sensitivity` with `--decisive` or `--replication` is refused before any lock is
  written (`test_no_sensitivity_refused_outside_dev`, both flags). `pytest` passes, 36 tests on
  Python 3.9.
- Claimed: no Python 3.12 environment with numpy and scipy could be built. The local pip cache
  (`~/Library/Caches/pip`) holds only HTTP cache entries and no cp312 wheels, and a download was
  not allowed.
