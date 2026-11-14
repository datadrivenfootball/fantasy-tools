# JEG-1601 step 4: pre-registered tests (written 2026-11-09, before any step 2-3 result)

Committed before the prototype exists, so the tests cannot be tuned to it.
Any change after this commit is logged at the end with its date and reason.

## What is being compared

| Label | What it is |
| --- | --- |
| `FC_raw` | FantasyCalc as published at the target scoring (its ppr switch: one constant per position). |
| `FC_corr` | FantasyCalc 12-team Full PPR base, anchored at Full PPR (option A of the FantasyCalc study), rescaled to the target scoring by the step 2 decomposition. |
| `FC_corr_half` | Same, anchored at Half (option B), sensitivity only. |
| `DDF_cur` | Current DDF Value (live method, VP-0 to VP-6) at the target scoring. |
| `DDF_new` | Step 3 proposal: charts without a column at the target scoring are rescaled by the step 2 decomposition before VP-2; everything else unchanged. |
| `DDF_new_noFC` | Step 3 with FantasyCalc excluded (option C), sensitivity only. |
| `PROJ` | Benchmark, not a contestant: mean projected points per game times expected games. |

Target scorings: Standard, Half, Full PPR. 12 teams, default roster, 1 QB.

## Benchmark (independent of DDF and of the charts)

Realized fantasy points at the target scoring, from `data/inputs/weekly_actuals_2024_2026.csv`,
summed over weeks `w` to 8 of 2026 for a snapshot taken in week `w` (`w` = 5, 6, 7, 8; week 9
actuals are incomplete). A player with no row in a week scored 0 that week. Small sample:
four overlapping windows of 4, 3, 2 and 1 weeks. Every result is labelled small-sample.

No chart snapshots exist before 2026, so no 2015-2025 back-test of the charts is possible.
A 2015-2025 **mechanism test** (M below) checks only the rescaling rule.

## Player set

Fixed before scoring, the same for every method: per snapshot week, the top 36 RB, 36 WR, 18 TE
and 18 QB by mean projected points per game at Half PPR (a neutral order no contestant owns).

## Metrics

- **M1, within position.** Spearman correlation between a method's value and realized points,
  per (week, scoring, position), averaged over weeks and positions (RB, WR, TE; QB reported
  separately).
- **M2, trade verdicts.** For every pair of players in the set (any positions), does the method
  order them the same way as realized points above replacement? Replacement per position = mean
  realized points of the players ranked `N_p` to `N_p + 6` by projected points (VP-2.3 band),
  `N_p` from the week's default-league allocation. Score = share of concordant pairs.
- **Uncertainty.** Paired bootstrap over players (2,000 resamples, seed 1597), 95% interval of
  the difference between two methods.

## Hypotheses and what counts as failing

| ID | Claim | Passes if | Fails if |
| --- | --- | --- | --- |
| H1 | `FC_corr` beats `FC_raw` at Standard and Half | M1 and M2 differences > 0 at Standard with the 95% interval above 0 | interval includes 0 (not shown) or is below 0 (correction hurts; the steelman wins) |
| H2 | `DDF_new` beats `DDF_cur` | M1 and M2 differences > 0 at Standard and at Full, interval above 0 | as H1; also fails as "not robust" if the sign flips between `FC_corr` and `FC_corr_half` anchors or with `DDF_new_noFC` |
| H3 | Attribution: `FC_corr` vs `DDF_new` | no pass/fail; reports which is closer to realized points and by how much | n/a |
| S | Steelman: FantasyCalc's flat scoring response carries market information | supported if the change `FC_corr - FC_raw` correlates negatively with the realized residual `realized - FC_raw` (the correction moves values away from realized points) | rejected if the correlation is positive with the interval above 0 |
| FP | First principles: a rescaled scoring-blind chart reorders within position between Standard and Full, in the right direction | at least 90% of within-position swaps in the top 36 move the player with the larger reception share up in Full | under 90% |
| L | Labelled check (charts as target, not independent): rescaling CBS Sports' and USA Today's own Standard column predicts their own Full column better than leaving it unchanged | Spearman with the published Full column higher than unchanged, both charts, most weeks | otherwise. Also reports the damping `λ` (0 = no change, 1 = full projection ratio) that fits CBS best, tested on USA Today |
| M | Mechanism, 2015-2025: rescaling a trailing Full PPR rate by trailing reception share predicts Standard rest-of-season points better than the unscaled rate | M1 difference > 0 with interval above 0, pooled over seasons | otherwise |

Rules:
- The primary claim "the scoring-aware DDF is stronger" needs H2 to pass. H1 passing alone
  supports only "the FantasyCalc correction helps".
- If `PROJ` beats every method, say so; it means realized points reward projections, which is
  not the same as trade value.
- Realized points are not market value. A pass says the values track what players scored at
  that scoring, not that a trade partner would accept them.
- No result is dropped. Negative and null results go on the page.

## Changes after this commit

- 2026-11-09, before any test was run: the step 2 builder found the literal inverse
  ("map back through the same fit") gives `native x ratio^b` with `b` about 2-5 on convex charts,
  moving FantasyCalc WR vs RB about 3.5 times the projections' own move. `DDF_new` and `FC_corr`
  therefore use the position-scaled mapping (each position's level moves as its projected points
  do; only a player's deviation from his position's ratio goes through the chart's curve). The
  literal variant is scored too, as `DDF_new_literal` / `FC_corr_literal`, under the same tests.
  Damping variants lambda 0.5 are reported as sensitivity; lambda 1 is primary.
- 2026-11-09, JEG-1601 test runner, made after the prototype existed but before seeing any
  test result (all choices below are coded in `tools/research/jeg1597/step4_tests.py` as first
  run; none was changed after the output appeared). Where the text above is silent or not
  implementable as written:
  - Labels: the literal variant is `*_samefit` in the step 3 files, lambda 0.5 is `*_l05`, the
    FantasyCalc Half anchor is `DDF_new_fchalf` / `FC_corr_half`.
  - `N_p`: replacement index of `value_reference.allocate` (base allocation, no seat-sigma mix)
    at the target scoring; band = 0-based ranks `N_p` .. `N_p + 6` by PROJ at the target scoring.
  - M2: pairs tied on realized points above replacement are not scored; a method tie counts half.
    M1 and M2 are averaged over snapshot weeks 5-8 with equal weight.
  - Bootstrap unit: a player (union of the four weekly sets, 130 players); his resample count
    applies to every week and scoring, so every comparison is paired.
  - H1 verdict uses Standard only, as the "passes if" column says; Half is reported as information.
  - H2 robustness: the sign of `DDF_new_fchalf - DDF_cur` and of `DDF_new_noFC - DDF_cur` is
    compared with `DDF_new - DDF_cur` for M1 and M2 at Standard and Full.
  - S: values and points are in different units, so all three quantities are ranks (share of
    the set). Primary: ranks across the whole player set, realized as points above replacement
    (the M2 target). Secondary: ranks within position against realized points. Supported needs
    the interval below 0; positive with interval above 0 rejects; otherwise not shown.
  - FP: charts FantasyCalc (anchor Full) and FantasyPros (anchor Half), rescaled to Standard and
    to Full, weeks 5-9 pooled, RB / WR / TE (a QB has no receptions), top 36 by the chart's own
    base list. Reception share = mean over the three projection sources of `(ppr - std) / ppr`
    per game (the rescale's ratio uses only Razzball / CBS ROS, so this is not the same number).
    Also reported: trailing 2026 realized reception share, and the rescale's own ratio (a
    tautology check that must read 100%).
  - L: within-position Spearman (RB / WR / TE, averaged) on the pre-registered player set,
    restricted to players the chart lists in both columns; weeks 5-9; "most weeks" = at least
    3 of 5. Lambda grid 0 to 2 in steps of 0.05, objective = mean over weeks. Whole-set Spearman
    is reported as secondary (it depends on the mapping mode; within position it does not).
  - M: per season 2015-2025, snapshot weeks 5-8; trailing = weeks 1 to `w - 1` per game played,
    at least 2 games; player set = top 36 RB, 36 WR, 18 TE by trailing Half ppg; target =
    Standard points weeks `w` to the last regular-season week, a missing week = 0. The rescale is
    `decompose.rescale_chart` with the trailing Full rate as the "chart" and as its own points
    (b = 1), which within position is the trailing Standard rate. Bootstrap unit = player id.
  - `PROJ_VAR` (projected points minus the projected mean of the same band) is added beside
    `PROJ` for M2 only, labelled not pre-registered: raw PROJ ranks every QB above every RB.
