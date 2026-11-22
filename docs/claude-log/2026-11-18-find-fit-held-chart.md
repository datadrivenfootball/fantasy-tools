## 2026-11-18 - Find judges fit with one analyst chart on hold (Jeremy's option A, plus the empty text)

Ticket: none filed (Linear/MCP calls time out from agent sessions this week). Branch `fix/find-fit-held-chart`.

### Cause
`app/next/find-engine.js` `context()` set `analyst` to null unless all three analyst charts (CBS Sports, USA Today,
FantasyPros) were available. The default "Their valuation" is their average (`chart_avg`), so in a mixed week with one chart
on hold `searchPartner` judged no offer: zero Natural fits for every team, all offers under Partner neutral as "Fit not
judged", and the Natural fit section said "No offers clear the bar", which reads as "this league has no trades".
Seen in a USO league report (Team 3, snapshot `tests/fixtures/league_levels/raw/uso_rosters_2026-10-29.json`).

### Change
- `find-engine.js`: `MIN_ANALYST = 2`. `context().analyst` is the available analyst charts when at least two are, else
  null; `context().analystMissing` names the rest; `searchPartner` returns `unjudged: "charts" | "depth" | null`;
  `DDF.find.chartNames(keys)` for copy. Every page that reads `DDF.find.context()` follows (find, waivers, team's
  opportunity line, the Why panel).
- `find-page.js` / `find.html`: `#analyst-note` ("USA Today is on hold this week, so fit on the analyst charts uses CBS Sports
  and FantasyPros.") when an analyst-chart valuation is picked and one chart is held. Below two charts the Natural fit and
  Force fit empty text is "Fit can't be judged this week: <charts> are on hold. Offers are listed under Partner neutral as
  "Fit not judged"." instead of "No offers clear the bar".
- `build-trade.js`: same two-of-three rule, so a Natural fit from Find does not open Build a Trade on "Analyst charts are not
  available".
- The connector (`supabase/functions/mcp/fit.ts`) already judges with 3 of its 4 trade charts (finder.js `MIN_CHARTS`),
  so site and connector now both judge fit with one chart held. They still average different chart sets (3 analyst charts vs
  4 trade charts incl. FantasyCalc); that difference predates this change.

### Proof
- `tests/test_find_held_chart.py` (desktop and 375): hold = `getSourceInfo` reports the chart unavailable, then
  `DDF.findPage.run(true)`. 2 of 3 gives Natural fits whose "Them" numbers equal tradeFit on a two-chart mean computed in the
  test; 1 of 3 fails closed with the new empty text; serving `MIN_ANALYST = 3` makes the 2-of-3 case fail.
- USO, Team 3, half PPR, 3 WR + flex, 5 bench, dist build: all charts 13 Natural fit groups; USA Today held 14 (was 0);
  USA Today and FantasyPros held 0, with the new empty text.

### Review (round 1, APPROVE with follow-ups)
- Fixed here: the test picks the charts to hold from the served week (`plan()`), so a real hold week still tests 2-of-3
  and 1-of-3 instead of failing; the unjudged status / empty text names the cause when it is missing lineup settings, not
  charts ("Fit can't be judged: this league's lineup settings are not available").
- Open: the Team page opportunity line, the Why panel, pickups' market view and Build a Trade also run on two charts in a
  hold week but do not say so.

### Local test note
Homebrew python3.12 has Playwright 1.63, whose headless shell (1243) is not downloaded here; the cached 1208 shell works:
`CHROMIUM_PATH=~/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell`.
`tests.test_waiver_gain_basis` (bench basis: no cards) fails on main too at this data; not from this change.
Under heavy machine load `ensure_built()`'s sync can time out in `pipelines/answer_tables.cjs` (900s); when dist/ already
matches app/next, run the modules with `tests._render_env._built = True` set first.
