# JEG-1605: v2 round trip, results (run 2026-11-09)

Spec: `preregistration.md` (committed 1b3513f54 before any code; 16 implementation readings logged
in its change log, all coded before the first run). Code: `tools/research/jeg1605/roundtrip.py`
(stages 1-8), `l_gate.py`. Numbers: `tools/research/jeg1605/out/l_gate.json`. Tests:
`tests/test_jeg1605_roundtrip.py` (20 pass; identity `s = s0` exact on 360 real runs).

## Verdict: v2 fails the L gate. By the stop rule, H, M, the page and steelman rounds were not run.

The prediction written into the spec before building held: within a position the chain reduces to
"chart points times the player's projected ratio", and stages 6-8 cannot change that order.

| Cell (weeks 5-9) | Weeks chain beat "unchanged" | Chain minus unchanged, within position, by week |
| --- | --- | --- |
| CBS Sports, Standard to Full | 2 of 5 | +.004 / -.006 / -.001 / +.000 / -.006 |
| CBS Sports, Full to Standard | 1 of 5 | +.003 / -.009 / -.005 / -.012 / -.022 |
| USA Today, Standard to Full | 2 of 5 | +.005 / -.004 / -.002 / +.002 / -.008 |
| USA Today, Full to Standard | 0 of 5 | -.000 / -.002 / -.006 / -.005 / -.008 |

Pass needed at least 3 of 5 in every cell. "Unchanged" already scores 0.99-0.995: the publishers'
own Standard and Full columns barely reorder within a position.

## Diagnostics (pre-registered, no verdict)

- **L-level (the part v2 adds):** worse than unchanged in 20 of 20 cell-weeks. CBS Standard to
  Full, week 5: published WR level x1.17, RB x1.06 (WR/RB 1.11); chain WR x1.30, RB x1.04
  (WR/RB 1.26). Full to Standard the chain moves WR to about 0.55 against a published 0.85.
  USA Today's WR/RB level barely moves (about 1.00); the chain moves it 1.12-1.18.
  Cause: re-deriving replacement at the new scoring moves the league allocation (`N_p` RB 72 at
  Standard vs 60 at Full, WR 54 vs 66, week 5), so the RB replacement level moves a lot. That is
  the stage Jeremy asked for, done as pre-registered; the publishers do not move this much.
- **L-xpos:** chain worse across positions, 1 of 20 cell-weeks won.
- **L-mix (mix-aware vs position-level):** a position-level rescore equals "unchanged" within
  position, so L itself is that test, and mix-aware loses. On the extreme pairs (pass-catching
  backs or receiving tight ends against the least-used receivers at the position) the chain is
  right more often than unchanged: 5, 3, 5, 4 of 5 weeks across the four cells. The direction
  from each player's projected mix is right; the size is too large for the middle of the list.
- **L-source:** no single source's mix passes all four cells (Razzball and CBS ROS 3 of 5 only on
  USA Today Standard to Full; ESPN 0 of 5 everywhere). Median spread of a player's ratio across
  sources: RB 0.06, WR 0.08, TE 0.09. Fallback to the position median: CBS 0-1, USA Today 3-5,
  FantasyCalc 0-2, FantasyPros 0-1 players a week.
- **L-split:** additive split 0 of 5 in every cell; per-position curves 0-1 of 5, worse levels.
- **L-anchor:** a one-step wrong anchor (Standard column treated as Half) ties within position and
  has lower level error in 4 of 5 CBS weeks, because the smaller wrong step overshoots less.
- **Curve exponent `b` (value against VORP):** 0.39-1.37; Full-anchored CBS about 1.0-1.09.

## What v1 got wrong or skipped (evidence)

1. **v1 fitted value against points, not VORP**, so a position-wide points change was raised to the
   chart's convexity (`b` 2-5) and overshot about 3.5x; v1 patched it with `position_scaled`.
   Against VORP the exponent is 0.4-1.4 (about 1 for Full-anchored CBS): most of the "convexity"
   was the replacement offset. v2 removes the patch on principle.
2. **v1 never re-derived replacement or the allocation at the new scoring.** v2 does, and that
   shows the real problem: done properly, the replacement re-derivation moves position levels
   further from the publishers, not closer (L-level above).
3. Neither version can move within-position order less than the projected mix says without a
   damping factor, and the pre-registered gate forbids a tuned one. v1's best fit was about 0.3.

## What stays unidentifiable

- **Anchor for FantasyCalc and FantasyPros.** The new estimator (cross-position fit of the
  one-currency curve, a signal step 1 did not use) scored 9 of 20 on the labelled lists with 9
  Standard/Full cross errors, under the 16-of-20 bar; it reads almost every list as Full, so it is
  not informative (FantasyCalc Full 5 of 5 weeks, FantasyPros Full 4 / Half 1). The estimated-mix
  variant was not run. The site read (`06-audit/chart-site-scoring-evidence-2026-11-09.md`) adds:
  FantasyPros' base values point to Half PPR pages (implied, not stated) and it publishes separate
  2QB and TE-premium columns; FantasyCalc's method is unstated; USA Today could not be read.
  Under the anchor decision rule the formal "hinge" verdict needs H, which did not run. Descriptive:
  Half versus Full anchor shifts FantasyCalc's Standard WR level by 1.30-1.46x while
  within-position order stays at 0.995+, so its levels depend on an anchor we cannot pin down.
- **Games versus rate:** not separable, and under the uniform split it does not change any result.
- **The stat-mix prior:** the chart's disagreement with projections cannot be assigned to
  receptions, yards or touchdowns from the chart alone (uniform vs additive split both fail L).

## Constraints honoured

No live FantasyCalc request was made (its terms, effective 2026-10-10, allow only
`GET /values/current`, cached, 3 h per parameter set); all FantasyCalc inputs were saved
snapshots. Python: `/usr/bin/python3` 3.9.6 with numpy (the venv in the brief has no numpy).

## Durable learnings

- Value is roughly linear in VORP for the labelled charts at their Full column (`b` about 1); fit
  against VORP, not points.
- The publishers' format columns move much less than projected stats imply at both levels:
  within position (order 0.99+ unchanged) and across positions (CBS WR/RB about 1.1, USA Today
  about 1.0, versus 1.26 from a proper replacement re-derivation).
- Re-deriving the league allocation per scoring swings RB/WR rostered depth by 12 players at
  12 teams and moves the RB replacement level a lot; any scoring rebuild has to face this.
- Within-position mix direction from projections is right on extreme pass-catcher pairs.
