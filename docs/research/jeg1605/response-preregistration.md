# JEG-1605 / JEG-1597: chart-to-chart scoring-response test, pre-registered

Written 2026-11-10, **before any code for this test exists and before any of its numbers have been
looked at**. Research only: no change to published numbers, the value model or the pipeline. Any
change after the commit that adds this file is logged at the end with its date and reason. No
tuning after results.

Jeremy, 2026-11-10 (review page, on M1): "That's not the right test. The test should look at
sources that show meaningful change based on settings and see if the ones we have to adjust for a
lack of settings adjustment get closer to them in how rankings are made."

Jeremy, 2026-11-10 (review page, via the lead): "ESPN has how many games the player will play based
on non-0s." Added as a games variant (section 6).

Why the old benchmark is replaced: M1/M2 (JEG-1601 step 4) scored every list against realized
fantasy points over 1-4 weeks, which rewards projection-like orderings. This test scores the
adjusted scoring-blind charts against the charts that do respond to scoring.

## 1. Lists

Weeks 5-9 of 2026 (history snapshots, the same inputs as JEG-1601 and the v2 L gate). Positions
RB, WR, TE (CBS Sports publishes QB in separate columns; QB has no reception term). 12 teams,
default roster, 1 QB. Scorings: Standard (`standard`) and Full PPR (`ppr`).

**Reference (charts that respond to scoring):** CBS Sports and USA Today, each its own published
column at the scoring; and their **mean** (defined per measure below). The mean reference is
primary; each single reference is reported.

**Subjects (charts that do not respond):**

| Subject | Base list | Anchor (primary) | Anchor sensitivity |
| --- | --- | --- | --- |
| FantasyCalc | its `ppr` column (12-team base list) | Full | Half (same list read as Half) |
| FantasyPros | its `half_ppr` column (all three columns identical) | Half (assumed) | none |

**Methods per subject and scoring `s`:**

| Label | What it is |
| --- | --- |
| `today` | The list as DDF uses it today: the subject's published column at `s` (FantasyCalc's per-position constant switch; FantasyPros' one list). Within a position this equals the base list. |
| `base` | The base list at every scoring (zero move). Equal to `today` within position. |
| `v1` (primary) | JEG-1601 prototype, `decompose.rescale_chart`, `position_scaled`, lambda 1 |
| `v1_l05` | same, lambda 0.5 |
| `v1_literal` | same, `same_fit`, lambda 1 |
| `v2` (primary) | JEG-1605 round trip, `roundtrip.chain_mix`, uniform split, pooled curve |
| `*_fchalf` | the FantasyCalc Half-anchor sensitivity of each adjuster |

All adjusters are rerun from the code on the committed branch (not copied from saved CSVs); the
v1 rerun must reproduce `tools/research/jeg1597/out/rescaled_natives.csv` (max abs diff < 1e-3
after its 4-decimal rounding) before anything is scored.

At an anchor equal to the target (FantasyCalc Full anchor at Full) every adjuster returns the base
list exactly, so that cell is a tie by construction and is reported as such, not scored.

## 2. Player sets

Per subject, reference and week: within each position, the subject's top N by its **base list**
among players priced (value > 0) by the subject and by the reference in **both** its Standard and
Full columns (for the mean reference: by CBS Sports and USA Today, both columns each). N = RB 36,
WR 36, TE 18, or every eligible player when fewer (CBS Sports lists about 43 RB, 43 WR, 11-14 TE).
The set is fixed across methods and the two scorings.

Within-position percentile rank of a list = average rank (ties averaged) divided by n, higher value
= higher percentile, computed inside the set. Mean reference percentile = the mean of CBS Sports'
and USA Today's percentiles.

## 3. Questions and measures

Bootstrap: paired over players (the union of all weekly sets of that subject and reference), 2,000
resamples, seed 16052; a player's resample count weights him in every week, scoring and method.
Week statistics are averaged over weeks 5-9 with equal weight; the interval is the 2.5-97.5
percentile of that average.

**(a) Rank agreement.** Per week, scoring and position: Spearman between the method's values and
the reference's values at that scoring (mean reference: its mean percentile). Averaged over RB,
WR, TE. Statistic: `method - base` (equal to `method - today` within position). Also reported:
weeks (of 5) the method is strictly higher.

**(b) Response.** Per player in the set: the method's Standard-to-Full **move** in within-position
percentile, `pct(Full) - pct(Standard)`, and the reference's own move. `base` and `today` move 0.
Per week, pooled over RB, WR, TE:
- `corr`: Pearson correlation of the method's move with the reference's move (0 when the method
  does not move).
- `slope`: `cov(method, ref) / var(ref)` (1 = right size; above 1 overshoots). Reported.
- `closer`: `mean(ref^2) - mean((method - ref)^2)`, the reduction in squared move error against
  not moving. Positive = the method's moves are closer to the reference's than standing still.
- On the **pass-catching extremes**: RB and TE players in the top third and bottom third of the
  set at that position by projected reception share (`rec / (std + rec)`, mean of the three
  projection sources, as the v2 L-mix): `corr`, `closer`, and the share of those players whose
  move has the reference's sign (reference moves of exactly 0 excluded). Reported, no verdict.
- **Value-share move** (secondary, reported): share = value / sum of the set's values (RB+WR+TE)
  at the scoring; move = `log(share Full / share Standard)`; `corr` and `closer` as above but the
  comparator is `today` (FantasyCalc's published columns do move shares), statistic `closer(method)
  - closer(today)`.

**(c) Cross-position levels.** Level of a position in a list at `s` = geometric mean of its top k
values by that list's own order at `s` (k = RB 24, WR 24, TE 10). Ratios WR/RB and TE/RB. Mean
reference ratio = geometric mean of the two references' ratios. Error = `|log r_method - log r_ref|`.
Per week: summed error over the two ratios and the two scorings, method vs `today`. Also reported:
each list's own Standard-to-Full change in `log r`.

**(d) Null and leave-one-out.**
- **Placebo:** per subject, week and position, the method's per-player log adjustment
  `log(method_s / base)` at Standard and at Full (as a pair per player) is shuffled across the
  set's players at that position and applied to the base list. 1,000 shuffles, seed 16053. Report
  the placebo mean and 95th percentile of the (a) Standard statistic and the (b) `corr` and
  `closer` statistics (week-averaged), against the observed values.
- **Leave-one-out:** the adjusters are rerun with no CBS-derived input: CBS rest-of-season
  projection lines dropped (points, stat mix, ratios, the v2 curve fit), CBS `gp` dropped from
  expected games (schedule minus bye times the miss rate instead), and CBS ROS dropped from the
  mean ppg that sets the allocation `N_p`. Scored against CBS Sports and against the mean
  reference. No projection source comes from USA Today.
- **Code check:** the adjusters' inputs are the subject's own list plus projections, games and the
  allocation (projection family only, `value_reference.mean_ppg`). The runner asserts that
  replacing CBS Sports' and USA Today's natives with shuffled values leaves every adjusted list
  identical.

## 4. What counts as passing and failing

Per primary adjuster (`v1`, `v2`), on the **mean reference**, for **both** subjects (FantasyCalc
Full anchor, FantasyPros Half):

**PASS ("brings the scoring-blind charts closer to how the scoring-aware charts rank") needs all of:**
1. (a) at Standard: `method - base` > 0 with the 95% interval above 0.
2. (a) at Full: for FantasyPros, the interval not entirely below 0 (FantasyCalc Full is a tie by
   construction).
3. (b): `corr` > 0 with the interval above 0, **and** `closer` > 0 with the interval above 0.
4. (d) placebo: the observed (a) Standard statistic and (b) `closer` both above the placebo 95th
   percentile.
5. (d) leave-one-out: the signs of the point estimates in 1 and 3 are unchanged.

**FAIL (harms):** for either subject, the (a) Standard interval is entirely below 0, or the (b)
`closer` interval is entirely below 0. **Otherwise NOT SHOWN.**

**(c) levels, own verdict:** "moves toward the reference's levels" if the summed level error is
lower than `today`'s in at least 4 of 5 weeks for both subjects; "moves away" if higher in at least
4 of 5 for either; otherwise mixed.

Variants (`v1_l05`, `v1_literal`, `*_fchalf`, single references) are reported with the same
statistics and no verdict. If the FantasyCalc Half anchor flips the sign of the (a) Standard or
(b) `closer` point estimate, that is stated as the result hinging on the anchor.

**Prediction stated now:** the v2 L gate showed these publishers' Standard and Full columns agree at
0.99 within position and the projection-ratio move overshoots them. So we expect `corr` > 0 (right
direction) but `closer` <= 0 (too large), and (a) at Standard near 0 or negative for `v1` and `v2`;
expected verdict NOT SHOWN or FAIL, with `v1_l05` closer than `v1`. Levels: v2 moved WR/RB further
than the publishers in the L gate, so (c) for `v2` is expected to move away.

## 5. Caveats carried into the result

- CBS Sports and USA Today barely reorder within a position (about 0.99 between their Standard and
  Full columns), so the reference move is small and partly rounding noise (CBS values are in
  steps of 0.5).
- CBS Sports' Half column is the midpoint of Standard and Full, possibly formula-derived; if both
  publishers use a formula, this test measures agreement with a formula, not independent judgment.
- Weeks 5-9 of 2026 only; five overlapping snapshots, not five independent samples.
- The reference charts are judged against each other only through the mean; they are not truth.

## 6. Games variant (Jeremy, 2026-11-10)

ESPN publishes a projection for every unplayed week. Saved captures: Supabase
`public.source_projection_captures` (source `espn`, horizon `week`, `full_ppr`, phase `midweek`),
which holds future weeks only for content weeks 7, 8, 9 (captures 2026-10-24, 10-27, 11-03; the
weeks 2-7 backfill is per-game ROS only, and `data/inputs/espn_weekly_projections_2026.csv` holds
one week per row, not future weeks). Saved to `tools/research/jeg1605/cache/espn_nonzero_games.json`
on 2026-11-10 (one read-only query; no live pull from ESPN). `G_espn` = the count of target weeks
`w .. 18` with a non-zero projection in the content week `w` capture (`w` = the snapshot week).

Variants of the expected-games input (current rule: CBS `gp`, else schedule minus bye times
`1 - miss_p`):
- **G1:** CBS `gp`, else `G_espn`, else the schedule rule.
- **G2:** `G_espn`, else CBS `gp`, else the schedule rule.
A `G_espn` of 0 is used as 0 games (the existing code drops non-positive points from the fits).

Run on weeks 7-9 only, for `v1` and `v2` (both subjects, primary anchors, mean reference and each
reference): the change versus the current rule in the (a) Standard and Full statistics and in (b)
`corr` and `closer`, with bootstrap intervals over weeks 7-9; and the count of players whose games
input moves by more than one game (all priced players at RB/WR/TE in the subject, and inside the
scored sets). Reported, no verdict: three weeks.

## Changes after this commit

**2026-11-10, implementation readings, coded in `tools/research/jeg1605/response_test.py` before
the first scored run** (no pre-registered choice changed; each is the most literal reading where
the text did not pin the code down):

1. *Percentiles.* Within-position percentiles (moves, the mean reference) are computed once per
   week on the full set; the bootstrap reweights players but does not re-rank them. The (a)
   Spearman itself is re-ranked per resample (`step4_tests.spearman` with weights).
2. *Mean reference.* (a): Spearman against the mean of the two charts' percentiles. Value share:
   the mean of the two charts' share vectors. Levels: geometric mean of the two ratios (as written).
3. *`today`.* FantasyCalc's published column at `s`; a set player it does not list there counts as
   0 (log share floored at 1e-12).
4. *Levels* use every priced player of each list (top k by its own order), not the scored set.
5. *Placebo.* The (a) statistic per shuffle is the week mean of (position mean of Spearman of the
   shuffled Standard list minus Spearman of the base list), unweighted. Adjusted values <= 0 are
   floored at 1e-9 before taking logs (counted in the output). Run for `v1`, `v1_l05`,
   `v1_literal`, `v2` against every reference (not the Half-anchor variants).
6. *Leave-one-out sign check* compares the point estimates of (a) Standard, `corr` and `closer` on
   the mean reference.
7. *FAIL rule* uses the `closer` interval for (b) as written (not `corr`).
8. *Games variant.* `G_espn` applies to any player in that week's ESPN capture; a player not in it
   keeps the current rule. Differences versus the current rule use the same bootstrap rows (same
   weeks 7-9 sets, which do not depend on games).
9. *Extremes* use the all-source reception share in every run, including leave-one-out (it only
   selects players).
