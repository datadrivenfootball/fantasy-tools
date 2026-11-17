# JEG-1691 v5: pre-registration (written 2026-11-16, before any v5 code or run)

Status: **decisions D1-D5 frozen by Jeremy on 2026-11-16 (see "Frozen decisions"). No experiment
has been run. No v5 number exists.** Runs start only on Jeremy's go. Nothing here
changes a published number, the pipeline, or DDF Value. Jeremy, 2026-11-16: "Don't mess with the
current architecture, we are exploring an enhanced value, not doing a cutover." Parent: JEG-1597.
Prior versions: v1 JEG-1597 (#1405), v2 JEG-1605 (#1408, #1414), v3 JEG-1610 (#1415), v4 JEG-1611
(#1417). Issue numbers below refer to the 22-issue walkthrough of 2026-11-16.

Nothing in sections 1-5 changes after the first holdout number is printed. Any change before that
is appended at the end, dated, with its reason. A change may fix a bug or a missing input; it may
not loosen a pass rule after a dev number has been seen.

---

## Summary for a fantasy manager (one page)

**The problem.** Two of the four trade charts behind DDF Value, FantasyCalc and FantasyPros, give
one value per player whatever your league's scoring. In a Standard league a pass-catching back is
worth less than in a Full PPR league, but those two charts do not show it. CBS Sports and USA Today
do publish a value per format.

**The idea (Jeremy's, 2026-11-16).** Take what a chart says a player is worth and turn it into the
points per game it implies. Look at how that player has actually scored his points in past games:
how much from catches, from yards, from touchdowns. Split the chart's points the same way into an
assumed stat line (for example 5.1 catches, 38 receiving yards, 41 rushing yards, 0.4 TDs a game).
Then score that stat line in your league's format and value it exactly the way DDF already values
ESPN's projected stat lines. Only the two charts that ignore scoring are treated this way.

**What is new compared with the last try (v4).** v4 split points into only two parts (catches and
everything else) and converted back to chart units with a fixed slope, which made values move too
far, about 1.5 to 1.8 times as far as the publishers' own format columns. v5 uses every stat
category and values the stat line with DDF's own ESPN method, so a point is worth what DDF already
says it is worth at each scoring.

**How we will judge it, decided now, before running anything.**
1. On real games only: does a player's own stat mix predict how he scores in later games better
   than a generic "average running back" mix?
2. Do the assumed stat lines look like what ESPN and Sleeper project for the same players? They
   publish full stat lines, so they show directly how a player's value should change with scoring.
   This replaces judging against CBS Sports and USA Today, whose format columns barely reorder
   players and disagree with each other.
3. When a league switches from Standard to Full PPR, do players move the way they move when ESPN's
   and Sleeper's own stat lines are rescored? We check who moves (order), how far, and how whole
   positions shift.
4. Does it do no harm, compared with leaving the chart alone and with today's DDF Value?
5. Does it beat a fake version that hands each player another player's stat mix at random?

**What Jeremy fixed on 2026-11-16.** The rebuild starts from the chart's own value and adds only
the change DDF's ESPN-style pricing gives, so nothing moves at the chart's own scoring. History is
the stored per-stat lines from 2024 on, nothing new is loaded. A move counts as the right size if it
is within a factor of 1.5 either way of the reference. Weeks 11-14 decide in one run. Thin
histories may be pulled toward the position average, by an amount set on real games only.

**One honest catch.** Two seasons of per-stat history give the real-games test (test 1) little
power. If it comes out "can't tell" rather than "no", that is not read as a no: it blocks the
separate value, but allows one more round once more 2026 games are recorded.

**What happens next.** Weeks 5-10 are for building and checking code. Weeks 11-14 are kept
untouched and decide the result in one run. Three outcomes: **A** close it and keep DDF Value as
is; **B** one more pre-registered round on the step that failed; **C** build a separate, clearly
labelled "scoring-aware" value next to DDF Value. In no case is DDF Value replaced.

**What this cannot settle.** Nobody knows whether a trade chart's number really stands for a points
forecast (so far, chart points forecast real points worse than projections do). Nobody knows which
scoring FantasyCalc and FantasyPros assume. We test both guesses, but cannot answer them. In
Standard, Half and Full PPR, the only stat whose weight differs is the catch. So for DDF's three
formats, the full stat mix works only through the player's catch rate. The other categories matter
only for custom scoring, which DDF does not price today.

---

## 1. Method, step by step

Notation: chart `c` in {FantasyCalc, FantasyPros}; player `i`; position `p`; anchor scoring `s0`
(the scoring the chart is assumed to be built for); target scoring `s` in {Standard, Half, Full}.
Default league: 12 teams, default roster (VP-0). Other league sizes are reported, not judged.

| Step | v5 | Carried from v4 unchanged? |
| --- | --- | --- |
| 1 Pick charts | FantasyCalc (anchor Full), FantasyPros (anchor Half). CBS Sports and USA Today as published. | Yes |
| 2 Adjusted | `A_i(s0)` from the unmodified pipeline (`value_reference.run_pipeline`) at `s0` | Yes |
| 3 Unwind to VORP | chart-unit VORP `v_i = max(0, x_i - w_p)` for `A_i(s0) > 0`; exact inversion | Yes |
| 4 Chart-implied points | `P_i(s0)` = mean over ESPN, CBS ROS, Razzball of the inverse of each projection's monotone ppg-to-Adjusted map at `p` (`unwind.inverse`, `expected_points`) | Yes |
| 5 Stat mix | per-player mix over all seven ESPN stat categories, from history, shrunk by forward CV on actuals | **New** (v4: one reception share) |
| 6 Assumed stat line | `P_i(s0)` apportioned by the mix at `s0` | **New** (v4: two buckets) |
| 7 Rebuild | assumed stat line through DDF's ESPN-style projection path at each `s`, delta form; DDF Value = mean of the charts' Adjusted | **New** (v4: fixed chart-points-per-VORP slope `b_p`) |

### Steps 1-4 (carried from v4)

- In: the chart's saved 12-team native list at `s0` for the content week; the week's projection
  inputs. Out: `A_i(s0)`, `v_i`, `P_i(s0)` (points per team game, the projections' native basis,
  VP-0), and a label per player: `invertible`, `below_waiver` (`A_i(s0) = 0`) or `no_inverse`.
- Code reused as is: `tools/research/jeg1610/unwind.py` (`projection_pairs`, `build_map`,
  `inverse`, `expected_points`) and the v4 allocation-mix handling (`tools/research/jeg1611/v4.py`,
  iteration 3a, reading 1). These are on branch `claude/JEG-1611-logic-iteration` (draft PR #1417).
  v5 imports them and does not edit them.

### Step 5: the player's stat mix

- Categories `C` = the seven that DDF's ESPN path scores (`ESPN_COMPS` in
  `pipelines/bake_players.py`): passing yards, passing TDs, rushing yards, rushing TDs, receptions,
  receiving yards, receiving TDs. Interceptions, fumbles lost and 2-pt conversions are left out of
  the primary, because DDF's ESPN rest-of-season path does not score them (bake `scoring_note`: "No
  INT/fumble data in season sources"). Step 7 must be that same path. See 2.3.
- History: every `player_game_stats` row for player `i` (regular season, 2024 week 1 through the
  week before the chart's content week; never a later week). Per-game rates `h_ic` = the mean over
  his game rows. Recency weighting with half-life `t` games, where `t` is chosen in the CV below.
- Mix, scale-free: stats per anchor point, `m_ic = h_ic / F(h_i, s0)`, where `F(stats, s)` =
  `sum_c w_c(s) x stats_c` with the weights of `pipelines/lib/scoring.py` (the seven categories,
  no rounding). By construction `F(m_i, s0) = 1`.
- Shrinkage (allowed only because it is estimated on actuals by forward CV, never on charts):
  `m~_ic = a_ic m_ic + (1 - a_ic) mbar_pc`, with `a_ic = n_i / (n_i + k_pc)`, `n_i` = the player's
  game rows (recency-weighted count). `mbar_pc` = the games-weighted mean of `m_ic` over the
  position's players with at least 8 games in the window. Then renormalise:
  `m*_i = m~_i / F(m~_i, s0)`.
- Grid, fixed now: `k_pc` in {0, 2, 4, 8, 16, 32, 64, 128, infinity} per position and category;
  `t` in {infinity, 8, 17} per position. `k = 0` is the raw history mix, `k = infinity` is the
  position mix. Selection rule: the lowest standardised stat-line error (2.4, objective S) on the
  selection origins. Ties go to the larger `k`.
- Fallback, labelled `fallback_position_mix`: no game rows (rookies, first-time players), or
  `F(h_i, s0) <= 0`. The player gets `mbar_p`. The fallback count per chart, week and position is
  reported.
- QBs go through the same steps. On the three presets their response is near 0 (only receptions
  change weight), and they are reported, not judged.

### Step 6: assumed stat line

- `shat_ic = P_i(s0) x m*_ic`, per team game, for `invertible` players. By construction
  `F(shat_i, s0) = P_i(s0)`.
- Not computed for `below_waiver` or `no_inverse` players (no `P_i(s0)`). They keep the unchanged
  treatment in step 7 and are counted.

### Step 7: rebuild through DDF's ESPN-style path

ESPN's path in DDF today: a stat line times the scoring weights, divided by team games remaining,
gives `espn_ppg` at each scoring (`bake_players.py`). That ppg goes through VP-2 to VP-5 like any
projection: league allocation, waiver line, value above waivers, slices, implied weights, and
Adjusted at the shared weights `W` and the pie. v5 does the same with the assumed line:

- 7a. `P_i(s) = F(shat_i, s)` for each target `s`.
- 7b. Pseudo-source `c-v5`: natives `P_i(s)`, run at `s` as a projection source **outside `I`**.
  That is the existing VP-1.4 path: it goes through VP-2, VP-3, VP-5 against the run's allocation,
  pie and `W`, and contributes nothing to weights, peers, `m` or DDF Value. The allocation is
  re-derived at `s` as DDF does (Jeremy's literal step 7); a variant holds it at the anchor's.
  The one stated deviation: the pseudo-source lists only `invertible` players, so its own waiver
  index `R_p` can fall past its list. Its waiver line is the mean of the projections' blended
  waiver values in ppg at `s` (v4 iteration 3a, reading 2), with no other change.
- 7c. Delta form (primary): `Av5_i(s) = max(0, A_i(s0) + Aps_i(s) - Aps_i(s0))`, where `Aps` is
  the pseudo-source's Adjusted. The identity at `s = s0` is exact. The scoring response comes only
  from DDF's own ESPN-style pricing of the assumed stat lines, so v4's fixed slope `b_p` is gone.
  Delta form frozen as primary (D1 A, Jeremy 2026-11-16). Literal variant (reported only):
  `Av5_i(s) = Aps_i(s)`, with its mismatch to `A_i(s0)` at the anchor reported as a diagnostic.
- 7d. Players without an assumed line keep the chart's unmodified Adjusted at `s` (labelled).
- 7e. DDF Value v5 at `s` = the equal-weight mean of the four charts' Adjusted (VP-6.3): CBS Sports
  and USA Today unmodified at `s`, FantasyCalc and FantasyPros `Av5(s)`. Hidden-source and basis
  rules as VP-1 and VP-6.3. It is a research column only.
- **Unchanged** (baseline) = the chart's unmodified Adjusted at `s`, which is today's treatment.
  **Current DDF Value** = today's `ddf_value` at `s`.

Arithmetic: IEEE doubles with no intermediate rounding (VP-0). The bake's ppg rounding is not
applied.

### Algebra written down before the run

On the three presets only the reception weight `r_s` (0, 0.5, 1) differs, so
`P_i(s) / P_i(s0) = (1 + r_s rho_i) / (1 + r_s0 rho_i)`, where `rho_i` = receptions per
non-reception point in `m*_i`. On DDF's formats, steps 5-6 therefore reduce to a reception-share
model, as in v4. The full-category mix only changes the result under scorings DDF does not price
(TE premium, 6-pt passing TD, and so on), which are tested on actuals only (T1b). What v5 changes
for DDF's formats is (i) how the share is estimated (full-mix CV on 2024+ per-stat lines instead of
v4's 2015-2025 share model) and (ii) step 7 (DDF's own pricing at `s` instead of `b_p`).

Prior evidence that bears on step 7: v3's `v3_proj` variant priced `P_i(s)` through the
projections' own maps at `s` and lost every week on within-position agreement with CBS Sports and
USA Today (0 of 40, `docs/research/jeg1610/results.md`). v5's step 7 is close kin to it. v5 differs
in the target it is judged against (section 3), the delta form, and the shrunk mix.

---

## 2. Data

### 2.1 What exists (checked 2026-11-16 from repo docs; counts to be re-read by the pre-run check)

| Need | Source | Coverage | Notes |
| --- | --- | --- | --- |
| Per-stat history (step 5, T1) | Supabase `player_game_stats` (JSONB `stats`) | 2024-2025 full; 2026 weeks 1-4 full (about 1,000-1,100 rows a week); weeks 5-8 partial (258-294 rows a week as of 2026-11-09); ESPN actuals written daily since 2026-10-09 (JEG-521) | Has pass, rush and receiving yards and TDs, receptions, targets, interceptions. No fumbles, no 2-pt. Joins to `player_key` through `players` (complete). |
| Per-stat history 2015-2023 | none in repo | none | `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz` holds points only. The nflverse idmap covers 59.4% of chart players. Not loaded (D2 A, Jeremy 2026-11-16). |
| Receptions 2015-2025 | `ppr - std` from the nflverse points file | exact | Used only by v4's share model (sensitivity variant V-mix3). |
| ESPN ROS stat lines | `data/inputs/espn_projections.csv`, 7 categories, at the commit that built each content week's fixture (68 commits since 2026-09-22) | weeks 5-10 dev; 11+ as they land | Divided by team games remaining as in the bake. |
| ESPN weekly stat lines | `source_weekly_projections` (JEG-1641), 9 keys incl. INT | runs from 2026-11-14 | Cross-check only. |
| Sleeper stat lines | `source_weekly_projections`, Sleeper's full stat dict (about 56 keys) | runs from 2026-11-14, target weeks content week to 18 | ROS = the sum over the same target weeks as ESPN's window, from the latest run with `as_of` <= the chart snapshot time, divided by the same team games. The Sleeper-to-ESPN key map is pinned in code with a test. |
| Sleeper before 2026-11-14 | `data/inputs/weekly_projections_sleeper.csv.gz` | points only | Single-week receptions = `pts_ppr - pts_std`, no ROS stat line. Reported for dev weeks 5-9 only. |
| Charts | weekly saved lists, weeks 5-10 (dev); 11-14 (holdout, as they arrive) | | Same fixtures as v4. |

### 2.2 Thin and rookie histories

- No rows, or non-positive anchor points: the labelled position-mix fallback (step 5).
- Thin history is handled only by the shrinkage, whose strength is chosen on actuals by forward CV
  (2.4). No hand-set minimum game count enters the mix. The 8-game rule is used only to build the
  position prior.
- Reported per chart, week and position: invertible players, fallbacks, and the median game count.
  If more than 25% of invertible RB/WR/TE in a chart-week fall back, that is stated beside every
  result for that week. The run is not stopped.

### 2.3 Fumbles, 2-pt and interceptions (JEG-1687)

- ESPN's stored stat lines have no fumble or 2-pt fields (JEG-1687, Backlog). DDF's ESPN ROS path
  also scores no interceptions. The primary v5 uses the same seven categories, so step 7 is exactly
  DDF's ESPN path and the three presets are unaffected (these terms carry the same weight in all
  three).
- These terms are out of scope until JEG-1687 lands and a history source has them. In the T1b
  custom-scoring check, interceptions (in `player_game_stats`) are included and fumbles and 2-pt
  are not, which is stated.

### 2.4 Forward cross-validation on actuals (step 5 selection and T1)

- History is always strictly before the origin week. Truth = the player's realized stat lines over
  the 4 weeks starting at the origin. Players with at least 2 truth games are scored.
- Selection origins (choose `k`, `t`): 2025 weeks 4, 5, 6, 7, 8 (truth windows end by week 11).
- Test origins (T1 verdict): 2025 weeks 12, 13, 14 (truth through week 17). 2026 origins are added
  only where every truth week has at least 90% of the 2026 weeks 1-4 median row count. That check
  runs and is recorded before any T1 number is computed.
- **Power (D2 A).** With per-stat history only from 2024, the selection origins have one prior
  season, and the test origins are three 2025 weeks plus whatever 2026 weeks qualify. That is
  roughly a few hundred RB/WR/TE per origin and heavily overlapping truth windows, against v4's
  8-11 seasons. The T1 interval will be wide, so INCONCLUSIVE is a likely T1 outcome even if the
  player mix is real. Section 5 treats that case separately from FAIL.
- Objective S (selection): with the player's realized anchor points over the window given, predict
  his stat line as `realized F(s0) x m*_i`. S = the sum over categories of squared error divided by
  that category's variance at the position, averaged over players.

### 2.5 Out of scope

Publication of any kind; changes to `pipelines/`, the engine, fixtures or DDF Value; custom scoring
inside DDF (no path today; JEG-1688 is a separate Backlog ticket); K/DST; superflex and 2-QB as
verdicts (reported only); league-loaded rosters (VP-2.2 d2); fumbles and 2-pt; any fit to CBS
Sports or USA Today.

---

## 3. Tests (pass or fail stated now; no tuning)

### 3.1 Split and the rule for touching weeks

- **Dev = content weeks 5-10.** Every one of them has already been seen by v3 or v4 runs, so they
  can never decide anything. They are used to build the code, run T2, and print descriptive
  numbers. Dev numbers cannot change a rule (preamble).
- **Holdout = content weeks 11, 12, 13, 14.** No chart snapshot for them existed at registration.
  The runner refuses weeks of 11 or later unless given `--holdout <registration commit>`. It runs
  once, after week 14's charts and that week's Sleeper and ESPN runs exist, and everything it
  prints is final. Before that, a holdout week may only be checked for row counts (no value is
  computed).
- The T1 split is on actuals (2.4) and is separate from the chart weeks.
- Intervals: paired player bootstrap, 2,000 resamples, seed 16911, with players resampled within
  position and the holdout weeks averaged within each resample. Shuffle control: within position,
  each player's mix is replaced by another same-position player's, 1,000 permutations, seed 16911.
- Pooling: Tier 1 statistics pool RB, WR and TE (equal weight per position). Per-position values
  are always reported, and a TE result is named when it differs in sign.
- References for T3-T6: `ESPN+Sleeper` = the mean of the two where both exist (all holdout weeks).
  On dev weeks 5-9, ESPN alone (labelled).

### 3.2 Tier 1 (all must pass on the holdout for outcome C)

| # | Test | Statistic | Pass rule |
| --- | --- | --- | --- |
| T1 | **Mechanism on actuals** (no charts): does the player's own full-category mix predict later stat lines better than the position-average mix? | On the test origins (2.4): (a) the error in rescored points when the realized Half points are split by the mix and rescored at Standard and at Full, MAE averaged over both; (b) objective S. Player mix (selected `k`, `t`) vs position mix (`k = infinity`), paired difference. | PASS if, for (a) pooled RB/WR/TE, the interval of (position-mix error - player-mix error) is entirely above 0 **and** the player mix beats the shuffle control's 5th-percentile error. FAIL if the interval is entirely below 0. Otherwise INCONCLUSIVE. (b) is reported with the same labels and is not part of the verdict. |
| T1b | Custom scorings on actuals (descriptive) | (a) at TE premium (+0.5 per TE catch on Full), 6-pt passing TD (Half), and -1 per interception (Half) | Reported, no verdict: the only place the full mix differs from a reception share. |
| T2 | **Exactness** | (i) `Av5_i(s0) = A_i(s0)` for every invertible player, chart and week; (ii) current DDF Value reproduced exactly; (iii) **ESPN-path parity**: run step 7b with ESPN's own ROS stat lines (and ESPN's own waiver line) and it reproduces ESPN's Adjusted at all three scorings | PASS if the max absolute difference is 0.0 (for iii: at most 1e-9, since the bake rounds). (i)-(ii) cannot fail by design and are labelled so. (iii) is the proof that step 7 is the ESPN path. |
| T3 | **Scale and consistency of the mix** (shape) vs ESPN and Sleeper | For holdout chart players: `D_v5` = median over players of abs(log(receptions per anchor point in `m*_i` / the same in the reference)), per position; `D_src` = median abs(log(ESPN's / Sleeper's)) for the same players | PASS if, pooled, the point estimate of `D_v5` is at most `D_src` **and** `D_v5` is below the shuffle control's 5th percentile. FAIL if `D_v5 > 2 D_src`. Otherwise PARTIAL. Every other category is reported the same way, no verdict. |
| T4 | **Scoring response, rank level** (Standard to Full) | Within position, the percentile move of `Av5` (Standard to Full) vs that of the **reference-mix rebuild**: the same chart points `P_i(s0)` split by ESPN+Sleeper's own mix and taken through the same step 7. This isolates the mix: same points, same machinery. Spearman, both charts. | PASS if, for both charts, the pooled correlation's interval is entirely above 0 **and** its point estimate is above the shuffle control's 95th percentile. |
| T5 | **Scoring response, size** | SD of v5's percentile moves / SD of the reference-mix rebuild's, both charts | PASS if the point estimate is in [2/3, 3/2] for both charts: within a factor of 1.5 either way (D3 A, Jeremy 2026-11-16). The interval is reported, not part of the rule. |
| T6 | **Scoring response, level shift** | Standard-to-Full log change of the WR/RB and TE/RB ratios of summed Adjusted over the top 24 RB, 24 WR and 12 TE, for `Av5`, against **ESPN's and Sleeper's own lists** priced by DDF at Standard and Full (Sleeper as a VP-1.4 pseudo-source) | PASS if both ratios, for both charts, lie within [min, max] of ESPN's and Sleeper's own moves, widened on each side by the week-to-week SD of ESPN's own moves over dev weeks 5-10 (ESPN is the only granular list on every dev week), computed and committed before the holdout run. The overshoot count (both references on one side, v5 beyond both) is reported. |
| T7 | **No harm vs unchanged** | Within-position Spearman (RB/WR/TE pooled) of the chart's Adjusted at `s` against ESPN+Sleeper's own Adjusted at `s`: v5 minus unchanged. Cells: FantasyCalc at Standard and Half; FantasyPros at Standard and Full. | Per cell: PASS if the interval's lower bound is at least 0; HARM if the upper bound is below 0; else INCONCLUSIVE. The test passes if no cell is HARM. INCONCLUSIVE cells are named and reported as "not shown to harm", never "improves". |
| T8 | **No harm vs current DDF Value** | The same statistic for DDF Value v5 minus current DDF Value, at Standard, Half and Full | Same labels and rule as T7. |

Shared-input guard: ESPN is one of the three maps in step 4 and the pseudo-source's waiver line, so
T3-T8 are also run with step 4 and the waiver line built from CBS ROS and Razzball only. A Tier 1
verdict that differs between the two runs is marked "hinges on ESPN's shared input" and counts as
not passed. Sleeper is not a DDF input.

### 3.3 Tier 2 (reported, no verdict)

- **G2, chart to chart (kept as descriptive):** v4's T4/T5/T7 statistics against the mean of CBS
  Sports and USA Today: correlation of the Standard-to-Full percentile moves with the shuffle
  placebo, the SD ratio, scale-free WR/RB and TE/RB level moves, the overshoot count, and
  leave-one-out (drop CBS Sports, drop USA Today). The reasons it is no longer a gate are issue 4
  (columns barely reorder, the two publishers agree at 0.29) and section 3.4.
- Level consistency (stat lines per game, not per point) of `shat` vs ESPN and Sleeper. This
  carries the chart's own level opinion (step 4), so it is not a mix test.
- Calibration of `P_i(s0)` against realized ppg (issue 16), repeated on holdout weeks as truth
  accrues.
- Realized points, pre-registered here for when truth exists (season end): within-position
  Spearman at Standard and Full of v5, unchanged, current DDF Value, and FantasyPros as published
  (issue 17). Reported in a dated addendum, never a verdict for this round.
- Literal step-7 variant, v3-style forward maps (`v3_proj` with the v5 mix), allocation held at the
  anchor's, 8/10/14 teams, superflex. Coverage and fallback counts.

### 3.4 Why the ESPN/Sleeper target fixes issue 4, and what it cannot fix

It fixes:
- ESPN and Sleeper publish the stat lines that a scoring formula consumes. Their Standard-to-Full
  response is a computed consequence of their projected catches, not a format column set by hand.
  CBS Half is the exact midpoint 98-100% of the time, and USA Today's Full/Standard ratio is 1.066
  at every position.
- The two are independent projectors (ESPN; Sleeper's numbers come via RotoWire, warehouse doc).
  Their disagreement is measured on the same players and sets T3's tolerance, instead of a band
  chosen without a source.
- They cover every player and are not rounded to chart units. Rounding alone explains 21-56% of
  CBS's within-position move variance.
- The reference-mix rebuild (T4, T5) holds the chart's points and DDF's machinery fixed and swaps
  only the mix, so a failure points at step 5. It cannot be blamed on the publishers' currency or
  levels.

It cannot fix:
- Projections are forecasts, not truth. Agreeing with ESPN and Sleeper shows consistency with two
  projectors, not correctness. Both can share a bias (for example on rookies).
- It says nothing about whether a chart's number means a points forecast (issues 8 and 16). T3-T6
  take `P_i(s0)` as given.
- ESPN is also an input to steps 4 and 7 (guarded by the ESPN-left-out run, not removed).
- Sleeper ROS stat lines exist only from 2026-11-14, so dev weeks 5-9 have ESPN only.
- Levels inside DDF are still set by the shared weights `W` (issue 9). T6 compares DDF-priced moves
  with DDF-priced moves.

---

## 4. Sensitivity runs (each reports every Tier 1 statistic; none can rescue a failed verdict)

| Run | Change |
| --- | --- |
| S-FP-Full | FantasyPros anchored at Full instead of Half |
| S-FC-Half | FantasyCalc anchored at Half instead of Full |
| S-drop-FC, S-drop-FP, S-drop-CBS, S-drop-USAT | drop that chart from DDF Value v5 and current DDF Value (T8), and from the G2 reference where it is one |
| S-drop-ESPN, S-drop-CBSROS, S-drop-RZ | drop that projection from the step 4 maps and the waiver line (S-drop-ESPN is the shared-input guard of 3.2) |
| V-mix0, V-mixinf, V-mix3 | raw history mix (`k = 0`); position mix for all (`k = infinity`, which cannot reorder within a position); v4's reception-share model in place of the full mix |
| V-alloc | allocation held at the anchor's in step 7 |

Rule: a Tier 1 verdict that flips under S-FP-Full or S-FC-Half is marked "hinges on the anchor".
Because the anchors cannot be identified (issue 10), outcome C requires no such hinge. A flip under
dropping one chart or one projection is marked "hinges on <source>" and is stated in the summary
next to the verdict.

---

## 5. Stop rules and what each outcome means

Order: T2 first, on dev. A T2 failure is a bug: fix it, rerun dev, and never run the holdout with a
T2 failure. T1 can be run as soon as the actuals split is in place. It uses no chart week.

| Outcome | When | What it means for Jeremy's decision |
| --- | --- | --- |
| **A: close** | T1 FAIL (the position mix beats the player's own mix on real games), or T1 INCONCLUSIVE with a point estimate at or below 0, or T4 FAIL, or any HARM cell in T7 or T8 | "How the player tends to earn points" is not supported on this data, or the rebuild damages the order. Keep DDF Value as is. The v4 recommendation A stands. No further iteration of the chart unwind. |
| **B: iterate once** | T2 and T4 pass, no HARM, and either (i) T1 passes but T3, T5 or T6 fail or are PARTIAL, or a verdict hinges on an anchor; or (ii) T1 is INCONCLUSIVE with a point estimate above 0 (low power, D2 A), whatever T3, T5 and T6 show | (i) The premise holds but the size, levels or mix shape is off: one more pre-registered round changes only the failing step. (ii) The mix is not shown to fail, only underpowered: the round re-runs T1 with 2026 origins added as their actuals reach the 90% coverage rule. No other change, and no new history source (D2 A stands). Either way the round is written before its run, with holdout weeks 15-17. If it does not reach C, close (A). |
| **C: proceed to a separate enhanced value** | Every Tier 1 test passes (T7/T8 with no HARM), no hinge on either anchor | Open a new ticket to design a separate, labelled "scoring-aware" value shown beside DDF Value (like Personalized DDF). DDF Value, the charts and the pipeline stay as they are. The new value gets its own review and Jeremy's go before anything is published. C is not a finding that charts encode stat lines (section 6). |

Prediction, written now so the result can be compared with it:
- T1 passes at RB and WR and is weak at TE (v4 stability: reception share ICC 0.56 / 0.44 / 0.18).
- T2 passes. T4 passes.
- T5: the raw mix overshoots. For the shrunk mix, no prediction.
- T6: likely passes, because the fixed `b_p` that the lead named as the cause of issue 2 is gone.
- T7 and T8: INCONCLUSIVE.
- Expected overall: **B**. Most likely via (ii), T1 inconclusive with a positive point estimate on
  two seasons of per-stat data. **A** if that point estimate is at or below 0.

What the 2024-on history does to A versus B: low power makes a T1 FAIL unlikely, since the interval
must clear 0 on the wrong side, and makes INCONCLUSIVE likely. So with D2 A, T1 mostly decides
between B(ii) and A through the sign of its point estimate. It rarely produces C on its own: C
needs the interval entirely above 0, which two seasons may not give even for a real effect.

---

## 6. Limits: what stays unsolved

- **Issue 16: chart points are not a calibrated forecast.** v4's slopes of realized ppg on
  `P_i(s0)` ran from RB 0.21-0.53 to TE 1.07-1.70, with R^2 below the projections' in 16 of 18
  chart-positions. v5 does not change step 4, so this is inherited in full.
- **Issue 8: invertibility.** DDF's side of the inversion is exact. Nothing shows that a chart's
  value is a points forecast with a recoverable stat mix. FantasyPros is a fixed rank ladder, and
  FantasyCalc is one base list times position constants. v5 supplies the stat mix from history, not
  from the chart. So the assumed stat line is the player's history scaled to the chart's level, not
  something the chart says.
- **Issue 10: anchors.** FantasyCalc Full and FantasyPros Half are assumptions. The sensitivity runs
  show whether the result depends on them; they cannot settle them.
- **Issue 9: levels.** Adjusted forces every source's position totals to `Pie x W`, so the chart's
  own position levels are gone before step 7. v5's level moves are DDF's.
- **Issue 15: no adjudicating truth this season.** Realized points cannot separate the methods on a
  few weeks. T1 uses real games but tests only the mix, not the chart chain.
- **The full mix barely matters in DDF's formats.** On Standard, Half and Full only receptions
  change weight (section 1, algebra). The full-category mix pays off only for custom scoring, which
  DDF does not price (JEG-1688 is Backlog).
- **Data.** Per-stat history starts in 2024 (two seasons plus part of 2026), so T1 has few test
  origins. Fumbles and 2-pt are absent (JEG-1687). 2026 weeks 5+ actuals are partial.
- **Small, overlapping sample.** Four holdout weeks of slowly changing rest-of-season lists are not
  four independent tests. The bootstrap is over players, not weeks.
- **Close kin to a failed variant.** `v3_proj` (step 7 by the projections' maps) lost 0 of 40
  against the publishers. v5 is judged against a different target. If v5 passes here, the reading
  is "consistent with granular projectors", not "agrees with CBS Sports and USA Today".

---

## Frozen decisions (Jeremy, 2026-11-16, multiple choice)

| # | Decision | Where it binds |
| --- | --- | --- |
| D1 A | Step 7 in delta form: exact at the anchor; the response is DDF's ESPN-style pricing of the assumed line | Step 7c primary; the literal form is reported only |
| D2 A | History = stored `player_game_stats`, 2024 on; no nflverse per-stat load | Step 5, 2.1, 2.4 (power note), section 5 |
| D3 A | T5 passes within a factor of 1.5 either way, [2/3, 3/2] | T5 |
| D4 A | Holdout weeks 11-14, one decisive run | 3.1 |
| D5 A | Shrinkage allowed, strength chosen by forward CV on real games only, never on charts | Step 5; V-mix0 (raw) stays a reported variant |

## Amendments

- 2026-11-16, before any run: D1-D5 frozen as above.
  - Rules changed: T5 band confirmed; the T1 power note added (2.4); stop rules split T1
    INCONCLUSIVE by the sign of its point estimate (A vs B(ii)); the summary updated.
  - No pass threshold was loosened, and no dev number existed.
