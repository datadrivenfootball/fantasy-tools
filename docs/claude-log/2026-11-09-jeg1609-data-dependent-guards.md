## 2026-11-09 - main red: two tests whose premise depended on the synced data / JEG-1609

Related: JEG-1583 (same class: display rounding), JEG-1485 (weekly rollover), PRs #1410 and #1411 (blocked).

### What failed (pages.yml on main, every run from 42688134809, 2026-11-09 19:56Z, onward)
- shard 3: `tests.test_team_opportunity_render.test_guard_fails_on_shifted_threshold` "the check passes with the tier lines moved".
- shard 4: `tests.test_short_chart_waiver.test_chart_never_short_is_unchanged` (`n_imputed` 1 != 0).
- Last green: 42681785030 at 462654d64. First red: daeeb2164 "Automated comparison rebuild + players.json bake".
  No test or page code changed in between; only data.

### Root causes (test premises, not page or engine bugs)
1. **Opportunity guard.** The mutant moved the big line from 10% to 11%. It is caught only if a seeded case
   (me=0, 3 settings) lands in [10, 11)%. Reproduced: at 462654d64 the three percents were 10.58 / 10.66 / 10.83;
   at daeeb2164+ they are 5.72 / 9.15 / 5.92, so the mutant changes nothing. The seeded league is drafted from the
   committed player table and priced on today's values, so the percents move with every bake.
   Fix: run the unmutated page first (must be clean), take the highest tiered percent, and move that tier's line to
   the next whole percent above it. The guard now also requires a `tier page=` error for that case, not just any
   error. This tightens the check; nothing is loosened.
2. **Never-short chart.** The test assumed FantasyCalc lists more players than 12 teams roster at every position.
   FantasyCalc RB went from 59 to 58 listed with 58 rostered, which is short by the rule (`len <= rostered`), so the
   peer extension correctly imputes one RB and the metadata differs. Engine behaviour is as documented.
   Fix: a chart qualifies only if its no-peer translation lists more than it rosters at every position; each
   scoring must still have at least one qualifying chart (USA Today does today). **Coverage narrowing, logged:**
   FantasyCalc is skipped while any of its positions is short; the equality assertion itself is unchanged, and short
   charts stay covered by `test_real_short_charts_are_extrapolated` and the synthetic tests.

### Verified (check named)
- Both modules fail on main's data before the fix and pass after (`python -m unittest tests.test_team_opportunity_render tests.test_short_chart_waiver`, Python 3.12).
- The fixed modules also pass on 462654d64's data (old worktree, `make sync`).

### Left open
- The class remains: any discrimination check with a fixed mutant needs a case near the moved line. Derive the
  mutant from the observed values, as here.
