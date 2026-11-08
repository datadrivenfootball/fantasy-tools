## 2026-11-08 - JEG-1485 decision A: the chain and the deploy check data only

Contract: Jeremy, 2026-11-08 (multiple choice, relayed by the coordinator): "the chain checks
DATA only before publishing; code tests keep gating PRs and run nightly; a held week
still alerts within 2 hours." The gate must still fail closed on bad data. No value math,
no published numbers, no Supabase change.

Why: in the Week 5-9 audit (06-audit/weekly-rollover-audit-2026-11-08.md), every week that
slipped (W6 ~54 h, W8 ~16.5 h, W9 ~41 h) was held by `make validate` = all of test-core
failing on new data. Since 09-25 there are 760 "chain failed" status commits against ~300
publishes.

### Change
- Makefile: `data-gate` (21 test-core modules that assert the build's own artifacts) and
  `validate-data: validate-base data-gate`. test-core and validate are unchanged.
- rebuild-chain.yml: both post-rebuild validations run `make validate-data`; the isolator
  and retry flow are unchanged.
- pages.yml: the build job runs `make data-gate` after `validate-base` (blocking); deploy
  `needs: [build]` and checks only BUILD_RESULT. validate-shard (test-core) still runs on
  every push. preview.yml adds the same `make data-gate` step (the parity guard requires it).
- The guard tests that pinned the old rule now pin the new one: test_deploy_gate_unconditional,
  test_preview_workflow_matches_pages, test_rebuild_chain_bake (its removal mutation had
  matched nothing since the candidate_evidence wrapper landed; it now targets the real
  command), test_rebuild_chain_workflow, test_post_validate_workflow_wiring, test_value_check.
- New tests/test_chain_data_gate.py; the definitions are in docs/week-held-runbook.md
  ("What the chain checks before publishing").

### Verified (check named)
- `make reference && make sync && make -k data-gate` on main's committed Week 9 data
  (Chrome via CHROMIUM_PATH): 21/21 modules OK (gate=0), ~21 min locally
  (test_static_export 950 s).
- Fail-closed negative control: one K row injected into players.json makes
  `tests.test_kdst_removed` fail (2 failures); restored, it passes. Engine vs reference
  stays `value-check-compare --strict`, and guard-harness `--assert-bad` stays in validate-base.
- Guards: test_chain_data_gate, test_validate_shards, test_preview_workflow_matches_pages,
  test_deploy_gate_unconditional, test_ci_speedup_workflows, test_post_validate_workflow_wiring,
  test_rebuild_chain_workflow, test_rebuild_chain_bake, test_rebuild_chain_failclosed,
  test_week_held_alert: 187 tests OK. actionlint findings unchanged (44 on both sides).

### Claimed, not confirmed
- The first chain run on main after merge runs validate-data and publishes when the data
  checks pass even if a code test is red (check: chain status `command`, fixture `built_at`).
