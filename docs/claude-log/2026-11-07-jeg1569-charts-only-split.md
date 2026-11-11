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
- The get-values top-level `split` 400 path (index.ts) is not run under Deno here; `league.split` is covered through
  `tests/_edge_pipeline_runner.cjs`.

### Follow-up (Codex P1 on #1366): spec reference paired
- `pipelines/spec_reference/value_pipeline.py` now has `Setting.ddf_split`, with the same rule.
- `SpecReferenceEqualsReferenceOnTheChartsSplit`: the spec equals the Python reference on both weight sets, DDF Value
  and DDF Projections at 3 settings, in both modes.
- On identical inputs, the spec's live output (`pipeline_live.build`, 13 settings) hashes the same as main's
  (`80a628a4...`).

### 2026-11-09: the flip PR (#1367) brought up to date and made merge-ready
Jeremy's go, 2026-11-09 CT (relayed by the lead): "Flip all now."
- Merged origin/main (e14995fff) as a normal merge commit. #1366 had landed as a squash, so main's copies of the
  split-flag files were taken and only the flip delta was re-applied.
- Worked example regenerated on the charts split: the `expected` and `variant_bench_share_0_10` numbers from the spec
  reference, the expected-starts variants with `tools/worked_example_expected_starts.py`, the doc block with
  `tools/methodology_worked_example.py`. The engine and the Python reference reproduce it (0 mismatches at 1e-6). The
  generator now prints `W_proj` for a projection's hand-check (it printed the charts' `W` beside rates built on
  `W_proj`).
- Tests that assumed one shared weight set now compare a source with its own family's budgets on the charts split:
  `tests/test_bench_budget_cut_render.py` (pie x W_proj for a projection) and the audit pie's "positions" and
  "totals" checks (`app/v2/audit-pie.js`, compared within a weight set).
- `tests/fixtures/baseline_main_771c3422/value-model.js` re-frozen from the PR head (README paragraph): a deliberate
  default-value change.
- Still open (not blocking): the projection-influence ledger and `test_build_waiver_board` fail on main too (an
  old hook signature and a week-8 board vs week-9 data). Post 09 numbers and the JEG-1562 opportunity calibration are
  follow-ups.
