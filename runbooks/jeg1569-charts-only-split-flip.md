# Rollout: charts-only position split as the default (JEG-1569)

Jeremy decided this on 2026-11-07 (option A): DDF Value's position split comes from the four trade charts, and DDF
Projections uses its own projections-only split. The 2-QB rule uses the charts only. The default flips **with the trade
value audit article**, and only on Jeremy's explicit go at publish time.

PR 1 (merged, default off) built everything behind `DDF_VALUE_SPLIT`. This flip PR changes the default and the text.
Do not merge it without that go.

## Before merge
1. Jeremy's go, quoted with the date on JEG-1569. Replace `<date>` in `value-model.js`, `value_reference.py` and
   `docs/methodology.md` VP-4.6.
2. Spec reference: add the `"charts"` split to `pipelines/spec_reference/value_pipeline.py`, using the same rule
   as VP-4.6. Then regenerate `tests/fixtures/value_pipeline_worked_example.json`, schema /2, with
   `tools/methodology_worked_example.py` and its expected values. Three implementations must agree to 1e-6
   (`test_spec_reference_value_pipeline`, `test_value_reference_worked_example`, `test_methodology_worked_example`).
3. Regenerate the pinned numbers. Run the 35-module reference sweep with this branch's defaults and compare it
   with origin/main's sweep from the same day (data refreshes make some failures date-specific). Expect:
   - the JEG-1366 tests: pinned to `"all"` in this PR;
   - the projection-influence ledger (`docs/research/projection-influence-ledger`, `tests/test_projection_influence.py`):
     the weights route is about 0 on the charts split. Rerun `ledger.py freeze` and `run`;
   - audit-pie fixtures (`tests/fixtures/audit/*.json`) that store `ddfWeights`;
   - `tests/test_build_waiver_board.py`, if it pins values;
   - `docs/research/posts/09-how-position-weights-work.md` numbers (`tools/research_post9_numbers.py`).
4. Opportunity tiers: rerun the 36-roster calibration (`docs/claude-log/2026-11-07-opportunity-module.md`) on the
   charts numbers, under JEG-1562. Keep 3/6/10% unless the rerun moves the medians.
5. Article (JEG-1565 branch, PR #1352). Replace these lines (from `app/next/research/trade-value-audit.html`) in
   the same release:
   - "How we tested" (line ~144 and ~340): "The split of value between positions is set by averaging the four
     charts' own position mixes, each priced on your league's starter and waiver lines; the projections set only
     those lines (from projected points per game), not the split."
   - Superflex (line ~213): "DDF Value gives quarterbacks X%, the average of the four charts' own shares on a
     league-aware scale." Delete "which is why it sits above the charts' average".
   - Standard (line ~179): delete "comes partly from the projection inputs in its position budget (see How we
     tested)". Rerun the script and state the gap as measured.
   - TE and QB cards (lines ~286, 287): delete "with projection inputs in its position budget".
   - Rerun `pipelines/research_trade_value_audit.py`. On the article fixture the expected values are: superflex DDF
     QB 27.3%, 2-for-1 10%, top TE 46%; CBS is no longer level on TE.
6. Gates: `make validate` (including `value-check-compare --strict`), the render tests, `tools/guard_harness.mjs
   --assert-good`, `tools/engine_dump.py` against `value_reference` (0.0 max diff, as in PR 1), and an independent
   review.

## Deploy (after merge: Pages deploys main)
7. Pages builds and publishes. `value-model.js?v=<build>` busts the browser cache. Spot-check the Values page at
   Half PPR 12 superflex: Josh Allen about 67.9 and the QB share 27.4% (week 9 numbers; re-read them on the day).
8. MCP / get-values: no code deploy is needed. It loads the published `value-model.js` and follows within its
   5-minute bundle cache, the per-instance answer cache (5 minutes) and `Cache-Control: max-age=300`. Deploying the
   get-values `split` parameter (PR 1 code) is a separate Supabase step and needs Jeremy's yes. Until it is
   deployed, a `split` or `league.split` argument is ignored by the live function.
9. The local MCP copy `09-mcp-server/engine-local/site/value-model*.js` (handoff folder): refresh it before parity runs.

## What a reader sees change
- **Values:** cross-position re-pricing only. Order within a position and DDF tiers do not change.
  - Superflex: QBs fall about 17 to 22%, and WRs and TEs rise.
  - Standard 1QB: RBs fall 8 to 11%.
  - Full PPR 1QB: under 5%.
- **Overrides:**
  - Absolute overrides (`ov=2227:58.0`, localStorage `ddf.v2` overrides) keep their number, so their distance from
    DDF Value changes. A superflex QB override set 10 above the model is now about 20 above it.
  - Adjustments (`+5`) keep their meaning.
  - Recommended: a one-time note on the Overrides tab ("DDF Value's position split changed on <date>; check your
    absolute overrides"). Do not convert overrides automatically.
- **Basis:** unchanged in meaning. A basis picks which Adjusted values DDF Value averages, and each source's
  Adjusted value is now on its family's split. A blend of charts and projections averages values priced on two splits.
- **Links with stored values:**
  - LINK-FORMAT state, `make_state` and `read_state` carry settings and player ids, not values, so they reprice on open.
  - Shared chat answers, MCP replies and screenshots quoting numbers keep the old numbers.
  - The article quotes its own script output, rerun in step 5.
- **Week over week:** the prior week is repriced on the same split, so the "since last week" deltas stay consistent.

## Back out
Set `DDF_VALUE_SPLIT_DEFAULT = "all"` (and the Python default), then merge. Nothing is stored server-side.
