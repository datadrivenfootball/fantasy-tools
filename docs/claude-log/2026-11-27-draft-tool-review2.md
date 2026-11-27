## 2026-11-27 - Draft tool: second Opus review corrections (part of JEG-1667)

Contract: fix the independent Opus review of f662c66 (REQUEST CHANGES):
two blockers, three should-fixes, nits. Corrects
`2026-11-27-draft-tool-phase0-review.md` (keeper backtest $3.5 was inflated
by the Vegas distortion) and `2026-11-27-draft-tool-phase0-deploy-sim.md`
(simulation scored only with our own values, against bots that matched our
model). Defaults (push floor, personal inflation, blend) left for Jeremy.

### Verified (check named)
- Vegas covers the FantasyPros pool; Vegas equal to FantasyPros prices
  exactly like FantasyPros with the Vegas weight
  (`FullLeagueBuild.test_vegas_equal_to_fp_leaves_ours_unchanged`, max diff 0).
- The Vegas parser refuses combined, longest, attempts, targets and
  interceptions markets. An unknown header resets the market. It requires
  "season" on the page, checks the season year on every season line, rejects
  conflicting unders and reads "3,875.5". One test per case in
  `tests/test_draft_vegas_paste.py` (22 tests).
- Buy limit separate from push floor B (late probe: $4 vs $2);
  `topRivalMaxBid` is the room's max; "no slot" classification
  (`tests/test_draft_strategy.py`, 15 tests).
- 78 draft tests pass:
  `python3 -m unittest tests.test_draft_engine tests.test_draft_pull_parse tests.test_draft_strategy tests.test_draft_vegas_paste tests.test_draft_auction_paste`.
- Backtest re-run: ours $4.0 keeper room (market $4.3, platform $3.7), $4.7
  ESPN averages (market $5.3). Sensitivity: 70/15/15 best in the keeper room
  ($3.8).
- Simulation re-run (300 drafts, seed 2, misspecified bots, three judges): B
  beats A by 3.4 / 2.4 / 2.3 points (ours / market / noisy), each more than
  two standard errors; B and C tie under the independent judges.
- `make validate` exit 0 earlier today with
  `PATH=/Users/botcomp/code/fantasy-tools/.venv/bin:$PATH` (Python 3.12.12;
  Playwright in that venv) and `CHROMIUM_PATH` set to Google Chrome. System
  Python 3.9 fails in `make sync` on `fromisoformat`.

### Claimed, not confirmed
- `make validate` has not been re-run on this head (no files it builds
  changed).
- Bots still nominate simply; the noisy judge centres on DDF Value.

### Addendum (same PR): personal inflation is the board default
- Jeremy, 2026-11-27: "Personal by default (Recommended)". `boardRow` uses
  personal inflation unless `state.ourFactor = "room"`; every row carries
  `oursInflatedRoom` for reference. The worked example gains a hand-checked
  personal table (A's factor 0.8) next to the room table; the old
  "room is the default" assertion flipped because the rule changed.
  79 draft tests pass. Push floor and blend weights unchanged.
