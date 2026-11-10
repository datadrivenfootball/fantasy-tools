# JEG-1610: scoring-aware DDF v3, results (run 2026-11-10)

Spec: `preregistration.md` (committed a5521efee before any code). Implementation readings 1-16
committed with the code and tests in 7ab52b295 before the first gate run; reading 17 (the 2026-only
window is undefined at weeks 5-6) in 1c1d4d050, after the first G1 attempt stopped with an error and
before any G1 number was printed. Code: `tools/research/jeg1610/` (`history.py`, `unwind.py`,
`run_v3.py`). Numbers: `tools/research/jeg1610/out/` (`g1.json`, `g2.json`, `g3.json`,
`coverage.json`, `extremes.json`, `secondary.json`, `unwind_rows.csv`). Tests:
`tests/test_jeg1610_v3.py`, 14 pass, run before any gate number (identity at `s = s0` on all 45
chart-week lists, max diff 0; the pipeline at every anchor reproduces current DDF Value exactly, all
15 week-scorings; inverse exact at nodes; P monotone in A; P invariant to scaling the pie or W; pure
receiver; unlisted / 0 / below-waiver rules; no dependence on the games input).

Weeks 5-9 of 2026. Brackets = 95% paired player bootstrap (2,000 resamples, seed 16052).

## Verdicts

| Gate | Verdict | Why |
| --- | --- | --- |
| **G1** (labelled gate, stop rule) | **FAIL**: 0 of 5 weeks won in **all 12 cells** | rebuilt natives move 2-10x more than the publishers' own columns |
| G2 response test (descriptive after G1) | **FAIL** (harms); levels **move away** | `closer` interval below 0 for both subjects; FantasyPros (a) Standard below 0 |
| G3 v3 DDF vs current DDF (descriptive) | **worse** (primary and every robustness run) | `closer` difference below 0 for both references and both sets |

Per the stop rule, v3 stops: no page draft, no steelman. The prediction written before the run held
for within-position agreement (fails, moves too large) and did **not** hold for levels: v3 does
worse than v2 on levels, not better.

## Root cause (one mechanism behind all three failures)

Step 7 maps points back to chart units with `g_p`, fitted at the **anchor**. Chart natives are
priced above the anchor's replacement level (a chart value is about 0 at the waiver line). At the
target scoring a whole position's points shift (Full to Standard, every TE loses about 38% of his
points), but `g_p` keeps the anchor's waiver line, so the shift lands on every native in full.
Example, CBS Sports week 9, Full to Standard: the projections' TE waiver sits near 7.5 ppg at Full and
4.6 at Standard; Brock Bowers 17.8 -> 11.0 ppg maps to 8.4 chart points (published Standard 22.0);
from Colston Loveland (11.9 -> 7.4 ppg) down, TEs map below the anchor's waiver and are floored at 0.
Standard to Full, WRs gain about 50% of their points and Jaxon Smith-Njigba goes 49 -> 83 (published
53). The pipeline at `s` does re-derive waiver lines, W and the pie from these natives, but the
natives the charts are compared on (G1, G2) carry the shift, and the re-derived Adjusted values (G3)
inherit the reordering and the zeros. Not a coding error: it is the delta form "at the anchor" as
pre-registered. 69 rebuilt values in the G1 scored sets are 0 (floored).

**Lead's correction (2026-11-10): `g_p` explains the size of the level failure, not the
within-position failure.** The `v3_proj` variant does not use `g_p`: it re-derives replacement at
the target scoring in points and prices through the projections' own maps there. It also loses
every week on within-position and cross-position agreement (0 of 40; for example CBS Standard to
Full within 0.93-0.98 against unchanged 0.99-1.00, and identical to v3 in that direction). RB and
WR, where flooring does not happen, lose too (CBS Full to Standard, RB 0.981-0.993 against
unchanged 0.997). So the deeper cause is the one v1 and v2 found. Applying the full change in the
reception weight to each player's implied points moves the order far more than the publishers'
own columns move it, whatever the mix source (history or projected) and whichever way points go
back to value (chart curve at the anchor, or projection pricing at the target). `g_p` makes the
levels much worse on top of that.

## G1: weeks won by v3 over "unchanged" (of 5)

| Cell | within | levels (MALE) | xpos |
| --- | --- | --- | --- |
| CBS Standard -> Full | 0 | 0 | 0 |
| CBS Full -> Standard | 0 | 0 | 0 |
| USA Today Standard -> Full | 0 | 0 | 0 |
| USA Today Full -> Standard | 0 | 0 | 0 |

Typical sizes (week ranges): within 0.88-0.98 vs unchanged 0.99-1.00; levels error 0.38-0.74 vs
0.06-0.13; xpos 0.75-0.91 vs 0.98-0.99. Median rebuilt-to-input ratio, CBS Standard to Full: RB
1.36, WR 2.29, TE 2.74 (published 1.07 / 1.20 / 1.29); CBS Full to Standard: RB 0.64, WR 0.28, TE
0.02 (published 0.94 / 0.83 / 0.78). v2 for comparison (JEG-1605 L gate, week 9): within 0.97-0.99,
levels 0.11-0.36.

Reported with G1 (no verdict), weeks won summed over the 12 cells (of 60):
- **Projected mix** (v2's all-source mix in place of history): 1 of 60. History is not the cause; the
  move size comes from `g_p`.
- **History windows**: 2026 only 0 of 60 (undefined at weeks 5-6 in every cell, reading 17);
  2015-2026 0 of 60.
- **v3_proj** (price `P_i(s)` through the projections' maps at `s`): 0 of 40 (within, xpos; levels not
  comparable, reading 10).
- **History-share mixed pairs** (RB+TE, top vs bottom third by own reception share): v3 beats
  unchanged in 1, 0, 1, 0 weeks (CBS S->F, CBS F->S, USA Today S->F, F->S). Concordance falls from
  about 0.96-0.99 to 0.89-0.99.

## G2: chart-to-chart response (descriptive), mean reference

| Subject | (a) Standard, v3 - base | (a) Full | (b) corr | (b) closer | slope |
| --- | --- | --- | --- | --- | --- |
| FantasyCalc (Full anchor) | -0.004 [-0.068, +0.047] | tie | +0.43 [+0.33, +0.53] | **-0.004 [-0.007, -0.003]** | 1.23 [0.92, 1.58] |
| FantasyCalc (Half anchor) | +0.012 [-0.020, +0.059] | -0.009 [-0.045, +0.013] | +0.42 [+0.28, +0.55] | **-0.004 [-0.005, -0.002]** | 1.08 |
| FantasyPros (Half) | **-0.033 [-0.081, -0.010]** | +0.001 [-0.017, +0.011] | +0.31 [+0.17, +0.43] | **-0.004 [-0.006, -0.003]** | 0.85 |
| v2 rerun, FantasyCalc / FantasyPros | +0.012 / -0.016 | | +0.44 / +0.37 | -0.001 / -0.004 | 0.79 / 0.94 |

Direction is right (corr > 0, extremes' sign agreement 0.66 for both subjects vs v2 0.60 / 0.59),
size is wrong (`closer` < 0). Placebo 95th percentile is far below v3's observed (a) and `closer`
(v3 moves are large, so shuffling them is even worse); leave-one-out keeps every sign. Levels:
summed error higher than today in 5 of 5 weeks for both subjects (FantasyCalc mean 3.53 vs today
0.61 and v2 1.58; FantasyPros 1.86 vs 1.40 and v2 1.78): **moves away**. v1 and v2 recomputed in the
same run: FAIL / moves away, as in JEG-1605.

Code check (changed from v1/v2): shuffling CBS Sports' and USA Today's natives within position in the
anchor run changes v3 lists by up to 92 chart points (8x relative for a fringe player). v3's lists
depend on the reference charts through `W` and the fill-in peers of the anchor run; leave-one-out
(CBS ROS and CBS Sports dropped) is the guard and keeps every sign.

## G3: v3 DDF Value vs current DDF Value (descriptive), `DDF^-R` against `R`

| Set, reference | (a) Standard, v3 - current | (a) Full | closer diff | corr diff |
| --- | --- | --- | --- | --- |
| FantasyCalc set, CBS | -0.029 [-0.089, +0.014] | +0.005 [-0.001, +0.019] | **-0.003 [-0.005, -0.002]** | -0.04 [-0.13, +0.08] |
| FantasyCalc set, USA Today | -0.003 [-0.019, +0.013] | -0.002 [-0.009, +0.003] | **-0.002 [-0.002, -0.001]** | +0.26 [+0.15, +0.37] |
| FantasyPros set, CBS | -0.029 [-0.097, +0.013] | +0.005 [-0.001, +0.018] | **-0.003 [-0.005, -0.002]** | -0.02 [-0.12, +0.10] |
| FantasyPros set, USA Today | -0.009 [-0.034, +0.008] | -0.001 [-0.006, +0.004] | **-0.002 [-0.003, -0.001]** | +0.24 [+0.11, +0.37] |

Verdict **worse** on both sets (the `closer` difference is below 0 everywhere). Robustness, same
verdict each: FantasyCalc anchored at Half (worse), FantasyCalc dropped (worse), `v3_proj` (worse).
The (a) Standard point estimate flips sign against USA Today on the FantasyCalc set under the Half
anchor (-0.003 -> +0.000) and with FantasyCalc dropped (+0.001): that cell **hinges on** the anchor;
all are inside noise. Levels: higher error than current in 5 of 5 weeks in every cell (moves away).

Secondary (realized points through week 8, JEG-1601 M1/M2, v3 - current): Standard M1 +0.023
[-0.002, +0.058], M2 +0.005 [-0.004, +0.016]; Full M1 -0.001 [-0.014, +0.010], M2 +0.000 [-0.003,
+0.003]. Nothing shown either way; not a verdict.

## History coverage

| Chart, anchor (weeks 5-9 pooled) | priced | own history | under 6 games | rookie / no rows | below waiver |
| --- | --- | --- | --- | --- | --- |
| FantasyCalc, Full | 981 | 918 (93.6%) | 55 | 8 | 128 |
| FantasyPros, Half | 890 | 827 (92.9%) | 53 | 10 | 160 |
| CBS Sports, Standard / Full | 567 / 605 | 95.4% / 95.5% | 22 / 23 | 4 | 0 |
| USA Today, Standard / Full | 1,312 | 91.5% | 102 | 10 | 489 / 464 |

Scored sets on the fallback: G1 CBS 12 of 477, USA Today 15 of 538; G2 FantasyCalc 13 of 417,
FantasyPros 12 of 417. "No key" and "non-positive anchor points": 0 everywhere (the actuals file is
keyed by `player_key`). `no_inverse`: 0. The 2015-2023 nflverse rows left 24,798 rows (988 players)
unmapped.

Category table (`player_game_stats`): receptions match `ppr - std` exactly for every player-season
of 2024 (598) and 2025 (618), games equal too. 2026 is partial in the table (weeks 5-8 hold about
260-290 rows against about 1,110 in weeks 1-4): receptions exact for 366 of 532. Standard points
rebuilt from the categories (fumbles lost included; the table does carry `fumbles_lost`) are within
1 point for 77-79% of 2024-2025 player-seasons (two-point conversions and return or fumble-recovery
scores are not in the table). Display only; v3 reads only `std` and `ppr`.

## Extreme pairs: Standard-to-Full move, `log(Full / Standard)`, mean of weeks 5-9

| Group (6 players per week) | FantasyCalc v3 | FantasyPros v3 | CBS Sports | USA Today | DDF current | DDF v3 |
| --- | --- | --- | --- | --- | --- | --- |
| Pass-catching backs | +0.67 | +0.42 | +0.15 | +0.17 | -0.28 | -0.21 |
| Least pass-catching backs | +0.23 | +0.14 | +0.01 | +0.01 | -0.45 | -0.61 |
| Receiving tight ends | +2.16 | +1.59 | +0.24 | +0.07 | +0.18 | +0.61 |
| Least receiving tight ends | +2.50 | +1.31 | +0.25 | +0.05 | +0.17 | +0.47 |
| Rushing quarterbacks | +0.00 | +0.00 | 0.00 | 0.00 | -0.10 | -0.28 |

Direction vs the references: right for backs (pass-catchers up more than non-catchers, as both
references), but 3-4x too large; for tight ends the size swamps the mix (the least-receiving TEs move
as much as the receiving ones: the move is the anchor-waiver shift, not the reception share); for
rushing QBs v3 leaves the chart natives unchanged (right: no reception term), but DDF v3 lowers them
from Standard to Full almost 3x as much as current DDF, because the other positions' rebuilt natives
inflate at Full. Week 9 examples: Rachaad White (history share 0.26) FantasyCalc v3 +0.95 vs CBS
+0.15; Tyler Warren +4.20 vs +0.25; T.J. Hockenson floored to 0 at Standard.

## What is lost in the unwind (counted per chart-week in `coverage.json`)

- **Below waiver** (Adjusted 0, only "at or below waivers" known; native kept): FantasyCalc 128,
  FantasyPros 160, USA Today 489 / 464, CBS 0 player-weeks.
- **The chart's own cross-position level**: each chart's Adjusted share by position equals `W`'s
  exactly (FantasyCalc week 9: RB 0.418, WR 0.426 Adjusted and `W`; its native shares were 0.398 /
  0.406). It survives only as one vote in `W`.
- **Native scale**: replaced by `g_p`, which is where most of the level error comes from (the
  within-position loss does not depend on it; see the lead's correction under Root cause).
- Adjusted is monotone in the native within every position (0 violations); VORP display vs Adjusted
  Spearman 0.96-1.00.

## Negative results, plainly

- v3 fails its own pre-registered gate in every cell and every week. Against v2 it is worse on
  within-position agreement, `closer` and levels; the one measure where it is better is the
  extremes' sign agreement (0.66 vs 0.60 / 0.59), i.e. direction, not size.
- Replacing the projected mix with each player's history changes nothing material (projected-mix v3
  also wins 1 of 60). The mix is not the problem. Rebuilding natives at the anchor's waiver line
  makes the levels far worse. The within-position loss stays without it (`v3_proj`, 0 of 40).
- The pre-registered hope that inheriting the anchor `W` would help levels is refuted: levels are the
  worst measure (G1 MALE 3-10x unchanged; G2 and G3 levels move away 5 of 5 weeks).
- The secondary realized-points check shows no difference.

## Caveats

CBS Sports and USA Today are the reference, not truth, and barely reorder between their own columns
(0.99). Five overlapping weekly snapshots, not independent samples. FantasyCalc's Full and
FantasyPros' Half anchors are assumptions (the Half-anchor run gives the same verdicts).
