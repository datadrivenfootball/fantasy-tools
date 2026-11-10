## 2026-11-09 - JEG-1587 monitoring coverage manifest

Contract: add explicit, reasoned exemptions for three event/manual workflows missing from the coverage manifest. Publish a draft only; no workflow behavior, test assertions, schedules, Supabase, value math or published values change.

### Verified (check named)
- Base main: e30c295a82228ecda9527384d92b58025a84656f. Current AGENTS.md and repository skill inventory checked; no applicable repository engineering skill is present.
- Exact-base offline subset: 104 source files verified against GitHub blob SHAs, including all 43 workflow YAML files, all 48 migration SQL files and the coverage suite's dependencies. The prior subset's unrelated week-held runbook was not needed for execution.
- `python3 -m unittest tests.test_monitoring_coverage`: unchanged base runs 29 tests with one failure listing chain-run-feedback.yml, main-write-pause-switch.yml and main-writer-checks.yml. With only these three manifest entries added, all 29 tests pass. Tests and assertions are unchanged.
- chain-run-feedback.yml is event-driven attribution of completed rebuild-chain runs. main-write-pause-switch.yml is a manual bounded release control. main-writer-checks.yml is PR security-contract/lint CI. None has a periodic monitoring cadence; Actions summaries, artifacts and check results remain their evidence.
- PR #1381 changed existing rebuild-chain.yml and source-lateness.yml, not newly named workflows. The former retains its rebuild_chain check and always() recorder; the latter retains its explicit exemption and week-held tripwire/drill steps.
- Every existing manifest entry is preserved. Draft #1334's JEG-1140 deletion and #1341's separate review-receipt manifest additions are not imported.

### Claimed, not confirmed
- Focused tests are not full validation. This cloud source subset is not a full checkout; make validate, browser/aggregate tests and live alert delivery have not run here. Exact-head CI and full validation remain release gates.
- This change requires independent high-risk review because it touches config/**, after required CI is green. Draft publication does not authorize readiness promotion, merge or deploy. Current-main integration and normal release/live verification remain with the release owner.
