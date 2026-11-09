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

(none yet)
