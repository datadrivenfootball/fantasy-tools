# JEG-1610: scoring-aware DDF v3 (unwind Adjusted to points, history mix, rebuild), pre-registered

Written 2026-11-10, **before any v3 code or v3 result exists**. Research only: no change to
published numbers, the value model or the live pipeline. Any change after the commit that adds
this file is logged at the end with its date and reason. No tuned damping, no parameter chosen
after results.

Jeremy, 2026-11-10: "1) take 3rd party trade charts. 2) get to the indexed adj value for each which
feeds DDF today. 3) unwind those indexed adj values into VORP. 4) back out expected points from
VORP logic unwinded. 5) for each player, calculate how they tend to earn points based on
historical metrics by category. 6) apply how players get points to their points, to get their
implied metrics (rushing yards, receptions, etc.). 7) From there for each scoring setting build
all the way back up to DDF logic, and average as DDF does... note only do this for the charts that
don't adjust properly for scoring settings applied."

## 0. Reading of "indexed adj value"

DDF Value is the mean of the trade charts' **Adjusted** values (VP-6.3). **Indexed** is display
only (VP-6.4): the chart's published value times one factor per chart, so unwinding Indexed returns
the published list and carries no DDF logic. v3 therefore starts from **Adjusted**, the value that
feeds DDF today. Stated on the page.

## 1. The chain (fixed before building)

Per chart `c`, week `w` (history snapshots 5-9 of 2026), anchor `s0`, target `s`. 12 teams, the
live default roster and lineup parameters, 1 QB, fractional seats, as `rebuild_ddf.run`. Positions
QB, RB, WR, TE. Pipeline = `pipelines/value_reference.py` `run_pipeline`, unmodified, called as in
`tools/research/jeg1597/rebuild_ddf.py` (same included and hidden sets as the live setting).

1. **Chart list.** `x_i` = the chart's native at `s0`: FantasyCalc its `ppr` column (base list),
   FantasyPros its `half_ppr` column; for gate G1, CBS Sports' or USA Today's own column at `s0`.
   A player not listed, or listed at 0, has no price (implied 0) and gets no v3 value.
2. **Adjusted value.** Run the pipeline at `s0` with every source's natives at `s0` as today
   (FantasyCalc at a Full anchor = its live Full input). `A_i` = the chart's `adjusted` for `i`.
3. **Unwind to VORP (what is invertible).** Under expected starts (ES-5)
   `A_i = Pie x W[p,st] x sw_i / G_c[p,st] + Pie x W[p,bn] x fi_i / G_c[p,bn]`, with
   `sw_i + fi_i = v_i x share_p(x_i)` and `v_i = max(0, x_i - w_p)`. Within a position `A` is
   non-decreasing in `x` (both parts are, at non-negative rates; a weighted mix of allocations
   keeps that), so for `A_i > 0` the chart-unit VORP `v_i` (and `x_i`) is recovered exactly.
   - **W and the pie** are constants within a position group and are **the same for every source**
     (VP-4, VP-5). They do not need undoing separately: step 4 matches the chart against the
     projections priced on the same `W` and pie, so they cancel except for the starter/bench split.
   - **Lost:** (i) players at `A_i = 0` (at or below the chart's waiver line): only "at or below
     waivers" is known; (ii) the chart's **own cross-position level**: every source's Adjusted total
     at a position is `Pie x W[p]`, so the chart's view of position levels survives only as 1 of 7
     votes in `W`; (iii) the native's scale. Counted per chart-week.
   - Reported (no verdict): the chart's VORP display `V_i` (VP-5.6) beside `A_i`.
4. **Expected points.** `P_i(s0)` = the points per game at which DDF's own projection pricing at
   `s0` gives the same Adjusted value. For each projection `j` in `I` (ESPN, CBS ROS, Razzball): from
   the same pipeline run, the pairs (native ppg, `adjusted`) of `j`'s priced players at position
   `p`, sorted by ppg, with `adjusted` made monotone by a running maximum; `P_ij` = the
   piecewise-linear inverse at `A_i`. Above `j`'s top player: linear extrapolation with the OLS
   slope of `adjusted` on ppg over `j`'s top 3 players at `p`. `P_i(s0)` = mean over `j` with a
   defined inverse. `A_i = 0`: not invertible (step 3), labelled `below_waiver`.
5. **History mix (each player's own).** From `data/inputs/weekly_actuals_2024_2026.csv` (every
   game row of seasons 2024, 2025 and 2026 weeks `1 .. w - 1`): receptions per game
   `rec_h = mean(ppr - std)` (exact for these scorings: the only difference is receptions) and
   non-reception points per game `std_h = mean(std)`. **Minimum 6 games.** Category detail (pass,
   rush, receiving yards and TDs, interceptions, receptions, targets) from Supabase
   `player_game_stats` 2024-2026, cached once read-only to `tools/research/jeg1610/cache/`, is
   shown for the extreme pairs and the coverage report; it reduces exactly to `std_h` and `rec_h`
   for Standard, Half and Full (fumbles are in `std`, not in that table).
   - **Fallback (labelled, counted per chart-week and position):** fewer than 6 games (rookies,
     injured, new players), no key match, or `std_h + r_s0 x rec_h <= 0`: the **position-level
     mix**, `q_p` = the median over that chart-week's priced players at `p` with a history mix of
     `rec_h / (std_h + rec_h)`; ratio `(1 - q_p (1 - r_s)) / (1 - q_p (1 - r_s0))`.
6. **Implied metrics.** `k_i = P_i(s0) / (std_h + r_s0 x rec_h)`; implied receptions per game
   `k_i x rec_h`, implied non-reception points `k_i x std_h` (and each category times `k_i` for the
   display). Uniform split: the chart's yield is spread over his categories in his own proportions.
7. **Rebuild each scoring through DDF.** `P_i(s) = k_i x (std_h + r_s x rec_h)` (`r_s` = 0, 0.5, 1).
   Back to the chart's units by the exact inverse of steps 2-4 at the anchor: per position, `g_p`
   = the piecewise-linear map through the invertible players' (`P_i(s0)`, `x_i`) pairs; above the
   top and below the lowest node, linear with the OLS slope over the top 3 and the lowest 3 nodes;
   floored at 0. Delta form for exact identity: `x_i(s) = x_i + g_p(P_i(s)) - g_p(P_i(s0))`.
   `below_waiver` players keep `x_i`. Then the **unmodified pipeline at `s`** with FantasyCalc's and
   FantasyPros' natives replaced by `x(s)` and CBS Sports and USA Today at their own column at `s`
   re-derives the allocation, waiver and starter lines, expected starts, `W`, the pie and every
   Adjusted value at `s`. **DDF Value v3** = its blended `ddf_value` (the equal-weight mean of the
   charts' Adjusted values, as DDF does).
   - *Variant, reported, no verdict (`v3_proj`):* skip `g_p`; price `P_i(s)` directly with the
     projections' maps at `s` (mean over `j` of the forward map from step 4, run at `s`) as the
     chart's Adjusted value at `s`, and average with CBS Sports' and USA Today's Adjusted values.

**Games.** DDF prices projections per game, and expected starts apply availability by position,
not by player, so **games do not enter v3** (unlike v1 and v2). The ESPN non-zero-weeks games
variant therefore has nothing to change; a unit test proves the v3 output is independent of the
games input, and the page says so.

**Prediction stated now (so it cannot be retrofitted).** Within a position `g_p` is monotone, so
v3's order at `s` is the order of `P_i(s0) x ratio_i` with `ratio_i` from history: the structure of
v2 with the history mix in place of the projected mix. Single-player history is at least as spread
as the projections' (regressed) mix, so **we expect v3 to fail G1 on within-position agreement**
for the same reason v1 and v2 did (moves about twice too large). What can differ is levels: v3
inherits the anchor `W` instead of re-deriving replacement in points, so it may do better than v2
on levels.

## 2. Anchors

| Chart | Anchor (primary) | Sensitivity |
| --- | --- | --- |
| CBS Sports, USA Today | used as published at every scoring (not adjusted) | n/a |
| FantasyCalc | its base list read as **Full** (assumed; `value == redraftValue` only at ppr=1, 12 teams) | its base list read as **Half** (pipeline at Half with the base list as its native) |
| FantasyPros | **Half** (assumed; its pages link to Half PPR) | none |

## 3. Tests and what counts as failing

### G1, the labelled gate L (runs first; stop rule)

Push CBS Sports' and USA Today's own Standard column through steps 2-7 to Full (anchor Standard),
and their Full column to Standard (anchor Full). Compare the rebuilt natives with the published
target column. Players and metrics exactly as the v2 L gate (`tools/research/jeg1605/l_gate.py`
`metrics`): the JEG-1601 player set listed by the chart at `> 0` in both columns; weeks 5-9.

Three measures, each against "unchanged" (the input column as is):
- **within**: within-position Spearman (RB/WR/TE averaged) with the target column; higher is better;
- **levels**: mean absolute log error of values against the target column; lower is better;
- **xpos**: whole-set Spearman with the target column; higher is better.

Cells = 2 charts x 2 directions x 3 measures = 12. **G1 passes only if v3 strictly beats
"unchanged" in at least 3 of 5 weeks in every one of the 12 cells.** No damping, no tuned
parameter. **Stop rule:** if G1 fails, v3 stops: G2 and G3 are still run as **descriptive** results
(Jeremy asked for them; they cannot rescue the verdict), no page draft and no steelman rounds are
made, and the results go to Jeremy as they are, with a patch for the review page.

Reported with G1 (no verdict): the L-mix extreme pairs (v2 definition, with mixed pairs chosen by
the **history** reception share); the same chain with the **projected** mix (v2's all-source mix)
in place of history, to isolate what history changes; the history-window variants (2026 only;
2015-2026 adding nflverse 2015-2023 totals via `sleeper_projection_idmap.csv`, receptions =
ppr - std); `v3_proj`.

### G2, chart-to-chart response (Jeremy accepted, 2026-11-10)

`tools/research/jeg1605/response_test.py` with `v3` added as a primary method, everything else as
pre-registered in `docs/research/jeg1605/response-preregistration.md` (sets, percentiles, mean
reference, bootstrap seed 16052, placebo seed 16053, levels k, extremes). **PASS / FAIL / NOT SHOWN
by its section 4 rule, applied to `v3`.** Within-position agreement at Standard and Full; the
Standard-to-Full move's `corr` **and** `closer` (size relative to the references' moves) and
`slope`; cross-position levels (c) verdict; shuffle placebo; leave-one-out.
- **Leave-one-out for v3** drops CBS ROS from `I` in the anchor and target runs (so from the
  projection maps and the allocation) **and** CBS Sports from `I` in the anchor run (so its natives
  do not enter `W` or the fill-in peers). The history mix has no CBS input.
- **Code check (changed from v1/v2):** v3's anchor run includes CBS Sports and USA Today at `s0`
  (they enter `W` and the fill-in peers), so their natives at `s0` can move v3's lists. The runner
  reports the largest change in any v3 list when CBS Sports' and USA Today's natives are shuffled
  within position at `s0`, and the leave-one-out above is the guard. No reference column at the
  target scoring enters any v3 list.

### G3, v3 DDF Value against current DDF Value

Both are the pipeline's blended `ddf_value` at `s` (current: today's natives; v3: section 1).
Because DDF averages CBS Sports and USA Today themselves, the **primary** comparison leaves the
reference out: for reference `R` in {CBS Sports, USA Today}, `DDF^-R` = the mean of the other three
charts' Adjusted values from the same run, scored against `R`'s published column. Measures as G2
(a), (b) and (c), players as G2's sets, the same bootstrap.

| Verdict | Rule |
| --- | --- |
| **better** | for both `R`: (a) at Standard `v3 - current` > 0 with the interval above 0, (a) at Full not below 0, and (b) `closer` difference not below 0 |
| **worse** | for either `R`: (a) at Standard or Full, or (b) `closer`, interval entirely below 0 |
| **not shown** | otherwise |

Robustness (each reported with the same statistics; a sign flip of the (a) Standard point estimate
is stated as "hinges on"): FantasyCalc anchored at Half; FantasyCalc dropped (v3 and current both
without it). ESPN games variant: not applicable (section 1, Games), proved by test.

**Secondary only (not the verdict):** realized points, JEG-1601 M1 and M2 (`step4_tests`) on
snapshots 5-8 realized through week 8, v3 DDF minus current DDF, at Standard and Full.

### History coverage (reported, not gating)

Per chart-week and position: priced players, players with a history mix (6+ games), fallback count
by reason (rookie / no rows, under 6 games, no key, non-positive anchor points); `below_waiver`
count; share of the G1/G2 scored sets on the fallback. Category data coverage of
`player_game_stats` by season and week (2026 weeks 5-8 are known to be partial).

### Unit and property tests (must hold before any test runs)

- Identity: `s = s0` returns every chart's input natives exactly (max abs diff < 1e-9), every
  chart-week, and the pipeline at `s0` then reproduces current DDF Value exactly.
- Steps 2-4: a synthetic projection priced through its own map returns its own ppg (inverse
  exact at the nodes); `P` is non-decreasing in `A` within a position.
- Scaling the pie, or every group of `W` by one constant, leaves `P` unchanged.
- A pure receiver (`std_h = 0`) anchored at Full gains nothing at Full and loses exactly his
  implied receptions per game, Full to Standard.
- An unlisted or 0-priced player gets no v3 value; a `below_waiver` player keeps his native.
- The v3 output does not depend on the games input.

## 4. Rules

- CBS Sports and USA Today are the reference, not truth; their Half column is the midpoint of
  Standard and Full, and they barely reorder within a position (0.99).
- No live FantasyCalc request: saved snapshots only (terms: `GET /values/current`, cached, 3 h per
  parameter set).
- Weeks 5-9 of 2026 only; five overlapping snapshots, not independent samples.
- No result is dropped. Negative and null results are reported.

## Changes after this commit

(none yet)
