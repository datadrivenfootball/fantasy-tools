# JEG-1611 v4: pre-registered pass rule for the holdout (written 2026-11-10, before weeks 8-9 were loaded)

Holdout = 2026 snapshot weeks 8 and 9 (never loaded by any development script; see the iteration
log). Week 10 (charts of Tue 2026-11-10) is re-run with the same runner and the same rule when it
arrives. Nothing in this file changes after the first holdout number is printed; corrections are
appended, dated. Development numbers (weeks 5-7) are quoted so that a reader can see the rule was
not written to fit the holdout.

## What v4 is (unchanged for the holdout)

Jeremy's seven steps, implemented as in the iteration log (iterations 3, 3a, 4): Adjusted value
from the unmodified pipeline at the anchor; expected points by the inverse of the projections'
pricing; the **share model** (`expected_reception_share`, empirical Bayes on log(1 + rec/std),
strength chosen by leave-one-season-out cross-validation on 2015-2025 actuals, never on the
charts) for how a player earns points; replacement in points at each scoring with the roster
allocation held at the anchor's; one chart-points-per-VORP-point slope per position; additive
delta; the unmodified pipeline at the target scoring; DDF Value = the mean of the charts' Adjusted
values. FantasyCalc anchored at Full (Half as sensitivity), FantasyPros at Half, CBS Sports and
USA Today as published. Code `tools/research/jeg1611/v4.py`, runner `run_v4.py --weeks 8 9`.

## Challenges to the earlier gates, with the evidence (iterations 1 and 4)

These were found on dev weeks and on the publishers' own columns; they are stated here so the rule
below is a written redefinition, not a silent one.

1. **G1 within-position "beat unchanged"** has no reachable target: CBS Sports' and USA Today's
   own Standard-to-Full moves agree with each other only at RB (0.67); WR 0.06, TE 0.06; the best
   predictor of one publisher's move (the other publisher's move) gains +0.002 [-0.007, +0.010]
   over unchanged. Replaced by a **no-harm bound**.
2. **G1 levels in native units** mix the publishers' per-column currency with the points move:
   their chart-value slope on projected points at Full is 0.65-0.88 of its Standard value
   (CBS RB / WR / TE 0.88 / 0.73 / 0.69; USA Today 0.88 / 0.70 / 0.65), and DDF is scale-invariant
   per source. Replaced by **scale-free level moves** (position shares; WR/RB and TE/RB).
3. **G2 / G3 "closer"** (percentile-move size against a reference) cannot be passed by any method
   that moves anyone: even the other publisher's own move scores closer -0.0007 [-0.0011, -0.0003]
   against CBS Sports; against the mean reference a publisher clears 0 only because it is half of
   the reference. Reported, not a verdict; size is judged by the **slope** instead.
4. **Cross-position levels**: the two references disagree with each other (Standard-to-Full
   WR/RB level move CBS +0.067, USA Today -0.007; TE/RB +0.163 / -0.011; the projections' own
   points imply far more). No single level target exists; the rule asks whether v4 lands inside the
   span of the two publishers.

## Tier 1: hard tests (each PASS / FAIL on the holdout; all must pass for "v4 passes")

| # | Test | Rule | Dev result (weeks 5-7) |
| --- | --- | --- | --- |
| T1 | Mechanism on actuals (no charts) | Converting a calibrated Full forecast to Standard by the share model beats not converting in >= 9 of 11 seasons, interval above 0 (`out/shrink/results.json`, E) | PASS: 11 of 11, +0.030 [+0.016, +0.043] (fixed; not re-run) |
| T2 | Exactness | Identity at `s = s0` exact on every holdout chart-week; current DDF reproduced exactly; fixed-allocation anchor reproduced (tests) | PASS (14 tests, 468 combinations) |
| T3 | Within-position no harm (G1) | In each of the 4 cells, the mean over holdout weeks of (v4 within - unchanged within) >= -0.008 (the ceiling interval's lower bound, iteration 1) | CBS S->F -0.004, **CBS F->S -0.010 FAIL** (TE), USA Today S->F -0.001, F->S +0.001 |
| T4 | Direction (G2) | Against the mean reference, both subjects: corr interval above 0 and the point estimate above the placebo's 95th percentile | PASS: FC +0.50 [+0.31, +0.64], FP +0.36 [+0.19, +0.52]; placebo p95 0.12-0.14 |
| T5 | Size (G2) | Against the mean reference, both subjects: slope of the subject's percentile move on the reference's move has its interval overlapping [0.5, 1.5] and point estimate in [0.4, 2.0] | PASS: FC 0.86 [0.51, 1.17], FP 0.63 [0.32, 0.95] |
| T6 | Agreement no harm (G2 a, G3 a) | (a) Standard, adjusted minus unadjusted, interval not entirely below -0.008 for both subjects; G3 (a) Standard, v4 DDF minus current, interval not entirely below -0.008 for both references | FC +0.004 [-0.024, +0.030] pass; **FP -0.021 [-0.074, -0.002] borderline** (interval reaches below -0.008; rule as written: pass only if the upper bound is above -0.008: pass) |
| T7 | Cross-position levels, scale-free | v4's Standard-to-Full log WR/RB and TE/RB level moves (both subjects) lie within [min, max] of CBS Sports' and USA Today's own moves, widened by 0.05 each side | TE/RB: FC +0.126, FP +0.136 within [-0.06, +0.21] pass; **WR/RB: FC +0.206 FAIL, FP +0.101 within [-0.057, +0.117] pass** |

**Prediction written now:** on the holdout v4 passes T1, T2, T4, T5, T6 and fails T3 (CBS Full to
Standard, tight ends) and T7 (FantasyCalc WR/RB). So the pre-stated expected verdict is **"v4 does
not pass"**, with the failures located at TE within-position and WR-vs-RB level size. If the
holdout instead passes everything, that is a surprise and we would say so and wait for week 10.

## Tier 2: reported, no verdict (the two references disagree or the measure has no reachable pass)

G1 xpos and native-unit levels; G1 levels_norm; G2 and G3 closer; G2 levels "moves away" verdict
(err-based, conflates the anchor with the move); G3 closer and corr differences; secondary realized
points; extreme pairs; coverage. Robustness as pre-registered for v3: FantasyCalc at Half, dropped,
assumed mix (position prior for every player), allocation fixed at Half's, multiplicative and
chart-zero variants. A sign flip of any Tier 1 point estimate under a robustness run is stated as
"hinges on".

## What would change the answer

- A reference that re-levels positions the way points imply (neither publisher does) would turn T7
  into a pass for the same v4.
- Dropping the player-specific reception term at TE (its 2024-2026 share ICC is 0.18 against 0.56
  RB and 0.44 WR, but the cross-validated model still keeps a weak term) would likely clear T3; it
  is not done here because the choice would be made to fit the publishers, not the actuals.
- The anchors: FantasyCalc at Half (sensitivity) and FantasyPros at Half are assumptions.

## Amendments after review round 1 (2026-11-10, commit cf7c8592f was the first registration; written before any week 8-9 or week 10 number exists)

A fresh Opus reviewer (read-only) found that the first rule was weaker than it looked. Accepted
points and the amended rule:

1. **Weeks 8-9 are not a clean holdout.** v3's results (`docs/research/jeg1610/results.md`) were
   computed on weeks 5-9 and the lead read them. No jeg1611 development script loaded 8-9, but the
   lead's priors did. Weeks 8-9 are therefore a **confirmation run**; the **deciding holdout is week
   10 onward**, re-run with the same runner and this rule, no changes in between.
2. **T4, T5, T6 as first written do not separate v4 from v1/v2** (which also pass them on dev) and T1,
   T2 cannot fail. The discriminating content is T3, T7 and the new T5 and T8 below.
3. **T3 (within-position no harm), restated.** Statistic: per cell, the mean over weeks of the
   RB/WR/TE-averaged (v4 within - unchanged within), paired player bootstrap interval (2000, seed
   16052). Pass: point estimate >= -0.003 (half the available headroom, 1 - 0.994) **and** interval
   not entirely below 0. Per-position values are reported and a TE loss below -0.01 is named even
   when the cell passes. Dev values recomputed by the reviewer from `g1.json`: CBS S->F -0.0056,
   CBS F->S -0.0119, USA Today S->F +0.0004, F->S -0.0001 (the first registration quoted -0.004 /
   -0.010 / -0.001 / +0.001; the reviewer's are the rule's statistic). **Expected: CBS fails both
   directions, USA Today passes both.**
4. **T5 (size), restated.** The slope of method on reference mixes direction with size
   (slope = corr x sd_m / sd_r). Statistic: sd(method percentile move) / sd(reference percentile
   move) against the mean reference, per subject, with interval. Pass: point estimate in [0.5, 1.5]
   (the publishers' own ratios against the mean reference are 1.13 and 1.38). Implied dev value for
   v4: 0.86 / 0.50 = 1.72 (FantasyCalc), 0.63 / 0.36 = 1.74 (FantasyPros). **Expected: FAIL;** the
   first registration's "size is now right" was wrong and is withdrawn (iteration log 4b).
5. **T6, restated.** Add: point estimate >= -0.008 for every subject and reference. Dev FantasyPros
   -0.021: **expected FAIL.**
6. **T7, restated.** The 0.05 widening had no source. Widening = the pooled week-to-week SD of the
   publishers' own log WR/RB and TE/RB level moves (from `levels_by_week`, computed on dev weeks
   before the run). `v4_assumed` (no player mix) also passes T7, so T7 tests the level machinery
   only, not step 5/6, and is labelled so.
7. **T8 (new): realized points, the truth the charts can be scored against.** Within-position
   Spearman (RB/WR/TE averaged) against realized rest-of-season points at the target scoring, paired
   bootstrap. Pass requires, for the Full-to-Standard direction (the one with the largest move):
   (a) CBS Sports' and USA Today's Full column rebuilt to Standard by v4 scores at least as well as
   the unchanged Full column against realized Standard points (interval of the difference not
   entirely below 0, point estimate >= 0) and (b) FantasyCalc and FantasyPros v4 Standard lists
   at least as well as their base lists. Reported beside it: the publishers' own Standard column
   against the same truth. This is a mechanism check on the charts themselves, not a trade-value
   benchmark (Jeremy, 2026-11-10: realized points is not the main test), and it has only weeks
   w..9 of 2026 as truth; week 10 adds one more.
8. **Vocabulary corrected.** `closer` is passable in principle (any positively correlated move
   scaled far enough down) but undetectable here (best achievable about corr^2 x E[r^2], of order
   1e-4); "cannot be passed" in the challenges section is replaced by "cannot be detected".
   The publishers' smaller Full slope differs by position (0.88 / 0.73 / 0.69) and the two
   publishers agree on it within 0.04, so it is a cross-position value statement they share, not
   only a currency convention; v4 holds `b_p` fixed across scorings, which both publishers
   contradict. A test of whether DDF's own pricing does the same (projections at Standard vs Full)
   is added as a reported item.
9. **Overshoot count (reported).** The number of cells where both publishers lie on the same side
   and v4 lies beyond both. If that is most cells, the honest summary is "v4 overshoots", not "the
   publishers share no standard".

**Amended expected verdict, written now:** on weeks 8-9 and on week 10, v4 is expected to pass
T1, T2, T4, T7 (both subjects, TE/RB; FantasyCalc WR/RB may still fail) and to **fail T3 (CBS),
T5 and T6 (FantasyPros)**; T8 is the open question, no prediction. So the expected overall verdict
remains **"v4 does not pass"**. If T8 passes while T3/T5 fail, the reading is "v4 tracks realized
points at least as well as the unchanged chart but moves further than the publishers do".

## Amendments after review round 1b, Codex gpt-6-astra (2026-11-10, still before any week 8-9 or week 10 number)

Codex (read-only, session 01a1c383) concurred with the Opus reviewer on weeks 8-9, the T5 slope,
T6's reversed burden and the T7 widening, and added two points. Accepted:

10. **Burden of proof for no harm (T3, T6).** A no-harm test passes only when the **lower** bound of
    the paired bootstrap interval of (v4 - unchanged) is >= 0 (epsilon = 0; no independently
    justified tolerance exists). Interval crossing 0 = **inconclusive**; interval entirely below 0
    = **harm**. Point estimates and per-position values are reported. The earlier -0.008 / -0.003
    margins are withdrawn. Under this rule the dev values give: T3 CBS both directions harm or
    inconclusive, USA Today inconclusive; T6 FantasyPros harm. **Expected on weeks 8-9 and week 10:
    T3 and T6 do not pass.**
11. **T5 (size).** Kept as the SD ratio in [0.5, 1.5] (the one statistic that isolates size); next to
    it `closer` is reported normalised by E[r^2] with its lower bound, as Codex asked, labelled
    "undetectable at this sample" where the best achievable value is below the interval width.
12. **T7.** Widening set to 0; the publisher envelope is descriptive. T7 is no longer a Tier 1 test:
    it is reported, with the overshoot count (item 9).
13. **Share-model cross-validation.** Leakage paths named by Codex (history accumulated before the
    season split; the cross-fitted share used as a feature in E; model form chosen on all folds)
    are being re-run as a strict rolling-origin (forward-only) evaluation. **T1 is replaced by the
    rolling-origin result**: pass if the forward-only share-model conversion (E viii vs vi) beats
    not converting in >= 6 of the 8 forward seasons with interval above 0. If the rolling-origin
    numbers differ materially from the pooled CV, the pooled numbers are withdrawn from every
    summary.
14. **Chart-implied points are not shown to be a calibrated forecast.** Added as a reported
    calibration check (realized rest-of-season ppg on `P_i(s0)` per chart and position, slope,
    intercept, R^2, against the projections' own ppg). T8 remains the downstream test of the whole
    conversion against realized points.
15. **Wording.** The defensible conclusion if T8 passes and T3/T5/T6 fail is: "v4 implements the
    scoring transformation exactly; its conversion tracks realized points at least as well as the
    unchanged chart on this sample; it moves further than CBS Sports and USA Today, whose measured
    scoring responses disagree with each other on these samples." Not "the logic works" and not
    "the publishers share no standard".

**Tier 1 after both reviews:** T1 (rolling-origin mechanism), T2 (exactness), T3 (within no harm,
lower bound >= 0, four cells), T4 (direction), T5 (SD ratio), T6 (agreement no harm, lower bound
>= 0), T8 (realized points, lower bound of the difference >= 0 ... stated as: point estimate >= 0
and interval not entirely below 0, since T8 asks "at least as good" of a 3-week truth). Expected
verdict: **does not pass** (T3, T5, T6). Tier 2: everything else.
