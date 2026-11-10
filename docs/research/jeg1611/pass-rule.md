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
