# JEG-1691 v5.1: pre-registration of the one more round (written 2026-11-17, before any v5.1 code or run)

Status: **draft for review. No v5.1 code exists and nothing has run on weeks 11-14.** Jeremy chose
outcome B for v5 on 2026-11-17. This is the "one more pre-registered round that changes only the
failing step" of v5's section 5. The locked v5 files (`DECISIVE.lock`, `out/decisive/`, and every
file in v5's executed tree) are not touched. Research only, nothing published. Jeremy, 2026-11-16:
"Don't mess with the current architecture, we are exploring an enhanced value, not doing a cutover."

Nothing in sections 2-5 changes after the first v5.1 decisive number is printed. Any change before
that is appended at the end, dated, with its reason.

---

## Summary for a fantasy manager

- **What failed in v5.** When a league moves from Standard to Full PPR, v5 moved FantasyPros' wide
  receivers about a quarter as far as ESPN's and Sleeper's stat lines say they should.
  FantasyCalc's wide receivers looked fine, but only because about a third of them were pushed down
  to zero value in Standard, and that floor makes everyone move the same way.
- **Why.** v5 estimates how much of a receiver's scoring comes from catches using his past games,
  and pulls thin histories toward the average receiver. For receivers the method pulled very hard.
  On the dev weeks, receivers' estimated catch shares were about one fifth as spread out as ESPN's
  and Sleeper's. They were still in the right order, and even the best order of the three against
  what happened next. They were just squeezed together.
- **The one change.** Choose how hard to pull the catch share using a test on real games that looks
  only at catches per point, which is the one thing that matters in DDF's three scoring formats.
  v5 chose it with a score that mixed in every other stat. Everything else stays exactly as in v5.
- **When it runs.** Once, as soon as the chart weeks 11 and 12 exist (around 2026-11-25), with
  weeks 13-14 as a later check that blocks nothing.
- **What can happen.** This is the last round. It either passes every test (**C**: build a
  separate, labelled scoring-aware value next to DDF Value) or it closes (**A**: keep DDF Value as
  it is). There is no further iteration.
- **Honest expectation.** It may still fail. Receivers' catch shares are noisy from game to game,
  and the no-harm test for FantasyPros in Standard was already borderline (it showed harm on week
  10 alone).

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
realized on predicted receptions per point, on the **2025 selection origins**. A v5 slope well above
1 there confirms over-shrinkage on the selection data. It is computed and reported by the v5.1
selection step (3.3) before any decisive number exists.

## 2. The one change (step 5, reception category only)

- **v5:** `k_rec,p` and `t_p` were chosen jointly with the other six categories by the objective
  `S` (2.4 of the v5 pre-registration).
- **v5.1:** `t_p` and the six non-reception strengths `k_c,p` stay **exactly as v5 selected them**
  (frozen in `out/decisive/selection.json`). Only `k_rec,p` is re-chosen. It takes the value in v5's
  grid `K_GRID` = {0, 2, 4, 8, 16, 32, 64, 128, inf} that minimises
  `S_rec` = the mean squared error of receptions per anchor point
  (`realized receptions / realized F(s0)` against `m*_rec`, Half anchor). The search uses the same
  selection origins (2025 weeks 4-8), truth windows, eligibility, renormalisation and tie rule
  (larger `k`) as v5.
- Positions: RB, WR, TE, QB, each re-chosen; QB is reported, not judged.
- Nothing else changes: steps 1-4, 6, 7, the references, the pairing rule, the shuffle, the
  bootstrap and every band.
- Code: a new module `tools/research/jeg1691/v51/` that imports the v5 modules unchanged and
  replaces only `k_rec` in the selection. It is written after this pre-registration and Jeremy's
  decisions, checked on dev weeks 5-7 only, and reviewed before any run.

## 3. Tests (same as v5, same bands; additions only where the change needs them)

### 3.1 Tier 1, carried unchanged

T1, T2, T3, T4, T5 (pooled and per position, [2/3, 3/2]), T6, T7 and T8 have the definitions and
rules of v5 section 3.2. The runner reuses `tests5.py`, unchanged.

### 3.2 Tier 1, added for the change

| # | Test | Rule |
| --- | --- | --- |
| T1c | **The change does not hurt the mechanism.** On T1's test origins: the v5.1 mix against the v5 mix, paired, with the T1(a) error (rescored points at Standard and Full) and with `S_rec`. | No-harm labels as T7. HARM on T1(a) leads to A. |
| T5u | **T5 without the floor artifact (decision D3).** T5's statistic on players with a nonzero Adjusted value at both Standard and Full in both v5.1 and the reference-mix rebuild, pooled and per position. | The same band and rule as T5. |

### 3.3 Reported (Tier 2)

- v5's Tier 2 list.
- The selected `k_rec,p` against v5's.
- The calibration slope of realized on predicted receptions per point, on the selection origins,
  for v5 and v5.1 (section 1's distinguishing check).
- The SD of receptions per anchor point for v5.1, v5, raw history and the reference.
- The floored-player count per chart, position and week.

### 3.4 What the decisive weeks see

- T1 and T1c use v5's T1 test origins: 2025 weeks 12-14 and 2026 weeks 5-7. These were already
  scored in v5, for the v5 mix against the position mix, so v5.1's T1 is not on unseen origins.
  That is stated next to the result.
- A fresh-origin T1 (2026 origins 8 onward, truth from week 11 on) is reported in the replication
  only.

## 4. Decisive weeks and the sequential rule (decision D2)

- Weeks 8-10 are burned. Dev for code checks is weeks 5-7 only.
- **Primary proposal (D2-A): one decisive run as soon as content weeks 11 and 12 both exist.** That
  is about 2026-11-25. "Exist" means all of the following, checked by the runner:
  - a chart snapshot in `data/history/week-<w>.json` for all four charts;
  - an ESPN CSV commit whose `espn_snapshot_date` equals the week's ESPN snapshot;
  - a Sleeper warehouse run no later than that snapshot;
  - the references paired by v5's rule (v5 2.6), with fresh Sleeper for every week.
- No look before both weeks exist. Weeks 13 and 14 then run as a replication that blocks nothing:
  - with the same frozen code, each week alone and the four weeks together;
  - a replication verdict that differs is stated beside the decision and does not reopen it.
- **Confidence by choice.** Rest-of-season lists change slowly, so consecutive weeks are highly
  dependent, and extra weeks add less than their count suggests.
  - Two fresh weeks (D2-A, earliest): the first test on chart weeks nobody has seen, and fresh
    Sleeper on every week. It is the weakest sample.
  - Three weeks (D2-B, about 2026-12-02): somewhat tighter intervals. Most of the gain is in T7
    and T8, which were inconclusive in v5.
  - Four weeks (D2-C, about 2026-12-09): the most data. It waits two weeks longer for modest gain.
- **Week-alone hinge.** Every decisive week has fresh Sleeper, so v5's "W10-only" sensitivity is
  replaced by "each decisive week alone". A Tier 1 test that passes on the pooled weeks and fails on
  one week alone counts as a hinge.

## 5. Stop rules and outcomes (mechanical, as v5; this is the last round)

v5's section 5 says this round reaches C or closes. So the v5 outcome function is reused with one
mapping: **every rule that gave B in v5 gives A here.**

| Outcome | When |
| --- | --- |
| **void** | T2 fails on the decisive weeks. The run is void. After a dated bug fix, the next unused weeks (13-14) become the decisive weeks, run once. |
| **A: close** | Any of the following, or any rule that gave B in v5 (a Tier 1 test failing in the primary; a hinge on an anchor, on ESPN, CBS ROS or Razzball left out of step 4, on one chart dropped, or on one decisive week alone; T1 INCONCLUSIVE with point estimate above 0): T1 FAIL; T1 INCONCLUSIVE with point estimate at or below 0; T1c HARM; T4 FAIL; any HARM in T7 or T8. |
| **C: proceed to a separate enhanced value** | T1 PASS, T1c with no HARM, and every Tier 1 test (with T5u if D3-A) passes in the primary and in every sensitivity run. A new ticket designs a separate, labelled value beside DDF Value. Nothing replaces DDF Value. |

- **The FantasyPros Standard T7 HARM seen on week 10 alone in v5.** It gets no special treatment:
  - HARM in the primary leads to A;
  - HARM on one week alone is a hinge, and a hinge leads to A.
- **Prediction, written now.** Widening WR moves (the purpose of the change) can deepen that harm:
  - v5's weeks 8-10 FantasyPros Standard T7 was -0.011 [-0.032, +0.001].
  - So T7 is the most likely test to close the round, after T5u.
  - Expected outcome: **A**, with the failure most likely at T5u or T7. C needs both to clear.

## 6. Harness (kept hardened)

- Runner `tools/research/jeg1691/v51/run_v51.py`. The v5 files are imported and never edited, and
  the v5 manifest stays verifiable.
- Guards:
  - `V51_APPROVAL.json` (committed) names the reviewed commit;
  - the executed tree is blob-identical to that commit (v5's manifest plus `v51/`);
  - the once-only lock `V51_DECISIVE.lock` is written before any value is computed, and is also
    checked in git history and in `~/.local/state/jeg1691/v51-decisive.json`;
  - `--quick` and `--no-sensitivity` are refused outside dev;
  - the runner refuses any week set other than the registered one (D2), and refuses before those
    weeks exist.
- The outcome is written to `out51/decisive/verdict.json` with every rule that fired. The lock and
  outputs are committed and pushed together straight away, per v5's "How to run".

## 7. Limits (unchanged or new)

- **Issue 16:** chart-implied points are not a calibrated forecast. Step 4 is unchanged.
- **Issue 8:** invertibility. The stat line is the player's history scaled to the chart's level,
  not something the chart says.
- **Issue 10:** the anchors (FantasyCalc Full, FantasyPros Half) are assumed. Anchor runs are hinges.
- **T6 stays near-mechanical.** DDF prices every source's position totals the same way, so a T6 pass
  says little. v5's T6 failure (FantasyCalc TE/RB 0.645 against the edge at 0.644) was by a hair,
  and this change does not target it. T6 can still decide the round either way by small margins.
- **T4 and T5 compare with a rebuild through the same machinery,** so they test the mix's order and
  spread only.
- **Seen data.** The T1 test origins were scored in v5. The diagnosis's calibration check (*) reads
  weeks 6-10 game outcomes.
- **One more round only.** If v5.1 ends in A, the chart-unwind line closes. The fresh-origin T1 and
  the replication stay reported, not reopened.

## Decisions for Jeremy before any v5.1 code

| # | Question | Options (recommendation first) |
| --- | --- | --- |
| D1 | The one change | **A** re-choose only `k_rec` by a receptions-per-point forward-CV objective on the same 2025 selection origins / **B** re-choose `k_rec` so the calibration slope of realized on predicted is closest to 1 on those origins / **C** no change; close now (A), because WR catch shares carry little signal (split-half 0.26) |
| D2 | Decisive weeks | **A** one run as soon as weeks 11 and 12 exist (about 2026-11-25); 13-14 replicate / **B** weeks 11-13 (about 2026-12-02) / **C** weeks 11-14 (about 2026-12-09) |
| D3 | The floor artifact | **A** add T5u (T5 without floored players) to Tier 1 / **B** report it only (then FantasyCalc can pass T5 by the artifact) |

## Amendments

None yet.
