# JEG-1605: scoring-aware DDF v2 (round trip), pre-registered tests

Written 2026-11-09, **before any v2 code or v2 result exists**. Research only: no change to
published numbers, the value model or the live pipeline. Any change after the commit that adds
this file is logged at the end with its date and reason. No tuning after results.

Jeremy, 2026-11-09: "The method needs to move from trade value, to VORP, to assumed games +
points, to assumed games + metrics, to scoring method, back up to assumed games and points, back
to scoring all players, to VORP, to trade values."

Jeremy, 2026-11-09 (via the lead): "At the stages that require being aware of the way the player
gets their points (i.e. a pass-catching RB) lean on the projections to show how the player's mix
is achieved."

Jeremy, 2026-11-09 (via the lead): "You need to know the scoring setting implied by each trade
chart to know how to break the player down. If FantasyCalc doesn't have it, we can't use
FantasyCalc or need to get to an assumed mix of scoring settings."

## 1. The chain (fixed before building)

Per chart `c`, week `w`, anchor scoring `s0`, target scoring `s`. Positions QB, RB, WR, TE.
12 teams, default roster (QB1 RB2 WR2 TE1 FLEX1, bench 7), 1 QB.

Inputs reused from v1 (`tools/research/jeg1597/rebuild_ddf.py`): history week natives, the three
projection sources' `ppg` triplets (ESPN, CBS ROS, Razzball), expected games `G_i` (CBS `gp`,
else schedule x (1 - miss_p)), and the allocation `N_p(s)` from `value_reference.allocate`
(base allocation) at each scoring.

1. **Trade value.** `x_i` = the chart's native at `s0`. A player the chart does not list, or lists
   at 0, has no price: an implied 0. He gets no v2 value at any scoring (he still counts in the
   replacement pool through his projection, stage 6).
2. **Invert to VORP.** Projected points `P_i(s0) = mean ppg_i(s0) x G_i` (mean over the sources
   that list him with ppg > 0). Projected replacement `Rproj_p(s0)` = mean `P` of 0-based ranks
   `N_p .. N_p + 6` of the projected-points order at `s0` (the VP-2.3 band). Projected VORP
   `V_i = P_i - Rproj_p`. The chart's **value-vs-VORP curve** is one power law per chart-week,
   `log x = a + b log V`, fitted on rank-matched pairs (the chart's k-th value against the k-th
   projected VORP **within each position**, top `FIT_TOP_N` per position, pairs with `V > 0`),
   pooled over the four positions. One curve per chart is the "one currency" reading: trade
   value is a function of value above replacement. Chart VORP `Vc_i = (x_i / e^a)^(1/b)`.
   *Sensitivity (reported, not gating):* one curve per position.
3. **Games plus points.** `Pc_i(s0) = Vc_i + Rproj_p(s0)`. Games `G_i` (as above).
4. **Games plus metrics, from each player's own projected mix.** Per source `j` that lists him,
   the per-game stat line at `s0` is `std_ij` (all non-reception points) plus `rec_ij`
   (receptions per game = ppr - std, exact for these scorings: v1 matched Razzball `pg_rec` on
   570 of 570). The player's mix is the mean over **all three** sources that list him (ESPN,
   CBS ROS, Razzball, equal weight). The chart's per-game metrics are the projected line scaled
   by one factor `k_i = Pc_i(s0) / (G_i x ppg_proj_i(s0))` so the anchor points reproduce the
   chart's yield exactly (**uniform split**, primary). A player no source lists takes his
   position's median line (fallback, labelled, counted per chart per week).
   - Games versus rate: scaling games or scaling every per-game metric by `k_i` give the same
     points at every scoring. They are not separately identifiable, and under the uniform split
     the choice does not change any result. Stated, not tested.
   - *Pre-registered alternative split (reported, not gating):* **additive**: receptions per
     game as projected; the chart's excess over the projection sits in non-reception points.
   - Full stat lines (rush/rec/pass yards and TDs, turnovers) from Razzball `pg_*` and CBS ROS
     `raw_stats` are pulled for the mix display and for a TE-premium example; for Standard,
     Half and Full they reduce exactly to the reception term, so the tests below need only it.
5. **Apply the target scoring.** `ppgc_i(s) = k_i x (std_i + r_s x rec_i)` with `r_s` the
   reception weight (0, 0.5, 1; TE premium adds 0.5 at TE). Any scoring dict over the metric
   vector is accepted by the code.
6. **Rebuild games plus points for every player at `s`.** Chart-priced players: `Pc_i(s) =
   G_i x ppgc_i(s)`. Everyone else in the pool (unlisted or 0): projected `P_i(s)`.
7. **Re-derive replacement and recompute VORP.** `R_p(s)` = mean rebuilt points of 0-based ranks
   `N_p(s) .. N_p(s) + 6` of the rebuilt points order at `s` (rank and `N_p` both re-derived at
   `s`). `R_p(s0)` = the same rule on the stage-3 points. VORP at `s`:
   `Vc_i(s) = Vc_i + [Pc_i(s) - Pc_i(s0)] - [R_p(s) - R_p(s0)]`. Written as changes so that at
   `s = s0` the chain returns every input value exactly (identity test, section 4).
8. **Back to trade value.** `x_i(s) = e^a x max(Vc_i(s), 0)^b`, the same curve as stage 2.

**What v1 did instead (to be evidenced in the results doc):** v1 fitted value against projected
*points* (not VORP), so a whole position's points change went through the chart's convexity
(`b` 2-5), overshooting about 3.5x; it then patched this with `position_scaled` (each position's
level moves by its median points ratio). It never re-derived the replacement level at the new
scoring, and the allocation `N_p` never moved with scoring inside the rescore. v2 replaces the
patch with the replacement re-derivation.

**Prediction stated now (so it cannot be retrofitted):** within a position, stages 6-8 cannot
change the order (a per-position shift and a monotone curve). So within-position order at `s` is
the order of `Pc_i(s0) x ratio_i`, which is close to v1's lambda-1 rescale. v1 failed L on that
(1 of 5 weeks). **We expect v2 to fail the L gate.** Stages 6-8 can matter only for cross-position
levels (L-level and L-xpos below, and H2's M2).

## 2. Anchors are a parameter, as a distribution over settings

Each chart's anchor is a weight vector over {Standard, Half, Full}. The chain runs once per
setting with positive weight; the output value is the weighted mean of the per-setting outputs,
and the per-player interval is their min to max.

| Chart | Anchor | Basis |
| --- | --- | --- |
| CBS Sports, USA Today | their own column, weight 1 | published per format |
| FantasyCalc | **primary: Full 1.0** (its label: `value == redraftValue` only at ppr=1, 12 teams). Variants: Half 1.0; Half/Full 0.5/0.5; estimated mix (below) | `fantasycalc-pegged-or-blend.md` |
| FantasyPros | **primary: Half 1.0** (assumed; it states no scoring). Variants: Standard 1.0; Full 1.0; thirds; estimated mix | step 1 |

**Anchor estimator, one more try (a signal step 1 did not use).** Step 1 read within-position
order only and failed (3 of 20). Here: for a list and each candidate `s0`, fit the stage-2 pooled
curve and record its residual SD in log value pooled over positions (cross-position levels, the
signal the one-currency curve uses). The best `s0` is the lowest residual. **Calibration bar,
fixed now:** on the 20 labelled lists (CBS Sports and USA Today, Standard and Full columns, weeks
5-9) it must name the true column in at least 16 of 20, with no Standard read as Full or the
reverse. If it passes, a chart's **estimated mix** = the share of weeks 5-9 in which each setting
wins (week-to-week stability as the distribution). If it fails, the estimated mix is "not
identified" and that variant is not run. Also reported, no verdict: per-position level ratios of
the chart against projected VORP at 0/0.5/1, and FantasyCalc's 2026-09-29 and 2026-11-07
captures through the same estimator.

**Decision rule (stated on the page):** if any pre-registered verdict (L-style or H2), or the sign
of the H2 point estimate on M1 or M2 at Standard or Full, differs between the anchor variants of a
chart, the results **hinge** on an anchor we cannot pin down: we recommend excluding that chart
from the enhanced DDF (Jeremy decides; what is lost is stated: FantasyCalc is the only chart with
league-size and 2QB settings and the best single performer in JEG-1565). If they do not differ, we
keep it with the assumed mix disclosed.

## 3. Tests and what counts as failing

Player set, metrics and bootstrap as v1 (`docs/research/jeg1597/step4-preregistration.md`):
top 36 RB, 36 WR, 18 TE, 18 QB by mean projected Half ppg per snapshot week; M1 within-position
Spearman (RB/WR/TE averaged, QB separate); M2 cross-position pair concordance against realized
points above replacement; paired player bootstrap, 2,000 resamples, seed 1605.

### L, the labelled gate (runs first)

Rescore CBS Sports' and USA Today's own Standard column to Full, and their Full column to
Standard, through the chain (anchor = the input column's label). Compare with the published
target column. Players: the set above, listed by the chart in both columns. Weeks 5-9.

| ID | Measure | Passes if |
| --- | --- | --- |
| **L (gate)** | within-position Spearman (RB/WR/TE averaged) with the published target column, chain vs "unchanged" (the input column as is) | chain higher in **at least 3 of 5 weeks, for each chart and each direction** (4 cells). No damping, no tuned parameter. |
| L-xpos | whole-set Spearman, same comparison | reported, no verdict |
| L-level | mean absolute log error of values vs the published target column (players with value > 0 in both), and each position's median value ratio target/input, chain vs published | reported, no verdict |
| L-mix | mix-aware vs position-level rescore (every player at a position takes that position's median ratio). Within position the position-level rescore equals "unchanged" by construction, so L itself is this test. Added: pair concordance with the published target column on **mixed pairs**: RB pairs where one back is in the top third of the set's RBs by projected reception share `rec / ppg_full` and the other in the bottom third; same for TE | reported per chart, direction and week; "mix-aware helps" if higher in at least 3 of 5 weeks in all 4 cells |
| L-source | the chain run with each single source's mix (ESPN only, CBS ROS only, Razzball only) | reported; the spread of `ratio_i` across sources is carried as each player's interval |
| L-split | additive split and per-position curves | reported, no verdict |
| L-anchor | CBS Sports and USA Today Standard column run as if anchored at Half (a one-step wrong anchor) | reported: what a wrong anchor costs on charts where the truth is known |

**Stop rule (Jeremy, 2026-11-09):** if L fails, v2 stops there. H and M are not run, no page or
steelman round is made, and the results are reported to Jeremy as they are.

### H, versus current DDF Value on realized points (only if L passes)

`DDF_v2` = the live pipeline (`value_reference.run_pipeline`, unmodified) with FantasyCalc and
FantasyPros natives at `s` replaced by their v2 chain output; CBS Sports and USA Today read their
own column at `s` (as today). `DDF_cur` = current DDF Value (reproduces live exactly, v1).

| ID | Claim | Passes if |
| --- | --- | --- |
| H1 | `FC_v2` beats `FC_raw` | M1 and M2 differences > 0 at Standard, 95% interval above 0 |
| H2 | `DDF_v2` beats `DDF_cur` | M1 and M2 > 0 at Standard and at Full, intervals above 0, **and** no sign flip under the FantasyCalc anchor variants, the FantasyPros anchor variants, or dropping FantasyCalc (`DDF_v2_noFC`) |

Data: snapshot weeks 5-8, realized through week 8: **small-sample, exploratory**. The runner takes
`--first-week` and `--last-week` so the **clean out-of-sample test** is snapshots 10 onward
scored on realized weeks 10 onward, rerun when that data arrives; that run decides H.

### M, the mechanism over 2015-2025 (only if L passes)

As v1 M (trailing weeks 1 to `w - 1`, snapshots 5-8, at least 2 games, nflverse totals, receptions
= ppr - std), with the chain in place of v1's rescale: trailing Full points as the "chart" at
`s0` = Full, chain to Standard, target = Standard rest-of-season points. `N_p` from the 2026 week-9
default allocation at each scoring (constant across seasons; an approximation, labelled).

| ID | Passes if |
| --- | --- |
| M-within | M1 (chain vs the unscaled trailing Full rate) > 0, interval above 0. Within position this is v1's M by construction; expected to fail as v1 did (-0.071). |
| M-xpos | M2 (cross-position pair concordance vs realized Standard points above replacement) of the chain > unscaled trailing Full VORP (Full replacement), interval above 0 |

### Unit and property tests (must hold before any test runs)

- Identity: `s = s0` returns every input value exactly (max abs diff < 1e-9), every chart, week.
- A pure receiver (all points from receptions) gains exactly 1 point per projected reception per
  game times games, Standard to Full, before stage 7.
- A position-wide uniform points change with the pool moving the same way leaves VORP scaled by
  the same factor (no `b` amplification).
- An unlisted player gets no v2 value.

## 4. Rules

- Realized points are not market value. L measures agreement with publishers, not truth.
- No result is dropped. Negative and null results are reported.

## Changes after this commit

**2026-11-09, implementation readings, all decided and coded before any L, estimator or
descriptive result was looked at** (`tools/research/jeg1605/roundtrip.py`, `l_gate.py`). No
pre-registered choice is changed; each entry is the most literal reading where the text did not
pin the code down.

1. *Rank matching (stage 2).* Per position: the chart's listed players (`x > 0`) that have a
   projected VORP; their top `FIT_TOP_N` by value; the k-th largest value against the k-th
   largest VORP among those same players (v1's convention); pairs with `V <= 0` dropped after
   matching. Pooled OLS of `log x` on `log V`.
2. *Residual SD (estimator).* `sqrt(SSE / (n - 2))` of that pooled fit. Ties (never expected)
   break Standard, Half, Full in that order.
3. *"Sources that list him" (stage 4 mix).* A valid triplet with Full points `> 0`, so the mix
   does not depend on `s0` and a pure receiver is listed. `P_i` keeps v1's `ppg(s0) > 0` rule.
4. *Uniform split with no anchor points.* When a player's own mix line has `ppg(s0) <= 0` (a pure
   receiver anchored at Standard), `k_i` is undefined; he takes the position median line,
   counted separately from the no-source fallback (`zero_anchor_line`).
5. *Position median line.* Median `std` and median `rec`, taken separately, over the chart's
   priced players at the position that have a mix (in that variant's sources).
6. *Delta form.* Stages 5-6 are coded as `Pc(s) = Pc(s0) + [change]` and stage 8 as
   `x_i (Vc_i(s) / Vc_i)^b`, algebraically identical to `e^a Vc_i(s)^b` (since `x_i = e^a Vc_i^b`)
   but exact in floating point at `s = s0`; the closed form misses the 1e-9 bar on values near
   10,000.
7. *Pure-receiver property test.* Under the uniform split a pure receiver anchored at Standard
   has no points to scale (entry 4), so the "1 point per projected reception per game times
   games" test runs under the additive split (exact), plus a uniform-split test that every
   player gains `G x` (the chart line's receptions, `k_i x rec_i`) Standard to Full.
8. *Per-position curves (L-split).* A position with fewer than 8 pairs or `b <= 0` uses the
   pooled curve (flagged).
9. *L player list.* "Listed by the chart in both columns" = value `> 0` in both (USA Today lists
   some players at 0, which section 1 treats as no price). "Chain higher" is strict.
10. *L-mix.* Thirds = `floor(n / 3)` of the L players at RB (and at TE) by the all-source mix's
    `rec / (std + rec)`; mixed pairs = top third x bottom third. Pairs tied on the target are not
    scored; method ties count half. The "mix-aware helps" label uses RB and TE pairs pooled; RB
    and TE are also reported separately. Mix-aware vs position-level = chain vs unchanged (equal
    within position, as the spec says).
11. *L-source.* Each single-source run changes only the mix (stage 4); `P`, VORP and the curve
    keep all three sources. A player that source does not list takes that source's position
    median line (counted as fallback).
12. *L-anchor.* The Standard column anchored at Half is rescored to Full (vs published Full) and
    to Standard (vs published Standard), each beside the correctly anchored chain.
13. *Full stat lines (stage 4 display).* Not pulled: no display is built in this step and the TE
    premium example reduces exactly to the reception term. `N_p` at TE premium = Full's.
14. *Captures.* FantasyCalc 2026-09-29 (week 4 cache) uses the week-4 history projections and
    allocation (the nearest, captured 2026-10-01..03); 2026-11-07 and 2026-11-09 use week 9.
    2026-11-09 = the 12-team 1QB `value` columns at ppr 0, 0.5, 1. Descriptive: the ppr 1 column
    through the chain (primary anchor Full) compared with FantasyCalc's own ppr 0 / 0.5 columns.
15. *Estimated-mix variant.* Run only if the 20-list calibration passes (section 2).
16. *Python.* The brief's venv (`/private/tmp/claude-501/venv1586`) has no numpy; the v1 metric
    code needs it, so tests and runs use `/usr/bin/python3` 3.9.6 (numpy 2.0.2, scipy). The
    round-trip module itself is standard library only.
