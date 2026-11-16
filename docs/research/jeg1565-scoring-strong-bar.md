# Scoring formats: the Strong bar (JEG-1565)

Decision (Jeremy, 2026-11-16): no haircut. A chart is Strong on "Scoring
formats" when its Full PPR vs Standard top-36 reorder share (average over RB,
WR, TE) is at least the lower of ESPN's and Sleeper's own rest-of-season shares.
This replaces the fixed `SCORING_STRONG_PCT = 42`.

## Today's value: 74.1%

Measured read-only on 2026-11-16 from the warehouse table
`source_weekly_projections` (season 2026, content week 10, target weeks 10-18,
latest run per source; earlier runs identical).

- Each stat line rescored the same way in both columns: pass yards /25, pass TD
  4, INT -1, fumble lost -2, 2-pt 2, rush and receiving yards /10, TD 6. ESPN
  lines carry no fumbles or 2-pt fields (0 in both columns). Standard = that
  score; Full PPR = that score plus 1 per reception.
- Same metric as `_reorder` in `pipelines/research_trade_value_audit.py`: top 36
  by Full PPR with Standard above 0; count rank slots where the Standard order
  has a different player; average RB, WR, TE.
- Rest of season, weeks 10-18, players reordered out of 36 (RB / WR / TE):
  ESPN 22 / 32 / 28 = 75.9%; Sleeper 26 / 26 / 28 = 74.1%. Lower = **74.1%**.
- Checks: ESPN rescore matches stored points within 0.005, Sleeper within 0.07
  (it also scores return yards); stored PPR minus Standard equals receptions.
- For scale: real outcomes (2015-2025) reorder 84%; ESPN single weeks 82%,
  Sleeper 73%.

## Why a stored value, not a rebuild

The page pipeline reads only repo fixtures and saved history and runs offline
(`--check` in CI). The warehouse projections are not in the repo, so the bar is a
dated value in `data/research/jeg1565/scoring-strong-bar.json`, loaded by the
pipeline. To refresh, rerun the measurement above and edit that file (as_of,
both shares, strong_pct = the lower); the pipeline asserts strong_pct equals the
lower of the two. The page method text prints the value and its date.

## Labels under this bar

USA Today 59% OK, CBS Sports 32% OK, FantasyCalc OK (numbers change, 0%
reorder), FantasyPros Weak. No chart is Strong. Lead note (not adopted): the
charts are rest-of-season values with age and rookie effects, and CBS's TE list
has 11 players, so they may move less than weekly projections even when they
handle formats correctly.
