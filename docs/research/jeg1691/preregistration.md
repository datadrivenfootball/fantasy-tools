# JEG-1691 v5: pre-registration (written 2026-11-16, before any v5 code or run)

Status (2026-11-17): **decisions D1-D5 frozen by Jeremy on 2026-11-16 (see "Frozen decisions").
The dev run on weeks 5-7 has been done (debugging, amendment 9); its numbers decide nothing. The
decisive run on weeks 8-10 has not been done and waits for the independent review.** Nothing here
changes a published number, the pipeline, or DDF Value. Jeremy, 2026-11-16: "Don't mess with the
current architecture, we are exploring an enhanced value, not doing a cutover." Parent: JEG-1597.
Prior versions: v1 JEG-1597 (#1405), v2 JEG-1605 (#1408, #1414), v3 JEG-1610 (#1415), v4 JEG-1611
(#1417). Issue numbers below refer to the 22-issue walkthrough of 2026-11-16.

Nothing in sections 1-5 changes after the first decisive number (weeks 8-10) is printed. Any change before that
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
is within a factor of 1.5 either way of the reference. One decisive run, no peeking. Thin
histories may be pulled toward the position average, by an amount set on real games only.

**One honest catch.** Two seasons of per-stat history give the real-games test (test 1) little
power. If it comes out "can't tell" rather than "no", that is not read as a no: it blocks the
separate value, but allows one more round once more 2026 games are recorded.

**What happens next.** Jeremy's direct instruction on 2026-11-16 was "nothing in this project
needs to wait". So the test uses chart snapshots that already exist, instead of waiting for weeks
11-14 as first written. Weeks 5-7 were used only to debug the code. Weeks 8-10
decide the result in one run. Weeks 11-14 re-run the same frozen test later as a check, and no
decision waits for them. One caveat: weeks 8-9 charts were already looked at in the two earlier
tries (v3 and v4). v5's method, its ESPN and Sleeper target and these tests were not built on
them, but because people had seen those weeks, a pass there is somewhat weaker evidence than a
pass on brand-new weeks would be. Three outcomes: **A** close it and keep DDF Value as is; **B**
one more pre-registered round on the step that failed; **C** build a separate, clearly labelled
"scoring-aware" value next to DDF Value. In no case is DDF Value replaced.

**What the dev run already showed, and why it weakens the decisive run.**
- The dev run on weeks 5-7 ran every chart test (T2 to T8) and the sensitivity checks. Nothing in
  it decides anything.
  - Under the rules as first written, every chart test passed on dev.
  - Under the rules as amended after review, the code's dev verdict reads B:
    - T5 fails at FantasyPros wide receivers (the per-position rule, amendment 12);
    - T6 hinges on reading FantasyPros at Full;
    - T1 was not computed on dev.
- Weeks 8-10 overlap heavily with weeks 5-7. The charts' rest-of-season lists change slowly from
  week to week, so the decisive run is close to a repeat on very similar data, not an independent
  test.
- Some tests can barely fail by construction:
  - **T6 (position levels):** DDF prices every source's position totals the same way. v5's
    Standard-to-Full WR/RB move (0.7057 on dev) therefore lands almost exactly on ESPN's (0.7053).
  - **T5 (move size):** it compares v5 with a rebuild that runs the same chart points through the
    same machinery, so it measures only the spread of the stat mix.
  - **T2 (exactness):** it checks the code, not the idea.
- The tests that can fail on the idea are T1 (on real games), T3 and T4, T5 at each position (dev:
  FantasyPros wide receivers at 0.21-0.28, far outside the band), and T7/T8 (no harm).

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
- 7b. Pseudo-source `c-v5`: natives `P_i(s)` for the invertible players and the projections' mean
  ppg `m_j(s)` for every other player (amendment 4), run at `s` as a projection source **outside `I`**.
  That is the existing VP-1.4 path: it goes through VP-2, VP-3, VP-5 against the run's allocation,
  pie and `W`, and contributes nothing to weights, peers, `m` or DDF Value. The allocation is
  re-derived at `s` as DDF does (Jeremy's literal step 7); a variant holds it at the anchor's.
  Because the list holds every player the projections price, its waiver line comes out of the
  pipeline's own rule at `R_p`; no waiver override is needed (this replaces the waiver deviation
  first written here, which would have needed a pipeline change).
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
| Per-stat history (step 5, T1) | Supabase `player_game_stats` (JSONB `stats`), cache `cache/pgs_weekly_2024_2026.json.gz` (`fetch_history.py`, anon REST, 42,721 rows, fetched 2026-11-17) | 2024-2025, 2026 weeks 1-10. Weeks 1-4 hold about 1,110 rows but only 286-297 with any stat; weeks 5-10 (ESPN actuals, JEG-521) hold 258-294 rows, 241-273 with a stat, so they are not partial in substance (amendment 2) | Pass, rush and receiving yards and TDs, receptions, targets, interceptions; no fumbles or 2-pt. `player_key` via `projection_snapshots` (anon cannot read `players`): 739 keyed players; 929 stat rows stay unkeyed and out. |
| Per-stat history 2015-2023 | none in repo | none | `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz` holds points only. The nflverse idmap covers 59.4% of chart players. Not loaded (D2 A, Jeremy 2026-11-16). |
| Receptions 2015-2025 | `ppr - std` from the nflverse points file | exact | Used only by v4's share model (sensitivity variant V-mix3). |
| ESPN ROS stat lines | `data/inputs/espn_projections.csv`, 7 categories, at the commit that built each content week's fixture (68 commits since 2026-09-22) | weeks 5-10 dev; 11+ as they land | Divided by team games remaining as in the bake. |
| ESPN weekly stat lines | `source_weekly_projections` (JEG-1641), 9 keys incl. INT | first run 2026-11-16 | Not used (the CSV is DDF's own ESPN input). |
| Sleeper stat lines | `source_weekly_projections`, Sleeper's full stat dict | first Sleeper run 2026-11-16 (not 11-14), target weeks 10-18 | Week 10 only; cache `tools/research/jeg1691/cache/sleeper_ros_week10.json` (read-only SQL, checksums against SQL). |
| Sleeper before 2026-11-16 | `data/inputs/weekly_projections_sleeper.csv.gz` | one vintage, 2026-10-08 (week 5: 2026-10-10), target weeks 1-18, points only | Weeks 5-9; receptions = `pts_ppr - pts_std`. See 2.6. |
| ESPN captures | `source_projection_captures`, ESPN, week horizon | 2026-10-24 to 2026-11-15, target weeks 7-18, points by format only | Cross-check, weeks 7-10; cache `cache/espn_captures_ros.json`. |
| Charts | weekly saved lists in `data/history/week-<w>.json`, weeks 5-7 (dev), 8-10 (decisive), 11-14 (replication, as they arrive) | | Same fixtures as v4. |

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
  only where every truth week has at least 80% of the 2026 weeks 1-4 median count of rows with a
  stat (amendment 2). On 2026-11-17 that gives origins 2026 weeks 5, 6, 7 (truth through week 10).
  A game counts only when it has a nonzero stat in a scored category or targets.
- **Power (D2 A).** With per-stat history only from 2024, the selection origins have one prior
  season, and the test origins are three 2025 weeks plus whatever 2026 weeks qualify. That is
  roughly a few hundred RB/WR/TE per origin and heavily overlapping truth windows, against v4's
  8-11 seasons. The T1 interval will be wide, so INCONCLUSIVE is a likely T1 outcome even if the
  player mix is real. Section 5 treats that case separately from FAIL.
- Objective S (selection): with the player's realized anchor points over the window given, predict
  his stat line as `realized F(s0) x m*_i`. S = the sum over categories of squared error divided by
  that category's variance at the position, averaged over players.

### 2.6 Reference pairing with chart weeks (amendment 3)

Rule: every reference comes from a vintage no later than the DDF ESPN snapshot of the same
content week (`data/history/week-<w>.json`, `sources.espn.captured_at`). The ROS target weeks are
ESPN's own `weeks_covered` for that snapshot, except where noted. Pinned by
`tests/test_jeg1691_v5.py::test_reference_caches_respect_cutoffs`.

| Chart week | Charts pulled | ESPN ROS stat line (primary; 7 categories) | ESPN captures (cross-check; receptions only) | Sleeper |
| --- | --- | --- | --- | --- |
| 5 (dev) | 2026-10-06..09 | commit 71b5f891d, snapshot 2026-10-12, weeks 6-18 | none (captures start 2026-10-24) | CSV vintage 2026-10-08, weeks 6-18, points only |
| 6 (dev) | 2026-10-13..14 | e5b571f78, 2026-10-19, weeks 7-18 | none | CSV 2026-10-08, weeks 7-18 |
| 7 (dev) | 2026-10-22 | 693c0ca4a, 2026-10-25, weeks 7-18 | latest batch before 2026-10-25T19:49Z, weeks 8-18 | CSV 2026-10-08, weeks 7-18 |
| 8 (decisive) | 2026-10-27..28 | 8a3855823, 2026-10-31, weeks 8-18 | latest batch before 2026-10-31T19:47Z, weeks 9-18 | CSV 2026-10-08, weeks 8-18 (about 3 weeks stale) |
| 9 (decisive) | 2026-11-03..04 | 284b7efac, 2026-11-09, weeks 10-18 | latest batch before 2026-11-10T01:13Z, weeks 10-18 | CSV 2026-10-08, weeks 10-18 (about 4 weeks stale) |
| 10 (decisive) | 2026-11-10..12 | 24b3a6519, 2026-11-16, weeks 11-18 | latest batch before 2026-11-16T18:51Z, weeks 11-18 | warehouse run 2026-11-16T18:51Z, weeks 11-18, full stat dict (RotoWire) |
| 11-14 (replication) | as they arrive | the week's commit, same rule | same rule | the warehouse run nearest before the week's ESPN snapshot |

- ESPN captures (`source_projection_captures`, ESPN, week horizon) hold points by format only, not
  stat lines. Receptions = Full minus Standard points. They cross-check the CSV's receptions and
  enter no verdict.
- Sleeper: no stored history of past Sleeper vintages exists, and Sleeper's API serves only its
  latest projection for a week, so no back-fill reproduces what Sleeper said on a past date. Weeks
  5-9 use the one stored vintage (2026-10-08, `data/inputs/weekly_projections_sleeper.csv.gz`, points
  only). It is older than the charts of weeks 8-9, never newer. Week 10 uses the warehouse (JEG-1641;
  its first Sleeper run is 2026-11-16). So Sleeper on weeks 8-9 is stale and points-only.
  - Points-only is enough on DDF's three formats: catches = PPR minus Standard points, and the
    presets differ only in the catch weight (section 1, algebra).
  - Staleness is not neutral (corrected in amendment 14). It widens the ESPN-Sleeper disagreement,
    which makes T3 (`D_src`) and T6 (the envelope) easier to pass. It also feeds the reference half
    of T4, T5, T7 and T8.
  - So the decisive report shows the week-10-only result (fresh Sleeper) beside the weeks 8-10
    result. A Tier 1 test that passes on weeks 8-10 and fails on week 10 alone sends the outcome to
    B.
- Sleeper's own list as per-game natives (T6-T8) = ROS points / projected weeks. ESPN's own list
  is DDF's ESPN source as it is.

### 2.5 Out of scope

Publication of any kind; changes to `pipelines/`, the engine, fixtures or DDF Value; custom scoring
inside DDF (no path today; JEG-1688 is a separate Backlog ticket); K/DST; superflex and 2-QB as
verdicts (reported only); league-loaded rosters (VP-2.2 d2); fumbles and 2-pt; any fit to CBS
Sports or USA Today.

---

## 3. Tests (pass or fail stated now; no tuning)

### 3.1 Split and the rule for touching weeks

- **Dev = content weeks 5-7.** Used only to debug the code (run 2026-11-16, recorded in the
  amendments), to run T2, and to freeze the T6 widening. No dev number can change a rule.
- **Decisive = content weeks 8, 9, 10, one run.** The runner (`tools/research/jeg1691/run_v5.py`)
  refuses weeks 8-10 unless given `--decisive <commit>` equal to the checked-out HEAD, with a clean
  tree under the registered paths, and refuses a second decisive run. Everything it prints is final.
- **Honesty about weeks 8-10.** Weeks 8 and 9 chart data were loaded and read in v3 (JEG-1610) and
  v4 (JEG-1611, the "confirmation run"; issue 13). v4's pass rule planned a week 10 run; whether it
  ran is not found in the records. v5's method, its ESPN and Sleeper stat-line target, its tests and
  its thresholds were not tuned on any chart week: the step 5 strength is set on 2025 actuals
  only, and every rule here was written before any v5 number on weeks 8-10 existed. What lowers
  confidence: the people who wrote v5 knew v3's and v4's results on weeks 8-9 (for example that the
  rebuild overshoots the publishers), and the design choices of v5 (judge against ESPN and Sleeper;
  DDF's own pricing in step 7) were made knowing them. A pass on weeks 8-10 is therefore weaker
  evidence than a pass on unseen weeks, and the replication on weeks 11-14 is reported beside it.
- **Replication = content weeks 11-14**, run later with `--replication <commit>` and the same frozen
  rules. It blocks no decision. If its verdict differs from the decisive one, that is stated next to
  the decision; it does not reopen it.
- The T1 split is on actuals (2.4) and is separate from the chart weeks.
- Intervals: paired player bootstrap, 2,000 resamples, seed 16911, with players resampled within
  position and the decisive weeks averaged within each resample. Shuffle control: within position,
  each player's mix is replaced by another same-position player's, 1,000 permutations, seed 16911.
- Pooling: Tier 1 statistics pool RB, WR and TE (equal weight per position). Per-position values
  are always reported, and a TE result is named when it differs in sign.
- References for T3-T8: `ESPN+Sleeper` = the mean of the two, on players both price. The exact
  pairing of reference vintages with chart weeks is in 2.6.

### 3.2 Tier 1 (all must pass on the decisive weeks for outcome C)

| # | Test | Statistic | Pass rule |
| --- | --- | --- | --- |
| T1 | **Mechanism on actuals** (no charts): does the player's own full-category mix predict later stat lines better than the position-average mix? | On the test origins (2.4): (a) the error in rescored points when the realized Half points are split by the mix and rescored at Standard and at Full, MAE averaged over both; (b) objective S. Player mix (selected `k`, `t`) vs position mix (`k = infinity`), paired difference. | PASS if, for (a) pooled RB/WR/TE, the interval of (position-mix error - player-mix error) is entirely above 0 **and** the player mix beats the shuffle control's 5th-percentile error. FAIL if the interval is entirely below 0. Otherwise INCONCLUSIVE. (b) is reported with the same labels and is not part of the verdict. |
| T1b | Custom scorings on actuals (descriptive) | (a) at TE premium (+0.5 per TE catch on Full), 6-pt passing TD (Half), and -1 per interception (Half) | Reported, no verdict: the only place the full mix differs from a reception share. |
| T2 | **Exactness** | (i) `Av5_i(s0) = A_i(s0)` for every invertible player, chart and week; (ii) current DDF Value reproduced; (iii-a) **pipeline-path parity**: a pseudo-source outside I fed ESPN's own natives reproduces ESPN's Adjusted at all three scorings; (iii-b) **scoring parity**: ESPN's ppg ratios across scorings equal those of its CSV stat lines | PASS if (i) and (iii-a) are exactly 0.0, (ii) is at most 1e-9 (summation order), and (iii-b) is at most 1e-4 (the bake rounds ppg to 6 dp; loosened from 1e-9 after the dev run, amendment 16). (i) and (ii) cannot fail by design and are labelled so. (iii) is the proof that step 7 is the ESPN path. |
| T3 | **Scale and consistency of the mix** (shape) vs ESPN and Sleeper | For the decisive weeks' chart players: `D_v5` = median over players of abs(log(receptions per anchor point in `m*_i` / the same in the reference)), per position; `D_src` = median abs(log(ESPN's / Sleeper's)) for the same players | PASS if, pooled, the point estimate of `D_v5` is at most `D_src` **and** `D_v5` is below the shuffle control's 5th percentile. FAIL if `D_v5 > 2 D_src`. Otherwise PARTIAL. Every other category is reported the same way, no verdict. |
| T4 | **Scoring response, rank level** (Standard to Full) | Within position, the percentile move of `Av5` (Standard to Full) vs that of the **reference-mix rebuild**: the same chart points `P_i(s0)` split by ESPN+Sleeper's own mix and taken through the same step 7. This isolates the mix: same points, same machinery. Spearman, both charts. | PASS if, for both charts, the pooled correlation's interval is entirely above 0 **and** its point estimate is above the shuffle control's 95th percentile. |
| T5 | **Scoring response, size** | SD of v5's percentile moves / SD of the reference-mix rebuild's, both charts; pooled over RB/WR/TE and per position (each week-averaged) | PASS only if, for both charts, the pooled point estimate **and** each position's (RB, WR, TE) are in [2/3, 3/2], within a factor of 1.5 either way (D3 A, Jeremy 2026-11-16). The per-position rule is amendment 12, written after the dev per-position values were seen. The interval is reported, not part of the rule. |
| T6 | **Scoring response, level shift** | Standard-to-Full log change of the WR/RB and TE/RB ratios of summed Adjusted over the top 24 RB, 24 WR and 12 TE, for `Av5`, against **ESPN's and Sleeper's own lists** priced by DDF at Standard and Full (Sleeper as a VP-1.4 pseudo-source) | PASS if both ratios, for both charts, lie within [min, max] of ESPN's and Sleeper's own moves, each ratio averaged over the decisive weeks, widened on each side by the week-to-week SD of ESPN's own moves over dev weeks 5-7 (frozen in `out/t6_widening.json` by the dev run, before the decisive run). The overshoot count (both references on one side, v5 beyond both) is reported. |
| T7 | **No harm vs unchanged** | Within-position Spearman (RB/WR/TE pooled) of the chart's Adjusted at `s` against ESPN+Sleeper's own Adjusted at `s`: v5 minus unchanged. Cells: FantasyCalc at Standard and Half; FantasyPros at Standard and Full. | Per cell: PASS if the interval's lower bound is at least 0; HARM if the upper bound is below 0; else INCONCLUSIVE. The test passes if no cell is HARM. INCONCLUSIVE cells are named and reported as "not shown to harm", never "improves". |
| T8 | **No harm vs current DDF Value** | The same statistic for DDF Value v5 minus current DDF Value, at Standard, Half and Full | Same labels and rule as T7. |

Shared-input guard: ESPN is one of the three maps in step 4 and part of the pseudo-source's waiver
pool, so T3-T8 are also run with **only those two uses** built from CBS ROS and Razzball
(`S-noESPN-step4`). ESPN stays in the pipeline runs, so the ESPN half of the reference in T6-T8 is
unchanged (amendment 10). A Tier 1 test that passes in the primary and fails there sends the
outcome to B (section 5). Sleeper is not a DDF input.

How hard each test is to fail (said plainly; amendment 13):
- **T2** checks the code. Parts (i) and (ii) cannot fail by design; (iii) can fail only through a
  pipeline-path bug.
- **T6** can barely fail. DDF forces every source's position totals to the same shared weights, so
  any list priced through DDF moves its levels about as ESPN's does (dev: v5 WR/RB 0.7057 vs ESPN
  0.7053). It stays in Tier 1, but a pass says little.
- **T5 and T4** compare v5 with a rebuild through the same machinery from the same chart points.
  They test only the spread and the order of the mix's moves, not the pricing. Pooled over
  positions, T5 can hide one position far off, hence the per-position rule.
- **T3** tests only the reception share per point against two projectors.
- **T1, T7 and T8** test the idea: real games, and no harm.


### 3.3 Tier 2 (reported, no verdict)

- **G2, chart to chart (kept as descriptive):** v4's T4/T5/T7 statistics against the mean of CBS
  Sports and USA Today: correlation of the Standard-to-Full percentile moves with the shuffle
  placebo, the SD ratio, scale-free WR/RB and TE/RB level moves, the overshoot count, and
  leave-one-out (drop CBS Sports, drop USA Today). The reasons it is no longer a gate are issue 4
  (columns barely reorder, the two publishers agree at 0.29) and section 3.4.
- Level consistency (stat lines per game, not per point) of `shat` vs ESPN and Sleeper. This
  carries the chart's own level opinion (step 4), so it is not a mix test.
- Calibration of `P_i(s0)` against realized ppg (issue 16), repeated on the decisive weeks as truth
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
- Sleeper stat lines exist only from 2026-11-16. Weeks 8-9 use a stale, points-only Sleeper vintage (2.6).
- Levels inside DDF are still set by the shared weights `W` (issue 9). T6 compares DDF-priced moves
  with DDF-priced moves.

---

## 4. Sensitivity runs (each reports every Tier 1 statistic; none can rescue a failed verdict)

| Run | Change |
| --- | --- |
| S-FP-Full | FantasyPros anchored at Full instead of Half |
| S-FC-Half | FantasyCalc anchored at Half instead of Full |
| S-noESPN-step4, S-noCBSROS-step4, S-noRZ-step4 | that projection is left out of step 4's maps and the pseudo-source's waiver pool only. The pipeline, and so every reference, keeps all sources (amendment 10) |
| S-drop-fantasycalc, S-drop-fantasypros, S-drop-cbs, S-drop-usatoday | that chart is left out of DDF Value v5 and current DDF Value (T8; the other tests are unchanged by it) |
| W10-only (fresh Sleeper) | the battery on week 10 alone (decisive run only; amendment 14) |
| V-mix-k0, V-mix-kinf, V-mix-v4share | raw history mix, position mix for all, v4's reception-share model: reported only (alternative methods, not assumptions, so they cannot move the outcome) |

Rule, applied by `tools/research/jeg1691/outcome.py` and not by judgement: a Tier 1 chart test
(T3, T4, T5, T6, or no HARM in T7/T8) that passes in the primary and fails in any run above except
the V-mix rows sends the outcome to B. The verdict names the run as "hinges on <run>". A T2 failure
under any run also sends it to B. V-alloc (allocation held at the anchor's) was listed in the first
registration and is not implemented; it is dropped (amendment 15).

---

## 5. Stop rules and what each outcome means

Order: T2 first, on dev. A T2 failure is a bug: fix it, rerun dev, and never run the decisive weeks with a
T2 failure. The outcome is picked by `outcome.decide()` (amendment 11) from the primary battery,
every sensitivity battery, the week-10-only battery and T1. It is written to
`out/decisive/verdict.json` with every rule that fired. Rules apply in order: void, then A, then
B, then C.

| Outcome | When (all of these are code) |
| --- | --- |
| **B (void run)** | T2 fails on the decisive weeks. The run is void. After a dated bug fix, weeks 11-14 become the decisive weeks of a B round, run once with the same rules. |
| **A** | T1 FAIL; T1 INCONCLUSIVE with point estimate <= 0; T4 FAIL in the primary; any HARM in T7 or T8 in the primary |
| **B** | none of the above, and any of: T1 INCONCLUSIVE with point estimate > 0; T3 not PASS, or T5 or T6 failing in the primary; a Tier 1 test passing in the primary but failing under an anchor, ESPN-left-out, CBS-ROS-left-out, Razzball-left-out, one-chart-dropped or week-10-only run; T2 failing in any sensitivity run |
| **C** | none of the above: T1 PASS, every Tier 1 chart test passes in the primary and in every sensitivity run |

What each outcome means for Jeremy's decision:

| Outcome | When | What it means for Jeremy's decision |
| --- | --- | --- |
| **A: close** | as in the table above | "How the player tends to earn points" is not supported on this data, or the rebuild damages the order. Keep DDF Value as is. The v4 recommendation A stands. No further iteration of the chart unwind. |
| **B: iterate once** | as in the table above: (i) a chart test fails or hinges; (ii) T1 INCONCLUSIVE above 0 | (i) The premise holds but the size, levels or mix shape is off: one more pre-registered round changes only the failing step. (ii) The mix is not shown to fail, only underpowered: the round re-runs T1 with 2026 origins added as their actuals reach the coverage rule of 2.4. No other change, and no new history source (D2 A stands). Either way the round is written before its run. Its decisive weeks are the first unused chart weeks (11-14, which then stop being a replication of this round). This is the only case where anything waits for new weeks. If it does not reach C, close (A). |
| **C: proceed to a separate enhanced value** | as in the table above | Open a new ticket to design a separate, labelled "scoring-aware" value shown beside DDF Value (like Personalized DDF). DDF Value, the charts and the pipeline stay as they are. The new value gets its own review and Jeremy's go before anything is published. C is not a finding that charts encode stat lines (section 6). |

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

### How to run the decisive run (amendment 17)

1. After the review, commit `tools/research/jeg1691/APPROVAL.json`:
   `{"reviewed_commit": "<full sha>", "reviewer": "...", "date": "..."}`. Push it.
2. Make a fresh clone of the branch and work only in it. Run with a Python 3.12 interpreter that
   has numpy and scipy. The decisive run of 2026-11-17 used a throwaway venv
   (`scratchpad/v5venv/bin/python`: Python 3.12.12, numpy 2.5.5, scipy 1.18.1). The system
   `python3` (3.9) also has numpy and scipy, but it is not the registered interpreter.
3. Run `<that interpreter> tools/research/jeg1691/run_v5.py --weeks 8 9 10 --decisive <reviewed sha>`. The
   runner refuses `--quick`, `--no-sensitivity`, a subset of the weeks, or a tree that differs from
   the reviewed commit.
4. Straight away, commit and push `tools/research/jeg1691/DECISIVE.lock` and
   `tools/research/jeg1691/out/decisive/` together, in one commit. Then copy the outcome and its
   rules from `out/decisive/verdict.json` into Linear.

Known limits of the guard:
- Git-ignored files such as `__pycache__` are not checked.
- Until the lock commit is pushed, someone who deletes the worktree lock and the home record
  (`~/.local/state/jeg1691/`), or who uses another clone, can run again. Pushing the lock commit at
  once is what closes this.

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
  origins. Fumbles and 2-pt are absent (JEG-1687). 2026 weeks 5-10 are complete in substance
  (amendment 2).
- **Weeks 8-10 were not unseen** (3.1). The decisive weeks were read by v3 and v4.
- **Small, overlapping sample.** Three decisive weeks of slowly changing rest-of-season lists are not
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
| D4 (week choice replaced 2026-11-16) | Jeremy, 2026-11-16: "nothing in this project needs to wait". Decisive run once on existing weeks 8-10; dev 5-7 for debugging only; weeks 11-14 an automatic later replication that blocks nothing (amendment 1). One run, no peeking, as D4 A asked | 3.1, section 5 |
| D5 A | Shrinkage allowed, strength chosen by forward CV on real games only, never on charts | Step 5; V-mix0 (raw) stays a reported variant |

## Amendments

- 2026-11-16, before any run: D1-D5 frozen as above.
  - Rules changed: T5 band confirmed; the T1 power note added (2.4); stop rules split T1
    INCONCLUSIVE by the sign of its point estimate (A vs B(ii)); the summary updated.
  - No pass threshold was loosened, and no dev number existed.
- 2026-11-16, before any v5 number on weeks 8-10 (coordinator relaying Jeremy: "nothing in this
  project needs to wait"). These are implementation and data findings; no pass threshold was
  loosened.
  1. **Weeks.** Decisive run once on the existing weeks 8-10. Weeks 5-7 are for debugging only.
     Weeks 11-14 are a later replication that blocks nothing (3.1, section 5). The seen-weeks
     caveat is in 3.1 and section 6.
  2. **Game rows and 2026 coverage.** A game counts only when it has a stat. The 2026 weeks 1-4 rows
     are mostly zero-stat rows, and weeks 5-10 are complete in substance. So the T1 coverage rule
     uses rows with a stat, at 80% of the weeks 1-4 median, instead of 90% of all rows (2.4).
  3. **Reference pairing** fixed in 2.6. Two discoveries:
     - Sleeper's first warehouse run is 2026-11-16, not 11-14.
     - No source holds past Sleeper vintages, so weeks 8-9 use the stale 2026-10-08 points-only
       vintage.
  4. **Step 7b.** The pseudo-source lists the projections' mean ppg for every other player. Its
     waiver line then comes from the unmodified pipeline, with no override.
  5. **Shuffle control for T4.** Each permutation is priced through the pseudo-source's own
     ppg-to-Adjusted map from the primary run (`unwind.forward`). That replaces 1,000 new pipeline
     runs per chart-week. The permutation itself is unchanged.
  6. **T2 tolerances.**
     - The identity is exact (0.0).
     - DDF Value reproduction: at most 1e-9, because sums run in a different order.
     - ESPN-path parity of the pipeline: exact.
     - ESPN scoring parity against the CSV stat lines: at most 1e-4, because the bake rounds ppg to
       6 dp.
  7. **Implementation choices.**
     - T6 uses the mean over the decisive weeks.
     - T3 compares v5 with the geometric mean of ESPN and Sleeper (log measure).
     - The reference mix for T4/T5 is the arithmetic mean of their receptions per anchor point.
     - T4, T5 and T3 use the invertible RB/WR/TE players both references price.
     - Step 5's strengths are chosen at the Half anchor and applied at both anchors.
     - The search is coordinate descent: two passes, categories in a fixed order, ties to the
       larger `k`.
  8. **Code base.** v4's lane code (`tools/research/jeg1597`, `jeg1605`, `jeg1610`, `jeg1611`, and
     `out/shrink/model.json`) is copied unchanged from commit 7c53ed9 of PR #1417, so the harness
     runs on current main's pipeline. v4's own tests pass there (20 of 20).
  9. **Dev run done 2026-11-16.**
     - `run_v5.py --weeks 5 6 7` (quick mode while debugging, then full) ran on dev weeks only.
     - It found and fixed one bug: floating-point order in the delta form broke the exact identity.
     - The T6 widening was frozen from these weeks.
     - It also ran the step 5 selection, which uses selection origins only.
     - No T1 test origin was run, and no week 8-10 value was computed or printed. v4's loader reads
       the history files whole, as v4 noted.
- 2026-11-17, after review round 1 of PR #1472 (head 0637e6680), before any week 8-10 v5 number.
  10. **ESPN-left-out** removes ESPN from step 4's maps and the waiver pool only, not from the
      pipeline. Earlier code dropped ESPN from the pipeline, which also removed the ESPN half of
      the T6-T8 reference. CBS ROS and Razzball left-out work the same way.
  11. **Outcome in code.** `outcome.decide()` picks A, B or C, with void and hinge rules covering
      the gaps the review found: a T4 FAIL, a T2 failure on weeks 8-10, and a result that depends
      on ESPN or on one chart. The rule that fired goes into `out/decisive/verdict.json`.
  12. **Per-position T5.** The rule now requires each position in band, not only the pooled ratio.
      This was written after the dev values were seen (FantasyPros WR 0.21-0.28 on dev), so it is a
      tightening made with knowledge of dev, and it is recorded as such.
  13. **How hard each test is to fail** is now stated (3.2 and the summary). T6 is near-mechanical.
  14. **Stale Sleeper correction.** Amendment 3 said staleness "can only" make the references
      disagree more. That was wrong in effect: it makes T3 and T6 easier to pass and also feeds
      T4, T5, T7 and T8. The week-10-only battery is added, and a test that passes on weeks 8-10
      but fails on week 10 alone sends the outcome to B.
  15. **Guard hardening.**
      - `APPROVAL.json` (committed) must name the reviewed commit, and the run must be given that
        commit.
      - The executed tree must match the reviewed commit blob for blob: pipeline, config, history,
        inputs, v4's lane code, the harness and caches, the frozen T6 widening and this doc. No
        untracked file may be in it.
      - A lock is written before any value is computed, in the worktree and outside the repo
        (`~/.local/state/jeg1691/`). A lock in any git ref also blocks, so deleting `out/` cannot
        reset it.
      - V-alloc is dropped (it was never implemented).
  16. **Corrections to the record (said plainly).**
      - "No pass threshold was loosened" in amendments 2-9 is not fully true. T2(iii) was first
        registered as "at most 1e-9". After the dev run showed 1e-6 for ESPN scoring parity
        (the bake rounds ppg to 6 dp), it was set to 1e-4. That is a loosening made after seeing a
        dev number, for a reason in the bake, not to make a test pass.
      - The first dev outputs and `out/t6_widening.json` were written at 21:32 CST on 2026-11-16,
        on code not yet committed. The amendments that describe that run were committed at 21:53
        (0637e6680).
      - The T6 widening was frozen from that first dev run. The 0.0 identity bug fix came after it,
        but the widening reads only ESPN's own level moves, which the fix does not touch.
      - The status line "No experiment has been run" stayed in the header after the dev run. It is
        now corrected.
- 2026-11-17, after re-review of e81238c16, before any week 8-10 v5 number.
  17. `--no-sensitivity` is now refused with `--decisive` or `--replication`. It would have used
      up the lock and written no decision. The "How to run" procedure was added, with the guard's
      known limits.

