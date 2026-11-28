## 2026-11-27 - Draft tool: third Opus review of bc19862 corrections (part of JEG-1667)

Contract: fix the third review's parser, engine and doc findings on top of
bc19862 (not d58c0d7, which stays on local branch
`claude/draft-position-split-d58` while Jeremy re-decides the position
split). Vegas level and position split untouched. Committed locally on
`claude/draft-phase0-r3`; not pushed until the coordinator sends Jeremy's
answers.

### Verified (check named)
- Parser (`tests/test_draft_vegas_paste.py`, 42 tests; every reviewer probe has a test):
  - Only a market header marks a section as season-long.
  - One-line props are refused, and season floors are raised (rec yds 200, receptions 15, ...).
  - "Games" / "per game" / "week", "Post Season" and "25/26" labels are refused.
  - A bare "CIN"/"JSN" line clears the player.
  - "Over" plus a number on the next line is read; a dangling "Over" is listed.
  - The sample's two one-line rows were rewritten as multi-line rows, since the rule changed.
- Engine (`tests/test_draft_engine.py`, `tests/test_draft_strategy.py`):
  - With no projection, props are used only when they cover the position's scoring stats; otherwise the market prices the player.
  - A null in a plain line is treated as missing.
  - The market fallback maps dollars above the floor (`marketFallbackValues`, exact test).
  - `boardPrices` puts the source on every board row.
- 110 draft tests pass.
- Backtest re-run: identical to bc19862 ($6.47 keeper room, $5.38 ESPN averages; same source counts), as 2026 has no market-only player and every prop player has a projection.
- Docs: draft_sim.mjs header, engine.md limits, backtest.md inflation (-0.3%) and look-ahead line.

### Claimed, not confirmed
- The simulator was not re-run; its inputs are unchanged, as the identical backtest shows.
- `make validate` not re-run on this head.
