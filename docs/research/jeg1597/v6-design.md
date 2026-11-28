# Scoring-aware DDF, v6: design, evidence and limits (JEG-1597)

Written 2026-11-17. Research only. Nothing here changes DDF Value, the charts, the chart pipeline,
the architecture or any published number, and nothing goes to the live site.

**Status of every number below.** v6 is **exploratory**. It was designed after the locked v5
(PR #1472) and v5.1 (PR #1478) results were known, and every 2026 chart week (5-10) and every
2017-2025 season it touches was already seen. Locked results are quoted as locked and are not
re-run or re-argued. Nothing in this document is a pre-registered pass.

Jeremy, 2026-11-17: "I'm not looking to replace ddf, but instead create a new metric for now.
Finish creating it and get it right, create a walkthrough artifact when you've given it your best
shot so I can see the end to end approach and then I can give feedback."

Code: `tools/research/jeg1597v6/` (this branch). Tests: `tests/test_jeg1597_v6.py` (11 pass).
Outputs: `tools/research/jeg1597v6/out/` (`share_backtest.json`, `evidence.json`, `levels.json`,
`examples.json`). Prior lane code (v4 steps 1-4, v5 step 7 machinery, the v5.1 backtest harness)
is imported read-only from a detached worktree pinned at `8105a5f78` (`prior.py`); no locked file,
lock or out dir is touched, and the run checks that the prior tree stays clean.

---

## 1. What the metric is, and is not

**Is.** A separate column, "Scoring-aware DDF" (placeholder name), shown beside DDF Value. It is
DDF Value's own average of four charts' Adjusted values, except that the two charts that publish
one list for every scoring (FantasyCalc and FantasyPros) are re-priced for the league's scoring.
The re-pricing gives each player an assumed stat line (the chart's implied points, split by his own
catch history) and runs it through DDF's ESPN-style projection path, exactly as ESPN's stat lines
are priced today. CBS Sports and USA Today are used as published.

**Is not.** A replacement for DDF Value. A claim that FantasyCalc or FantasyPros "really" hold a
stat line inside their numbers. A forecast tested against outcomes at the chart level (no pre-2026
chart snapshots exist). A metric tuned to match CBS Sports or USA Today.

**What the chart is allowed to contribute** (Jeremy, 2026-11-16: the charts "don't do strong
math"). Only two things:
1. its anchor-format value as DDF already prices it (the chart's Adjusted value at its anchor
   scoring, which DDF Value uses today), and
2. where that value sits on DDF's own projection pricing curve, which sets the size of the
   assumed stat line.

Everything about the scoring response comes from DDF's own pricing and the player's real game
history. Section 4.4 tests how much the answer depends on the chart's cardinal numbers: barely.

**Suggested user label.** "Scoring-aware DDF (research). DDF Value with FantasyCalc and
FantasyPros re-priced for your scoring from each player's catch history. CBS Sports and USA Today
as published. Not a replacement for DDF Value; ranges show the effect of the unknown scoring that
FantasyCalc and FantasyPros assume."

---

## 2. The method, step by step

Notation: chart `c` in {FantasyCalc, FantasyPros}; player `i`; position `p`; anchor scoring `s0`
(FantasyCalc Full, FantasyPros Half, both assumed); target scoring `s` in {Standard, Half, Full}.
12 teams, default roster.

| Step | Input | Output | Assumption | Evidence |
| --- | --- | --- | --- | --- |
| 1 Pick the charts | the week's saved lists | FantasyCalc and FantasyPros to adjust; CBS Sports and USA Today as published | the two anchors (issue 10) | FantasyCalc is one base list times position constants (issue 11); FantasyPros prints one column |
| 2 Adjusted at the anchor | chart natives at `s0` | `A_i(s0)` from the unmodified pipeline | Adjusted, not Indexed, is the starting point (Indexed is display only) | identity exact on 6 weeks (T2: max diff 0.0; DDF Value reproduced within 1e-9) |
| 3-4 Chart-implied points | `A_i(s0)` | `P_i(s0)`, points per game at which DDF's own projection pricing (ESPN, CBS ROS, Razzball) gives the same Adjusted | a chart value can be read as a points level | exact inversion (v4); **not calibrated** as a forecast (issue 16); section 4.4 shows the scoring change barely depends on it |
| 5 Catch share | 2024-2026 per-stat game lines before the chart week | `q_i` = catches per anchor point = `a q_hist + (1-a) q_pos`, `a = n/(n+k_p)`; `k_p` RB 8, WR 24, TE 16, QB position share | the player's history predicts his catch share, with a pull toward the position sized by outcomes | backtest 2017-2025 (exploratory): calibration slope RB 0.98, WR 0.94 [0.80, 1.08], TE 0.99 [0.59, 1.18]; beats the position average at all three (section 4.1) |
| 5b Other categories | same history | pass/rush/receiving yards and TDs per Standard point, pulled 8 games toward the position | the split of non-catch points | untested; it matters only for custom scoring, never on the three presets |
| 6 Assumed stat line | `P_i(s0)`, the mix | per-game line; catches `q_i P_i(s0)`; `F(line, s0) = P_i(s0)` exactly | the chart's points split the way the player's history does | identity tested |
| 7 Rebuild like ESPN | the line, rescored at `s` | a pseudo projection source outside DDF's included set, priced through VP-2 to VP-5 at `s`; delta form `A6_i(s) = max(0, A_i(s0) + Aps_i(s) - Aps_i(s0))` | DDF's ESPN-style pricing is the right response; allocation re-derived at `s` (Jeremy's literal step 7) | level response matches DDF's projection sources (WR Standard/Full 0.64-0.65 vs 0.63; section 4.3) |
| 8 Average as DDF does | four charts' Adjusted at `s` | Scoring-aware DDF(s) = mean of CBS, USA Today (as published), FantasyCalc and FantasyPros `A6(s)` | equal weights (VP-6.3) | at Full the metric differs from DDF Value only through FantasyPros, at Half only through FantasyCalc (tested) |

Players without an assumed line (at or below waiver at the anchor) keep the chart's unchanged
Adjusted at `s`, labelled. Week 10: 169 of 195 FantasyCalc and 147 of 178 FantasyPros players are
invertible; position fallback (no history) 1 player.

**On the three presets only the catch weight differs**, so steps 5-6 act only through `q_i`. The
full stat line is shown so the assumption is visible and so custom scoring could use it later.

---

## 3. What changed from v4 and v5, and why

| Item | v4 (#1417) | v5 (#1472, locked) | v6 | Why |
| --- | --- | --- | --- | --- |
| Catch share | shrunk share model, k RB 4 / WR 25 / TE 20 | seven-category mix, k chosen on a summed seven-category objective: WR catches pulled with k = 64 | two-bucket catch share with a pull chosen by catch error alone on 2015-2025, wide grid | v5's objective could not see that the presets respond only to catches and over-shrank WRs (v5.1 diagnosis); v5.1's light pull hit its cap of 8 in every season and over-reacted (WR slope 0.59, locked) |
| History window for selection | all | 2024+ | k chosen with the history the chain really has (2 prior seasons) | at a 2026 chart week a player has at most about 2.5 seasons of per-stat history |
| Step 7 | fixed chart-points-per-VORP slope | ESPN-style pricing, delta form | unchanged from v5 | v5's T6 showed the levels now land with ESPN and Sleeper |
| Response target | CBS Sports and USA Today | ESPN and Sleeper rescoring | ESPN and Sleeper rescoring **and** real outcomes (calibration) | the projectors are not ground truth either (section 4.2) |
| Anchors | assumed, one sensitivity run | assumed, sensitivity runs | assumed, shown as a range on every value | issue 10 cannot be closed; it is shown instead |
| Zero-value ties | in the statistics | in the statistics | removed from response statistics, counted | v5.1 diagnosis: FantasyCalc's WR pass was the floor ties |

**Options considered and rejected.**
- **Size the move to CBS Sports or USA Today** (damping about 0.3): rejected; it fits the
  publishers, whose columns barely move and disagree with each other (issue 4), and breaks the
  no-tuning rule.
- **The light pull (k at most 8)**: rejected as primary. It matches the projectors' WR response
  better (0.86 vs 0.58) but over-reacts on outcomes (WR slope 0.59, locked v5.1).
- **v5's seven-category objective**: rejected; it compresses WR shares about 5 times.
- **Calibration-target selection** (k whose share slope is closest to 1): kept as a variant; it
  picks WR k = 32 instead of 24 and changes the answer almost nowhere (Spearman 0.999-1.0 of value
  changes).
- **Points from the projections instead of the chart** (`projP`) or **only the chart's rank**
  (`rankP`): kept as robustness variants, not primary, because Jeremy's method takes the points
  from the chart. They agree closely with the primary (section 4.4).
- **Holding the allocation at the anchor's** (v4): not used; v5 showed the re-derived allocation
  already lands levels with ESPN and Sleeper.
- **Running CBS Sports and USA Today through the chain too**: not done; Jeremy said "used as
  published". It is decision D3 (section 8), because their own columns respond about as little as
  a scoring-blind list does inside DDF.
- **A position-specific rule for receivers** (for example no pull at all, or a targets prior):
  rejected; the v5.1 diagnosis found no extra WR signal in targets or point level, and raw history
  is badly over-dispersed (WR slope 0.24).

---

## 4. Evidence (all EXPLORATORY)

### 4.1 Step 5 backtest: how hard to pull the catch share

`share_bt.py`, nflverse weekly actuals 2015-2025 (catches = Full minus Standard), origins weeks 5,
9 and 13, truth the next 4 weeks, `k` chosen per evaluation season on earlier seasons only (nested
forward), history limited to the 2 prior seasons plus the current one. Grid: 0, 1, 2, 4, 8, 12,
16, 24, 32, 48, 64, 96, 128, position share. Intervals: player-cluster bootstrap, 1,000 draws.

| Position | k chosen (2017-2025) | Share slope v6 [95%] | light k = 8 | raw history | v5 heavy | E gain vs position average |
| --- | --- | --- | --- | --- | --- | --- |
| RB | 8 every season | 0.98 [0.89, 1.08] | 0.98 | 0.50 | 1.14 | +0.540 [0.309, 0.784] |
| WR | 24-48 (24 from 2019) | 0.94 [0.80, 1.08] | 0.59 [0.49, 0.67] | 0.24 | 2.40 | +0.113 [0.063, 0.168] |
| TE | 12-24 | 0.99 [0.59, 1.18] | 0.77 [0.45, 0.96] | 0.39 | 0.56 | +0.230 [0.035, 0.548] |

- With all history (not window-matched), the light k = 8 rows reproduce the locked v5.1 figures
  (WR slope 0.588, TE 0.783, RB 0.997), which checks the harness reuse.
- Against the light pull, v6's catch error is lower at WR (+0.016 [-0.003, +0.035]) and TE
  (+0.004 [-0.038, +0.033]): not shown either way. The gain is calibration, not error.
- Strengths used on the 2026 charts (chosen on 2016-2025): RB 8, WR 24, TE 16, QB position
  share (`params.json`).
- Caveat: the grid was widened after the locked v5.1 cap hit was seen, and 2017-2025 were seen.

### 4.2 Calibration on 2026 outcomes (small)

Snapshot weeks 5-7, FantasyPros-invertible players, predicted catch share against realized share
in weeks w-10 (points-weighted slope; 1.0 is calibrated; player-cluster intervals).

| Position (rows / players) | v6 | light k = 8 | v5 heavy | ESPN | Sleeper | lowest weighted error |
| --- | --- | --- | --- | --- | --- | --- |
| RB (131 / 51) | 0.88 [0.36, 1.42] | 0.88 | 1.04 | 0.62 [0.33, 0.97] | 0.53 [0.18, 1.03] | v5 heavy, then v6 |
| WR (167 / 66) | 1.47 [0.69, 2.24] | 0.86 [0.35, 1.50] | 4.96 | 0.63 [0.17, 1.05] | 0.82 [0.34, 1.28] | **v6** (10.9 vs ESPN 11.9, Sleeper 11.3, light 11.1) |
| TE (54 / 19) | -0.45 [-2.13, 0.67] | -0.39 | 0.57 | 0.62 | -0.17 | ESPN (v6 worst but one) |

Reading: the projectors' own WR catch shares are over-dispersed against 2026 outcomes (ESPN slope
0.63). So moving less than ESPN and Sleeper at WR is not by itself a defect. The sample is far too
small to settle it, and TE on 2026 is a warning (19 players).

### 4.3 Response against ESPN and Sleeper rescoring, weeks 5-10

v5's T4/T5 machinery: Standard-to-Full percentile moves of the chart against the same chart rebuilt
with the ESPN+Sleeper catch share. Spread ratio 1.0 = moves as far; v5's band was [2/3, 1.5].

| Rule | FantasyCalc ratio (RB / WR / TE) | FantasyPros ratio (RB / WR / TE) | Direction (corr) FC / FP |
| --- | --- | --- | --- |
| v5 heavy (locked v5 weeks 8-10: FP WR 0.26) | 0.87 (0.75 / 0.95 / 0.92) | 0.68 (0.81 / **0.25** / 0.97) | 0.72 / 0.56 |
| light k = 8 | 0.98 (0.77 / 0.97 / 1.21) | 0.89 (0.83 / 0.86 / 0.98) | 0.61 / 0.51 |
| **v6** | 0.93 [0.88, 1.04] (0.77 / 0.95 / 1.08) | 0.76 [0.71, 0.92] (0.83 / **0.57** / 0.86) | 0.63 [0.55, 0.69] / 0.49 [0.40, 0.58] |
| v6, zero ties removed | 0.82 (0.77 / **0.58** [0.51, 0.67] / 1.10) | 0.76 (0.83 / **0.58** [0.53, 0.63] / 0.86) | 0.59 / 0.50 |

- Direction beats the shuffle control everywhere (FC p95 0.22, FP p95 0.06).
- **The WR gap is real and is the main weakness**: v6 receivers move about 0.58 as far as
  ESPN/Sleeper rescoring, at both charts once FantasyCalc's zero ties are removed. That is up from
  0.25 (v5) and would fail v5's band. Section 4.2 is the case that this is the calibrated size; it
  rests on a small sample.
- Week 10 alone (fresh Sleeper): FC 0.91, FP 0.70 (WR 0.50).

**Position levels (how far a top player's value moves Full to Standard, median, weeks 5-10).**
`levels.py`.

| | ESPN | projections mean | CBS published | USA Today published | FP today | FC v6 | FP v6 | DDF Value | Scoring-aware DDF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WR top 24 | 0.63 | 0.63 | 0.84 | 0.86 | 0.86 | 0.64 | 0.65 | 0.85 | 0.75 |
| TE top 12 | 0.73 | 0.72 | 0.94 | 0.95 | 0.94 | 0.72 | 0.74 | 0.95 | 0.84 |
| RB top 24 | 1.30 | 1.32 | 1.15 | 1.12 | 1.14 | 1.34 | 1.35 | 1.14 | 1.23 |
| QB top 12 | 1.15 | 1.15 | 1.06 | 1.06 | 1.06 | 1.14 | 1.13 | 1.06 | 1.10 |

- v6's two charts now respond like DDF's own projection sources (that is what "the way DDF treats
  ESPN" means). T6 levels: WR/RB log move 0.713 against ESPN 0.710 and Sleeper 0.687.
- CBS Sports' and USA Today's own columns move about as little as an unadjusted FantasyPros does
  inside DDF (WR 0.84-0.86). Used as published, they pull the metric halfway back (WR 0.75). This
  is decision D3.

### 4.4 Robustness of the unwind (what depends on the chart's math)

Spearman of each player's Standard-to-Full value change, v6 against a variant, and the variant's
spread relative to v6 (weeks 5-10, within position):

| Variant | FantasyCalc RB / WR / TE | FantasyPros RB / WR / TE |
| --- | --- | --- |
| rank only (the chart's order, the projections' points at that rank) | 0.93 / 0.99 / 0.98 | 0.98 / 0.99 / 0.96 |
| projections' points (no chart points at all) | 0.89 / 0.96 / 0.90 | 0.86 / 0.92 / 0.84 |
| calibration-target k | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |

Spread ratios 0.84-1.11. The scoring change comes almost entirely from the player's catch history
and DDF's pricing, not from the chart's cardinal values. This is the honest answer to issue 8:
the metric does not need the charts to be invertible math; it needs their anchor value, as DDF
Value already does.

### 4.5 Rank agreement and how much the metric moves

Within-position Spearman, top players (RB/WR 24, TE/QB 12), weeks 5-10 average:

| Scoring | vs projectors' own lists: new / DDF | vs CBS+USA Today published: new / DDF | new vs DDF | median change from DDF Value |
| --- | --- | --- | --- | --- |
| Standard | RB 0.93/0.92, WR 0.82/0.81, TE 0.75/0.76 | 0.98/0.98, 0.98/0.98, 0.95/0.95 | 0.99-1.00 | RB 5.6%, WR 10.7%, TE 10.2%, QB 1.9% |
| Half | RB 0.93/0.94, WR 0.87/0.87, TE 0.78/0.80 | about equal | 0.99-1.00 | 1-3% |
| Full | RB 0.94/0.94, WR 0.90/0.90, TE 0.84/0.82 | about equal | 0.99-1.00 | 0.5-3% |

- No-harm against unchanged (v5's T7): FantasyPros at Standard **HARM** -0.0081 [-0.0207,
  -0.0009] (week 10 alone -0.015, inconclusive); the other cells inconclusive.
- Against current DDF Value (T8): Standard +0.0003 [-0.009, +0.009], Half -0.0018 [-0.010,
  +0.003], Full +0.0028 [+0.0001, +0.0091].
- Reading: the metric mostly moves levels between positions (a WR is worth about 11% less in
  Standard), and reorders little within a position. It is not shown to rank better.

### 4.6 Anchors, shown not hidden

Every value is computed under the four anchor pairs (FantasyCalc Full or Half x FantasyPros Half or
Full). Median width of the range relative to the value, top players, weeks 5-10:
Standard WR 7.3% (90th pct 10.1%), RB 4.2%, TE 3.9%, QB 1.7%; Half and Full 2-6%. The page shows the
range beside each worked example.

### 4.7 The FantasyCalc zero floor

At Standard, 17-23 FantasyCalc WRs per week sit at 0 under v6. Today's DDF Value already puts 15
of them at 0 (week 10): at Standard fewer WRs are rostered, and DDF's waiver rule zeroes the rest.
So the floor is mostly DDF's own rule. v6 adds about 4. FantasyPros shows the opposite: v6 leaves
no WR at 0 where today's FantasyPros at Standard zeroes 8, because the delta form never re-applies
the chart's own waiver line. Response statistics drop these ties (counted); the metric keeps them.
Open issue N2.

### 4.8 Worked examples (week 10; Adjusted-value units)

DDF Value and the new metric at Standard / Half / Full; the anchor range at Standard; the catch
share (FantasyPros, Half anchor) from history games, own share, v6 share and the ESPN+Sleeper
share; and FantasyPros' assumed line per game. Full detail: `out/examples.json`.

| Player | Pos | DDF Value | Scoring-aware DDF | Range (Std) | Catch share | Assumed line (FP, per game) |
| --- | --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | 64.0 / 66.8 / 68.4 | 56.7 / 65.1 / 70.3 | 55.0-58.3 | 43 g, 0.413 -> 0.423 (proj 0.384) | 20.0 pts: 8.5 rec, 112 rec yds, 0.7 TD |
| Christian Watson | WR | 37.1 / 39.7 / 41.8 | 34.1 / 39.1 / 42.4 | 33.5-34.8 | 31 g, 0.314 -> 0.370 (proj 0.364) | 14.8 pts: 5.5 rec, 84 rec yds, 0.6 TD |
| Christian McCaffrey | RB | 59.5 / 57.2 / 54.6 | 58.5 / 57.2 / 54.4 | 58.5-59.0 | 29 g, 0.274 -> 0.266 (proj 0.219) | 15.0 pts: 4.0 rec, 34 rec yds, 54 rush yds, 0.7 TD |
| Derrick Henry | RB | 33.7 / 30.7 / 27.7 | 38.3 / 32.2 / 26.2 | 37.0-39.9 | 43 g, 0.062 -> 0.090 (proj 0.097) | 12.7 pts: 1.1 rec, 70 rush yds, 0.7 TD |
| Trey McBride | TE | 27.3 / 28.2 / 29.1 | 23.0 / 27.2 / 30.0 | 22.3-23.9 | 42 g, 0.546 -> 0.540 (proj 0.557) | 12.5 pts: 6.7 rec, 66 rec yds, 0.4 TD |
| George Kittle | TE | 19.0 / 19.6 / 19.7 | 17.6 / 19.4 / 19.8 | 17.5-17.8 | 33 g, 0.404 -> 0.443 (proj 0.407) | 10.6 pts: 4.7 rec, 54 rec yds, 0.5 TD |
| Josh Allen | QB | 35.6 / 35.2 / 33.5 | 36.6 / 35.7 / 33.1 | 36.0-37.0 | QB: position share (0.001) | 23.5 pts: 237 pass yds, 31 rush yds, 2.3 TD |
| Jonah Coleman (rookie) | RB | 32.4 / 30.2 / 28.0 | 33.9 / 30.7 / 27.6 | 33.4-34.3 | 4 g, 0.231 -> 0.236 (proj 0.191) | 12.4 pts: 2.9 rec, 52 rush yds, 0.6 TD |
| Jordyn Tyson (rookie) | WR | 3.4 / 5.0 / 6.5 | 3.1 / 4.7 / 6.6 | 3.0-3.3 | 1 g, 0.800 -> 0.456 (proj 0.537) | 8.2 pts: 3.7 rec, 47 rec yds, 0.2 TD |
| Mike Evans (no games weeks 7-9) | WR | 12.8 / 15.3 / 17.8 | 12.0 / 15.0 / 18.0 | 11.6-12.3 | 27 g, 0.378 -> 0.408 (proj 0.350) | 10.5 pts: 4.3 rec, 55 rec yds, 0.5 TD |

What drives the changes:
- **Receivers lose value at Standard** (Smith-Njigba -11%) because about a fifth of his Half points
  come from catches (8.5 a game), and a full catch point at Full; DDF's pricing of that stat line drops them as far as it drops ESPN's own line.
  Two of the four charts (CBS, USA Today) barely move, so the metric moves half as far as ESPN.
- **Catch share separates players at a position**: Henry gains 13.5% at Standard (1 catch a
  game) while McCaffrey loses 2% (4 a game). Watson's low own share (0.31) is pulled up toward
  the WR average because his 31 games are not enough to trust a low share fully.
- **Thin history** (Tyson, 1 game): the pull does most of the work (weight 0.04 on his own
  0.80); Coleman (4 games) sits close to the RB average anyway.
- **Injury**: the history does not know a player is out; the chart's anchor value carries that,
  and v6 leaves it alone. Evans moves like any WR with his catch share.
- **QB**: barely changes on the presets (his own line has no catches); the small moves are
  position levels.
- **Chart-implied lines look high at the top** (Smith-Njigba 112 receiving yards a game at
  FantasyPros, 120 at FantasyCalc): chart points are not calibrated (issue 16). The line is an
  assumption made visible, not a projection.

---

## 5. Receivers' over-reaction and FantasyPros' low response, in one place

- Over-reaction (locked v5.1: light pull WR slope 0.59, raw history 0.24) came from too little pull.
  v6 chooses the pull on outcomes over a wide grid with the history window the chain really has:
  WR k = 24, slope 0.94 [0.80, 1.08] (exploratory).
- FantasyPros' low WR response (locked v5: 0.26) came from too much pull (k = 64). With k = 24 it is
  0.57-0.58. The rest of the gap is the projectors moving more than outcomes support, on a small
  2026 sample (section 4.2). It is not FantasyPros' rank ladder: with the position share, the move
  is exactly zero, as the algebra requires.
- FantasyCalc's apparent WR pass in v5 was its zero ties; with ties removed it shows the same
  0.58 as FantasyPros. Both charts now say the same thing.

---

## 6. The 22 issues, and new ones

| # | Issue | v6 status |
| --- | --- | --- |
| 1 | Labelled gate G1 (CBS/USA Today round trip) | Failed v1-v4 (locked). Not used as a target in v6 (issue 4). |
| 2 | Size | Changed sign: no overshoot; WR now under-responds against ESPN/Sleeper (0.58). Levels match DDF's projection sources. Open at WR (N1). |
| 3 | No-harm tests, TE | FantasyPros at Standard HARM -0.008 [-0.021, -0.001] on weeks 5-10; TE weak on 2026 (N4). Open. |
| 4 | Target validity | v6 judged on ESPN/Sleeper rescoring and on outcomes, not on CBS/USA Today. Projectors are not ground truth either (4.2). Open, reduced. |
| 5 | G2 chart-to-chart | Descriptive: corr FC 0.27, FP 0.25. Reported only. |
| 6 | "Closer" statistic | Resolved (not used). |
| 7 | Better than DDF Value? | Not shown (T8 within ±0.01). The metric is separate and claims no ranking gain. |
| 8 | Invertibility | Mitigated: the chart contributes only its anchor value; the scoring change is 0.84-0.99 the same without the chart's points (4.4). Open as a premise. |
| 9 | Adjusted erases chart levels | Accepted by design: the chart's anchor Adjusted is DDF's own. Open, structural. |
| 10 | Anchors unknown | Shown as a range on every value (4.6). Open. |
| 11 | FantasyCalc pegged | Resolved; Full anchor, disclosed. |
| 12 | Data limits | 2024+ per-stat for chart players; pull chosen with a matched window; no fumbles or 2-pt. Open, handled. |
| 13 | Small sample, seen weeks | All exploratory; weeks 11+ are the first unseen chart weeks. Open. |
| 14 | No tuning to publishers | Held. The pull comes from outcomes. The grid widening came after seeing the v5.1 cap (N6). |
| 15 | Realized points can't separate | Not tested for the metric. Open. |
| 16 | Chart points uncalibrated | Still true; affects only the line's size, and the answer barely depends on it (4.4). Open, mitigated. |
| 17 | FantasyPros as published tracked actuals better | Untested. Open. |
| 18 | Catches carry usage signal | Resolved: v6 rescoring keeps catches via the share. |
| 19 | Leakage, independence | v6 selection is forward-only; seasons seen. Independence open. |
| 20 | Allocation re-derivation | Re-derived (literal step 7); levels land with ESPN/Sleeper (T6 WR/RB 0.713 vs 0.710 / 0.687). Mostly addressed. |
| 21 | v1 errors | Resolved. |
| 22 | Open review findings | v6 has had no adversarial review yet. Open. |
| N1 | WR responds 0.58 as far as ESPN/Sleeper rescoring | Open; decision D1. |
| N2 | Zero floor: FantasyCalc 17-23 WRs at 0 at Standard (DDF today 15); FantasyPros none (DDF today 8) | Open; ties removed from statistics. |
| N3 | CBS/USA Today as published move little, so the metric moves about half as far as the projections | Open; decision D3. |
| N4 | TE on 2026 outcomes: v6 share slope -0.45 [-2.13, 0.67], 19 players | Open (backtest TE is fine). |
| N5 | Chart-implied lines look inflated at the top | Consequence of issue 16; display caveat. |
| N6 | Wide grid chosen after the v5.1 cap was seen; 2017-2025 seen | Needs an unseen check (2026 season end, weeks 11+). |
| N7 | Non-catch split (k = 8) untested | Matters only for custom scoring. |

---

## 7. Limits

- Exploratory throughout; no holdout exists yet. The first unseen chart weeks are 11+.
- Anchors assumed (FantasyCalc Full, FantasyPros Half); the range shows the effect.
- Chart-implied points are not a calibrated forecast; the line is an assumption.
- ESPN stat lines and the 2024+ history lack fumbles and 2-pt; fine for the presets, not for
  custom scoring.
- Per-stat history before 2024 is not in the repo; the backtest uses catches only (exact).
- 2026 outcome checks are small (66 WRs, 19 TEs).
- 12 teams and the default roster only; superflex not studied.
- Not reviewed adversarially yet (Codex/Opus).

## 8. Decisions for Jeremy (recommendation first)

- **D1 receiver response size.** A (recommended): size the catch share to outcomes (v6, WR moves
  about 0.58 as far as ESPN/Sleeper rescoring). B: size it to the projectors (light pull, about
  0.86, but over-reacts on outcomes). C: halfway (k about 12).
- **D2 how to treat the anchor.** A (recommended): show the four-anchor range beside the value.
  B: average the four anchors into the value. C: primary anchors only.
- **D3 CBS Sports and USA Today.** A (recommended for now): as published, as you said, with the
  label saying their own columns move little. B: re-price them too from their anchor column, so all
  four charts respond like ESPN. C: leave them out of the metric.
- **D4 next check.** A (recommended): freeze v6 as is and score it once on weeks 11-14 and the 2026
  season-end catch shares, with rules written before those weeks arrive. B: adversarial review
  first, then freeze.

## 9. How to run

```
PY=<python 3.12 with numpy and scipy>
$PY tools/research/jeg1597v6/share_bt.py     # step 5 backtest -> out/share_backtest.json, params.json
$PY tools/research/jeg1597v6/evidence.py     # weeks 5-10 evidence -> out/evidence.json (about 3 min)
$PY tools/research/jeg1597v6/levels.py       # level ratios -> out/levels.json
$PY tools/research/jeg1597v6/examples.py     # worked examples -> out/examples.json (--list for the pool)
$PY -m pytest -q tests/test_jeg1597_v6.py
```
`prior.py` creates the pinned prior worktree (`../ft-wt-jeg1597-v6-prior` at 8105a5f78) if it is
missing, or use `V6_PRIOR_TREE`.

## 10. Choice log (dated; what informed each choice)

| Date | Choice | Informed by |
| --- | --- | --- |
| 2026-11-17 | Build v6 on v5's chain (steps 1-4, 7 unchanged) | locked v5: T2, T3, T4 pass; T6 levels near ESPN/Sleeper |
| 2026-11-17 | Change only step 5, to a two-bucket catch share | v5 algebra (presets see only catches); v5.1 diagnosis (seven-category objective over-shrank WRs) |
| 2026-11-17 | Widen the pull grid to 0-128 and the position share | locked v5.1: light pull at its cap of 8 in every season; WR slope 0.59 |
| 2026-11-17 | Select with a 2-season history window | the chain's per-stat history starts in 2024 |
| 2026-11-17 | E-min selection primary, calibration-target as a variant | E-min was v5.1's rule; both pick nearly the same k (WR 24 vs 32) |
| 2026-11-17 | k RB 8, WR 24, TE 16, QB position share frozen in `params.json` | `share_bt.py` on 2016-2025, before any 2026 chart run |
| 2026-11-17 | Non-catch categories pulled 8 games | untested; no effect on the presets |
| 2026-11-17 | Response statistics drop zero-value ties | v5.1 diagnosis (FantasyCalc floor); counts in `evidence.json` |
| 2026-11-17 | Add 2026 calibration of v6, light, v5, ESPN and Sleeper shares | the WR response gap (0.57) seen in the first weeks 5/8/10 look |
| 2026-11-17 | Add the level-ratio table | ESPN's own Standard/Full move for Henry (1.59) matched v6 FantasyCalc (1.52) in a spot check |
| 2026-11-17 | Choose 10 worked examples from the week 10 pool | position mix, a pass-catching and an early-down RB, two rookies, one player with no games weeks 7-9 |
