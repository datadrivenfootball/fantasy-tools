# JEG-1599 (step 2 of JEG-1597): decompose a trade chart, rescore it, rebuild it

Research prototype. No change to the value model, the pipeline, the engine or any
published number. Code: `tools/research/jeg1597/decompose.py` (pure functions),
runner `tools/research/jeg1597/rebuild_ddf.py`, tests `tests/test_jeg1597_decompose.py`,
cache `tools/research/jeg1597/cache/cbs_ros_gp.json`. Outputs in
`tools/research/jeg1597/out/` (`rescaled_natives.csv`, `rebuild_values.csv`,
`rebuild_summary.json`). Written 2026-11-09.

## 1. What a chart gives, and what it does not

A trade chart gives **one number per player** at one scoring. That number mixes
games, points per game and stat mix (receptions vs yards and touchdowns). None
of the three can be pulled apart from the chart. The chart pins two things:

- **its order** within a position at its own scoring (the anchor `s0`);
- **its total yield**: how much more one player is worth than another.

Everything else comes from the projections, as a prior: expected games, and the
stat mix that sets how a player's points change between scorings. Step 1 showed
that a single list's scoring cannot be read from its order, so the anchor is an
assumption (section 4), not an estimate.

## 2. Model

Per chart `c`, position `p`, week `w`, anchor scoring `s0`:

1. **Projected rest-of-season points at `s0`.** `P_i = mean ppg_i(s0) x G_i`. The
   ppg is the mean of the projection sources that list the player with ppg > 0
   (espn, cbsros, razzball; history week `w` triplets). `G_i` = CBS ROS `gp` where
   CBS has the player, else schedule games from week `w` through 18 minus a bye
   still ahead, times `1 - miss_p` (VP-2.2d: QB 0.12, RB 0.14, WR 0.11, TE 0.15).
   CBS covered 363-367 players a week; the schedule rule covered 189-281 more.
2. **Fit (native to points).** A power law `log native = a + b log P`, fitted on
   **rank-matched pairs**: the chart's k-th highest native against the k-th
   highest `P` among the players both list. It uses the chart's top 36 RB/WR and
   24 QB/TE. Rank matching treats the fit as a change of units. An ordinary
   regression of native on `P` would flatten the slope, because the chart and the
   projections disagree about who is better (the plain-regression slope `b_ols`
   is in the summary for comparison). Because the map is monotone (`b > 0`), the
   chart's implied points `fit^-1(native)` keep the chart's own order.
3. **Stat mix.** `ratio_i(s0 -> s) = ppg_i(s) / ppg_i(s0)`. Scorings differ only in
   the receptions weight (`pipelines/lib/scoring.py`: 0, 0.5, 1), so for every
   source `ppg(s) = std + r_s x (ppr - std)`. Source order: the mean of Razzball
   and CBS ROS where either has a line; ESPN only where both are missing; a
   player with no line takes the median ratio of the chart's players at his
   position (flagged). Games are the same at every scoring, so they cancel out of
   the ratio.
   Check: on Razzball's 2026-11-08 snapshot, `per_game_ppr - per_game_standard`
   equals `raw_stats.pg_rec` within 0.10 for 570 of 570 players (stored to 0.1).
   So the history triplets carry exactly the stat line's receptions term.
4. **Rescore in points units.** `points_c(i, s) = points_c(i, s0) x ratio_i^lambda`.
   A pure receiver gains exactly one point per projected reception from Standard
   to Full (tested).
5. **Map back to native units** so that VP-2 receives a native list as before.
   Two mappings, both in `rescale_native`:
   - **same_fit** (the brief's literal "same fit, inverse"):
     `native x ratio^(b x lambda)`.
   - **position_scaled** (the default, used for `DDF_new`): the fit is restated
     in the target scoring's points scale, `g_s(x) = K g(x / K)` with
     `K = k_p^lambda`, where `k_p` is the median ratio of the chart's top-N players
     at the position. Result: `native x K x (ratio / k_p)^(b x lambda)`. The
     position's level moves exactly as its projected points do (times `lambda`).
     Only a player's deviation from his position's ratio goes through the chart's
     curve.
6. **Damping.** `lambda` in {0, 0.5, 1}. `lambda = 0` returns the natives unchanged
   (tested); for a position the fit cannot identify, `lambda = 0` is the fallback
   (fewer than 8 shared players, or a slope that is not positive), flagged.

### Why position_scaled is the default (a deviation from the brief, disclosed)

Every chart is strongly convex in points. The rank-matched elasticities `b` for
weeks 5-9 were:

| Chart | QB | RB | WR | TE |
| --- | --- | --- | --- | --- |
| FantasyCalc (Full anchor) | 2.8-5.1 (r2 >= 0.66) | 2.1-2.6 | 2.6-3.1 | 4.1-5.2 |
| FantasyPros (Half anchor) | 1.5-8.1 (r2 >= 0.33) | 1.05-1.28 | 1.24-1.41 | 2.4-2.9 |

The positions other than QB fit with r2 >= 0.84. Under same_fit, FantasyCalc's
Full-to-Standard move at WR is `0.64^2.9`, about 0.27, and at TE `0.60^4.5`,
about 0.10. That moves WR relative to RB by about 3.5 times the projections' own
move, in log terms (RB `0.82^2.2`, about 0.65, so WR/RB is about 0.42, against
0.78 for the projections). Step 1 found that labelled charts move it by 0-41% of the projections'
move, so this is far outside anything observed. The cause: the convexity measures
how value grows *within* a position, since points above replacement grow faster
than points. When a whole position's points shrink, its replacement level shrinks
with it, so the position-wide part should scale like points (degree 1), not like
points to the power `b`. position_scaled does that, and it keeps `lambda`
readable as "the share of the projections' own move". same_fit is still computed
and written out (`DDF_new_samefit`, `FC_corr_samefit`, `FP_corr_samefit`), so
step 4 can score both. The choice is open decision D1 in the step 3 proposal.

## 3. What is pinned, what is a prior, how uncertain

| Item | Pinned by the chart? | Source |
| --- | --- | --- |
| Order within position at `s0` | yes | the chart |
| Total yield (spacing, convexity `b`) | yes, given the anchor | the chart, via the rank-matched fit |
| Anchor scoring `s0` | **no** (step 1: not identifiable) | assumption: publisher label (FantasyCalc Full), "assumed Half" (FantasyPros) |
| Expected games | no | CBS gp, else the schedule and VP-2.2d rates; cancels under the power law |
| Stat mix (receptions share) | no | projections (Razzball and CBS ROS, ESPN fallback) |
| Whether the publisher's own value would move with scoring as projections do | no | `lambda` is a modelling choice; step 4's L test fits it on CBS |

**Ratio uncertainty** (week 9, top 36 by projected Half points; spread = max - min
over the projection sources that list the player):

| Move | RB median ratio (spread median / max) | WR | TE |
| --- | --- | --- | --- |
| Full -> Std | 0.82 (0.04 / 0.11) | 0.64 (0.04 / 0.11) | 0.60 (0.04 / 0.10) |
| Half -> Std | 0.90 (0.02 / 0.07) | 0.78 (0.03 / 0.08) | 0.75 (0.03 / 0.09) |
| Half -> Full | 1.10 (0.02 / 0.07) | 1.22 (0.03 / 0.08) | 1.25 (0.03 / 0.09) |

The sources agree on the stat mix far more closely than the anchor is known. A
one-step anchor error (step 1 section 3.4) costs about 10% at RB, 22% at WR and
25% at TE, which is roughly 5-10 times the source spread. **The anchor is the
dominant uncertainty, not the stat line.** Flags: 0-2 FantasyCalc players and
0-1 FantasyPros players a week fell back to the median ratio; no position was
non-identifiable in any week.

## 4. Anchors used (working assumptions)

- CBS Sports and USA Today: their own published column at each scoring, with no
  adjustment. Their QB values are one per format, so QBs are unadjusted for them.
- FantasyCalc: its base list (the ppr=1, 12-team column, `value == redraftValue`)
  anchored at Full PPR. Sensitivities: anchored at Half (`*_fchalf`), and excluded
  (`DDF_new_noFC`).
- FantasyPros: one list for every format, anchored at "assumed Half" (step 1
  option A: the smallest worst-case error).

## 5. Back-test

No chart snapshots exist before 2026, so a 2015-2025 back-test of the charts is
impossible. Only the mechanism can be tested (pre-registered test M), and that is
left to the step 4 agent. `decompose.rescale_native`, `rescale_chart`,
`player_ratio` and `fit_chart` are pure functions for that use. For the labelled
check L, `rescaled_natives.csv` also carries CBS's and USA Today's own Standard
column rescaled to Full (both mappings, `lambda` 0.5 and 1).

## 6. Durable learnings

- Trade charts are convex in projected points: native is about points^2-3 at
  RB/WR and points^4-5 at TE (FantasyCalc), and about points^1.1-1.4 at RB/WR
  (FantasyPros). Any rescoring that maps back through a fixed points-to-value
  curve amplifies a position-wide points change by that power. Scale the curve
  with the position instead.
- Scorings differ only in receptions, so `ppr - std` in the history ppg triplets
  is receptions per game (it matches Razzball `pg_rec` within storage rounding).
  No separate stat-line pull is needed for a rescore.
- `data/history` has no `served.json`. `make sync` writes it into
  `dist/assets/history` from `data/history/superseded`. A script that reads
  `data/history` through `value_reference.History` must rebuild it (as
  `rebuild_ddf.load_world` does), or the served FantasyCalc week fails with "the
  served version is not saved".
