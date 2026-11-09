# JEG-1600 (step 3 of JEG-1597): scoring-aware DDF, prototype and proposal

Research prototype. No published number, value-model file, engine or pipeline
changed. The prototype calls `pipelines/value_reference.py` as an unmodified
library: `run_pipeline`, `Setting`, `History`, `snapshot_natives`. Runner:
`tools/research/jeg1597/rebuild_ddf.py` (about 35 s). Model: `step2-decomposition.md`.
Written 2026-11-09.

## 1. What was built

12 teams, default roster (QB1 RB2 WR2 TE1 FLEX1, bench 7), 1 QB; Standard, Half
and Full PPR; content weeks 5-9. Each week runs on its own history snapshot
(`data/history/week-<w>.json`: chart natives and projection ppg), the same way the
reference prices a prior week (VP-8). The included set and the held (hidden)
sources are the live week 9 state: all 7 sources in the pipeline, ESPN and
Razzball hidden from the blend, USA Today on an amber hold.

`out/rebuild_values.csv` has `week, scoring, player_key, name, pos, method, value`.
A missing row means the value is 0 or not priced; zeros are dropped to keep the
file small.

| method | What it is |
| --- | --- |
| `DDF_cur` | Live method, each chart's saved column at the scoring |
| `DDF_new` | FantasyCalc base (Full) and FantasyPros (assumed Half) rescaled to the scoring, position_scaled, `lambda` 1; CBS and USA Today unchanged |
| `DDF_new_l05` | Same, `lambda` 0.5 |
| `DDF_new_fchalf` | FantasyCalc anchored at Half (sensitivity) |
| `DDF_new_noFC` | FantasyCalc excluded from I (option C) |
| `DDF_new_samefit` | The brief's literal inverse (`native x ratio^b`), for step 4 to score |
| `FC_raw` / `FC_corr` / `FC_corr_l05` / `FC_corr_half` / `FC_corr_samefit` | FantasyCalc's Adjusted value in the matching run |
| `FP_raw` / `FP_corr` / `FP_corr_samefit` | FantasyPros' Adjusted value in the matching run |

### Reproduction of current DDF

`DDF_cur` built from the history snapshots equals the live reference exactly:
**max abs diff 0.0** on all 662 week-9 rows (against `Setting.result()` on
`data/fixtures/current`) and on all 683 week-8 rows (against the reference's own
`Setting.prior_result()`), at all three scorings. This is pinned by
`test_ddf_cur_reproduces_live_reference_week9`. The reference itself agrees with
the engine to 0.05 (`value_check compare`), so this stands for the live site
numbers. The live site was not queried.

## 2. Pipeline interface (VP-2 to VP-6)

One new step, **VP-1.6 chart rescore**, between reading natives (VP-0) and VP-2.
Every later step is unchanged and still sees "a native list per chart".

- **Inputs:** each chart's anchor list (FantasyCalc: its ppr=1, 12-team base per QB
  count, superflex overlay included; FantasyPros: its one list), the week's
  projection triplets (already in `players.json` and history `ppg`), expected
  games (CBS gp, else schedule x (1 - miss_p)), the reader's scoring, `lambda`,
  and the mapping mode.
- **Output:** natives at the reader's scoring, per player `rescored: {ratio,
  basis, spread}`, and per chart-position `{b, k_p, n, r2, identifiable}`.
- **VP-2:** the allocation and projected-points order are untouched. Waiver and
  starter lines, and the fill-in (VP-2.4), read the rescored natives. Peers in
  the ratio path use the rescored lists, so estimates follow the same scoring.
- **VP-3 / VP-4 (position weights):** this is where the change acts. A rescored
  chart's group totals move by position. For example, FantasyCalc at Standard
  loses about 35% of its WR level and 40% of its TE level against its saved
  column. That moves its mix and, through the average, the DDF weights used to
  split the pie for **every** source, including CBS and USA Today. Week 9 DDF
  weights, Standard, cur to new: QB starter 8.1% to 8.6%, RB starter 51.0% to
  51.6%, WR starter 27.5% to 26.8%, TE starter 6.5% to 6.1%. At Full PPR they
  barely move: RB starter 38.8% to 38.7%, WR starter 39.7% to 39.9%. FantasyCalc's
  base is Full, so only FantasyPros moves there.
- **VP-5 / VP-6:** the pie is unchanged. Adjusted values, DDF Value and the
  counts are computed as today. Indexed (VP-6.4) keeps one factor per chart
  applied to the rescored natives, so a rescored chart's Indexed order can differ
  from the publisher's within a position. The display must say so (section 4).
- **VP-8:** the prior week applies the same rescore to the prior week's natives
  and the prior week's projections. Nothing from the current week enters.
- **Two implementations:** the engine (`value-model.js`) and both Python
  references have to carry VP-1.6, so that `value_check compare --strict` keeps
  agreeing. This is a value-math change that ships alone.

## 3. Flag and fallback

- `setting.scoring_rebuild` (default **off**), plus `scoring_rebuild_lambda` and
  `scoring_rebuild_mode`. Off reproduces today bit for bit, which is
  `lambda = 0` (tested).
- **Fallback when not identifiable:** a chart-position with fewer than 8 shared
  players, or a slope that is not positive, keeps its natives (`lambda` 0) and
  shows the label "shown at its published scoring (not adjusted)". A player with
  no projection line takes his position's median ratio, labelled "estimated
  scoring adjustment". In weeks 5-9: no non-identifiable position, and 0-2
  median-ratio players per chart per week.
- Charts with a published column at the reader's scoring (CBS, USA Today) are
  never rescored. FantasyCalc at Full, and FantasyPros at Half, are unchanged by
  construction.

## 4. User disclosure (proposed wording)

On a rescored chart's column header and tooltip:

> **Adjusted to your scoring.** FantasyCalc publishes one list (12-team, Full PPR). We
> rescored it to {Standard} using projected receptions: each player's value moves by
> how much his projected points change, at {100%} of the projections' change. The
> publisher did not make this column. Its order can differ from the publisher's.

For FantasyPros: "FantasyPros does not state a scoring; we assume Half PPR and
rescore from there." On DDF Value: "Includes 2 charts adjusted to your scoring
(FantasyCalc, FantasyPros)." On a fallback: "Shown at its published scoring (not
enough shared players to adjust)."

## 5. Week 9 old vs new (DDF_new, position_scaled, lambda 1)

**Position share of total DDF Value**

| Scoring | Method | QB | RB | WR | TE |
| --- | --- | --- | --- | --- | --- |
| standard | DDF_cur | 8.4% | 55.8% | 29.0% | 6.8% |
| standard | DDF_new | 8.9% | 56.5% | 28.2% | 6.4% |
| standard | DDF_new_l05 | 8.7% | 56.1% | 28.6% | 6.6% |
| standard | DDF_new_fchalf | 8.8% | 56.1% | 28.6% | 6.5% |
| standard | DDF_new_noFC | 8.1% | 57.1% | 28.2% | 6.6% |
| standard | DDF_new_samefit | 9.8% | 59.1% | 26.0% | 5.1% |
| half_ppr | DDF_cur | 8.1% | 47.7% | 36.6% | 7.6% |
| half_ppr | DDF_new | 8.3% | 48.2% | 36.1% | 7.5% |
| half_ppr | DDF_new_noFC | 7.5% | 48.6% | 36.2% | 7.7% |
| ppr | DDF_cur | 7.5% | 41.8% | 42.6% | 8.0% |
| ppr | DDF_new | 7.3% | 41.7% | 42.9% | 8.1% |
| ppr | DDF_new_noFC | 6.7% | 41.9% | 43.1% | 8.3% |

Weeks 5-8 at Standard show the same pattern: WR down 0.9-1.2 points and TE down
0.4-0.6 points of share, with RB and QB up.

**Top movers (DDF Value, cur to new)**

| Scoring | Up | Down |
| --- | --- | --- |
| standard | James Cook RB 66.7->71.1, Derrick Henry RB 39.2->43.7, Kenneth Walker III RB 77.4->80.4, Josh Allen QB 35.8->38.2, Ollie Gordon II RB 26.3->28.2 | Trey McBride TE 26.1->20.4, Puka Nacua WR 51.9->47.7, Chase Brown RB 31.8->28.1, Ashton Jeanty RB 27.5->24.1, Amon-Ra St. Brown WR 40.5->37.3 |
| half_ppr | James Cook RB 61.3->62.9, Derrick Henry RB 34.8->36.4, Kenneth Walker III RB 72.1->73.3, Josh Allen QB 34.7->35.5, Jonathan Taylor RB 51.2->52.0 | Trey McBride TE 29.0->27.2, Puka Nacua WR 58.8->57.2, Amon-Ra St. Brown WR 46.6->45.4, Malik Nabers WR 42.4->41.2, Ja'Marr Chase WR 52.7->51.6 |
| ppr | Trey McBride TE 30.7->31.8, Chase Brown RB 25.1->25.9, Ashton Jeanty RB 22.4->23.2, Puka Nacua WR 63.4->64.0, Germie Bernard WR 3.9->4.4 | James Cook RB 54.5->53.6, Josh Allen QB 32.3->31.5, Derrick Henry RB 30.2->29.5, Joe Burrow QB 24.7->24.1, Drake Maye QB 21.5->20.9 |

Pass-catching backs (Chase Brown, Ashton Jeanty) fall at Standard and rise at Full
within RB, as the receptions term says they should. Example at Standard: Trey
McBride's FantasyCalc Adjusted goes from 32.6 (`FC_raw`) to 18.7 (`FC_corr`); it
is 23.0 at the Half anchor and 14.9 under same_fit.

**Top-36 within-position reorders after the rescale** (pairs whose order differs
from the chart's published column at that scoring; in brackets, the median
native multiplier against that column)

| Scoring | Chart | QB | RB | WR | TE |
| --- | --- | --- | --- | --- | --- |
| standard | FantasyCalc | 0/595 (x1.01) | 35/630 (x0.82) | 30/630 (x0.65) | 14/378 (x0.59) |
| standard | FantasyPros | 0/496 (x1.00) | 15/630 (x0.91) | 26/630 (x0.78) | 4/190 (x0.75) |
| standard | DDF Value top 36 | 0 | 16 | 16 | 4 |
| half_ppr | FantasyCalc | 0/595 | 17/630 (x0.91) | 9/630 (x0.82) | 5/378 (x0.81) |
| half_ppr | FantasyPros | 0 (anchor) | 0 | 0 | 0 |
| half_ppr | DDF Value top 36 | 0 | 1 | 1 | 0 |
| ppr | FantasyCalc | 0 (anchor) | 0 | 0 | 0 |
| ppr | FantasyPros | 0/496 | 11/630 (x1.09) | 13/630 (x1.22) | 1/190 (x1.25) |
| ppr | DDF Value top 36 | 0 | 3 | 1 | 0 |

Within position the change is small (at most 5.6% of pairs, FantasyCalc RB at
Standard). The material effect is the level by position, as step 1 predicted.

## 6. Options

- **A (recommended): VP-1.6 behind `setting.scoring_rebuild`, default off**, in
  position_scaled mode, with FantasyCalc anchored at Full and FantasyPros at
  assumed Half. Ship it on only if step 4's H2 passes. Set `lambda` from step 4's
  pre-registered L fit on CBS (checked on USA Today), not by hand; if L gives
  about 0, the right answer is B. Disclose per section 4.
- **B: status quo** (`lambda` 0). No new error, but FantasyCalc and FantasyPros
  stay scoring-blind at Standard. WR and TE keep about 0.8 and 0.4 points more
  DDF Value share at Standard in week 9 than the rescored version gives them
  (0.9-1.2 and 0.4-0.6 in weeks 5-8; section 5).
- **C: rescore FantasyPros only, and exclude FantasyCalc from the scoring-aware
  DDF.** `DDF_new_noFC` shows the cost: QB share falls 0.3-0.8 points at every
  scoring against `DDF_cur`. FantasyCalc was the best-performing chart in the
  JEG-1565 tests, and it is the only source with 2-QB and league-size
  settings.

## 7. Decisions for Jeremy

- **D1 mapping mode.** A: position_scaled, where the position level moves like its
  projected points (recommended; section 2 of the step 2 note). B: the literal
  same_fit, which amplifies WR and TE moves by the chart's convexity (WR share
  -3.0 points and TE share -1.7 points at Standard, about 3.5 times the
  projections' cross-position move). Both are in the outputs for step 4.
- **D2 lambda.** A: take it from step 4's L fit (recommended). B: 1 (the full
  projection move). C: 0.5.
- **D3 FantasyCalc anchor.** A: Full, its own label (recommended). B: Half
  (minimax). C: exclude. Step 4 checks whether H2's sign holds across all three.
