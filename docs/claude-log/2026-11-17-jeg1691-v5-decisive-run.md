## 2026-11-17 - JEG-1691 v5 decisive run, weeks 8-10 (PR #1472, draft)

Contract: run the approved commit's decisive run once, per the pre-registration's "How to run".
No rerun, no tuning, no edit to the harness.

### Verified (check named)
- The reviewed commit is aa1476d0be6893cbae0f28c2aa36e15a467d05f4. `APPROVAL.json` was committed on
  top of it as 941de0e39 and pushed before the run.
- The run used a fresh clone at aa1476d0 (`git rev-parse HEAD`), with a throwaway venv: Python
  3.12.12, numpy 2.5.5, scipy 1.18.1, an import check passed. That was the one approved download.
- The caches are the committed ones. Their blob ids match the dev worktree's: pgs 880a320,
  sleeper 2ecc182, captures 8246522, t6_widening 4637b41.
- A pre-flight dev run (weeks 5-7, `--quick`) in a second clone on 3.12 reproduced the dev point
  estimates. It is not a decisive run.
- The decisive command ran once (206 s, exit 0). `DECISIVE.lock` and `out/decisive/` were committed
  together as 98c375d0f and pushed straight away.
- `verdict.json` records reviewed_commit aa1476d0, head 941de0e39 and decision.outcome **B**.

### Claimed, not confirmed
- None for the run. What the result means is limited to the pre-registered rules (sections 5-6).
