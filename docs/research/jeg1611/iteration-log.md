# JEG-1611: scoring-aware DDF v4, iteration log (append-only)

Research only: no change to published numbers, the value model or the live pipeline. Each entry:
hypothesis, change, result on the development set, decision. Development set = 2026 snapshot weeks
5-7 and the 2015-2025 actuals; **weeks 8-9 are held out** (not loaded by any development script);
week 10 charts (Tue 2026-11-10) are the out-of-sample test. No strength parameter is ever fitted
to CBS Sports' or USA Today's columns; every such number comes from historical actuals by
cross-validation. Entries are dated and never edited after the fact; corrections are new entries.

Jeremy's logic (2026-11-10) is the design: 1) third-party charts; 2) the adjusted value that feeds
DDF; 3) unwind to VORP; 4) back out expected points; 5) per player, how he earns points from
historical metrics by category; 6) apply that mix to get implied metrics; 7) per scoring, build back
up through DDF and average as DDF does; only for charts that do not adjust for scoring.

## Iteration 0 (2026-11-10): what v1-v3 established

- Full-strength moves (each player's raw projected or history reception mix) fail G1 in every cell;
  the best-fitting damping on the publishers' columns is about 0.3 (v1 L gate, v2, v3).
- The failure does not depend on the mix source (history vs projected: 1 of 60 vs 0 of 60) nor on
  the way back to value (chart curve at the anchor vs projections' pricing at the target: 0 of 40).
- Mapping back through a curve fitted at the anchor's waiver line (v3 `g_p`) wrecks levels (TEs
  floored to 0 at Standard); re-deriving the roster allocation per scoring swings RB/WR depth by
  about 12 players and moves levels away from the publishers (v2).

## Iteration 1 (2026-11-10): is there a reachable target in the publishers' within-position moves? (H-b)

Hypothesis: G1's within-position cells may have no reachable target because the publishers'
Standard-to-Full moves within a position are mostly noise or a light formula.
Script `tools/research/jeg1611/diag/publisher_moves.py`; numbers `out/diag/publisher_moves.{json,md}`.
Dev weeks 5-7 only; 95% bootstrap, 2000 resamples, seed 1611.

Result:
- CBS Sports' and USA Today's de-meaned moves agree with each other only at RB (Spearman 0.67
  [0.46, 0.82]); WR 0.06 [-0.26, 0.34] and TE 0.06 [-0.33, 0.43] are indistinguishable from 0,
  while their Full and Standard columns agree at 0.95 (RB, WR) and 0.86 (TE).
- Ceiling: predicting each publisher's move from the other's move (fitted slope) gains +0.002
  [-0.007, +0.010] (CBS) and -0.000 [-0.008, +0.006] (USA Today) over "unchanged" (0.994 / 0.991).
  A realized rest-of-season receptions oracle with the fitted slope gains nothing either (-0.002 to
  -0.004); at slope 1 it is harmful (-0.026 [-0.071, -0.008] CBS; -0.053 [-0.115, -0.027] USA Today).
- Damping the publishers apply to the full-strength history move (OLS slope): CBS RB 0.59, WR 0.31,
  TE -0.19; USA Today RB 0.75, WR 0.53, TE 0.34; pooled 0.36 / 0.60. Their moves follow past
  reception share (not future receptions: slope 0.06-0.16 on realized ROS receptions).
- Formula signs: both columns are integers; rounding alone explains 56% (RB), 21% (WR), 29% (TE) of
  CBS's within-position move variance. CBS WR and TE Full columns fit "additive bump plus
  multiplier" (WR: F = 1.77 + 1.065 S cuts the residual SD from 1.79 to 1.10). USA Today's median
  Full/Standard ratio is 1.066 at every position. CBS Half is exactly the midpoint 98-100% of the
  time; USA Today's within 0.5 for 98%.

Decision: **G1's within-position cells are not a reachable target** (headroom under 0.01 and the
two publishers do not agree with each other at WR and TE). This is a challenge to the gate, written
down with the evidence above, not a silent redefinition: the pre-registered pass rule (iteration 4)
will keep G1 within-position as a **no-harm** bound (v4 may not lose more than the ceiling's own
interval, -0.008) and judge within-position order on the actuals mechanism test and on G2's
direction and size (corr, closer). The levels and cross-position cells of G1 keep their "beat
unchanged" rule.

## Iteration 2 (2026-11-10): a cross-validated model of step 5/6 on actuals only (H-a)

Hypothesis: the raw history mix is an overconfident estimate of the player's future mix; a shrunk
estimate, chosen by cross-validation on actuals, gives the move's dispersion from data.
Code `tools/research/jeg1611/shrink/` (`model.py`, `run_shrink.py`), numbers `out/shrink/`,
tests `tests/test_jeg1611_shrink.py` (5 pass). nflverse weekly 2015-2025 (receptions = ppr - std
exactly), leave-one-season-out, decision weeks 5-10, truth = realized rest-of-season per game.

Result:
- Receptions per game: an empirical-Bayes estimate with recency weighting (half-life 8 games, 17
  for WR; prior-season discount 0.3-0.5) and a prior linear in the player's Standard points level
  (RB, WR; TE constant prior) beats raw history in 11 of 11 seasons per position (MSE RB 0.74 vs
  0.99, WR 1.15 vs 1.62, TE 0.78 vs 1.07).
- **The number that matters (D):** the slope of the true (realized) within-position move on the
  raw-history move, top 36/36/18 pool with a history points base: RB 0.73 [0.60, 0.85], WR 0.21
  [0.15, 0.27], TE 0.33 [0.26, 0.39]. The raw move overshoots the truth by 1.4x to 5x: the
  shortfall is not only receptions; when receptions fall short so do yards and Standard points.
- A **share model** that shrinks z = log(1 + rec/std) directly (RB k=4, WR k=25, TE k=20; weight
  about 0.4-0.46 at 17 games for WR/TE, 0.81 for RB) is calibrated: slope 0.99-1.03 on all eligible
  players, 1.2-1.36 on the top pool (slightly conservative), with Spearman against the oracle as
  good as or better than raw. Its move SD relative to raw history: RB 0.65, WR 0.25, TE 0.40,
  close to the damping the publishers apply (iteration 1: RB 0.59-0.75, WR 0.31-0.53, TE 0-0.34).
- Mechanism (E): subtracting receptions from a **trailing** Full rate still loses (0 of 11, the
  earlier result; one trailing reception predicts 0.32 / 0.79 / 0.66 future Standard points). But
  converting a **calibrated Full forecast** (which a chart is) to Standard by dividing by
  (1 + share_hat) beats not converting in **11 of 11 seasons** (+0.030 [+0.016, +0.043] within-
  position Spearman against realized ROS Standard points); subtracting rec_hat 8 of 11.
- Stability (F, 2024-2026 ICC): reception share 0.56 / 0.44 / 0.18 (RB / WR / TE) vs TD share
  0.25 / 0.12 / 0.14 and yards share 0.21 / 0.13 / 0.18: a player-specific term is warranted for
  receptions only. QB: 0.012 receptions per game, left alone.

Decision: v4's step 5/6 is the share model (`expected_reception_share`), fallback = its position
prior (labelled). The raw history mix (v3) and the rec/g model are kept as reported variants. The
publishers' damping is now explained by data, not fitted: a properly shrunk mix lands near it.

## Iteration 3 (2026-11-10): the exact unwind and the clean delta (H-c, H-d, H-e), design

Change from v3, before any run (design written here first):
- Steps 2-4 as v3 (Adjusted from the unmodified pipeline at the anchor; expected ppg `P_i(s0)` by
  the inverse of the projections' pricing in the same run).
- Replacement in points: `R_p(s0)` and `R_p(s)` = the projections' waiver line in ppg at each
  scoring **with the roster allocation held at the anchor's** (the pipeline's `allocation`
  argument), so the scoring delta never moves the allocation.
- Step 5/6: `P_i(s) = P_i(s0) x (1 + r_s sh_i) / (1 + r_s0 sh_i)`, `sh_i` the shrunk share.
- Step 7, chart units: points-space VORP `V_i = P_i - R_p` at each scoring and **one slope per
  position** `b_p` (OLS of the native `x` on `V(s0)` over the invertible players; value is about
  linear in VORP, v2) in the delta form `x_i(s) = max(0, x_i + b_p (V_i(s) - V_i(s0)))`. Identity
  at `s = s0` is exact. No piecewise `g_p`, no anchor waiver line. Variant: multiplicative
  `x_i V_i(s)/V_i(s0)`.
- Below waiver / no inverse: keep `x_i` (primary, counted); variant `tail_scaled` moves them by the
  position's median invertible ratio. QB untouched.
- Target run: the unmodified pipeline at `s` (allocation re-derived, Jeremy's literal step 7) as
  primary; variant with the allocation fixed at Half's.
