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

## Iteration 3a (2026-11-10): implementation readings for v4, written with the code and tests

Code `tools/research/jeg1611/v4.py` (chain) and `run_v4.py` (runner, `--weeks`, default 5,6,7; other
week sets write to `out/v4/weeks_<list>/`), tests `tests/test_jeg1611_v4.py` (13 pass, run before the
gates, weeks 5-7 only). Where the design did not pin the code down, the most literal reading:

1. **"Allocation fixed" does not work as written.** The pipeline's default run is a blend of 8-9
   seat vertices (`allocation_mix`, heaviest weight about 0.4), and `out["allocation"]` is only the
   heaviest vertex, so `run_pipeline(allocation=out["allocation"])` does **not** reproduce the anchor
   run. Read as: hold the anchor's whole allocation mix (vertices and weights), run each vertex with
   `allocation=a` and blend with `value_reference._blend_runs`, which is what `run_pipeline` does once
   it has built its mix. Tested: this reproduces today's run exactly at every scoring and week
   (`ddf`, every `adjusted`, every `waiver_value`), and the FantasyCalc Half-anchor run.
2. `R_p(s)` = mean over the projections in `I` (ESPN, CBS ROS, Razzball; hidden ones included) of the
   blended `waiver_value` at `p` (weight-average over the vertices, as `blend_values`). The run at
   `s` uses today's inputs at `s`; only the projections' waiver lines are read, and with the mix held
   they do not depend on the chart inputs.
3. `b_p` fallback (under 4 invertible players) = `x_top / V_top(s0)`, top = highest native among the
   invertible players. Never used in weeks 5-7 (84 of 84 position-chart-weeks are OLS, R^2 >= 0.980).
4. `fallback_prior` = the share model returned `w = 0` (no rows before `w`, or recency-weighted
   Standard ppg under `min_std_h` = 1.0). QB: `sh = 0`, not counted. With `R_QB` identical at every
   scoring (QB projections do not depend on the reception weight) QBs are untouched exactly (tested).
5. Multiplicative variant: `x (max(0, V(s)) / V(s0))` for `V(s0) > 0`, else `x` kept (parenthesised for
   bit-exact identity). `tail_scaled`: below_waiver and no_inverse players move by the median of
   `x(s)/x` of the delta form over the invertible players at the position.
6. Raw-mix variant = v3's history mix with its 6-game minimum and `q_p` fallback; rec/g variant
   `P(s) = P(s0) + (r_s - r_s0) rec_hat` (unclamped; QB `rec_hat = 0`). Assumed-mix variant: every
   RB/WR/TE at `expm1` of the ratio model's position mean; it cannot reorder within a position (its
   G2 move statistics are exactly 0 by construction), so it speaks to levels only.
7. Target-run variant "allocation fixed to the Half run's" = today's Half run's mix (with the same
   dropped sources when dropping).
8. With 3 weeks, the G2 (c) and G3 levels rule "4 of 5 weeks" is read as at least 80% of the weeks,
   `ceil(0.8 x 3) = 3` of 3. G1 is reported as weeks won of 3 per cell, no verdict here.
9. G2: v4 and each variant are methods of `response_test`; placebo for `v4` against every reference
   and for the variants against the mean reference; leave-one-out drops `cbsros` and `cbs` from the
   anchor, fixed and target runs. Extreme-pair groups as v3 (raw history share) for comparability,
   with the shrunk share reported per player.
10. Weeks 8-9: the runner never loads their week inputs unless passed `--weeks`; the world loader
    reads the snapshot file whole (as v3), nothing of weeks 8-9 is run or printed.

Result on weeks 5-7 (`out/v4/summary.md`): G1 primary wins 4 of 36 week-cells (xpos 1, within 3, levels
0); rebuilt moves still overshoot the publishers' (CBS Standard to Full median ratio RB 1.29 / WR 1.47 /
TE 1.38 against published 1.06 / 1.18 / 1.28). G2 FAIL for v4 and every variant except assumed-mix
(NOT SHOWN, no move); `closer` -0.001 [-0.001, -0.001] (FantasyCalc) vs v3 -0.004. G3 worse in the
primary and every robustness run. Decision is the lead's.

## Iteration 4 (2026-11-10): scale-free levels, per-position views, the chart's own zero (H-d)

Hypothesis: the publishers re-normalise their chart currency per column (their own VORP slopes
differ between Standard and Full: CBS WR b(Full)/b(Std) 0.65-0.68, TE 0.72-0.82, RB 1.14-1.25; USA
Today WR 0.62, TE 0.63-0.68, RB 1.02-1.07), so native-unit level measures mix that convention with
the points move; DDF is scale-invariant per source. And v4's move may be too large because the
zero is the projections' waiver line rather than the chart's own zero.

Change (added to `run_v4.py` / `v4.py`, nothing already reported changed; weeks 5-7):
- G1 `levels_norm` (MALE after scaling rebuilt and target to the same total over the scored set) and
  `levels_norm_pos` (mean absolute log error of the RB/WR/TE shares of the scored set's total, QB in
  the total); per-position share move `log(share Full / share Standard)`; per-position within diffs.
- G2 per-position `corr` / `closer` (mean reference, same bootstrap rows) for v4, v4_chartzero, v2;
  level-move table: each method's log WR/RB and TE/RB move against CBS's, USA Today's and the mean
  move, weeks closer than unchanged (move 0).
- Variant `v4_chartzero`: from `x = a_p + b_p V(s0)`, zero `Z_p(s0) = R_p(s0) - a_p / b_p`, fallback to
  `R_p(s0)` when `a_p >= 0` (or `b_p` missing / not positive; counted); `Z_p(s) = Z_p(s0) (1 + r_s sh_p)/
  (1 + r_s0 sh_p)` with `sh_p = expm1` of the share model's position mean (QB 0); same additive delta.
  Identity at `s = s0` tested (14 tests pass). G1, G2, G3 as the other variants.

Result (`out/v4/summary.md`, "Iteration 4 additions"):
- G1 `levels_norm`: v4 and v4_chartzero win 0 of 3 in all four cells (CBS 0.098-0.120 vs unchanged
  0.079-0.084; USA Today 0.106-0.124 vs 0.046-0.054). `levels_norm_pos`: v4 wins CBS S->F 3, CBS F->S
  1, USA Today 0 / 0; v4_chartzero 2 / 0 / 0 / 0; v4_mult 3 / 3 / 0 / 0. Share moves: CBS published
  RB / WR / TE about -0.04 / +0.04 / +0.11, v4 -0.06 / +0.10 / +0.06 (S->F) and -0.08 / +0.14 / +0.05
  (F->S); USA Today published about 0 at every position, v4 RB -0.04 to -0.07, WR +0.07 to +0.13.
- Within diffs: TE carries the loss at CBS (-0.012 to -0.044 in 5 of 6 week-cells); RB -0.000 to
  -0.011; WR within +/-0.004. v4_chartzero is identical to v4 within position (a per-position constant
  shift of the zero cannot reorder a position) and in G2's per-position statistics.
- G2 per position (FantasyCalc / FantasyPros): v4 corr RB +0.63 / +0.44, WR +0.38 / +0.45, TE +0.31 /
  +0.22; `closer` RB -0.001 / -0.001, WR -0.000 / -0.001, TE -0.003 / -0.004 (v2: WR -0.002 / -0.004, TE
  -0.001 / -0.004). The remaining `closer` harm is mostly TE.
- Level moves (mean of weeks): references WR/RB CBS +0.067, USA Today -0.007, mean +0.030; TE/RB
  +0.163 / -0.011 / +0.076. v4 FantasyCalc +0.206 / +0.126, FantasyPros +0.101 / +0.136 (v2 +0.43 /
  +0.41); v4_chartzero +0.227 / +0.255 and +0.112 / +0.217. Closer than unchanged: TE/RB vs CBS 3 of 3
  for every v4 variant and both subjects; WR/RB vs CBS 3 of 3 for FantasyPros v4 (0 for FantasyCalc);
  never vs USA Today.
- v4_chartzero: chart zero falls back in most TE and QB cells and in every USA Today Full cell; where
  it holds it sits above R_p (RB: CBS 3.83 vs 1.40 at Standard, FantasyCalc 5.85 vs 4.63). G1
  original measures 6 of 36 (v4 4); G2 FAIL, levels move away; G3 worse.

## Iteration 4b (2026-11-10): lead's reading of iteration 4 and the diagnostics follow-up

Follow-up diagnostics (`tools/research/jeg1611/diag/publisher_moves_followup.py`, appended to
`out/diag/publisher_moves.{json,md}`, dev weeks 5-7):
- G2 `closer` ceiling: with CBS Sports as the reference, **USA Today's own move** scores closer
  -0.0007 [-0.0011, -0.0003] (corr 0.27, slope 0.34); reversed -0.0003 [-0.0006, +0.0001]. The
  most `closer` can ever be is 0.0007-0.0020 and 34-56% of players have a percentile move of
  exactly 0. Against the mean reference a publisher clears 0 only because it is half the reference.
- Currency per column: the publishers' chart-value slope on projected points at Full is 0.88 /
  0.73 / 0.69 (CBS, RB / WR / TE) and 0.88 / 0.70 / 0.65 (USA Today) of its Standard value; their
  top-12 value ratio Full/Standard is 1.06 / 1.12 / 1.23 (CBS) and 1.06 / 1.07 / 1.07 (USA Today)
  against a projected-points ratio of 1.20 / 1.55 / 1.65 for the same players.

Reading of iteration 4 (v4 at weeks 5-7):
- Within position v4 is at the ceiling for RB and WR (diffs 0 to -0.011 and within +/-0.004) and
  loses at TE (CBS -0.012 to -0.044). The publishers do not differentiate tight ends by reception
  share (CBS slope -0.19 on the history move); the actuals keep a weak TE term (share ICC 0.18;
  cross-validated k = 20). Left as is: removing it would be fitting to the publishers.
- Size in percentile units is now right (slope of v4's move on the mean reference's 0.86 FC, 0.63
  FP; v3 moved 2-10x too far), direction is right (corr 0.50 / 0.36, placebo p95 0.13).
- Cross-position level moves: v4 WR/RB +0.10 to +0.21, TE/RB +0.13; CBS +0.07 / +0.16, USA Today
  -0.01 / -0.01; the projections' own points imply about +0.26 WR/RB before replacement. v4 sits
  between the publishers and the points; the two publishers do not agree with each other.
- Native-unit level error (G1 levels, median rebuilt/published ratio) is the publishers' currency
  convention and is dropped as a verdict measure (kept as reported).
- `v4_chartzero` (H-d) cannot reorder within position and mostly falls back; `v4_mult` is best on
  position shares (CBS 3 of 3 both directions) but not on anything else. Primary stays additive.

Decision: no further implementation iteration on dev; write the pass rule (`pass-rule.md`,
with the expected verdict stated in advance), run the adversarial reviews, then the holdout.

## Iteration 6 (2026-11-10): test-retest of the publishers' moves (review objection B)

Reviewer B asked whether each publisher's within-position move is noise or a standard the other
does not share. `publisher_moves_followup.py` item 8 (commit 1e04aab9c), weeks 5->6 and 6->7, 151
player pairs: CBS agrees with its own move next week at 0.82 [0.70, 0.91] (RB 0.89, WR 0.83, TE
0.49), USA Today at 0.84 [0.76, 0.90]; the two agree with each other in the same week at 0.29
[0.08, 0.49] (RB 0.75, WR -0.05, TE 0.00). Dropping players whose columns were carried over
unchanged leaves self-agreement at 0.72 / 0.81. Reading: **each publisher applies a stable
within-position scoring response of its own; the two responses agree only at RB.** So the
within-position target is not noise; it is two different formulas. A method can match at most one
of them at WR and TE, and the mean reference is a blend of the two. This replaces "mostly noise"
in iteration 1's decision; the no-harm form of T3 stands.

Corrections after round 1: "size is now right" (4b) is withdrawn (SD ratio about 1.7); "the
publishers' damping is explained by data" (iteration 2) compared an SD ratio with an OLS slope and
is withdrawn; `closer` is passable in principle but undetectable here.
