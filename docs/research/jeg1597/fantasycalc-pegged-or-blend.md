# JEG-1598 sub-question 1: is FantasyCalc pegged to one scoring, or a blend?

Part of JEG-1597. Research only: no published number, value model or pipeline change.
Script `tools/research/jeg1597/fantasycalc_scoring.py` -> `tools/research/jeg1597/out/fantasycalc_scoring.json`;
tests `tests/test_jeg1597_fantasycalc_scoring.py`; live data
`data/research/jeg1597/fantasycalc/2026-11-09/` (SOURCE.md there).

Jeremy (2026-11-09): "Figure out if FantasyCalc is just blending data across leagues with all
scoring settings or it is picking a scoring setting it is pegging to. Use logic for how to
decompose it based on that, and if it's not possible, we may exclude from enhanced DDF."

## 1. Pre-stated method and decision rules (written 2026-11-09, before the analysis run)

The live pull (section 2) was taken and its fields inspected before this section was written;
the profile, calibration and classification below had not been run.

### 1.1 Parameter response (live endpoint, 24 settings)

For every switch (ppr 0 / 0.5 / 1; numTeams 8 / 10 / 12 / 14; numQbs 1 / 2) and for the API's
`value` against its own `redraftValue` field: per position (top 36 with value >= 300, to stay
clear of integer rounding), `k_p` = median of `v1 / v0`; residual = `log(v1/v0)` minus a
straight-line fit on `log v0` (allows a smooth value-level curve); residual SD; within-position
reordered pairs; Spearman of the residual with the projection reception share `rec / m(0.5)`.
**Rule:** a switch is a *player-level (per-scoring) computation* if any position reorders > 2%
of its pairs, or its residual has |Spearman with reception share| >= 0.3 with residual SD
> 0.5%. Otherwise it is *multiplier only*, and the switch is not identifiable within position.

### 1.2 r-profile (pegged vs blend), two statistics

Reference `m(r) = std + r * rec` (step-1 loader: mean of espn, cbsros, razzball). A mixture
`a*std + b*half + c*full` is `m(b/2 + c)`, so the mixture weight is one number `r`.
Estimation grid `r` in [-0.5, 2.0] (wider than the [0, 1.5] asked for so a Standard column is
not piled on the grid edge, which would flatter calibration). Bootstrap B = 300, seed 1598, 80%
percentile interval.
- **Within position:** for RB, WR, TE (top 36 / 36 / 24 by the chart's value), the sum over
  positions of `(n-3) * mean(atanh Spearman(v, m(r)), atanh Pearson(log v, log m(r)))`
  (order and spacing). Players resampled within position.
- **Cross position:** the chart's k-th value (RB, WR k = 1..24; TE 1..12) against the
  projection's k-th points above replacement at `r` (replacement rank RB 30, WR 36, TE 15; all
  reference players ranked by `m(r)`), one log-log line for all three positions, `r_hat` =
  least squares. Rank slots resampled within position. Sensitivity: K 18/18/9, R 24/30/12.
- **Realized reference (small sample):** the same two profiles with realized points per game
  (2026 actuals; capture week 5 -> weeks 5-8, week 6 -> weeks 6-8; players with >= 2 games).

### 1.3 Calibration (before reading any FantasyCalc answer)

Labelled cases: CBS and USA Today, Standard (truth r = 0) and Full (r = 1), weeks 5-9 = 20 per
method. **Pass bar:** `|r_hat - truth| < 0.25` on >= 80% (16 of 20). A method that fails is not
used to read FantasyCalc; its FantasyCalc `r_hat` is reported only as uninterpretable.

### 1.4 Classification of FantasyCalc (weeks 5-9 history; current and live reported)

Only with a calibrated method:
- **Pegged at g** (g in 0, 0.5, 1): the 80% interval lies inside (g - 0.25, g + 0.25) in >= 80%
  of weeks, same g.
- **Stable blend:** every weekly `r_hat` is >= 0.15 from 0, 0.5 and 1, every 80% interval is
  <= 0.5 wide, and the weekly range is <= 0.3.
- **Not identifiable:** anything else, or no calibrated method.

Caveat stated in advance: in reception-weight terms a blend and a peg can be the same number
(a 1/3-1/3-1/3 blend is r = 0.5, which is Half). The r-profile can only say *where* the list
sits, not whether that position came from one league type or many. The parameter response and
the API fields are the evidence on *how* FantasyCalc computes settings.

### 1.5 Decomposition per outcome (stated before the run)

- (a) Pegged at g: anchor the list at scoring g and adjust to the reader's scoring via the
  step-2 stat decomposition (`v * m(target) / m(g)` per player).
- (b) Stable blend: treat the list as `m(r_hat)` with the estimated weight and its interval,
  adjust from `r_hat`; carry the interval into the source's uncertainty.
- (c) Not identifiable: recommend excluding FantasyCalc from the enhanced (scoring-aware) DDF,
  with the cost stated; exclusion is Jeremy's decision.

## 2. What the API itself shows (live pull 2026-11-09, 24 settings)

Each response row carries `value` (the setting's number) and `redraftValue`. Grouping the 24
responses by their `redraftValue` and `maybeTradeFrequency` columns:

- **One base list per QB count, shown as 12-team Full PPR.** Within a group, `redraftValue`
  is identical across every ppr and numTeams setting, and `value == redraftValue` for all 196
  players exactly at ppr=1, numTeams=12 (for numQbs 1 and 2). Trade frequency, position rank
  and 30-day trend are also identical across ppr settings.
- **Every setting is the base times a per-position constant.** `value / redraftValue` per
  position has residual SD <= 0.05% (RB, WR <= 0.02%; integer rounding only, visible at
  values under ~150) in 24 of 24 settings. No reorders, no player-level term.
- **Two data vintages in one pull (called pools P and Q in the script).** 16 settings shared
  base P (all ppr=1; most 10-12-team). 8 settings (ppr0 qb1 t8/t14, ppr0.5 qb1 t8, ppr0 qb2
  t8/t10/t14, ppr0.5 qb2 t8/t14) served base Q, with different trade frequencies.
  P vs Q bases: 10 of 630 RB pairs and 10 of 630 WR pairs reorder, residual SD 3.3% RB / 4.8%
  WR, and the residual is unrelated to reception share (Spearman -0.05 RB, -0.15 WR). The
  split does not follow scoring (ppr0 qb1 t10/t12 were P, ppr0 qb1 t8/t14 Q).
  **Recheck at 07:02Z** (`recheck/`, 6 settings, after the 20-minute cache window): the Q
  settings were unchanged, and the P settings (ppr0 and ppr1 qb1 t12, ppr1 qb2 t12) had moved
  to exactly the Q base and Q trade frequencies (196 of 196). So Q was simply the newer data
  refresh, and each setting is cached separately: a pull across settings can mix two vintages.
  This is not a per-setting trade sample.

### 2.1 Parameter response (pre-stated rule 1.1)

| Switch (12 teams unless named) | QB k | RB k | WR k | TE k | Reorders (top 36) | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| ppr 0 -> 1, 1QB | 1.012 | 0.994 | 1.018 | 1.023 | 0 | multiplier only |
| ppr 0 -> 1, 2QB | 1.011 | 0.994 | 1.018 | 1.023 | 0 | multiplier only |
| teams 12 -> 8, ppr1 1QB | 0.934 | 1.002 | 0.984 | 0.991 | 0 | multiplier only |
| teams 12 -> 14, ppr1 1QB | 1.006 | 0.999 | 1.010 | 1.015 | 0 | multiplier only |
| numQbs 1 -> 2, ppr1 | 2.667 | 0.733 | 0.864 | 1.005 | 0 | multiplier only (by rule) |

- Pre-stated rule over all switches: ppr 19 of 24 multiplier only, teams 15 of 18, qbs 9 of 13.
  **Every flagged switch crosses the two vintages or crosses QB counts**; none has a residual tied
  to reception share at RB or WR (max |Spearman| 0.23). Flags come from the pool-Q base (QB 3
  of 136 pairs reordered) and, in one 2QB case, TE (Spearman 0.35 on a 4.5% residual).
- **numQbs is a real separate list**: the 2QB base differs from the 1QB base player by player
  (residual SD 3.3-5.0%), presumably a separate superflex trade pool; inside it, scoring and
  league size are again position constants.
- **Size of the scoring switch**: WR-vs-RB move from ppr 0 to 1 as a share of the projections'
  own Standard-to-Full move on the same players: FantasyCalc 0.091-0.099 (WR) and 0.094-0.098
  (TE), every week 5-9 and live. Labelled charts for comparison: CBS 0.17-0.41 (WR), 0.51-0.68
  (TE); USA Today -0.07 to 0.00 (WR) and -0.05 to 0.00 (TE).
- **Earlier captures**: 2026-11-07 ppr 0 vs 1 is multiplier only (0 reorders). 2026-09-29 has
  the vintage-mix signature (RB 7 of 630 pairs reordered, residual SD 3.1%, Spearman with
  reception share 0.27 RB / 0.20 WR, under the 0.3 bar): consistent with its two lists coming
  from different data refreshes, not with a per-scoring computation.
- **Pipeline consequence (not acted on here):** `pull_fantasycalc_full_feed.py` pulls the 24
  settings one by one, so a weekly pull can mix vintages across settings; comparing settings
  within one pull is only clean when their `redraftValue` columns match.

## 3. r-profile: calibration fails, so FantasyCalc's r_hat is not interpretable

Calibration (pre-stated bar: |r_hat - truth| < 0.25 on >= 80% of CBS and USA Today Standard and
Full columns, weeks 5-9):

| Method | Within bar | Pass |
| --- | --- | --- |
| Within position, order + spacing, projections | 6 / 20 | no |
| Cross position, k-th vs points above replacement, projections | 1 / 17 (CBS Standard lists < 12 TE in 3 weeks) | no |
| Cross position, sensitivity K 18/18/9, R 24/30/12 | 4 / 20 | no |
| Within position, realized points (weeks 5-8 / 6-8, small sample) | 0 / 8 | no |
| Cross position, realized points | 2 / 7 | no |

Why: within position, the step-1 opinion offset (WR reads high, TE low on both columns) is
the size of the whole scoring step. Cross position, the labelled charts' own Standard and Full
columns barely move against each other: USA Today's Full column is close to a flat ~6-7%
increase at every position, and CBS moves WR relative to RB by only 17-41% of a projection
step. Projection points-above-replacement cannot recover a scoring label that the charts
themselves only partly express.

For the record (not interpretable per rule 1.3):
- Within position: FantasyCalc r_hat 0.85-1.25 by week (80% intervals about 0.3 to 1.7),
  identical on all three ppr columns (same order).
- Cross position: weeks 5-8 jump between -0.5 and 2.0; week 9, current and live sit at
  1.0-1.05 with 80% interval 0.85-1.15, again the same on all three columns.

**Pre-stated classification: not identifiable** (no calibrated method), on every column.

## 4. FantasyCalc's own statements

FantasyCalc's site pages (FAQ, about, terms) render client-side; fetches return only the page
title, so no method or terms text could be read. Third-party write-ups describe its values as
built from real completed trades on league platforms such as Sleeper; none documents how
settings are handled. Its Bluesky profile says only that the site uses an algorithm. No
terms of use were readable: whether the public API may be used this way should be checked by
Jeremy on the site itself (the pipeline already uses the same endpoint).

## 5. Answer to Jeremy's question

- **Neither, in the sense asked.** FantasyCalc does not compute a value per scoring setting.
  It computes one market list per QB count from its trades, publishes it as the 12-team
  Full PPR number, and makes Standard, Half and other league sizes by multiplying each
  position by a constant (RB 0.994, WR 1.018, TE 1.023 from Standard to Full). Whether that
  list comes from PPR leagues only or from all leagues is not visible in the output and is
  not published. The r-profile cannot settle it: it fails calibration on charts whose
  scoring is known.
- **What is identifiable:** the base label (Full PPR, 12 teams, via `value == redraftValue`);
  that the scoring and league-size switches are position constants (no within-position
  information); that numQbs is a genuinely separate list.

### 5.1 Decomposition options

- **A (recommended): one list, anchored at its own label.** Read FantasyCalc's base (the
  ppr=1, 12-team list, per QB count), treat it as Full PPR because that is the only scoring
  the publisher attaches to it, and apply DDF's own step-2 stat adjustment from Full to the
  reader's scoring, labelled "assumed". Ignore its ppr switch (about 9% of a real move).
  Keep its numQbs list; its numTeams constants are optional. Risk: if the list is really a
  Half-like blend, the step-1 cost table applies (about 10% RB, 22% WR, 25% TE level error
  for a one-step miss); report the Half anchor as a sensitivity.
- **B: one list, anchored at Half (minimax).** Same, but anchor at Half, per step-1 option A.
  Halves the worst-case level error, but contradicts the publisher's own label.
- **C: exclude FantasyCalc from the enhanced (scoring-aware) DDF**, keep it in the plain DDF.
  Cost: it is the best-performing chart in the JEG-1565 tests, and the only source with
  league-size and 2QB settings; superflex readers would lose their only native 2QB market.

**Steelman for leaving its scoring response alone.** The flat response may be real market
behavior: traders price players roughly the same across formats. USA Today's labelled Full
and Standard columns move WR against RB by about 0% of a projection step and CBS by 17-41%, so
a full projection-ratio adjustment would move FantasyCalc further than any labelled chart
moves itself. Under A or B, the adjustment should be checked against that, possibly damped.

## 6. Durable learnings

- FantasyCalc's API exposes its base: `redraftValue`, equal to `value` at ppr=1, 12 teams.
  Every ppr and numTeams setting is that base times a per-position constant; numQbs has its
  own base. Each setting is cached separately, so one pull across settings can mix two data
  refreshes; check that `redraftValue` matches before comparing settings.
- Labelled trade charts move cross-position levels with scoring by 0-40% of a projection
  step (WR vs RB), so neither within- nor cross-position projection fits can recover a
  chart's scoring.
