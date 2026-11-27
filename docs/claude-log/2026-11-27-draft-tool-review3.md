## 2026-11-27 - Draft tool: delta review of f0fcfb1 corrections (part of JEG-1667)

Contract: fix the delta review of f0fcfb1 (REQUEST CHANGES) on top of
d8d20c4. Corrects `2026-11-27-draft-tool-review2.md`: its "52-58 points"
mixed two comparisons, and its noisy judge centred on our own values.
Blend weights unchanged (50/25/25, Jeremy deciding).

### Verified (check named)
- Vegas parser:
  - Combined headers are refused in any order or joiner.
  - Each market needs its own season marker, and weekly or game sections are refused.
  - The year is checked on every line, and half, quarter, playoff and "incl." markets are refused.
  - An unknown name line clears the selected player; "(SEA)" team tags are stripped.
  - An over and under more than 5% apart is an error.
  - Each reviewer probe has its own test in `tests/test_draft_vegas_paste.py` (33 tests).
- C is capped at the best rival's max bid - $1 (the probe now gives C = B = $8), and "no money" is its own label (`tests/test_draft_strategy.py`).
- Truth-world simulator: seeded, with true value drawn first and independent errors for ours and market (`test_truth_world_is_seeded_and_independent`).
- 94 draft tests pass (`python3 -m unittest tests.test_draft_engine tests.test_draft_pull_parse tests.test_draft_strategy tests.test_draft_vegas_paste tests.test_draft_auction_paste`).
- Simulation re-run, 300 drafts, seed 2: B beats A by 3.3 +/- 0.3 under the truth judge, walk-away by 3.5 +/- 0.3 and C by 6.0 +/- 0.3. Personal minus room walk-away: 51.6 / 57.7 / 6.5 (ours / market / truth).

### Claimed, not confirmed
- `make validate` was not re-run on this head. The reviewer ran it at f0fcfb1 with the venv PATH and it exited 0; no files it builds changed since.
- The truth world assumes ours and market are equally accurate.
