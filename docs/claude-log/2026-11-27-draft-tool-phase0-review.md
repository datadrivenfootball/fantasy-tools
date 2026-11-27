## 2026-11-27 - Draft tool Phase 0: Opus math review corrections (part of JEG-1667)

Contract: fix the nine findings of the Opus math review of PR 1556 at
f8123a4 on the same branch. Still under the hold: no merge, deploy or apply.
Corrects `2026-11-27-draft-tool-phase0.md`, where ours was claimed to be
built "from market + Vegas": on the default basis it ignored a player's own
projections and Vegas lines.

### Verified (check named)
- A projection or Vegas change now moves ours: the value build's own `blend`
  basis, weights `DRAFT_BASIS_WEIGHTS` 50/25/25
  (`FullLeagueBuild.test_projection_change_moves_ours`, `test_vegas_change_moves_ours`;
  probe RB $15.73 -> $25.43 at 1.6x projections).
- Late-draft walk-away capped at best rival max + $1: the review probe gives
  walk-away $4, push floor $2 (`ReviewCases.test_late_draft_walk_away_capped_by_rival_max`).
- Plain-count `open` refused; IR ignored; draft-start inflation exactly 1.0
  with K/DST slots; `lineupConfig` required; $1 walk-away outside the pool;
  Yahoo presets; FLEX/superflex/bench eligibility; pool-size check
  (`ReviewCases`, `FullLeagueBuild.test_lineup_config_is_required`).
- Worked example and the three mutation guards still pass unchanged.
- 32 tests pass: `python3 -m unittest tests.test_draft_engine tests.test_draft_pull_parse`.
- Backtest re-run with the blend and a weight sensitivity table
  (`node tools/draft_backtest.mjs ...`): ours all-player MAE $3.5 keeper
  auction, $4.9 ESPN averages (shape), vs market $4.3 / $5.3.

### Claimed, not confirmed
- Part of ours' backtest edge may be hindsight: projections and props are
  dated three weeks after the keeper auction.
- The ESPN-averages test shares ESPN's dollar curve with ours and market
  (disclosed in `backtest.md`).
