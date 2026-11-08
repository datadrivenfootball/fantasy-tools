## 2026-11-08 - JEG-1512 week-held escalation; JEG-1194 alert read the wrong index (part of JEG-1485)

Contract: a chain gate holding a new week must raise an owned alert the same run,
plus a 2-hour staleness tripwire, inside GitHub Actions (no Muse). No value math,
no published numbers, no Supabase change.

### Week 9 timeline (evidence for why this exists)
- Sources complete in Supabase (first chain status showing each at content week 9):
  cbsros 11-03 03:28Z, fantasycalc 10:09, fantasypros 15:53, espn 18:44,
  razzball 23:28, cbs and usatoday 11-04 00:38Z.
- Chain red every run 11-01 00:55Z to 11-05 17:54Z (git history of
  `output/comparison-chain-status.json`): 11-01..03 fractional-seat stability and
  rank-guard tests on Week 8 refreshes; 11-03..05 `test_python_reference_flag_on_equals_baseline`
  from the all-source hold caused by the FantasyCalc history-clock bug (JEG-1479);
  11-05 the JEG-1511 waiver-band tests. Week 9 live 11-05 17:54Z (commit 47d6d1012),
  about 41 h after the last source landed.
- Alerts: `chain-stuck` (JEG-1194) never opened, in its whole life (no issue ever
  carried the label). ops-alert #1268 "Rebuild chain is failing" opened 11-01 13:16Z
  (12 h threshold) and stayed open, among about 20 fidelity ops-alerts that week.

### Root cause of the silent JEG-1194 alert (verified)
`chain_stuck_alert.py` measured fixture age from the working-tree
`data/history/index.json`. The chain's `make validate` runs `make sync`, whose
`sync_week_history` calls `build_week_history --served-only`, which rewrites
`fixture_built_at` from the candidate fixture just built (not published). So the
fixture always looked minutes old. Reproduced locally: set the fixture's built_at
to 2026-11-08T21:00Z, ran `build_week_history.py --served-only`, the index then
said 2026-11-08T21:00Z. Run 41952295990 (11-05 02:08Z, 4 days red) logged
"chain stuck alert: nothing to do".

### Change
- `chain_stuck_alert.py`: default history is the committed `HEAD` copy.
- New `pipelines/week_held_alert.py` (chain / tripwire / drill modes): GitHub issue
  `week-held` + Urgent Linear sub-issue of JEG-1512 (existing LINEAR_API_KEY,
  pattern of `open_divergence_issues.py`). Fidelity holds excluded (source-late's job).
- `rebuild-chain.yml`: new step after the JEG-1194 alert. `source-lateness.yml`:
  hourly tripwire step and a `week_held_drill` dispatch input.
- Runbook `docs/week-held-runbook.md`. Tests in test-unit-modules (non-blocking).

### Verified (check named)
- `python3 -m unittest tests.test_week_held_alert tests.test_chain_stuck_alert`: 46 OK.
- Discrimination: with the old working-tree read, `ChainStuckReadsCommittedHistory`
  fails ('none' != 'open').
- `tests.test_validate_shards`, `tests.test_run_suite` OK; actionlint finding count
  unchanged (40, all pre-existing shellcheck notes).

### Claimed, not confirmed
- Live drill (dispatch of source-lateness.yml with week_held_drill=true): see PR.
- First real chain run on main after merge prints "week-held alert: github: nothing to do".
