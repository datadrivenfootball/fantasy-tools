## 2026-11-27 - Draft tool: Vegas scaling, projection split, 2026 re-test (part of JEG-1667)

Contract: Jeremy's decisions of 2026-11-27, relayed by the coordinator:
- Vegas level: "Scale to projections (Recommended)".
- Position split: "Projection split (Recommended)", replacing "A"; d58c0d7 dropped, never pushed.
- Push floor: "Re-test on 2026 results (Recommended)".
Built on the third-review fixes (688003f) as one head.

### Verified (check named)
- `vegasScaleFactors` / `scaleVegas`: for each market, the median of projection / line; Vegas still wins where it has a line. 2026 factors: pass_yds 1.117, pass_tds 1.074, rush_yds 1.238, rush_tds 1.107, rec 1.106, rec_yds 1.137, rec_tds 1.109.
  - 0.9x lines give ours equal to projections only (`test_vegas_lines_scaled_to_projection_level`; `test_unscaled_lines_would_move_ours` is the discrimination check).
  - The snapshot meta records the factors and the pull date (`test_writes_dated_snapshot_in_the_0912_shape`).
- `tools/draft_outcome.mjs`: reproduces the reviewer's pre-scaling numbers within $0.2. Scaled, ours is $9.2 / $8.3 / $7.7 against market $10.5 / $9.1 / $8.4 (standard keeper / half PPR / ESPN PPR). Unit test `tests/test_draft_outcome.py`.
- Backtest: ours $5.6 in the keeper room and $5.1 on ESPN averages (market $4.3 / $5.3).
- Simulation, 300 drafts, seed 2, with the realized judge: B beats A by 36.8 +/- 3.1, walk-away by 49.4 +/- 3.0 and C by 6.7 +/- 1.4. B stays the default.
- Personal minus room inflation under the realized judge: -22.0 +/- 3.8, reported, not changed.
- 113 draft tests pass.

### Claimed, not confirmed
- Realized value uses weeks 1-11 scaled to 17; late-season injuries and role changes are not in it.
