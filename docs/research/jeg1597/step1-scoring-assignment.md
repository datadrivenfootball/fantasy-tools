# JEG-1597 step 1 (JEG-1598): which scoring does each trade chart resemble?

Research only. No published number, value-model file or pipeline changes.
Script: `tools/research/jeg1597/scoring_assignment.py`, output
`tools/research/jeg1597/out/scoring_assignment.json`, tests
`tests/test_jeg1597_scoring_assignment.py`.

## 1. Pre-stated method (written before the first run, 2026-11-09)

**Question.** For each trade chart (cbs, usatoday, fantasypros, fantasycalc),
each saved column (Standard, Half, Full) and each week (history weeks 5-9 plus
the current fixture), which scoring does the chart's *within-position* order
most resemble?

**Reference.** Per player, the projection mean at a scoring family indexed by
receptions weight `r`: `m(r) = std + r * rec`, where `std` and `rec = full -
std` are the means over the projection sources (espn, cbsros, razzball) that
list the player with `ppg_full > 0` (history `ppg` triplets; for the current
fixture `players.json` `espn_ppg`, `cbsros_ppg`, `rz_ppg`). Projections are
linear in `r` (half = midpoint), so `r = 0, 0.5, 1` are Standard, Half, Full,
and `r = 1.5` at TE is a 0.5 TE premium. Zero-ppg ESPN rows are left out of the
reference (VP-0 counts them as 0 for pricing; here they would only add noise).

**Players.** Per chart column and position, the chart's own top N by native
(N = 36 RB/WR, 24 TE/QB, or fewer if the chart lists fewer) among players with
native > 0 and a reference. Selection by the chart, not the projections, so the
selection does not depend on the scoring being tested.

**Statistic (scale-free; no cross-position level is used).**
- `rho_p(r)`: Spearman between chart native and `m(r)` over those players, on
  a grid `r = -0.5 .. 2.0` step 0.05. `r_hat_p` = argmax.
- Pass-catching signal: partial Spearman of chart native with `rec` given
  `m(0.5)`. Expected sign: negative for a Standard list, ~0 Half, positive Full.
- Chart-level fit: `F(r) = sum over RB, WR, TE of (n_p - 3) * atanh(rho_p(r))`
  (Fisher-z, weighted by information). QB is reported, never pooled: QB
  projections barely move with receptions.
- **Probability.** Bootstrap support: resample players within each position
  (B = 500, seed 1597), take the argmax of `F` over {Standard, Half, Full} in
  each resample, add-one smoothing. Per position the same with `rho_p`. No
  temperature to tune; the labelled test below checks whether this support is
  calibrated.
- **Identifiable within position** only when the reference orders at `r = 0`
  and `r = 1` differ on at least 5% of the position's pairs. Otherwise the
  position is reported "not identifiable".
- **TE premium probe.** `r_hat_TE - r_hat_WR` with its bootstrap interval;
  flagged only if `r_hat_TE >= 1.25` and the 80% interval of the difference is
  above 0. There is no labelled TE-premium chart, so a flag (or its absence) is
  unvalidated on real data; the synthetic test is the only check. Cross-position
  level (TE vs WR value ratio) is not used: chart units and position pricing
  are the publisher's.

**Labelled test (pass bar fixed in advance).** CBS and USA Today publish
Standard and Full PPR columns (their Half columns are, to rounding, the
midpoint of the two). Cases: 2 charts x {Standard, Full} x weeks 5-9 = 20.
- P1: chart-level top label correct on >= 16 of 20 (80%).
- P2: Standard and Full separated: `r_hat(Full) > r_hat(Std)` in 10 of 10
  chart-weeks, and zero cross errors (a Standard column labelled Full or the
  reverse).
- Reported, not pass/fail: Half columns' top label and whether `r_hat(Half)`
  lies between the other two; mean support on the true label (calibration).
- If P1 or P2 fails, the method is not trusted for assignment and the note
  says which parts are identifiable.

**Other charts.** FantasyCalc ppr=0/1: expected identical within-position
order, so identical answers on both columns, meaning its scoring switch is not
identifiable within position; its per-position Full/Std multipliers are
compared with the projections' (a within-chart ratio, so units cancel).
FantasyPros: one column for all formats; one answer per week.

**Cost of a wrong assignment.** For a chart whose true column is Standard or
Full but which is assigned Half, with a step-2 style rescale `v * m(target) /
m(assigned)`: the per-player value error is `m(true) / m(assigned) - 1`
(independent of the reader's target), and the count of top-N pairs per
position whose order differs between the true and the assigned rescale, for
targets Standard and Full. Pass-catching backs = the top third of the chart's
top-36 RBs by `rec / m(0.5)`.

## 2. Data notes found on the way

- CBS's and USA Today's saved Half columns equal, to the publishers' rounding
  (within 0.5), the midpoint of their Standard and Full columns (98-100% of
  players, every week). The Half label is therefore not independent evidence.
- FantasyPros' three columns are identical (100%, every week).
- `app/trade-value-chart/assets/comparison-sources-data.json` is a Week 7 copy
  (built 2026-10-26). The current week was read from
  `data/fixtures/current/comparison-sources-data.json` (Week 9 content); its
  answers match history week-9 exactly.
- Within the top 36, the projection reference's own Standard and Full orders
  disagree on only about 5% of RB and WR pairs and 2-4% of TE pairs. That is
  the whole signal the method has to work with.

## 3. Results (run 2026-11-09, B = 500, seed 1597)

### 3.1 Labelled test: FAIL

| Variant | Correct (of 20) | Cross errors | Std < Full r_hat | Mean support on truth | P1 | P2 |
| --- | --- | --- | --- | --- | --- | --- |
| Pre-stated (5% identifiability floor) | 3 | 3 | 4/10 | 0.35 | fail | fail |
| Post hoc: every RB/WR/TE pooled (floor 0) | 5 | 2 | 7/10 | 0.33 | fail | fail |
| Post hoc: + per-position offset learned on the other labelled chart | 8 | 1 | 7/10 | 0.40 | fail | fail |

The pre-stated floor dropped some positions entirely (the reference sits at
4.4-5.6% discordance), so pre-stated cases include "not identifiable". The two
post-hoc variants were added after seeing the first run and are labelled as
such; neither comes close to the bar either. Chance is 6.7 of 20.

Why it fails, in the per-position estimates (`r_hat`, receptions weight that
best matches the chart's order): at WR the charts' order matches `r` 0.6-2.0
(often the grid edge) on Standard *and* Full columns; at TE it matches -0.5 to
0.3. The offset is consistent across the two charts (learned offsets: WR +0.47
CBS / +0.66 USA Today, TE -0.46 / -0.78, RB about 0), so it is the charts'
opinion of who earns targets (or the projections' view of receptions), not
sampling noise. That opinion is about the same size as the whole
Standard-to-Full step.

**Sanity check that confirms it is not a coding error:** using one projection
(espn, cbsros, razzball) as the "chart" at a known scoring and the mean of the
other two as reference, the method labels 18 of 30 correctly with 7 cross
errors. Razzball's Standard column reads as `r` 1.2-1.6 every week. Even a list
that literally is a scoring's points per game is not labelled reliably by
within-position order against other sources. The bootstrap support is also
overconfident (support on the truth as low as 0.02 when wrong), so the
distributions must not be read as calibrated probabilities.

### 3.2 What is identifiable

| Question | Identifiable? | Evidence |
| --- | --- | --- |
| Absolute scoring of a single list (Std / Half / Full) | **No** | 3-8 of 20 on labelled columns; 18 of 30 on projections |
| QB scoring | No | QB projections do not move with receptions (0% discordant pairs) |
| TE premium | No | No probe flag on any real chart-week; the TE `r_hat` is pinned low by the same opinion offset; there is no labelled premium chart. Synthetic test only |
| Whether a chart's two published columns differ by receptions | **Yes** | CBS and USA Today Full/Std ratio vs reception share, Spearman > 0 at RB, WR, TE in all 6 weeks (RB 0.55-0.92, WR 0.24-0.56, TE 0.17-0.57) |
| FantasyCalc's ppr switch, within position | Not a scoring change | Identical within-position order on both columns, every week, every position; method gives identical answers |
| FantasyCalc's ppr switch, level | Tiny | Full/Std: QB 1.012, RB 0.994, WR 1.018, TE 1.023 (all weeks). Projections on the same players: QB 1.00, RB 1.20-1.22, WR 1.54-1.57, TE 1.63-1.68. WR relative to RB: FC 1.024 vs projections 1.27-1.31, i.e. about 8% of a real Standard-to-Full move |
| FantasyPros | No | One column; per-week answers wander Standard / Half / Full (`r_hat` -0.1 to 0.6), which is the noise level seen on labelled columns |

### 3.3 Per-chart assignment (for the record; not reliable per 3.1)

Post-hoc all-positions variant, the column the pipeline reads at Full PPR;
point-estimate label, then bootstrap support on that label:

| Chart | wk5 | wk6 | wk7 | wk8 | wk9 / current |
| --- | --- | --- | --- | --- | --- |
| FantasyPros | Full 0.47 | Half 0.46 (Std 0.49) | Std 0.76 | Half 0.30 (Std 0.45) | Half 0.54-0.56 |
| FantasyCalc | Full 0.81 | Full 0.55 | Full 0.50 | Full 0.71 | Full 0.59-0.61 |

FantasyCalc leans Full every week (`r_hat` 0.75-1.55), but CBS and USA Today
Standard columns also read as 0.2-1.2, so the lean is within the noise of the
labelled test. Confidence: none usable.

### 3.4 Cost of a wrong assignment (true Standard or Full, assigned Half)

Step-2 rescale `v * m(target) / m(assigned)`; CBS and USA Today, weeks 5-9,
medians (range). Pairs are within-position pairs among the top 36 (TE 24).

| True | Position | Value error, position median | Pair flips, target Std | Pair flips, target Full |
| --- | --- | --- | --- | --- |
| Full | RB | +9.6% (9.1-10.1) | 6 of 630 (1-18) | 4 (1-10) |
| Full | WR | +21.9% | 4.5 of 630 (1-13) | 1.5 (0-8) |
| Full | TE | +24.7% | 0 (0-3) | 0 (0-2) |
| Std | RB | -9.4% | 4.5 (1-11) | 9.5 (2-15) |
| Std | WR | -21.9% | 3.5 (0-12) | 7 (2-19) |
| Std | TE | -24.6% | 0 (0-2) | 0 (0-6) |

- Within position the cost is small: at most 19 of 630 pairs (3%) reorder.
  Pass-catching backs (top third of the top-36 RBs by reception share) are off
  by 12% in absolute terms (max 23%), but only 2.4-2.8% relative to the RB
  median (max 8.8-15.3%).
- The real cost is position level: a wrong Half assignment moves WR values by
  11-14% relative to RB, and TE by about 14% relative to RB. That shifts the
  per-source position weights (VP-3) and every cross-position trade.

## 4. Recommendation

The data cannot assign a scoring to a single-column chart. Options for step 2:

- **A (recommended).** Use the publisher's stated format where it states one
  (a documentation check per chart, not inferred), and otherwise treat the
  list as Half PPR, labelled "assumed", because Half is the minimax choice: a
  wrong Half costs at most the 10% RB / 22% WR / 25% TE level error above,
  where a wrong Standard-for-Full costs about double. Treat FantasyCalc's two
  columns as one list (its switch is a near-uniform 1-2% factor).
- B. Keep the status quo (each chart's saved column read as is, no rescale).
  Zero new error, but FantasyPros and FantasyCalc stay effectively
  scoring-blind.
- C. Use this inference anyway. Not supported: it fails its own pre-stated bar
  and a projection-only sanity check.

Durable learning: within-position order against projections cannot recover a
list's scoring. Publisher opinion on target earners moves the implied
receptions weight by about as much as the whole Standard-to-Full step.
