# JEG-1605 / JEG-1597: chart-to-chart scoring-response test, results (run 2026-11-10)

Spec: `response-preregistration.md` (committed ba3281e32 before any code; implementation readings
logged in its change log and committed with the runner before the first run). Code:
`tools/research/jeg1605/response_test.py`. Numbers: `tools/research/jeg1605/out/response_test.json`.
Tests: `tests/test_jeg1605_response.py` (5 pass). Checks before scoring: the v1 rerun reproduces
`rescaled_natives.csv` (17,112 rows, max diff 5e-5); shuffling CBS Sports' and USA Today's values
leaves every adjusted list identical (the adjusters use the subject's own list plus projections,
games and allocation only).

Weeks 5-9, RB/WR/TE. Reference = mean of CBS Sports and USA Today (primary). Brackets = 95%
paired player bootstrap (2,000 resamples; 100-108 players per subject). FantasyCalc anchored Full,
FantasyPros Half. At FantasyCalc Full every adjuster returns the base list (tie by construction).

## Verdicts

| Adjuster | Ranking verdict (a, b, d) | Levels verdict (c) |
| --- | --- | --- |
| v1 (position_scaled, lambda 1) | **FAIL** | moves away (5 of 5 weeks, both subjects) |
| v2 (round trip) | **FAIL** | moves away (5 of 5 weeks, both subjects) |

FAIL because the (b) "closer" interval is below 0 for both subjects and, for FantasyPros, the (a)
Standard interval is below 0. The prediction written before the run held.

## (a) Within-position rank agreement with the reference, adjusted minus unadjusted

| Subject, scoring | v1 | v2 | v1 lambda 0.5 |
| --- | --- | --- | --- |
| FantasyCalc, Standard | +0.007 [-0.012, +0.043], 4 of 5 wk | +0.012 [-0.003, +0.046], 4 of 5 | +0.013 [-0.001, +0.045] |
| FantasyPros, Standard | **-0.011 [-0.029, -0.003]**, 0 of 5 | **-0.016 [-0.037, -0.005]**, 0 of 5 | -0.007 [-0.024, +0.000] |
| FantasyPros, Full | +0.001 [-0.040, +0.016] | -0.007 [-0.048, +0.005] | +0.002 [-0.003, +0.009] |

Single references agree in sign except FantasyCalc v1 against USA Today (-0.001). FantasyCalc Half
anchor: Standard +0.010 (v1) / +0.012 [+0.000, +0.043] (v2), but Full turns negative with the
interval below 0 (v1 -0.007 [-0.040, -0.001]); no sign flip at Standard, so no hinge by the rule.

## (b) Response: does the Standard-to-Full move track the reference's own move?

| Subject | Method | corr | slope | closer (vs not moving) | extremes: corr / sign agreement |
| --- | --- | --- | --- | --- | --- |
| FantasyCalc | v1 | **+0.43 [+0.30, +0.54]** | 0.94 | **-0.0023 [-0.0029, -0.0017]** | +0.54 / 60% |
| FantasyCalc | v2 | +0.44 [+0.31, +0.56] | 0.79 | -0.0013 [-0.0017, -0.0009] | +0.56 / 60% |
| FantasyCalc | v1 lambda 0.5 | +0.41 | 0.56 | -0.0006 [-0.0009, -0.0003] | +0.56 / 52% |
| FantasyPros | v1 | +0.41 [+0.29, +0.51] | 0.83 | -0.0020 [-0.0027, -0.0014] | +0.45 / 55% |
| FantasyPros | v2 | +0.37 [+0.27, +0.48] | 0.94 | -0.0035 [-0.0048, -0.0025] | +0.42 / 59% |
| FantasyPros | v1 lambda 0.5 | +0.33 | 0.41 | -0.0006 [-0.0009, -0.0003] | +0.38 / 39% |

The direction is right and clearly not chance (placebo corr 95th percentile about 0.13), but each
adjusted list's moves are about twice as spread out as the reference's (slope / corr about 2), so
standing still is closer to the reference than moving. Descriptive only, not tested: the scale that
would minimise the move error is corr^2 / slope, about 0.15-0.25, in line with the L gate's fitted
damping of 0.3. The reference move is small: SD 0.024-0.039 in percentile (about one place in 36),
and 22-56% of reference moves are exactly 0. Value-share moves: every adjuster is further from the
reference than today's list (v1 FantasyCalc -0.022 [-0.031, -0.015]); v2 sets some players to 0 at
the non-anchor scoring (VORP below 0), which blows up its log-share error.

## (c) Cross-position levels (Standard-to-Full change in log ratio)

| Week 9 | WR/RB move | TE/RB move |
| --- | --- | --- |
| Reference mean (CBS / USA Today) | +0.04 (+0.10 / -0.02) | +0.08 (+0.17 / -0.01) |
| FantasyCalc today (its per-position switch) | +0.02 | +0.03 |
| FantasyCalc v1 / v2 | +0.21 / +0.78 | +0.27 / +0.68 |
| FantasyPros v1 / v2 | +0.24 / +0.70 | +0.28 / +0.86 |

Level error against the reference is higher than today's in 5 of 5 weeks for every adjuster and
both subjects, except FantasyCalc lambda 0.5 Half-anchor (lower in 5 of 5). The two references
disagree on direction (CBS Sports moves WR and TE up in Full, USA Today slightly down).
FantasyCalc's own published switch has the move closest to their mean; on level error the unmoved base list is lowest (mean error 0.56 vs today 0.61, v1 1.05, v2 1.58).

## (d) Placebo and leave-one-out

- Placebo (adjustment shuffled within position, 1,000 times): a random adjustment of the same
  size gives (a) Standard -0.016 (FantasyCalc, v1) and -0.013 (FantasyPros), closer -0.004.
  FantasyCalc v1 and v2 beat the placebo 95th percentile on both; **FantasyPros does not on (a)**
  (v1 -0.011 vs placebo p95 -0.004): its Standard reordering is no better than a random one.
- Leave-one-out (no CBS rest-of-season lines, no CBS `gp`, allocation without CBS): every sign on
  the mean reference holds (FantasyCalc v1 (a) +0.011, corr +0.34, closer -0.0027; FantasyPros v2
  (a) -0.019 [-0.048, -0.004]). Against CBS Sports alone FantasyCalc v1 (a) turns -0.009.

## Games variant (ESPN non-zero weeks, weeks 7-9, descriptive)

- G1 (ESPN ahead of the miss-rate fallback): changes 2-3 priced players a week (CBS `gp` covers
  all but 3-4) and no scored player; every statistic changes by exactly 0.
- G2 (ESPN replacing CBS `gp`): 120-134 of about 163 priced FantasyCalc players change games
  (mean |change| 1.1-1.3, a few by 9-10 games); 10-15 by more than one game, 1-3 inside the scored
  sets. Effect on agreement: (a) within +/-0.002, corr within +/-0.015, closer +0.0001 to +0.0008
  (v2 FantasyPros [+0.0004, +0.0010]), far short of turning closer positive. Games barely matter
  to within-position order: they enter only through the fit and the replacement level.

## What changes against the M1/M2 verdicts, and what does not

Changes:
- v1 and v2 move from "not shown" (M1/M2 on realized points) to **FAIL** on the test Jeremy asked
  for: adjusted FantasyCalc and FantasyPros do not rank more like the scoring-aware charts.
- FantasyPros is now evidence against the adjustment: at Standard it lowers agreement with both
  references, and no better than a random reshuffle.
- The direction finding is now measured against charts, not projections: the adjusted moves
  correlate +0.4 with the references' moves (M1's FP check said 97% but was near-mechanical).

Does not change:
- Close as not shown/failed (option A); no published number changes.
- The size problem found by the L gate (best damping about 0.3) appears again on different charts.
- Levels: the v2 replacement re-derivation moves WR/RB 15-25 times as much as the references' mean.
- The anchor for FantasyCalc and FantasyPros stays unidentified; the Half anchor does not flip any
  Standard sign here.

## Caveats

- CBS Sports and USA Today barely reorder within a position (0.99 between their own columns); the
  reference move is about one place in 36 and often exactly 0 (CBS values step by 0.5).
- CBS Sports' Half column is the midpoint of Standard and Full, possibly formula-derived; the
  references may encode a formula, not independent judgment. They also disagree on levels.
- Weeks 5-9 of 2026 only, five overlapping snapshots; the games variant covers weeks 7-9 only
  (ESPN future weeks were not stored before content week 7).
