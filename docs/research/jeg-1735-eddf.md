# EDDF: enhanced DDF Value from the charts plus individual rankers (JEG-1735)

Research and design record. Part of JEG-1733. Off by default; DDF Value is unchanged.
Run 2026-11-27 on the committed fixture and `data/history`, rankers read the same day.
Data and scripts: `docs/research/data/jeg1735/` (`lists.json`, `evidence.json`,
`before_after_<scoring>.csv`, `variants.json`, `candidates.json`, `candidate_study.json`),
`tools/research/eddf_prepare.py`, `eddf_evidence.py`, `eddf_variants.py`, `eddf_candidates.py`.
Code: `pipelines/eddf.py` (reference), `app/trade-value-chart/assets/eddf-model.js` (JS twin, not
wired), `config/eddf_sources.json` (registry), `tests/test_eddf.py`.

## Decision (Jeremy, 2026-11-27)

"every stable source is a separate EQUAL-WEIGHT source in the average, NOT pooled into one 1/5th
source; stale sources are excluded; each FantasyPros staff ranker (Andrew Erickson, Derek Brown,
Pat Fitzmaurice) is its own source; actively add more rankers over time; goal is robustness so DDF
still works when a source is down." Also 2026-11-27, answering the rule-change question with "A":
amend `docs/pipeline-rules.md` section 7 so an off-by-default EDDF stage may read the rankings,
build now, wire the JS engine only after PR 1332 merges or the hot-file slot is released.

## What it does

EDDF = equal-weight mean of (the Adjusted values of the charts DDF Value averages, held charts
removed as DDF does) plus (one rank-implied value per fresh ranker), over the sources that have
the player.

- Registry: `config/eddf_sources.json`, one row per ranker (id, outlet, analyst, scoring list, url,
  how read, enabled). 21 rows: every expert list in the ROS feed. Adding a ranker is one row.
- Stale rule: a list is out when its own `source_vintage` is older than `stale_days` (14); a
  14-day-old list is in, 15 is out. The report names each ranker in or out and why.
- Implied value: anchors are players whose chart-mean value moved under 10% of its mean over the
  last three weekly pulls (chart values only, so the curve never fits itself); a non-increasing
  isotonic curve of anchor value on the ranker's overall rank, pooled across positions, per scoring;
  every ranked player gets curve(rank). QBs are excluded (`exclude_positions`, switch in the config).
- Available only at 12 teams, one QB. Superflex and other team counts are reported unavailable
  (`eddf.available`) until a fit against DDF values at that setting is tested.

## Read-date state (2026-11-27)

- Charts in DDF: USA Today, FantasyCalc, CBS. FantasyPros's chart is held on the fixture
  (`held: fidelity: publisher_vs_stored`), so DDF itself averages three charts today.
- Rankers: 21 in the registry, 7 stale by the 14-day rule (Beatson, Boggis, Chaves, Chmyz,
  MacCarrick, Smelser, and Heilman, last updated 2026-11-07). The research note said six of
  21; Heilman is 20 days old on 27 Nov, so it is out under the stated rule. Wolf of Roto Street has
  no PPR list, so PPR has 13 fresh rankers; Half PPR and standard have 14.
- Anchors per scoring: 520 (PPR), 522 (Half), 522 (standard).

## Weight consequence

With 3 charts and 13 to 14 fresh rankers the charts carry 18 to 19% of the weight (3/16.. 3/17),
and the rankers 81 to 82%. Moving from DDF to EDDF, with random subsets of fresh rankers
(mean absolute value change against DDF in value points, rank correlation with DDF), Half PPR:

| fresh rankers | chart weight share | mean abs change | rho vs DDF |
| -- | -- | -- | -- |
| 0 | 100% | 0 | 1.000 |
| 1 | 75% | 0.24 | 0.905 |
| 3 | 50% | 0.38 | 0.872 |
| 5 | 38% | 0.46 | 0.860 |
| 8 | 27% | 0.55 | 0.848 |
| 10 | 23% | 0.57 | 0.842 |
| 14 | 18% | 0.59 | 0.837 |

PPR and standard are within about 0.05 on both columns (`evidence.json`, `weights`). Most of the
change arrives with the first three rankers; the rest adds little. Pooling all rankers into one
source (the design Jeremy rejected) differs from the separate version by 0.41 to 0.48 points and
rho above 0.998, because the curves are similar across rankers: the choice matters for weight
share and for what happens when a source drops, not for today's values.

## Evidence on real Adjusted values (QBs excluded, the default)

Leave one chart out: predict the held-out chart's Adjusted value from the other two charts (DDF
estimate) or from the other two charts plus the fresh rankers (EDDF). Anchors use the other two
charts only. Mean over the three held-out charts.

| scoring | rho DDF | rho EDDF | MAE DDF | MAE EDDF | rho on ranked players only, DDF / EDDF |
| -- | -- | -- | -- | -- | -- |
| PPR | 0.908 | 0.797 | 0.738 | 0.976 | 0.930 / 0.864 |
| Half PPR | 0.919 | 0.787 | 0.733 | 0.880 | 0.940 / 0.862 |
| Standard | 0.926 | 0.775 | 0.775 | 1.057 | 0.940 / 0.841 |

**EDDF agrees less with a held-out chart than DDF does, in every scoring and for every held-out
chart.** This is worse than the stand-in test in the research (rho 0.928 vs 0.929, no change). A
single ranker's implied value correlates 0.83 to 0.91 with a held-out chart on ranked non-QB
players, against about 0.95 for the mean of the other charts, so adding fourteen noisier
estimators at equal weight pulls the mean away from the charts. Among the top players (values at
least a quarter of the top value) the gap is smaller: rho 0.855 vs 0.848 in Half PPR, MAE 6.10 vs
6.40, and worse in PPR and standard. Including QBs makes it worse again (Half PPR rho 0.776,
MAE 0.913). The held-out chart is itself a chart, so this test favours the charts by
construction; it measures agreement with the charts, not correctness.

Robustness (mean over the three charts, Half PPR; PPR and standard in `variants.json`):

| test | DDF | EDDF |
| -- | -- | -- |
| scramble one chart's values (15 permutations): mean abs change from unscrambled | 2.12 | 2.05 |
| scramble: rank corr with unscrambled | 0.696 | 0.712 |
| drop one chart: mean abs change | 0.24 | 0.29 |
| drop one chart: rank corr with full | 0.980 | 0.991 |

**Correction (2026-11-27, same session).** A first run used one random permutation per chart and
reported EDDF as 14 to 26% less moved by a scrambled chart. One permutation is far too noisy (the
top few values dominate the mean change); averaged over 15 permutations shared by every variant,
the gain is 3 to 8% in points (PPR 2.11 to 1.94, Half 2.12 to 2.05, standard 2.14 to 2.02) and
about +0.02 in rank correlation. The Linear and chat reports that carried the 14 to 26% figure
are superseded by this table. Dropping one chart moves EDDF's values a little more in points
(the anchors are refit from two charts) while keeping the order better.

Stability (week 12 vs week 11, rankers held at the read date, so only the charts vary): mean abs
week-over-week change 0.51 (DDF) vs 0.31 (PPR), 0.37 (Half), 0.26 (standard) for EDDF. This is
not a test of rankers over time: one list date exists in this run (the feed has daily snapshots
since 2026-10-29 that this session could not read; see Limits).

Coverage: DDF prices 669 players, EDDF 674 to 675 (five or six players the rankers list and no
chart prices); players priced by one source only: 0 (DDF), 1 to 4 (EDDF, ranker-only players).

## Variants side by side (Jeremy, 2026-11-28: "One per expert" is primary)

`variants.json`, same harness and inputs. none = DDF Value; per_expert = every list one vote
(Jeremy's choice, the default); site_once = a publisher's lists share one vote (only the three
FantasyPros staff lists share a group); grouped = all lists averaged into one source beside the
charts. Half PPR (PPR and standard are within a few hundredths):

| variant | LOO rho | LOO rho, ranked | LOO MAE | scramble MAE / rho | drop-one MAE / rho | week-change MAE | chart weight | priced |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| none | 0.919 | 0.940 | 0.73 | 2.12 / 0.696 | 0.24 / 0.980 | 0.51 | 100% | 669 |
| per_expert | 0.787 | 0.862 | 0.88 | 2.05 / 0.712 | 0.29 / 0.991 | 0.36 | 18% | 675 |
| site_once | 0.787 | 0.863 | 0.88 | 2.03 / 0.713 | 0.28 / 0.991 | 0.36 | 20% | 675 |
| grouped | 0.790 | 0.873 | 0.73 | 2.02 / 0.717 | 0.21 / 0.990 | 0.42 | 75% | 675 |

Independence of the added views, Half PPR (non-QB players all fresh lists rank): the fresh lists
agree with one another at rank correlation 0.918 (charts with each other 0.966, lists with charts
0.882). With 14 lists at that agreement the effective number of independent views is **1.08**, not
14: the lists are one view in fourteen costumes. The three FantasyPros staff lists agree at 0.927,
no more than the rest, so per-site down-weighting changes almost nothing (site_once is within 0.01
of per_expert on every metric); one site does not dominate, the whole ranker group does. Under
per_expert that one view holds 82% of the weight; grouped puts it at 25% and keeps the
charts-only agreement (MAE 0.73) while gaining the same coverage and a little robustness.
Dispersion: among the three charts the per-player standard deviation of value is 2.25 points;
among the 14 lists' implied values it is 4.07; the chart mean and the list mean differ by 3.18.

Reading for Jeremy's goal (a better consensus of the market): per_expert buys steadier values week
to week and slightly more coverage, and costs agreement with the charts, because it counts one
view fourteen times. grouped keeps the charts in charge and adds the ranker view once. The choice
is his; this PR builds per_expert as the default and ships site_once and grouped as options in
`eddf.py` (`variant=`).

## Candidate sources (disabled, study only)

`candidates.json`, `candidate_study.json`, `tools/research/eddf_candidates.py`. Seven files from
the consensus session. Each is a candidate row, never enabled by this PR. Half PPR unless noted:

- Wolf (Roto Street Journal): the same analyst and date as the Wolf list already in the feed
  (`fp-wolf-of-roto-street`), so it would double count him; scoring unstated.
- Rotoballer (Mariano), 172 non-QB players priced: the most chart-like (0.945 with the feed mean,
  0.936 with the charts).
- GWTTKB (PPR, model-based) and StickToTheModel (PPR, top 30 per position): near the feed mean
  (0.947, 0.936). They list few players.
- Razzball ROS points and FanDuel projections: the most different views (0.888 and 0.834 with the
  feed mean, 0.819 and 0.754 with the charts). They add the most independent information and the
  largest loss of agreement with a held-out chart (rho 0.925 to 0.822, 0.928 to 0.800 on the players
  they rank). Model files, ranked by points; FanDuel's scoring is inferred and undated.
- Footballguys (QBs only): prices nothing while QBs are excluded.

None of this decides a weight; it shows which views carry information the charts and the staff
lists do not.

## Before and after

`before_after_<scoring>.csv`: every player with a DDF or EDDF value, both values, ranks and source
counts. Spearman DDF vs EDDF over the 669 common players: 0.854 (PPR), 0.837 (Half), 0.826
(standard); top-24 overlap 21, 21, 19; largest single-player move 11.8, 10.1, 18.3 points.
Half PPR top: Gibbs 83.97 to 83.97, Robinson 66.10 to 67.59, Smith-Njigba 67.60 to 67.37,
McCaffrey 69.76 to 66.83, Walker 66.10 to 64.28.

## Limits

- Supabase `ros_rankings` could not be read: this session's only repo path (`sbclient`) holds the
  anon key and `public.players` and the table refuse it (401), and no auth store was read. The
  lists in this study are the repo's own puller (`pipelines/pull_ros_rankings.py`, public pages)
  run on 2026-11-27; names resolved offline (`tools/research/ros_rank_keys.py`). So there is one
  list date, no ranker history, and nothing here tests rankers over time. The daily-snapshot read
  and a live EDDF build wait for a session or job with table access.
- Anchors: the third week's pull uses saved natives through the same pipeline (`run_pipeline`);
  weeks 12, 11, 10.
- FantasyPros's chart is held today, so every "four charts" statement in the brief is three
  charts in this run. The weight share is 3/(3+n).
- Rank guard and `value_check` are unchanged by this PR (DDF code untouched); see the claude-log.
- Nothing is wired: no page, bake or edge function reads EDDF. Wiring the JS engine
  (`value-model.js`, `curve-widget.js`) and a bake step needs the hot-file slot and Jeremy's yes.

## Recommendation

Build is as Jeremy ruled (one per expert, primary). Keep EDDF off. On real values per_expert is
steadier week to week (0.36 vs 0.51 mean weekly change in Half PPR) and prices a few more players,
but it tracks the charts less closely (leave-one-chart-out rho 0.787 vs 0.919) and the 14 lists are
about one independent view carrying 82% of the weight; robustness to a scrambled chart is about the
same. Options for Jeremy to choose from, none substituted here: keep per_expert; site_once (no
visible effect today); or grouped (the ranker view once beside the charts), which keeps the
charts-only agreement. A floor share for the charts is a fourth option.
