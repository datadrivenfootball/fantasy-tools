# Sleeper username finds your leagues and your team (2026-11-25, JEG-1714)

League entry cheap win 2 of 3 (Jeremy, 2026-11-24: cheap wins, then the Chrome helper, then accounts).

- Sleeper's public API, all `Access-Control-Allow-Origin: *`, no key:
  `GET user/{username}` (null or 404 when unknown; also accepts a user ID) -> `user_id`, `display_name`;
  `GET state/nfl` -> `league_season`; `GET user/{user_id}/leagues/nfl/{season}` -> the leagues (`league_id`, `name`,
  `total_rosters`, `scoring_settings.rec`). Research measured 0.29 s for the whole username-to-rosters path.
- Your team: the roster whose `owner_id` is the user, or whose `co_owners` lists them. `sleeper-import.js mineOf`
  returns its index in roster_id order, the order the read card lists teams.
- connect.html: one box takes a username or a league link or ID (`parseUsername`: 2 to 30 letters, digits or
  underscores, not all digits; digits are league IDs). One league loads at once; several are listed to pick from.
  The username is never stored; the loaded league's ID is remembered as `{v:2, platform:'sleeper', id}` as before.
- Tests: `tests/test_sleeper_import.js` (username case), `tests/test_entry_sleeper_username_render.py` (Sleeper faked
  by a Playwright route). Fixtures `tests/fixtures/sleeper/user.json` and `user-leagues.json`.

## Lesson (review on #1549, 2026-11-27)

- Imported league settings (Sleeper, ESPN) reach the engine on Next only (`applyImported` in connect-entry.js), so
  Edit league then Keep my league leaves them as they were (the #1536 rule).
- When a change moves *when* something is saved, grep every test that fakes that platform (`grep -ln api.sleeper.app
  tests/*.py`) and run them all. `test_sleeper_entry` checked the old timing and was missed until review.
