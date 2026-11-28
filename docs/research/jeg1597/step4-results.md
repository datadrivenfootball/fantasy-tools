# JEG-1601 step 4a: pre-registered test results (run 2026-11-09)

Spec: `step4-preregistration.md` (implementation choices logged in its "Changes after this
commit", all fixed before the first run). Code: `tools/research/jeg1597/step4_tests.py`.
Numbers: `tools/research/jeg1597/out/step4_results.json`. Unit tests: `tests/test_jeg1597_step4.py`.

**Every result here is small-sample.** Realized points cover 2026 weeks 5-8 only: four
overlapping windows of 4, 3, 2 and 1 weeks. 108 players per snapshot week (36 RB, 36 WR, 18 TE,
18 QB), 130 distinct players in the bootstrap (2,000 resamples, seed 1597, paired over players).
M1 = within-position Spearman vs realized points (RB / WR / TE averaged; QB separate).
M2 = share of concordant pairs vs realized points above replacement. Differences are
"first minus second"; brackets are 95% intervals.

## Summary

| ID | Verdict | Key number |
| --- | --- | --- |
| H1 `FC_corr` > `FC_raw` | **NOT SHOWN** | Standard M1 +0.026 [-0.004, 0.058], M2 +0.002 [-0.006, 0.009] |
| H2 `DDF_new` > `DDF_cur` | **NOT SHOWN** (also not robust) | Standard M1 +0.010 [-0.003, 0.025]; Full M1 -0.001 [-0.010, 0.004] |
| H3 attribution | `DDF_new` closer than `FC_corr` everywhere | Standard M2 -0.010 [-0.021, -0.000] |
| S steelman | **NOT SHOWN** (primary); rejected within position at Standard | whole set +0.087 [-0.049, 0.222] |
| FP first principles | **PASS** | 97.3% (FantasyCalc), 97.0% (FantasyPros) of swaps right way |
| L labelled check | **FAIL** | rescaling beat "unchanged" in 1 of 5 weeks, both charts; fitted lambda 0.30 |
| M mechanism 2015-2025 | **FAIL** | M1 -0.071 [-0.102, -0.038]; 0 of 11 seasons positive |

**The primary claim (scoring-aware DDF is stronger) is not supported.** H2 needs four intervals
above zero; none is. At Full PPR the point estimates are negative. H1 alone would only support
"the FantasyCalc correction helps", and it is not shown either.

## H1: `FC_corr` vs `FC_raw` (verdict on Standard)

| Scoring | Metric | FC_corr | FC_raw | Diff [95%] |
| --- | --- | --- | --- | --- |
| Standard | M1 | 0.318 | 0.293 | +0.026 [-0.004, 0.058] |
| Standard | M2 | 0.623 | 0.621 | +0.002 [-0.006, 0.009] |
| Half (info) | M1 | 0.324 | 0.315 | +0.009 [-0.009, 0.029] |
| Half (info) | M2 | 0.619 | 0.619 | -0.000 [-0.004, 0.004] |
| Full (info) | M1 / M2 | 0.333 / 0.621 | 0.333 / 0.621 | 0.000 / -0.000 (identical natives) |

Sensitivity, Standard (diff vs `FC_raw`): literal mapping M1 +0.026 [-0.004, 0.058], M2 +0.005
[-0.005, 0.015]; lambda 0.5 M1 +0.014 [-0.006, 0.036], M2 +0.001 [-0.003, 0.005]; Half anchor
M1 +0.015 [-0.006, 0.038], M2 +0.001 [-0.004, 0.006]. QB M1 is unchanged by construction.

The correction points the right way at Standard (M1 up in all four snapshot weeks: +0.016,
+0.001, +0.035, +0.050) but the interval crosses zero and the cross-position trade metric (M2)
barely moves. Not shown, not failed: four weeks cannot separate a 0.03 Spearman gain from noise.

## H2: `DDF_new` vs `DDF_cur` (verdict on Standard and Full)

| Scoring | Metric | DDF_new | DDF_cur | Diff [95%] |
| --- | --- | --- | --- | --- |
| Standard | M1 | 0.335 | 0.325 | +0.010 [-0.003, 0.025] |
| Standard | M2 | 0.633 | 0.630 | +0.003 [-0.001, 0.008] |
| Full | M1 | 0.346 | 0.347 | -0.001 [-0.010, 0.004] |
| Full | M2 | 0.631 | 0.631 | -0.000 [-0.002, 0.002] |
| Half (info) | M1 / M2 | 0.340 / 0.628 | 0.337 / 0.628 | +0.003 [-0.004, 0.014] / 0.000 [-0.002, 0.002] |

Sensitivity (diff vs `DDF_cur`):

| Variant | Std M1 | Std M2 | Full M1 | Full M2 |
| --- | --- | --- | --- | --- |
| literal (`samefit`) | +0.010 [-0.003, 0.025] | +0.005 [-0.005, 0.014] | -0.001 [-0.010, 0.004] | +0.000 [-0.002, 0.003] |
| lambda 0.5 | +0.004 [-0.004, 0.015] | +0.001 [-0.002, 0.004] | -0.001 [-0.009, 0.003] | -0.000 [-0.001, 0.001] |
| FC Half anchor | +0.007 [-0.004, 0.020] | +0.002 [-0.002, 0.005] | -0.005 [-0.015, 0.003] | -0.001 [-0.003, 0.002] |
| no FantasyCalc | +0.020 [-0.008, 0.048] | **+0.006 [+0.001, +0.011]** | +0.009 [-0.009, 0.033] | +0.003 [-0.002, 0.008] |

Robustness: the Half anchor keeps every sign; dropping FantasyCalc flips both Full signs
(negative to positive). So H2 is not shown and would also have failed as "not robust".

Plain language: at Standard the proposal is slightly better on both metrics in point terms but
inside the noise. At Full, where only FantasyPros is rescaled, it is a wash leaning negative.
The one interval above zero anywhere in H2 belongs to the no-FantasyCalc variant (option C) at
Standard M2. That is a sensitivity row, not a pre-registered hypothesis, so it does not change a
verdict; it is the only signal worth a follow-up.

## H3: `FC_corr` vs `DDF_new` (no pass / fail)

| Scoring | M1 diff (FC_corr - DDF_new) | M2 diff |
| --- | --- | --- |
| Standard | -0.017 [-0.049, 0.012] | -0.010 [-0.021, -0.000] |
| Half | -0.016 [-0.051, 0.017] | -0.009 [-0.019, 0.000] |
| Full | -0.013 [-0.054, 0.022] | -0.010 [-0.021, 0.001] |

`DDF_new` is closer to realized points than corrected FantasyCalc alone at every scoring, by
about 0.015 Spearman and 1 point of pair concordance. Whatever gain H2 shows comes from the
blend, not from FantasyCalc being made good on its own. On QB, FantasyCalc is better (0.164 vs
0.151 M1), with a very wide interval.

## PROJ benchmark

| Scoring | PROJ M1 | best contestant M1 | PROJ M2 | PROJ_VAR M2 (not pre-reg.) | best contestant M2 |
| --- | --- | --- | --- | --- | --- |
| Standard | 0.386 | 0.335 DDF_new | 0.603 | 0.656 | 0.633 DDF_new |
| Half | 0.384 | 0.340 DDF_new | 0.596 | 0.643 | 0.628 DDF_cur/new |
| Full | 0.392 | 0.347 DDF_cur | 0.609 | 0.650 | 0.631 DDF_cur |

PROJ beats every contestant on M1 at every scoring (e.g. vs `DDF_new` Standard +0.051
[-0.042, 0.141]); raw PROJ loses on M2 only because raw points rank every QB above every RB.
In replacement units (`PROJ_VAR`) it beats every contestant on M2 too (vs `DDF_cur` Standard
+0.026 [-0.004, 0.058]). None of these intervals excludes zero. As the spec says: this means
realized points over 1-4 weeks reward projections, not that projections are better trade
values. QB M1 for every chart-based method is weak (0.15-0.16) against PROJ 0.25.

## S: steelman (does the correction move values away from realized points?)

| Scoring | Version | corr(change, residual) | n rows | Verdict |
| --- | --- | --- | --- | --- |
| Standard | whole set, VAR (primary) | +0.087 [-0.049, 0.222] | 432 | NOT SHOWN |
| Standard | within position, points | +0.193 [+0.041, +0.332] | 360 | steelman rejected |
| Half | whole set, VAR (primary) | +0.024 [-0.094, 0.140] | 432 | NOT SHOWN |
| Half | within position, points | +0.115 [-0.034, 0.255] | 360 | NOT SHOWN |

Every sign is positive: the correction tends to move FantasyCalc toward what players scored,
not away. Only the within-position Standard version is clear of zero. The primary version is
not shown, so there is no evidence that FantasyCalc's flat scoring response carries market
information that the correction destroys, and weak evidence against.

## FP: first-principles direction of within-position swaps (weeks 5-9, RB / WR / TE)

| Chart, variant | Swaps | Right way (projected rec. share) | Trailing 2026 realized share | Rescale's own ratio |
| --- | --- | --- | --- | --- |
| FantasyCalc, lambda 1 | 413 | **97.3%** PASS | 88.9% (n 396) | 100% |
| FantasyCalc, lambda 0.5 | 200 | 97.0% PASS | 88.5% | 100% |
| FantasyCalc, literal | 413 | 97.3% PASS | 88.9% | 100% |
| FantasyPros, lambda 1 | 333 | **97.0%** PASS | 91.0% (n 332) | 100% |
| FantasyPros, lambda 0.5 | 166 | 98.2% PASS | 91.0% | 100% |
| FantasyPros, literal | 333 | 97.0% PASS | 91.0% | 100% |

By week (FantasyCalc, lambda 1): 97.6%, 100%, 93.9%, 96.0%, 98.7%. This pass is close to
mechanical: the rescale reorders exactly on the projected stat mix, so the 3% misses are only
where the Razzball / CBS ROS ratio disagrees with the three-source mean. Against realized 2026
reception share (more independent) FantasyCalc is at 88.9%, under the 90% line; that is not the
pre-registered measure and does not change the verdict.

## L: labelled check (CBS / USA Today Standard column rescaled to Full vs their own Full column)

| Chart | Weeks rescaled better | Within-position diff by week 5 / 6 / 7 / 8 / 9 | Verdict |
| --- | --- | --- | --- |
| CBS | 1 of 5 | +0.001 / -0.007 / -0.012 / -0.008 / -0.013 | FAIL |
| USA Today | 1 of 5 | +0.001 / -0.002 / -0.003 / -0.005 / -0.013 | FAIL |

Unchanged Standard columns already match the Full columns at about 0.99 Spearman within
position; the full-ratio rescale moves players too far. Fitted damping on CBS: **lambda = 0.30**
(0.9950 vs 0.9943 at 0 and 0.9865 at 1). Tested on USA Today: 0.9935 at 0.30 vs 0.9921 at 0
and 0.9880 at 1 (its own best is 0.40). So both labelled charts say the right damping is about
0.3-0.4, not 1. Whole set (across positions): position-scaled 0.95-0.98, literal 0.82-0.93,
unchanged 0.98-0.995. The literal mapping is clearly wrong for these charts. The gains from
damping are tiny in absolute terms and the charts are the target, not an independent truth.

## M: mechanism test, 2015-2025

| Rescaled (trailing Standard rate) | Unscaled (trailing Full rate) | Diff [95%] | Seasons positive |
| --- | --- | --- | --- |
| 0.274 | 0.345 | **-0.071 [-0.102, -0.038]** | 0 of 11 |

132 season-week-position groups, 448 players. Removing the reception share from a trailing
rate makes it a worse predictor of rest-of-season Standard points, in every season (worst 2017,
-0.164). Receptions carry usage information that predicts future yards and touchdowns. This is
a clean negative result for the mechanism as stated: scaling a player down by his reception
share discards signal. It does not test the prototype directly (the prototype uses projected,
not trailing, stat mix), but it argues for damping (L agrees) rather than the full ratio.

## By snapshot week (no verdict changes)

| Diff | w5 (4 wk) | w6 (3) | w7 (2) | w8 (1) |
| --- | --- | --- | --- | --- |
| H1 Std M1 | +0.016 | +0.001 | +0.035 | +0.050 |
| H1 Std M2 | -0.002 | -0.003 | +0.001 | +0.011 |
| H2 Std M1 | -0.001 | +0.001 | +0.014 | +0.024 |
| H2 Std M2 | +0.002 | -0.000 | +0.005 | +0.007 |
| H2 Full M1 | +0.000 | +0.004 | -0.002 | -0.007 |
| H2 Full M2 | +0.001 | +0.001 | +0.000 | -0.003 |

The Standard gains come from weeks 7-8, the shortest and noisiest windows (2 and 1 weeks). The
longest window (week 5, four weeks of points) shows nothing for H2. PROJ's own M1 falls from
0.51 (w5) to 0.25 (w8), a measure of how noisy the short windows are.

## Caveats

- `FC_raw` / `FC_corr` are FantasyCalc's adjusted column from different pipeline runs, so even at
  Full (identical natives) M2 differs by 0.0001; negligible.
- No 2015-2025 back-test of the charts exists; M tests only the rescaling rule.
- Realized points are not market value.
