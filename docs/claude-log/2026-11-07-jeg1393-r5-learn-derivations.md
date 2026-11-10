## 2026-11-07 - JEG-1393 round 5 fixes (Learn derivations, methodology bench share)

Contract: copy and presentation fixes for R5-OP-02/03/05/06/08 and R5-CX-01. No value-model, reference or engine math changed; Learn only reads more of the engine's own inspection (lineup bye and missed-game rate, chartSigma, per-source weights, allocationMix starters, estimate paths).

### Verified (check named)
- Starter line rebuilt from each source's list (rank order) and allocationMix starter counts, floored at the waiver line, equals the engine's `positions[pos].starterLine` for all 7 sources x 4 positions at ppr/12/SF0 and half_ppr/10/SF1 (max difference 4.5e-13; in-page probe).
- DDF weight = mean of the included sources' own `weights[group]` (ES-15.1): RB starter 38.83% at default, 32.88% at half_ppr/10/SF1; availability (1 − 0.0625) × (1 − 0.1443) = 80.2%; CBS Gibbs σ 0.5107 × 56.50 = 28.86 at half_ppr/10/SF1 with band RB21–61 (rendered Build-up and Trace; tests.test_learn_engine_parity `test_round5_derivations_and_status` recomputes each from the engine's raw inspection at both settings).
- CBS estimates at default: 56 from the other charts, 1 from its own curve (estimate `path`), shown in the Build-up footer (same test).
- Status line after a settings change shows the new DDF Value; the test fails with the old `changed` (checked by reverting the fix).
- Full tests/test_learn_engine_parity.py and the three methodology tests: 27 passed. Rendered learn.html at 1280 and 390 px at both settings: no horizontal overflow, 0 console errors.
- No live page has a bench-share slider: curve-widget.js builds one only into markup that no current page ships; the override reaches the engine only from saved league settings or a Build a Trade link's `bso`.

### Claimed, not confirmed
- When a reader has set position shares, the DDF-weight line prints the mean and then says the engine rescales; not exercised in a test.
