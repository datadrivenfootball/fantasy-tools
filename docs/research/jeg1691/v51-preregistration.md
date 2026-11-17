# JEG-1691 v5.1: pre-registration of the one more round (first written 2026-11-17; redesigned 2026-11-17 on Jeremy's answers)

Status: **draft for review. No v5.1 code exists and nothing has run.** Jeremy chose outcome B for
v5 on 2026-11-17, and this is the "one more pre-registered round" of v5's section 5. The first
version (878582a0e) gated on chart weeks 11-12. Jeremy's answers of 2026-11-17 (quoted in
"Frozen decisions") replace that with a **backtest on historical actuals**. The locked v5 files
(`DECISIVE.lock`, `out/decisive/`, v5's executed tree) are not touched. Research only, nothing
published. Jeremy, 2026-11-16: "Don't mess with the current architecture, we are exploring an
enhanced value, not doing a cutover."

Nothing in sections 2-6 changes after the first backtest number is printed. Any change before that
is appended at the end, dated, with its reason.

---

## Summary for a fantasy manager

- **What failed in v5.** When a league moves from Standard to Full PPR, v5 moved wide receivers
  about a quarter as far as ESPN's and Sleeper's stat lines say they should. The cause: v5 pulled
  each receiver's catch share hard toward the average receiver, so every receiver looked alike.
- **Jeremy's answer.** The catch share should reflect the player's own history. Pull toward the
  average only as much as the data prove is needed for very small samples.
- **How it is tested now: a backtest, not future weeks.** For every season from 2017 to 2025, we
  stand at weeks 5, 9 and 13. From each player's past games we predict his catches per point over
  the next four weeks, then compare with what he actually did. Four rules are compared:
  - his raw history;
  - v5's heavy pull;
  - the new light pull, set by testing on earlier seasons only;
  - the position average.

  A second check rebuilds whole stat lines (yards, touchdowns, catches) from points for 2025, and a
  fake version that hands each player someone else's history is the control.
- **What can happen.** This is the last round.
  - **C:** the light pull predicts better than the position average at running back, receiver and
    tight end, is not worse than v5's, and is well calibrated. A separate, labelled scoring-aware
    value can then be designed next to DDF Value.
  - **A:** otherwise. Keep DDF Value as it is.
- **Charts.** The chart tests (T4-T8) are re-run only to describe what happens, on the chart weeks
  that exist (2026 weeks 5-10). No chart snapshots exist before 2026, so the charts themselves
  cannot be backtested.
- **What the backtest cannot settle.** It tests the stat-mix step only. Whether a chart's value
  really stands for a points forecast (issues 8, 16), and which scoring FantasyCalc and FantasyPros
  assume (issue 10), stay open.

---

## 1. Diagnosis (read-only; dev weeks 5-7, actuals and structure only)

No weeks 8-10 chart-test number was used to choose anything here. Script:
`tools/research/jeg1691/diag/v51_fp_wr.py` (dev weeks only). The one actuals check marked (*)
below reads realized games from 2026 weeks 6-10. Those are game outcomes, not v5 test results,
and they set no threshold; it is disclosed because weeks 8-10 actuals enter it.

| Candidate cause | Evidence | Reading |
| --- | --- | --- |
| FantasyPros is a rank ladder (the same value sequence every week), so the delta form carries little response | Ties in the anchor Adjusted value: 3% of FantasyPros WRs. The delta form takes its response from the pseudo-source's pricing of `P_i(s)`, not from the ladder. With the position mix (`k = inf`), FantasyPros WR moves are exactly 0, as the algebra requires (no mix difference, so no reorder). | Not the cause. |
| DDF's position-total weights `W` | They set position levels (T6), not within-position percentiles. T5 is within position. | Not the cause of T5; they are the reason T6 is near-mechanical. |
| The Half anchor reading | S-FP-Full (dev): FantasyPros WR ratio 0.28, against 0.24 at Half. S-FC-Half: FantasyCalc WR drops from 1.02 to 0.57. | Not the cause for FantasyPros. The anchor decides whether a floor artifact (next row) hides the cause. |
| A floor artifact at FantasyCalc | At its Full anchor, 20-22 of 66-70 FantasyCalc WRs are floored at 0 in Standard, which ties them. The position-mix rebuild (no mix variation) still has a move SD of 0.125-0.146, against v5's 0.126-0.146. Without the floored players, FantasyCalc's WR ratio is 0.32-0.42 on dev. | FantasyCalc's WR pass was the floor, not the mix. Both charts share the real failure. |
| **The WR reception share and its shrinkage** | SD of receptions per anchor point, WR common set (dev): v5 0.006-0.010, raw history 0.055-0.095, ESPN+Sleeper 0.033-0.060. Correlation of v5 with the reference is 0.80-0.85. Step 5 chose WR `k_rec = 64` with half-life 8 (weight about 0.16 on the player). (*) Against realized weeks 6-10 receptions per point, from the week 5 snapshot, WR n = 102: the slope of realized on v5 is 4.85, on ESPN 0.25, on Sleeper 0.63; correlation 0.34, 0.13, 0.24. | **The cause.** v5 orders WRs' reception shares best of the three but compresses their scale about 5x. A slope of 4.85 means it is over-shrunk against outcomes, not only against the projectors. |
| Is there more WR signal to find? | 2025 actuals, WRs with at least 10 games, split-half (odd vs even games): receptions per point r = 0.26, targets per point 0.29. Standard ppg level against receptions per point: -0.08. | Neither a targets prior nor a level prior adds signal for WRs. The fix has to be in how hard step 5 shrinks, not in a new predictor. |

Why step 5 over-shrank WR receptions: v5 chose every category's strength with one objective `S`
summing standardised errors over all seven categories. It searched category by category, with the
mix renormalised at each step. Receptions are one term of seven, and for WRs the yards and TD terms
dominate. So `S` cannot see that the presets respond only to receptions per point.

What would distinguish this from "the projectors are over-dispersed": the calibration slope of
realized on predicted receptions per point on historical actuals. A v5 slope well above 1 confirms
over-shrinkage. The backtest reports it for every rule (B3, with Rv5 beside RL), on 2017-2025
evaluation seasons that no diagnosis used.

## 2. The change (step 5, the catch share): a light, data-justified shrinkage

The catch share is `q_i` = receptions per Half-PPR point, the only quantity DDF's three formats see
(v5 section 1, algebra). Four rules predict it from a player's games before the origin:

| Rule | Definition |
| --- | --- |
| **RL (light, the v5.1 rule)** | `q_i = a_i q_raw,i + (1 - a_i) q_pos`, with `a_i = n_i / (n_i + k_p)`. `n_i` = the player's history games, all weighted equally (no recency weighting: "the player's historical mix"). `k_p` per position comes from the light grid `G_L` = {0, 0.5, 1, 2, 4, 8} (decision D-a), chosen by nested forward CV (2.2). Ties go to the **smaller** `k`, the lighter pull. |
| R0 (raw history) | `k = 0`: the player's own history only |
| Rv5 (v5 shrunk) | v5's frozen choices from `out/decisive/selection.json` (RB `k_rec` 8, half-life 17; WR 64, 8; TE 2, 8), applied to the catch share |
| Rpos (position average) | `k = inf`: the games-weighted mean `q` of the position's players with at least 8 history games |

Shared rules:
- Players with no history get `q_pos` under every rule. They are counted and excluded from the
  comparison, since every rule gives them the same prediction.
- A game is a row with nonzero Standard or PPR points.
- History runs from 2015 to the week before the origin.

### 2.1 Data

- **2015-2025:** `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`.
  - 61,977 player-weeks, with gsis id and position.
  - Points by format only, so receptions = PPR minus Standard points, exactly.
  - Identity is the gsis id, so the backtest needs no player_key and the 59.4% idmap does not limit
    it.
- **2024-2025 per-stat lines (B5 only):** the committed `player_game_stats` cache
  (`tools/research/jeg1691/cache/pgs_weekly_2024_2026.json.gz`), rows of 2024-2025 only.
- **2026:** no 2026 data enters the backtest. The runner refuses any 2026 row.

### 2.2 Choosing `k_p` (nested, forward only)

For each evaluation season `Y` (2017-2025), `k_p` is the value in `G_L` that minimises the
reconstructed-receptions error (metric E below) on all origins of seasons 2016 to `Y - 1`. Ties go
to the smaller `k`. The `k_p` for season 2026 use (the chart chain) is chosen on 2016-2025. No
fold ever sees its own season or a later one.

### 2.3 Metrics

Origins: weeks 5, 9 and 13 of each season. Truth: the player's games in the 4 weeks from the origin
(5-8, 9-12, 13-16; these windows do not overlap). Eligible: RB, WR or TE (QB reported), at least 2
truth games, truth Half points above 0, and at least 1 history game.

- **E (stat-line reconstruction, receptions):** predicted receptions per game
  = `q_pred x` (realized Half points per game), against realized receptions per game. Squared
  error, averaged over players.
- **Calibration:** the OLS slope of realized `q` on predicted `q`, pooled over the evaluation seasons,
  per position.
- **Order:** the within-position Spearman of predicted against realized `q` (reported).
- **Shuffle control:** within position and origin, the rule's predictions are permuted among
  players. 1,000 permutations, seed 16911.
- **Intervals:** cluster bootstrap by player (gsis id) within position, 2,000 draws, seed 16911.

## 3. Pre-registered tests and bands

| # | Test | Rule (per position RB, WR, TE unless said) |
| --- | --- | --- |
| B0 | **Exactness** (code) | RL with `k = 0` reproduces R0, RL with `k = inf` reproduces Rpos, and Rv5 reproduces v5's `shrunk_mix` reception component on the same history, all exactly. Otherwise the run is **void**. |
| B1 | **History predicts catches** (RL against Rpos) | PASS if all three hold: RL has the lower E in at least 7 of the 9 evaluation seasons; the pooled interval of (E_pos - E_RL) is entirely above 0; RL's pooled E is below the shuffle control's 5th percentile. FAIL if the pooled interval is entirely below 0. Otherwise INCONCLUSIVE. |
| B2 | **No worse than v5's pull** (RL against Rv5) | Pooled interval of (E_v5 - E_RL): PASS if the lower bound is at least 0; HARM if the upper bound is below 0; otherwise INCONCLUSIVE. |
| B3 | **Calibrated** | RL's pooled calibration slope is in [2/3, 3/2] (the factor-1.5 band of D3). |
| B5 | **Whole stat-line reconstruction, 2024+ per-stat** | Origins: 2025 weeks 4-14, history 2024 to the origin, truth 4-week windows. Rule: RL's `k_p` (chosen on 2016-2024) for the reception category, and v5's frozen strengths for the other six. Metric: v5's T1(a) error (rescored points at Standard and Full, given realized Half points), pooled RB/WR/TE. PASS if the interval of (Rpos error - RL error) is entirely above 0 and RL beats the shuffle 5th percentile. HARM if, against Rv5, the interval is entirely below 0. The per-category objective S is reported. |
| B4 | Raw against light (reported) | E and calibration for R0. This shows what the safeguard buys. |

B5's origins (2025) overlap v5's selection and T1 origins, which were scored in v5; this is stated
next to the result. 2026 is not used.

### 3.1 Sensitivity runs (a verdict that flips under any of them blocks C)

| Run | Change |
| --- | --- |
| S-anchor-Full | `q` per Full-PPR point instead of Half |
| S-truth-ROS | truth = the rest of the season instead of 4 weeks |
| S-origins-alt | origins at weeks 4, 8 and 12 |
| S-no-2020 | the 2020 season left out (shortened preseason; one season held out) |

## 4. Chart-based replays: descriptive only

- **No pre-2026 chart snapshots exist**, so the chart unwind cannot be backtested.
- After the backtest, the v5 chart chain is re-run with RL's 2026 `k_p` on the existing chart
  weeks. That covers dev weeks 5-7 and weeks 8-10, which were already burned for v5's verdict.
- T2-T8 are reported, including T5 per position and T5u (D3: "If the logic plays out that way,
  that's ok"), next to v5's numbers. **None of them gates the outcome.**
- Weeks 11+ are an optional later replication with the same frozen code. It blocks nothing.
- That replay needs RL's catch share on 2026 chart players. It uses the per-stat history as in v5
  (2024+ `player_game_stats`, keyed), because the 2015-2023 points file joins chart players only
  through the 59.4% idmap. This is stated as a limit.

## 5. Outcomes (mechanical; this is the last round)

| Outcome | When |
| --- | --- |
| **void** | B0 fails. Fix the bug with a dated amendment, then rerun once. |
| **A: close** | At any of RB, WR or TE: B1 FAIL or INCONCLUSIVE, B2 HARM, or B3 outside the band. Or B5 not PASS, or B5 HARM. Or any verdict that flips under a sensitivity run. |
| **C: proceed to design a separate enhanced value** | B1 PASS, B2 no HARM and B3 in band at all three positions, and B5 PASS, with no flip under any sensitivity run. |

- The outcome is picked by code and written to `out51/backtest/verdict.json` with every rule that
  fired.
- What C means: the history-based mix step is supported by the backtest. It does **not** validate
  the chart unwind (issues 8, 10, 16). A separate enhanced value would carry those as open limits.
- Decision D-b asks whether a subset of positions can reach C.

Prediction, written now:
- RB passes B1-B3: split-half 0.77 on 2025.
- TE is uncertain.
- WR is the open question. Its split-half is 0.26, so a light pull may predict worse than the
  position average (B1), and the slope may fall outside the band (B3).
- Expected outcome: **A if WR fails, C only if WR passes**.

## 6. Harness (kept hardened)

- New code under `tools/research/jeg1691/v51/` (backtest runner, rules, tests). The v5 files are
  imported or read, never edited.
- Guards, carried from v5:
  - `V51_APPROVAL.json` (committed) names the reviewed commit;
  - the executed tree is blob-identical to that commit;
  - a once-only lock `V51_BACKTEST.lock` is written before any number, in the worktree, in git
    history and in `~/.local/state/jeg1691/`;
  - sensitivity runs are required, and `--quick` is dev only.
- The runner reads no 2026 row in backtest mode. Dev code checks use synthetic fixtures and 2015
  only (2015 is never an evaluation season).
- Run from a fresh clone. Commit the lock and outputs together straight away.

## 7. Limits

- **The backtest tests the mix step only.** Issue 16 (chart points are not a calibrated forecast),
  issue 8 (invertibility) and issue 10 (anchors) are not tested by it and stay open. Passing says
  "a player's history predicts how he earns points", not "the charts encode stat lines".
- **Data.** 2015-2023 has points only, so the backtest covers receptions only. That suffices for
  DDF's three formats (catches are the only weight that differs), not for custom scoring. The full
  seven-category check (B5) has one season (2025) of 2024-based history.
- **Seen data.**
  - The diagnosis (section 1) used 2026 weeks 6-10 outcomes.
  - B5's 2025 origins were scored in v5.
  - The chart replays reuse burned weeks and are descriptive only.
- **Not a forecast of future charts.** The chart chain's behaviour is only described (section 4).
- **T6 stays near-mechanical, and T7's FantasyPros Standard HARM on week 10** is reported in the
  replay without a verdict.

## Frozen decisions (Jeremy, 2026-11-17, answers on PR #1478)

| # | Jeremy's answer | How it binds |
| --- | --- | --- |
| D1 | "It should reflect that player's historical mix" | RL: own history, shrinkage only as light as forward CV on 2015-2025 actuals justifies (sections 2-2.2). This replaces the first version's `k_rec`-by-reception-objective change. |
| D2 | "Focus on backtesting not forward results for now" | The decisive evidence is the backtest (section 3). The chart replays are descriptive. Weeks 11+ are an optional replication that blocks nothing (section 4). |
| D3 | "If the logic plays out that way, that's ok" | T5u is reported and does not gate. |

## Decisions for Jeremy before any v5.1 code

| # | Question | Options (recommendation first) |
| --- | --- | --- |
| D-a | How light the safeguard can be | **A** light grid {0, 0.5, 1, 2, 4, 8} (at most 8 games of pull, so history dominates once a player has a few games) / B v5's full grid up to infinity (the data may choose a heavy pull, as v5 did for WR) |
| D-b | Can a subset of positions reach C? | **A** no: C needs RB, WR and TE / B yes: C for the positions that pass; the others keep the position average |

## Amendments

- 2026-11-17: redesigned on Jeremy's answers D1-D3 before any v5.1 code or number. The first
  version's change (`k_rec` by a reception objective), its chart-week gate (weeks 11-12) and T1c
  are withdrawn. T5u is reported only.
