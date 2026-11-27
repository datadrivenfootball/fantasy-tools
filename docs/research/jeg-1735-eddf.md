# EDDF: enhanced DDF Value from the charts plus individual rankers (JEG-1735)

Research and design record. Part of JEG-1733. Off by default; DDF Value is unchanged.
Run 2026-11-27 (a Friday) on the committed fixture and `data/history`, rankers read the same day.
Data and scripts: `docs/research/data/jeg1735/` (`lists.json`, `evidence.json`,
`before_after_<scoring>.csv`, `variants.json`, `candidates.json`, `candidate_study.json`),
`tools/research/eddf_prepare.py`, `eddf_evidence.py`, `eddf_variants.py`, `eddf_candidates.py`.
Code: `pipelines/eddf.py` (reference), `pipelines/eddf_model.js` (JS twin, not
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
| 3 | 50% | 0.38 | 0.888 |
| 5 | 38% | 0.45 | 0.866 |
| 8 | 27% | 0.49 | 0.855 |
| 9 | 25% | 0.50 | 0.854 |

Most of the change arrives with the first three rankers. Pooling all rankers into one source
differs from one-vote-each by 0.34 to 0.40 points with rank correlation of 0.999 or more: the choice
matters for weight share and for what happens when a source drops, not for today's values.

## Evidence on real Adjusted values (QBs excluded, the default; Tuesday rule)

Leave one chart out: predict the held-out chart's Adjusted value from the other two charts (DDF
estimate) or from the other two plus the fresh rankers (EDDF). Anchors use the other two charts
only. Mean over the three held-out charts.

| scoring | rho DDF | rho EDDF | MAE DDF | MAE EDDF | rho on ranked players only, DDF / EDDF |
| -- | -- | -- | -- | -- | -- |
| PPR | 0.908 | 0.815 | 0.738 | 0.881 | 0.931 / 0.883 |
| Half PPR | 0.919 | 0.803 | 0.733 | 0.810 | 0.943 / 0.881 |
| Standard | 0.926 | 0.786 | 0.775 | 0.981 | 0.943 / 0.859 |

**EDDF agrees less with a held-out chart than DDF does, in every scoring and for every held-out
chart.** The research stand-in showed no loss (rho 0.928 vs 0.929). A single ranker's implied
value correlates 0.83 to 0.91 with a held-out chart on ranked non-QB players, against about 0.95
for the mean of the other charts, so equal-weight fresh rankers pull the mean away from the charts.
Among the top players (values at least a quarter of the top value) the gap is smaller or reverses:
Half PPR rho 0.855 DDF and 0.871 EDDF, MAE 6.10 and 5.93; PPR and standard are worse for EDDF.
Including QBs lowers EDDF further (Half PPR rho 0.792). The held-out chart is itself a chart, so
this test favours the charts by construction; it measures agreement with the charts, not correctness.

Robustness (mean over the three charts, Half PPR, 15 shared permutations for the scramble):

| test | DDF | EDDF |
| -- | -- | -- |
| scramble one chart's values: mean abs change from unscrambled | 2.12 | 1.93 |
| scramble: rank corr with unscrambled | 0.696 | 0.706 |
| drop one chart: mean abs change | 0.24 | 0.25 |
| drop one chart: rank corr with full | 0.980 | 0.990 |

**Correction (2026-11-27, same session).** A first run used one random permutation per chart and
reported EDDF as 14 to 26% less moved by a scrambled chart. One permutation is far too noisy (the
top few values dominate the mean change). Averaged over 15 permutations shared by every variant,
the gain was 0 to 4% before the rescale and is 8 to 10% after it (PPR 2.11 to 1.93, Half 2.12 to
1.93, standard 2.14 to 1.95), with about +0.01 to +0.02 in rank correlation. Most of the later
gain is the rescale pinning EDDF's total to the unscrambled DDF total while the scrambled anchors
shift the raw EDDF total. Earlier chat and Linear figures are superseded. Dropping one chart now
moves EDDF's values about as much as DDF's (0.25 vs 0.24 in Half PPR) and keeps the order slightly
better.

Stability (week 12 vs week 11, rankers held at the read date, so only the charts vary): mean abs
week-over-week change 0.51 (DDF) vs 0.34 (PPR), 0.39 (Half), 0.30 (standard) for EDDF. The advantage is partly built in: the lists do not change between the two weeks, so only the charts move, and averaging in a fixed view dampens any change. This is not
a test of rankers over time: one list date exists in this run.

Coverage: DDF prices 669 players, EDDF 674 (five players the rankers list and no chart prices);
players priced by one source only: 0 (DDF), 1 to 3 (EDDF, ranker-only players).

## Variants side by side (Jeremy, 2026-11-28: "One per expert" is primary)

`variants.json`, same harness and inputs. none = DDF Value; per_expert = every list one vote
(Jeremy's choice, the default); site_once = a publisher's lists share one vote (only the three
FantasyPros staff lists share a group); grouped = all lists averaged into one source beside the
charts. A fifth, `chart_floor`, keeps the charts at no less than half the weight (one vote per expert
until the rankers would outweigh them; shown in the candidate study below). Half PPR (PPR and
standard are within a few hundredths):

| variant | LOO rho | LOO rho, ranked | LOO MAE | scramble MAE / rho | drop-one MAE / rho | week-change MAE | chart weight | priced |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| none | 0.919 | 0.943 | 0.73 | 2.12 / 0.696 | 0.24 / 0.980 | 0.51 | 100% | 669 |
| per_expert | 0.803 | 0.881 | 0.81 | 1.93 / 0.706 | 0.25 / 0.990 | 0.39 | 25% | 674 |
| site_once | 0.803 | 0.882 | 0.79 | 1.90 / 0.709 | 0.24 / 0.990 | 0.39 | 30% | 674 |
| grouped | 0.805 | 0.888 | 0.72 | 1.97 / 0.712 | 0.20 / 0.990 | 0.43 | 75% | 674 |

Independence of the added views, Half PPR (non-QB players all fresh lists rank): the fresh lists
agree with one another at rank correlation 0.925 (charts with each other 0.966, lists with charts
0.895). With 9 lists at that agreement the effective number of independent views is **1.07**, not
9: the lists are one view in nine costumes. The three FantasyPros staff lists agree at 0.927, no
more than the rest, so per-site down-weighting changes little (site_once is within 0.03 of
per_expert on every metric): one site does not dominate, the whole ranker group does. Under
per_expert that one view holds 75% of the weight; grouped puts it at 25% and keeps the
charts-only error (MAE 0.72). Dispersion: among the three charts the per-player standard deviation
of value is 2.24 points; among the 9 lists' implied values 3.64; the chart mean and the list mean
differ by 2.95.

Reading for Jeremy's goal (a better consensus of the market): per_expert buys steadier values week
to week and slightly more coverage, and costs agreement with the charts, because it counts one
view nine times. grouped keeps the charts in charge and adds the ranker view once. The choice is
his; this PR builds per_expert as the default and ships site_once and grouped as options in
`eddf.py` (`variant=`).

## Candidate sources: the consensus study (Jeremy, 2026-11-28)

`study.json`, `candidates.json`, `candidate_study.json`; `tools/research/eddf_candidates.py` and
`eddf_study.py`. Candidate rows are enabled only inside the harness; the registry rows stay
`enabled: false`. Each candidate at the scoring the file states (the pegging as catalogued), under
the Tuesday rule, on the same consensus metrics as the variants above:

| candidate | kind | pegging | dated | usable on 27 Nov |
| -- | -- | -- | -- | -- |
| Wolf, Roto Street Journal | analyst | scoring unstated, used for all three | 24 Nov | no: duplicates the Wolf list already in the feed (same analyst, same date) |
| Rotoballer (Mariano) | analyst | half PPR and PPR lists | 25 Nov | yes in Half PPR and PPR, 172 non-QB players priced |
| GWTTKB | model | PPR 1QB 12-team | 23 Nov | no: a Monday date, stale under the Tuesday rule |
| Razzball projections | model | points for standard, half, PPR | 26 Nov | yes in all three, 464 non-QB players priced |
| FanDuel Research | model | half PPR inferred, not stated | read date, no date on page | yes in Half PPR only, 520 priced; scoring inferred and undated |
| StickToTheModel | model | PPR only, top 30 per position | 24 Nov | yes in PPR only, 90 priced |
| Footballguys (Kluge) | analyst | QBs only | 24 Nov | no: QBs are excluded, so it prices nothing |

Source sets (Half PPR; PPR and standard in `study.json`): feed = the 9 fresh FantasyPros-feed lists;
+analyst adds Rotoballer; +models adds Razzball and FanDuel; +all usable adds all three. Leave-one-
chart-out rank correlation against the held-out chart, with a bootstrap 95% interval of the
difference from DDF (200 resamples of players):

| set | fresh lists | none (DDF) | per_expert | site_once | grouped | chart_floor 50% |
| -- | -- | -- | -- | -- | -- | -- |
| feed | 9 | 0.919 | 0.803 [-0.129, -0.100] | 0.803 | 0.805 | 0.804 |
| +analyst | 10 | 0.919 | 0.803 [-0.134, -0.099] | 0.803 | 0.805 | 0.804 |
| +models | 11 | 0.919 | 0.740 [-0.200, -0.163] | 0.740 | 0.743 | 0.742 |
| +all usable | 12 | 0.919 | 0.740 [-0.196, -0.162] | 0.740 | 0.743 | 0.742 |

Other metrics, Half PPR (none = DDF): scramble-one-chart mean change 2.12; drop-one 0.24; weekly
change 0.51; priced 669.

| set and variant | LOO MAE | scramble | drop-one | week change | chart weight | priced |
| -- | -- | -- | -- | -- | -- | -- |
| feed, per_expert | 0.81 | 1.93 | 0.25 | 0.39 | 25% | 674 |
| feed, grouped | 0.72 | 1.97 | 0.20 | 0.43 | 75% | 674 |
| feed, chart_floor | 0.73 | 1.89 | 0.21 | 0.39 | 50% | 674 |
| +models, per_expert | 0.82 | 1.65 | 0.20 | 0.34 | 21% | 718 |
| +models, grouped | 0.72 | 1.74 | 0.18 | 0.42 | 75% | 718 |
| +models, chart_floor | 0.73 | 1.60 | 0.18 | 0.36 | 50% | 718 |

Independence among the fresh lists (pair rank correlation, effective independent views):
feed 0.925 and 1.07; +analyst 0.921 and 1.08; +models 0.883 and 1.12. The models are the only added
views that differ from the feed, and even with them the lists are about 1.1 independent views.
Dispersion (SD of a player's value among the lists): 3.64 for the feed, 4.54 with the models, against
2.24 among the three charts.

**Reading.** No candidate set improves agreement with a held-out chart; the interval of the
difference excludes zero for every variant and set. Weights change the size of the error, not the
rank agreement: grouped and chart_floor cut the leave-one-chart-out MAE (0.72 and 0.73 against
0.81) while rank correlation stays within 0.003 of per_expert, so the rank loss comes from the
rankers' view itself, not from how many votes it gets. The models are the most independent views and
the most robust to a scrambled chart (1.65 vs 2.12 for DDF, per_expert) and steadier (0.34 vs 0.51),
and they cost the most agreement (0.740 vs 0.803).

**One list date.** Supabase `ros_rankings` was not readable from this session and the puller reads
only the pages as they are today, so there is no second date; re-running it later would add one, a
re-run today only repeats these dates. Nothing here tests rankers over time. The bootstrap above
puts an interval on each agreement difference across players, which says the result is not a few
players, not that it holds on another week. A second date should be added by a session or job with
`ros_rankings` access, or by re-running the puller after the next Tuesday reset.

**Recommendation (numbers above; Jeremy chooses).** Enable none of the seven for now:
- Rotoballer: usable and harmless (rho unchanged at 0.803, effective views 1.076 vs 1.071), but it
  adds no measurable information; enable only if Jeremy wants one more named analyst.
- Razzball: the one candidate that adds an independent view and robustness; if any is enabled,
  this one, as its own group, at PPR, Half PPR and standard. It lowers agreement with the charts.
- FanDuel: not until its scoring and date are stated (inferred half PPR, no update date) and it
  costs the most agreement; StickToTheModel (90 players, PPR only) and GWTTKB (stale on the Tuesday
  rule) have too little to weigh; Wolf is a duplicate; Footballguys prices nothing.
- Weight: per_expert (Jeremy's ruling) gives the charts 25% and ties to the feed's one view; for
  the same rank agreement and lower error, `chart_floor` at 50% or `grouped` are the options, shown
  here, not substituted.

## League value total (rescaled, Jeremy 2026-11-28)

DDF Value sums to 2352.0 over all players in every scoring. Before any rescale EDDF summed to
2378.6 in PPR (+1.1%), 2433.8 in Half PPR (+3.5%) and 2333.2 in standard (-0.8%). Jeremy ruled
(2026-11-28, multiple choice) that EDDF is rescaled to the league value total before it is ever
shown, so EDDF and DDF Value stay on one scale and trades and totals compare directly. EDDF is now
multiplied by one factor (0.9888 PPR, 0.9664 Half PPR, 1.0081 standard) so it sums to the DDF total
to 1e-6 in every scoring and variant; one factor leaves the order unchanged. `rescale_to_ddf_total`
in the config switches it off. Every number in this write-up is after the rescale.

## Weight and independence, together

Under one vote per expert the fresh lists hold 75% of the weight in Half PPR (the charts 25%), but
they are about 1.07 effective independent views (pair rank correlation 0.925), and all of them
come through FantasyPros's expert pages (the staff three among them). The weight sits with one
view, not with nine.

## Before and after

`before_after_<scoring>.csv`: every player with a DDF or EDDF value, both values, ranks and source
counts. Spearman DDF vs EDDF over the 669 common players: 0.874 (PPR), 0.854 (Half), 0.839
(standard); top-24 overlap 22, 22, 20; largest single-player move 10.0, 10.6, 14.8 points.
Half PPR top: Gibbs 83.97 to 81.15, Robinson 66.10 to 67.14, McCaffrey 69.76 to 66.13,
Smith-Njigba 67.60 to 65.01, Walker 66.10 to 60.41.

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
per_expert is steadier week to week (0.39 vs 0.51 mean weekly change in Half PPR; partly built in, because the lists are held fixed and only the charts move) and prices a few
more players, but it tracks the charts less closely (leave-one-chart-out rho 0.803 vs 0.919), the
fresh lists are about one independent view carrying 75% of the weight, and a scrambled chart moves
it 8 to 10% less than DDF (mostly the rescale). The Tuesday reset also means the ranker side empties after each reset and
refills as analysts update. Options for Jeremy to choose from, none substituted here: keep
per_expert; site_once (small effect today); grouped (the ranker view once beside the charts), which
keeps the charts-only agreement; or a floor share for the charts.
