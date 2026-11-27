# EDDF: enhanced DDF Value from the charts plus individual rankers (JEG-1735)

Research and design record. Part of JEG-1733. Off by default; DDF Value is unchanged.
Run 2026-11-27 (a Friday) on the committed fixture and `data/history`, rankers read the same day.
Data and scripts: `docs/research/data/jeg1735/` (`lists.json`, `evidence.json`,
`before_after_<scoring>.csv`, `variants.json`, `candidates.json`, `candidate_study.json`),
`tools/research/eddf_prepare.py`, `eddf_evidence.py`, `eddf_variants.py`, `eddf_candidates.py`.
Code: `pipelines/eddf.py` (reference), `app/trade-value-chart/assets/eddf-model.js` (JS twin, not
wired), `config/eddf_sources.json` (registry), `tests/test_eddf.py`.

## Decisions (Jeremy)

- 2026-11-27: "every stable source is a separate EQUAL-WEIGHT source in the average, NOT pooled
  into one 1/5th source; stale sources are excluded; each FantasyPros staff ranker (Andrew
  Erickson, Derek Brown, Pat Fitzmaurice) is its own source; actively add more rankers over time;
  goal is robustness so DDF still works when a source is down."
- 2026-11-27, later: "Ranks should go stale every Tuesday early morning after the prior weeks
  games were played." Built as the stale rule (below); the 14-day window stays as a backstop.
- 2026-11-28, "A": amend `docs/pipeline-rules.md` section 7 so an off-by-default EDDF stage may
  read the rankings; wire the JS engine only after PR 1332 merges or the hot-file slot is released.
- 2026-11-28, "One per expert": each expert list is its own vote, the primary variant. The
  variants below are shown for comparison, not substituted.

## What it does

EDDF = equal-weight mean of (the Adjusted values of the charts DDF Value averages, held charts
removed as DDF does) plus (one rank-implied value per fresh ranker), over the sources that have
the player.

- Registry: `config/eddf_sources.json`, one row per ranker (id, outlet, analyst, scoring list, url,
  how read, enabled). 21 rows: every expert list in the ROS feed, plus 7 candidate rows
  (`candidate: true`, `enabled: false`). Adding a ranker is one row.
- Stale rule: a list is fresh only if its own `source_vintage` is on or after the most recent
  Tuesday (`stale_weekday: 1`), the reset after the prior week's games; a Tuesday-dated list counts
  as the new week, a Monday-dated one does not. Lists carry a date, not a time, so "early morning"
  is read as the whole of Tuesday. `stale_days` (14) is a backstop for a ranker that stops updating.
  The report names each ranker in or out and why. Consequence: right after a Tuesday reset almost
  every list is stale until analysts update, and EDDF then equals DDF on the charts alone.
- Implied value: anchors are players whose chart-mean value moved under 10% of its mean over the
  last three weekly pulls (chart values only, so the curve never fits itself); a non-increasing
  isotonic curve of anchor value on the ranker's overall rank, pooled across positions, per scoring;
  every ranked player gets curve(rank). QBs are excluded (`exclude_positions`, switch in the config).
- Available only at 12 teams, one QB. Superflex and other team counts are reported unavailable
  (`eddf.available`) until a fit against DDF values at that setting is tested.

## State at the read date (Fri 27 Nov 2026)

- Charts in DDF: USA Today, FantasyCalc, CBS. FantasyPros's chart is held on the fixture
  (`held: fidelity: publisher_vs_stored`), so DDF itself averages three charts today.
- Rankers under the Tuesday rule (reset Tue 24 Nov): 21 in the registry, 12 stale, 9 fresh in Half
  PPR and standard, 8 in PPR (Wolf of Roto Street has no PPR list). Fresh: Dell, Brown, Erickson,
  Fitzmaurice, Fuhr, Linkletter, Stone, Wolf (24 to 26 Nov), Yates (24 Nov). Stale for a vintage
  before 24 Nov: Malachovsky (21 Nov), Maher (19 Nov), Wheeler (18 Nov), St Denis (16 Nov),
  Emrick-Wilson (15 Nov), Heilman (7 Nov) and six lists from September and October. Under the
  14-day rule alone the count was 14 fresh; the Tuesday rule drops five more.
- Anchors per scoring: 520 (PPR), 522 (Half), 522 (standard).

## Weight consequence

With 3 charts and 8 to 9 fresh rankers the charts carry 25 to 27% of the weight. Moving from DDF
to EDDF with random subsets of the fresh rankers (mean abs value change against DDF in points,
rank correlation with DDF), Half PPR:

| fresh rankers | chart weight share | mean abs change | rho vs DDF |
| -- | -- | -- | -- |
| 0 | 100% | 0 | 1.000 |
| 1 | 75% | 0.23 | 0.921 |
| 3 | 50% | 0.37 | 0.888 |
| 5 | 38% | 0.43 | 0.866 |
| 8 | 27% | 0.49 | 0.855 |
| 9 | 25% | 0.49 | 0.854 |

Most of the change arrives with the first three rankers. Pooling all rankers into one source
differs from one-vote-each by 0.33 to 0.40 points with rank correlation above 0.999: the choice
matters for weight share and for what happens when a source drops, not for today's values.

## Evidence on real Adjusted values (QBs excluded, the default; Tuesday rule)

Leave one chart out: predict the held-out chart's Adjusted value from the other two charts (DDF
estimate) or from the other two plus the fresh rankers (EDDF). Anchors use the other two charts
only. Mean over the three held-out charts.

| scoring | rho DDF | rho EDDF | MAE DDF | MAE EDDF | rho on ranked players only, DDF / EDDF |
| -- | -- | -- | -- | -- | -- |
| PPR | 0.908 | 0.815 | 0.738 | 0.874 | 0.931 / 0.883 |
| Half PPR | 0.919 | 0.803 | 0.733 | 0.805 | 0.943 / 0.881 |
| Standard | 0.926 | 0.786 | 0.775 | 0.970 | 0.943 / 0.859 |

**EDDF agrees less with a held-out chart than DDF does, in every scoring and for every held-out
chart.** The research stand-in showed no loss (rho 0.928 vs 0.929). A single ranker's implied
value correlates 0.83 to 0.91 with a held-out chart on ranked non-QB players, against about 0.95
for the mean of the other charts, so equal-weight fresh rankers pull the mean away from the charts.
Among the top players (values at least a quarter of the top value) the gap is smaller or reverses:
Half PPR rho 0.855 DDF and 0.871 EDDF, MAE 6.10 and 6.02; PPR and standard are worse for EDDF.
Including QBs lowers EDDF further (Half PPR rho 0.792). The held-out chart is itself a chart, so
this test favours the charts by construction; it measures agreement with the charts, not correctness.

Robustness (mean over the three charts, Half PPR, 15 shared permutations for the scramble):

| test | DDF | EDDF |
| -- | -- | -- |
| scramble one chart's values: mean abs change from unscrambled | 2.12 | 2.13 |
| scramble: rank corr with unscrambled | 0.696 | 0.706 |
| drop one chart: mean abs change | 0.24 | 0.30 |
| drop one chart: rank corr with full | 0.980 | 0.990 |

**Correction (2026-11-27, same session).** A first run used one random permutation per chart and
reported EDDF as 14 to 26% less moved by a scrambled chart. One permutation is far too noisy (the
top few values dominate the mean change). Averaged over 15 permutations shared by every variant the
scramble gain is within 0 to 4% in points (PPR 2.11 to 2.04, Half 2.12 to 2.13, standard 2.14 to
2.08) and about +0.01 to +0.02 in rank correlation, so there is no robustness gain to a scrambled
chart worth claiming. Earlier chat and Linear figures are superseded. Dropping one chart moves
EDDF's values a little more in points (the anchors are refit from two charts) while keeping the
order slightly better.

Stability (week 12 vs week 11, rankers held at the read date, so only the charts vary): mean abs
week-over-week change 0.51 (DDF) vs 0.33 (PPR), 0.39 (Half), 0.30 (standard) for EDDF. This is not
a test of rankers over time: one list date exists in this run.

Coverage: DDF prices 669 players, EDDF 674 (five players the rankers list and no chart prices);
players priced by one source only: 0 (DDF), 1 to 3 (EDDF, ranker-only players).

## Variants side by side (Jeremy, 2026-11-28: "One per expert" is primary)

`variants.json`, same harness and inputs. none = DDF Value; per_expert = every list one vote
(Jeremy's choice, the default); site_once = a publisher's lists share one vote (only the three
FantasyPros staff lists share a group); grouped = all lists averaged into one source beside the
charts. Half PPR (PPR and standard are within a few hundredths):

| variant | LOO rho | LOO rho, ranked | LOO MAE | scramble MAE / rho | drop-one MAE / rho | week-change MAE | chart weight | priced |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| none | 0.919 | 0.943 | 0.73 | 2.12 / 0.696 | 0.24 / 0.980 | 0.51 | 100% | 669 |
| per_expert | 0.803 | 0.881 | 0.81 | 2.13 / 0.706 | 0.30 / 0.990 | 0.38 | 25% | 674 |
| site_once | 0.803 | 0.882 | 0.79 | 2.11 / 0.709 | 0.29 / 0.990 | 0.38 | 30% | 674 |
| grouped | 0.805 | 0.888 | 0.71 | 2.05 / 0.712 | 0.21 / 0.990 | 0.42 | 75% | 674 |

Independence of the added views, Half PPR (non-QB players all fresh lists rank): the fresh lists
agree with one another at rank correlation 0.925 (charts with each other 0.966, lists with charts
0.895). With 9 lists at that agreement the effective number of independent views is **1.07**, not
9: the lists are one view in nine costumes. The three FantasyPros staff lists agree at 0.927, no
more than the rest, so per-site down-weighting changes little (site_once is within 0.03 of
per_expert on every metric): one site does not dominate, the whole ranker group does. Under
per_expert that one view holds 75% of the weight; grouped puts it at 25% and keeps the
charts-only error (MAE 0.71). Dispersion: among the three charts the per-player standard deviation
of value is 2.24 points; among the 9 lists' implied values 3.64; the chart mean and the list mean
differ by 2.95.

Reading for Jeremy's goal (a better consensus of the market): per_expert buys steadier values week
to week and slightly more coverage, and costs agreement with the charts, because it counts one
view nine times. grouped keeps the charts in charge and adds the ranker view once. The choice is
his; this PR builds per_expert as the default and ships site_once and grouped as options in
`eddf.py` (`variant=`).

## Candidate sources (disabled, study only)

`candidates.json`, `candidate_study.json`, `tools/research/eddf_candidates.py`. Seven files from
the consensus session. Each is a candidate row, never enabled by this PR. Half PPR unless noted;
the "rho vs feed mean" is against the fresh feed lists under the Tuesday rule:

- Wolf (Roto Street Journal): the same analyst and date as the Wolf list already in the feed
  (`fp-wolf-of-roto-street`), so it would double count him; scoring unstated.
- Rotoballer (Mariano), 172 non-QB players priced: the most chart-like (0.952 with the feed mean).
- GWTTKB (PPR, model-based) and StickToTheModel (PPR, top 30 per position): near the feed mean
  (0.944, 0.934). They list few players.
- Razzball ROS points and FanDuel projections: the most different views (0.884 and 0.807 with the
  feed mean). They add the most independent information and the largest loss of agreement with a
  held-out chart on the players they rank (rho 0.925 to 0.822, 0.928 to 0.800). Model files, ranked
  by points; FanDuel's scoring is inferred and undated.
- Footballguys (QBs only): prices nothing while QBs are excluded.

None of this decides a weight; it shows which views carry information the charts and the staff
lists do not.

## Before and after

`before_after_<scoring>.csv`: every player with a DDF or EDDF value, both values, ranks and source
counts. Spearman DDF vs EDDF over the 669 common players: 0.874 (PPR), 0.854 (Half), 0.839
(standard); top-24 overlap 22, 22, 20; largest single-player move 9.8, 10.1, 14.4 points.
Half PPR top: Gibbs 83.97 to 83.97, Robinson 66.10 to 69.48, McCaffrey 69.76 to 68.43,
Smith-Njigba 67.60 to 67.27, Walker 66.10 to 62.51.

## Limits

- Supabase `ros_rankings` could not be read: this session's only repo path (`sbclient`) holds the
  anon key and `public.players` and the table refuse it (401), and no auth store was read. The
  lists in this study are the repo's own puller (`pipelines/pull_ros_rankings.py`, public pages)
  run on 2026-11-27; names resolved offline (`tools/research/ros_rank_keys.py`). So there is one
  list date, no ranker history, and nothing here tests rankers over time. The daily-snapshot read
  and a live EDDF build wait for a session or job with table access.
- The weekly and drop-one comparisons use the saved natives of weeks 12, 11 and 10 through the
  same pipeline (`run_pipeline`).
- FantasyPros's chart is held today, so every "four charts" statement in the brief is three
  charts in this run. The weight share is 3/(3+n).
- The Tuesday rule reads a date, not a time; a list dated Tuesday counts as the new week.
- Rank guard and `value_check` are unchanged by this PR (DDF code untouched); see the claude-log.
- Nothing is wired: no page, bake or edge function reads EDDF. Wiring the JS engine
  (`value-model.js`, `curve-widget.js`) and a bake step needs the hot-file slot and Jeremy's yes.

## Recommendation

Built as Jeremy ruled (one per expert, primary, Tuesday reset). Keep EDDF off. On real values
per_expert is steadier week to week (0.38 vs 0.51 mean weekly change in Half PPR) and prices a few
more players, but it tracks the charts less closely (leave-one-chart-out rho 0.803 vs 0.919), the
fresh lists are about one independent view carrying 75% of the weight, and a scrambled chart moves
it no less than DDF. The Tuesday reset also means the ranker side empties after each reset and
refills as analysts update. Options for Jeremy to choose from, none substituted here: keep
per_expert; site_once (small effect today); grouped (the ranker view once beside the charts), which
keeps the charts-only agreement; or a floor share for the charts.
