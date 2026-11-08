## 2026-11-08 - JEG-1393 decisions 2 and 4: Team / Trading Partners leave estimates out; Buy / Sell explanation

Contract: carry out Jeremy's decision 4 (2026-11-08): "drop fill-in estimates on Team and Trading Partners for
consistency; a team counts as complete when every starter is priced; make sure Partners does not blank; add a test with
the real 11-team case; keep the ranking metric otherwise unchanged; note it in the claude-log." And decision 2: the
Buy / Sell comparison stays; its explanation says why top starters look off against indexed chart values.

### What changed
- `app/next/ddf-league.js`: new `chartRows(rows)` (exported as `DDF.league.chartRows`) nulls a chart's fill-in estimate
  (`row.estimated[k]`) on CBS Sports, USA Today, FantasyPros and FantasyCalc, the same rule as the page records
  (`ddf-engine.js` `record`), then adds the Analyst charts average. `lineup()` builds its Analyst charts and Live market
  sides from it. `complete` now means every DDF starter (the lineup behind the DDF starter figure) has a value on that
  side; a bench player without a chart value adds nothing. Before, `complete` meant no rostered player was unvalued,
  which is why the e86255800 attempt blanked all 11 partners (one estimated bench player per team).
- `team.html`: the Analyst premium list reads `DDF.league.chartRows`; the STARTER ANALYST (i) no longer says Team uses
  estimates. `learn.html` glossary "Missing (—)": Team and Trading Partners leave estimates out like the other pages.
  `partners.html` "What these compare": estimates are left out; a bench player a source does not list adds nothing.
- Ranking: `partnerRank()` is unchanged. Its score reads only positionTiers DDF ratios (no chart input); the tie-break
  reads `ratioAnalyst`, which now has estimate-free inputs. A partner whose DDF starter has no Analyst charts value
  (estimate dropped) is "not judged last" in the tie-break, as the metric already did for unlisted starters.
- `values.html` Buy / Sell (i) and fine print: DDF Value is the four charts adjusted to your league (value above the
  waiver line, starters paid at the starter rate); Charts is the same charts indexed (a straight rescale), so the best
  starters usually show DDF Value above Charts even when the charts agree. Headline kept; "Analyst charts" / "Live
  market" capitalised there. No badge counting touched. No value model or engine number changed.

### Seeded 11-partner league (tests.test_team_engine_parity.seeded_league), old main vs this branch, 12 settings
- Analyst charts "—" on Partners: before 0 of 11 at every setting; after 3 to 5 of 11, each one a team whose DDF
  starter has only an estimate on an Analyst chart (all CBS Sports estimates, e.g. Bo Nix, Khalil Shakir, Omarion
  Hampton, Dylan Sampson at the default setting). Blanks caused by a bench player: 0 (e86255800: 11 of 11).
- Live market "—": 0 of 11 before and after (FantasyCalc estimates in the fixture sit on benches only).
- Partners whose Analyst / Live figure changed: 3 to 5 of 11 per setting (the new dashes, plus e.g. Team 06 138.2 ->
  136.8 at half PPR / 10 / superflex, where an estimated bench player had made the Analyst charts lineup).
- Rank moves (tie-break only): 0 to 4 of 11 per setting (standard 10-team: 4; ppr 12-team: 0).

### Verified (check named)
- `tests/test_team_partners_estimates.py` (new): at 12 settings every partner's Analyst charts / Live market figure
  equals a recomputation with estimates left out; a dash appears only when a DDF starter lacks a value; partner order
  equals `test_partners_rank_parity.ORACLE` (estimates dropped); an estimated player (Chris Godwin when estimated, else
  the first) has no Analyst charts value and keeps DDF Value. Fails against old main `ddf-league.js` (figures where a
  dash is due) and against the e86255800-style completeness (Team 02 blank with every starter listed).
- `test_team_engine_parity`, `test_partners_rank_parity` (oracles updated: they encoded estimates and the all-roster
  completeness, the rule Jeremy changed), `test_team_opportunity_render`, `test_values_page_engine_parity`,
  `test_launch_copy_guard`, `test_jeg1130_copy_glossary`, `test_v2_copy_names`, `test_jeg1393_values_explainer_logic`:
  pass on a local `make sync` build.
- Render: team.html, partners.html, values.html#buy-sell with the seeded league at 1280 and 390 px, no page errors
  (only the hermetic route's blocked Google Fonts requests), no horizontal scroll.

### Claimed, not confirmed
- `test_public_copy_no_vorp` DOM mutation subtests ("old pill back", "old series label back") fail locally; they patch
  `app/v2/shell.html` / `v2.js`, which this change does not touch. Not checked on clean main.
- Explore (explore.html) still averages raw rows with estimates; out of this decision's scope.
