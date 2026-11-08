## 2026-11-07 - JEG-1569 PR 1: charts-only position split, built and off by default

Contract: Jeremy, 2026-11-07, multiple choice on the JEG-1569 report (`06-audit/ddf-value-charts-only-split-2026-11-07.md`
in the handoff folder):
- (1) option A: charts-only becomes the default for DDF Value's position split;
- (2) it ships with the trade value audit article, so the default flips only on his explicit go at publish time;
- (3) DDF Projections gets its own projections-only split;
- (4) the 2-QB rule (no superflex slot, JEG-1366) uses the charts only.

This PR builds all of it behind `DDF_VALUE_SPLIT` with the default `"all"`, so no published number changes.
The flip is a separate PR that stays unmerged until Jeremy says go.

### What changed
- `value-model.js`:
  - New `DDF_VALUE_SPLIT_DEFAULT = "all"` and `vpDdfSplit(setting)`. It reads `setting.ddf_split`, then the global
    `DDF_VALUE_SPLIT`, then the Node env var.
  - VP-4 is now `vpWeightsOver(sources, twoQbRule)`.
  - On `"charts"`, the split is computed over the charts with no 2-QB rule, and `W_proj` over the projections.
    Each source is paid its family's budgets (`o.budgets`).
  - The result gets `ddfSplit`, `ddfWeightsProjections` and `budgetsProjections`, only on `"charts"`.
- `value_reference.py` is the twin: `League.ddf_split` (env default), `ddf_weights(..., family=)`, family budgets in
  `_price`, and the new keys only on `"charts"`.
- `curve-widget.js` fixed-pie check and `app/v2/audit-pie.js` read `src.budgets` when present.
- get-values takes an optional `split` (`all` | `charts`), or `league.split`. It is passed as `setting.ddf_split`
  and added to `custom` (cache key). An absent value leaves the setting exactly as before. Not deployed.
- `docs/methodology.md` VP-4.6. New test `tests/test_jeg1569_charts_only_split.py` (3 tests).

### Verified (check named)
- **Flag off equals main, Python.** `ref_dump.py` hashes full `diagnostics()` and all three views at 30 settings:
  3 scorings x 8/10/12/14 x SF 0/1, plus 2-QB, 2-QB + SF, position shares, basis blend and fixed bench share.
  The overall digest 9a1267e3... is the same on origin/main cb2a83ad6 and this branch.
- **Flag off equals main, engine.** `tools/engine_dump.py` at 24 settings, on the same built dist with main's vs this
  branch's `value-model.js` and `curve-widget.js`: the output JSON is byte-identical (sha f375a404...).
- **Flag on, engine vs reference.** The browser engine (init-script global) matches the Python reference on every
  value at 24 settings: DDF Value 15,864 values and DDF Projections 8,832, max diff 4e-14.
- **Flag on, 2-QB.** In a 2-QB league, `tests/test_jeg1366_two_qb_native_share` engine==reference tests pass with
  both sides flagged (Node env).
- **Flag on, guard.** `tools/guard_harness.mjs --assert-good` passes in both modes, standard and ppr at 12 teams.
- Test sweeps (35 modules, 552 tests): see the PR body.

### Claimed, not confirmed
- The get-values `split` parameter is not deployed and not run under Deno here. Deploying the edge function needs
  Jeremy's separate yes.
- The spec reference (`pipelines/spec_reference/`) has no `"charts"` mode yet. It only has to follow at the flip
  (the worked example), which is listed in the flip PR.
