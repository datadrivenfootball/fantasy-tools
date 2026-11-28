## 2026-11-27 - Draft tool: ours by source availability (part of JEG-1667)

Contract: Jeremy, 2026-11-27: "Vegas when available is there, then
projections, then market. We are picking by what's available, not
averaging." Replace the 50/25/25 blend with a per-stat fallback, label each
price's source, re-run the backtest and the simulator. Corrects the blend
entries in `2026-11-27-draft-tool-phase0-review.md` and `-review2.md`.

### Verified (check named)
- `ddfDraftValues`: a Vegas prop is used per stat, otherwise the projection; a player with no projection uses the market. One projection source through `runValuePipeline`, reading the projections version. No basis weights remain.
- Source labels (vegas, vegas+proj, proj, market) are returned and shown on the board row.
- New tests in `FullLeagueBuild`, one per case:
  - all props
  - partial props
  - no props
  - no projection
  - Vegas equal to FP (max difference 0)
  - stale or rejected snapshot falls back to the projection, never zero
- 96 draft tests pass.
- 2026 sources: 25 vegas, 88 vegas+proj, 286 proj, 0 market.
- Backtest: ours $6.5 in the keeper room (RB +6.7, WR -6.5) and $5.4 on ESPN averages; market $4.3 / $5.3.
- Simulation, 300 drafts, seed 2: under the truth judge B beats A by 4.3 +/- 0.3, walk-away by 4.6 +/- 0.4 and C by 7.3 +/- 0.4. Under the market judge B loses to A by 9.5 +/- 0.5.

### Claimed, not confirmed
- That the backtest gap is the position split (projections alone set it, with no market chart): inferred from the RB/WR bias signs, not isolated by a run.
- `make validate` was not re-run on this head.
