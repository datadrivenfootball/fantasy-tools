# ESPN public leagues load from the ID (2026-11-25)

League entry cheap win 1 of 3 (Jeremy, 2026-11-24: cheap wins, then the Chrome helper, then accounts).

- `app/next/espn-import.js` reads `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{id}`
  from the browser: `view=mSettings` first (about 8 KB: name, size, scoring, slots), then `view=mTeam&view=mRoster`.
  `credentials: "omit"` and no custom headers, so it is a simple CORS request (no preflight). ESPN echoes our origin.
- Status codes: 200 public, 401 private (`AUTH_LEAGUE_NOT_VISIBLE`), 404 unknown ID for that season. Private leagues
  cannot be read from our page in any browser (ESPN's cookies are not sent cross-site); that needs the helper.
- Season: `seasonId=` from the link, else the calendar year (January and February count as last season).
- Mapping: `defaultPositionId` 1 QB, 2 RB, 3 WR, 4 TE, 5 K, 16 D/ST. `lineupSlotCounts` ids 0 QB, 2 RB, 3 RB/WR,
  4 WR, 5 WR/TE, 6 TE, 7 OP (superflex), 16 D/ST, 17 K, 20 bench, 21 IR, 23 FLEX. FLEX = 3 + 5 + 23. Reception
  points are scoring statId 53; a TE premium shows as `pointsOverrides["6"]` on that item (not yet seen on a real league).
- `proTeamId` maps to Sleeper-style codes (28 WAS, 30 JAX, 33 BAL, 34 HOU). D/ST becomes `"CHI Defense DEF"`, as the
  Sleeper import does, so the shipped kicker and defense matching marks it not evaluated.
- The record is `source: "espn"` with `importSettings`, so settings.html shows its one line "From ESPN".
- Tests: `tests/test_espn_import.js` (node, fixtures), `tests/test_entry_espn_load_render.py` (ESPN faked by a
  Playwright route). Fixture `tests/fixtures/espn/` is the USO rosters as an ESPN response.
