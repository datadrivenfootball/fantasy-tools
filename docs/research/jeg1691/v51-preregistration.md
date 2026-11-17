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
  - the new light pull (at most 8 games' worth, Jeremy 2026-11-17), set by testing on earlier
    seasons only;
  - the position average.

  A second check repeats this for 2025 using the 2024+ stat history the chart chain actually uses.
  In DDF's three formats only catches matter, so both checks test catches. A fake version that
  hands each player someone else's history is the control.
- **What can happen.** This is the last round.
  - **C:** all of the following hold, and a separate, labelled scoring-aware value can then be
    designed next to DDF Value:
    - the light pull predicts better than the position average at running back, receiver and
      tight end;
    - it predicts receivers clearly better than v5's heavy pull, and is not worse at the other two;
    - it is well calibrated.
  - **A:** otherwise. Keep DDF Value as it is.
- **Weak spots, said plainly.**
  - Running backs will almost surely beat the position average, so that part says little.
  - The fake-history control adds nothing once the position average is beaten.
  - 2025 was already looked at, so the result is also run without 2025.
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
evaluation seasons. Section 1 used 2025 actuals, so 2025 is not clean (amendment 3, S-no-2025).

## 2. The change (step 5, the catch share): a light, data-justified pull

The catch share is `q` = receptions per Half-PPR point, the only quantity DDF's three formats see
(v5 section 1, algebra). Every rule below is a **two-bucket** rule (catches, other points), because
2015-2023 has points only (amendment 2).
- **History share:** `q_hist,i` = total receptions / total Half points over the history games
  (a ratio of totals, amendment 2), recency-weighted only where a rule says so. A player whose
  history Half points total at most 0 gets the position share, counted.
- **Position share:** `q_pos,p,o` at origin `o` = the games-weighted mean of `q_hist` over the
  position's players with at least 8 history games. It uses games **before `o` only**.

| Rule | Definition |
| --- | --- |
| **RL (light, the v5.1 rule)** | `q_i = a_i q_hist,i + (1 - a_i) q_pos`, `a_i = n_i / (n_i + k_p)`, with all history games equally weighted ("that players historical mix"). `k_p` per position comes from the light grid `G_L` = {0, 0.5, 1, 2, 4, 8} (D-a, Jeremy 2026-11-17: "A: At most 8 games of pull (Recommended)"), chosen by nested forward CV (2.2), ties to the **smaller** `k`. When the chosen `k_p` is 8, the cap, that is reported and not acted on (amendment 4). |
| R0 (raw history) | `k = 0` |
| Rv5 (v5's pull, two-bucket) | the same form with v5's frozen catch strength and half-life from `out/decisive/selection.json` (RB `k` 8, half-life 17 games; WR 64, 8; TE 2, 8): `a_i = n_eff,i / (n_eff,i + k)`, history recency-weighted (`0.5 ** (age / t)`). This is **not** v5's seven-category `shrunk_mix`, which pulls each category separately and renormalises; 2015-2023 has no seven-category history. Rv5 is the closest two-bucket stand-in, and no exactness to `shrunk_mix` is claimed (amendment 1). |
| Rpos (position average) | `k = inf` |

Shared rules:
- Players with no history get `q_pos` under every rule. They are counted and excluded from the
  comparison.
- A game is a row with nonzero Standard or PPR points. Dropping the 9,684 all-zero rows shortens
  some players' game counts (played, no stat), which slightly increases their pull; this is stated.
- History runs from 2015 to the week before the origin.

### 2.1 Data

- **2015-2025:** `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`, 61,977 player-weeks with
  gsis id and position. Points by format only; receptions = PPR minus Standard points. Identity is
  the gsis id, so the idmap does not limit the backtest.
- **2024-2025 per-stat (B5 only):** the committed `player_game_stats` cache, keyed rows only:
  about 87% of 2024 and 96% of 2025 rows with a stat carry a player_key. B5 covers only that
  subset, stated next to its result.
- **2026:** no 2026 row enters the backtest; the runner refuses one.

### 2.2 Choosing `k_p` (nested, forward only)

- For each evaluation season `Y` (2017-2025), `k_p` is the value in `G_L` minimising E (2.3) on all
  origins of seasons 2016 to `Y - 1`, with ties to the smaller `k`.
- The bootstrap holds each fold's chosen `k_p` fixed (it resamples players, not the selection).
- B5 (2025 origins) uses the `k_p` chosen on 2016-2024. The chart replay (2026) uses the `k_p`
  chosen on 2016-2025.
- A sensitivity run that removes a season removes it from the selection folds too.

### 2.3 Metrics

Origins: weeks 5, 9 and 13. Truth: the player's games in the 4 weeks from the origin (5-8, 9-12,
13-16; the windows do not overlap). Eligible: RB, WR or TE (QB reported), at least 2 truth games,
truth Half points above 0, and at least 1 history game.

- **E (catch reconstruction):** predicted catches per game = `q x` (realized Half points per game),
  against realized catches per game. Squared error, mean over players.
- **Calibration, gating (amendment 9):** the weighted least-squares slope of realized window share
  `q_true` (window receptions / window Half points) on predicted `q`. Weights are the truth Half
  points, which bound the influence of near-zero-point windows. Pooled over evaluation seasons, per
  position. An undefined slope (no variation in predicted `q`) counts as outside the band.
- **Calibration, descriptive:** the OLS slope of realized catches per game on predicted catches per
  game. It is not a gate: predicted catches = share x realized points, so this slope is driven by
  points varying between players and sits near 1 for any rule.
- **Order:** within-position Spearman of predicted against realized catches per game (reported).
- **Shuffle control:** within position and origin, the rule's predictions are permuted among
  players. 1,000 permutations, seed 16911.
- **Intervals:** cluster bootstrap by player (gsis id) within position, 2,000 draws, seed 16911.

## 3. Pre-registered tests and bands

| # | Test | Rule (per position RB, WR, TE unless said) |
| --- | --- | --- |
| B0 | **Exactness and data integrity** | RL at `k = 0` reproduces R0; RL at `k = inf` reproduces Rpos; Rv5 at `k = 0`, `t = inf` reproduces R0; all exactly. Rows where Half points differ from the mean of Standard and PPR by more than 0.011 are counted. Void if any identity fails or more than 0.5% of rows break that relation. |
| B1 | **History predicts catches** (RL against Rpos) | PASS if all hold: RL has the lower E in at least 7 of the 9 evaluation seasons; the pooled interval of (E_pos - E_RL) is entirely above 0; RL's pooled E is below the shuffle 5th percentile. FAIL if the pooled interval is entirely below 0. Otherwise INCONCLUSIVE. |
| B2 | **Light against v5's pull** (RL against Rv5) | Pooled interval of (E_v5 - E_RL): PASS if the lower bound is above 0; HARM if the upper bound is below 0; otherwise INCONCLUSIVE. |
| B3 | **Calibrated** | RL's pooled points-weighted share slope (2.3) is in [2/3, 3/2]. Expected behaviour, reasoned without a run: the position average predicts almost the same share for every player of a position at an origin, varying only a little across origins and seasons. Its slope is driven by season drift and is expected to be undefined or far from 1, so it would fail. v5's heavy WR pull compresses the shares (in the 2026 diagnosis its share slope was 4.85), so it is expected above 3/2 and would fail. Raw history over-disperses at low split-half reliability (WR 0.26) and is expected below 2/3. So B3 can fail on either side, and only a pull near the right strength passes. |
| B5 | **Catch reconstruction on the chain's own history source** | Origins: 2025 weeks 4-14. History: per-stat `player_game_stats` from 2024 up to the origin (keyed subset). Truth: 4-week windows. RL's two-bucket share with the `k_p` chosen on 2016-2024 (the same rule as B1, amendment 2). PASS if the interval of (Rpos error - RL error) on E is entirely above 0 and RL beats the shuffle 5th percentile. HARM if, against Rv5, the interval is entirely below 0. It tests catches only, like B1. A custom-scoring error that sees the other six categories (v5's T1b scorings, other categories from v5's frozen mix) is reported only. |
| B4 | Raw against light (reported) | E and calibration for R0. |
| — | Cap report | Per fold and position, whether `k_p` hit the cap of 8. Reported only. |

### 3.1 What C needs from B2 (amendment 8; Jeremy's chosen outcome rule D-c, 2026-11-17)

The change matters where v5's pull was heavy: WR (`k` 64 against at most 8). RB (8) and TE (2) are
already near the light grid.
- **C requires B2 PASS at WR** (the light pull predicts better than v5's) **and no HARM at RB and
  TE.**
- An INCONCLUSIVE B2 at WR does not reach C, because it would not show that the change helps.
- Proposed by the lead and kept by Jeremy (D-c, 2026-11-17: "Keep it (Recommended)").

### 3.2 Weak tests, said plainly (amendment 8)

- B1's shuffle condition cannot fail on its own. A rule that beats the position average also beats
  its own shuffled predictions, so the condition adds nothing.
- B1 at RB is near certain to pass (split-half 0.77 in 2025).
- B0 checks code and data only.
- The tests that can fail on the idea are B1 at WR and TE, B2 at WR, B3 and B5.

### 3.3 Sensitivity runs (a verdict that flips under any of them blocks C)

| Run | Change | B1 seasons threshold |
| --- | --- | --- |
| S-anchor-Full | `q` per Full-PPR point instead of Half | 7 of 9 |
| S-truth-ROS | truth = the rest of the season instead of 4 weeks | 7 of 9 |
| S-origins-alt | origins at weeks 4, 8 and 12 | 7 of 9 |
| S-no-2020 | 2020 removed from evaluation seasons and selection folds | 6 of 8 |
| S-no-2025 | 2025 removed from evaluation seasons and selection folds | 6 of 8 |

Under S-no-2025, B5 is absent (it is a 2025 test). An absent test is not a flip, and C then rests
on the primary B5.

S-no-2025 is there because 2025 is not clean (amendment 3):
- the diagnosis (section 1) used 2025 actuals;
- v5's strengths, which Rv5 uses, were chosen on 2025 weeks 4-8. That makes Rv5 partly in-sample
  in 2025 and biases B2 toward HARM there.

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
| **A: close** | At any of RB, WR or TE: B1 FAIL or INCONCLUSIVE, or B3 outside the band. Or B2 HARM at any position, or B2 not PASS at WR (D-c). Or B5 not PASS, or B5 HARM. Or any verdict that flips under a sensitivity run. |
| **C: proceed to design a separate enhanced value** | B1 PASS and B3 in band at RB, WR and TE (D-b A); B2 PASS at WR and no HARM at RB and TE (3.1, D-c); B5 PASS; no flip under any sensitivity run (an absent test is not a flip). |

- The outcome is picked by code and written to `out51/backtest/verdict.json` with every rule that
  fired.
- What C means: the history-based mix step is supported by the backtest. It does **not** validate
  the chart unwind (issues 8, 10, 16). A separate enhanced value would carry those as open limits.
- D-b A (Jeremy, 2026-11-17): C needs all three positions; no partial C.

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
| D1 (2026-11-17) | "It should reflect that players historical mix" | RL: own history, shrinkage only as light as forward CV on 2015-2025 actuals justifies (sections 2-2.2). This replaces the first version's `k_rec`-by-reception-objective change. |
| D2 (2026-11-17) | "Focus on backtesting not forward results for now" | The decisive evidence is the backtest (section 3). The chart replays are descriptive. Weeks 11+ are an optional replication that blocks nothing (section 4). |
| D3 (2026-11-17) | "If the logic plays out that way, that's ok" | T5u is reported and does not gate. |
| D-a (2026-11-17) | Question "how much may the catch share be pulled toward the position average?"; answer "A: At most 8 games of pull (Recommended)". Light grid {0, 0.5, 1, 2, 4, 8} | RL's grid (section 2). The cap was informed by the diagnosis (v5's WR `k` 64 compressed the spread about 5x). Jeremy's D1 ("It should reflect that players historical mix") supports a light cap. A fold choosing 8 is reported, not acted on. |
| D-b (2026-11-17) | Question "how many positions must pass before the new rule counts as a win?"; answer "A: RB, WR and TE all pass (Recommended)" | Section 5 |
| D-c (2026-11-17) | Question "a win (outcome C) currently needs running backs, receivers and tight ends all to pass; the author also added that the light pull must beat v5's heavy pull at receivers, with no harm at running backs or tight ends. Keep that extra rule?"; answer "Keep it (Recommended)" | 3.1 and section 5: C needs B2 PASS at WR and no HARM at RB and TE |

Jeremy's answers to D1, D2, D3, D-a, D-b and D-c were multiple-choice answers in the lead session on
2026-11-17, quoted verbatim.

## Amendments

- 2026-11-17: redesigned on Jeremy's answers D1-D3 before any v5.1 code or number. The first
  version's change (`k_rec` by a reception objective), its chart-week gate (weeks 11-12) and T1c
  are withdrawn. T5u is reported only.
- 2026-11-17, review round 1 of #1478 (head a283bfa0); D-a A and D-b A recorded. No code, no number.
  1. Rv5 is a two-bucket catch-share pull with v5's catch strength and half-life. Exactness to v5's
     seven-category `shrunk_mix` is dropped, since that cannot be checked on 2015-2023.
  2. Every rule is two-bucket, and the history share is a ratio of totals. B5 is relabelled "catch
     reconstruction on the chain's own history source" and uses the same RL share as B1. At DDF's
     three formats it sees catches only; a custom-scoring error is reported for the other six.
  3. 2025 is not clean: section 1 used it, and Rv5's strengths were chosen on 2025 weeks 4-8. This
     is disclosed, and S-no-2025 is added (6 of 8).
  4. RL's pull hitting the cap of 8 is reported, not acted on.
  5. Calibration is on the catches scale, with a points-weighted share slope reported. The window
     share is unbounded, so it is not regressed unweighted.
  6. S-no-2020 needs 6 of 8 seasons, and 2020 also leaves the selection folds.
  7. Specified: the position share uses games before the origin only; the bootstrap holds each
     fold's pull fixed; the all-zero rows (9,684) are dropped and that is stated; B5's keyed subset
     (about 87% of 2024 rows, 96% of 2025) is stated.
  8. The weak tests are stated (3.2). C needs B2 PASS at WR (3.1).
- 2026-11-17, review round 2 of #1478 (head b6ed6b9d). No code, no number.
  9. B3 now gates on the points-weighted share slope, with the expected behaviour of the position
     average, v5's pull and raw history stated. The catches-per-game slope is descriptive.
  10. Jeremy's D1, D2, D3, D-a and D-b are quoted verbatim, dated 2026-11-17.
  11. B5 is absent under S-no-2025, and an absent test is not a flip.
  12. The 2.2 sentence on which pull is used for 2026 and which for B5 is reworded.
  13. The B2-at-WR condition for C is recorded as Jeremy's chosen rule D-c (2026-11-17: "Keep it (Recommended)").
- 2026-11-17, harness written (`tools/research/jeg1691/v51/bt.py`, `run_v51.py`, tests
  `tests/test_jeg1691_v51.py`), after approval of e915a661. Implementation readings, none of them a
  rule change:
  14. **Dry run.** Season 2015 only: `k` chosen on origin week 11 and evaluated on origin week 15,
      history from 2015.
      - 2015 is never an evaluation season or a selection fold (it is only history), and weeks 11
        and 15 are not registered origins.
      - B5 is not run, since its 2024-2025 data overlaps evaluation seasons.
      - No 2017-2025 number is produced.
  15. **B3 and the position average.** Section 3's expectation that the position average's slope
      is "undefined or far from 1" does not hold in general. On planted synthetic data its slope was
      RB 1.05 (inside the band), WR -4.77 and TE -0.96. Drift between origins can put it inside the
      band, so the position average is ruled out by B1, not by B3. B3 can fail for a heavy pull and
      for raw history (both shown on synthetic data), as the review required.
  16. **B5 pooled interval.** A joint bootstrap: each draw resamples players within every position
      and averages the per-position means.
  17. **Where the sensitivity runs apply to B5.** S-anchor-Full and S-truth-ROS change B5 too.
      S-origins-alt keeps B5's origins (2025 weeks 4-14), but B5's pull is then chosen on the
      selection folds at origins 4, 8 and 12, so B5 changes too. S-no-2020 changes B5's pull through
      the selection folds. Under S-no-2025, B5 is absent.
  18. **Positions.** An nflverse player's position is that of his latest history game. B5 keyed
      players take their position from the Sleeper idmap, else `players.json`; the counts are
      reported.
  19. **Custom-scoring report (B5, reported only).** It approximates v5's seven-category prior from
      the eligible rows at each origin. This is labelled in the output and never a gate.
  20. **Data integrity (B0), from the dry run's loader.** 61,977 rows, 0 rows outside the Half
      tolerance, 9,684 all-zero rows dropped, 0 negative receptions.
  21. **Test-only change, 2026-11-17, made after v5's lock was committed.**
      `tests/test_jeg1691_v5.py::test_no_sensitivity_refused_outside_dev` asserted that no
      `DECISIVE.lock` exists, which the committed lock made false.
      - It now snapshots `DECISIVE.lock` and `REPLICATION.lock` before the refused call and
        asserts they are unchanged after it.
      - `tests/` is outside v5's guarded manifest (v5's `MANIFEST_ROOTS` in `run_v5.py`, checked
        at 98c375d0f), so v5's executed tree and its verdict are unaffected.
      - No harness file changed.
- 2026-11-17, review of the harness (head 4d15d969). Fixes; no real backtest run.
  22. **Guard.**
      - `--approved` and `V51_APPROVAL.json`'s `reviewed_commit` must be full 40-hex shas and equal.
      - The reviewed commit must exist and be a strict ancestor of HEAD (HEAD is the approval commit
        on top), so symbolic HEAD, branch names and short shas are refused.
      - The guard tests pass only invalid or fake shas and snapshot the lock before and after, so
        they cannot start the real backtest.
  23. **Players whose history points total 0 or less** are excluded from the comparison and counted
      (`excluded.nonpositive_history_points`), exactly like players with no history. Every rule
      would give them the same position share, so excluding them changes no paired difference. This
      is the reading of section 2's "gets the position share, counted"; the code keeps it.
  24. **2026 rows of the per-stat cache** are dropped at load and counted
      (`rows_after_2025_dropped`), never used. That replaces 2.1's "the runner refuses one", since
      the committed cache holds 2026 rows. The nflverse loader refuses a 2026 row, and that file
      has none.
  25. **B5's shuffle threshold** now follows the registered form: the 5th percentile of the pooled
      shuffled statistic (each permutation's equal-weight mean over positions). The first harness
      used the mean of the per-position 5th percentiles.
  26. **B5's game definition** now follows section 2: a per-stat row counts as a game only when
      its Standard or PPR points are nonzero. The first harness also counted targets-only rows.

