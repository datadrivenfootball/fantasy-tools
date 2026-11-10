## 2026-11-10 - render-tests (contract) red on main: GL-05 clock pin / JEG-1612

Related: JEG-1485 (weekly rollover), JEG-1606 / JEG-1607 (blocked PRs #1410, #1411), JEG-787 (the clock pin).

### What failed
`tests.test_v2_contract_render.ContractRenderTest.test_every_live_contract_line`:
`GL-05: freshness: no confirmed source says Current`. It failed on plain main e14995fff and in #1410's
`render-tests (contract)`. pages.yml does not run render-tests, so main looked green.

### Root cause (a test clock, not the data or the page)
- The contract test pinned `window.TRADE_VALUE_TODAY` to the fixture's `built_at[:10]`.
- The chain build at 2026-11-10T01:13Z ran after the Tuesday flip (00:00 UTC), so the page date was
  2026-11-10, content week 10, while every source is week 9.
- product-data marked every series "older", and the freshness popover read "Prior week" for every
  source. GL-05 forces USA Today, CBS and FantasyCalc to warnings and needs one confirmed Current row,
  so it found none.
- It was not the holds: the test pins every source open (`tests/_holds.with_pinned_holds`).
- `tests.test_week_history._fixture_today` already handles this case (JEG-787: pin to the data's own
  week when built_at is in a newer week). It gives 2026-11-09 here. The contract test was the only
  test still using the naive pin.
- This class recurs every Monday evening Central time until the new week's charts land. Chains that
  build after 00:00 UTC Tuesday have built_at in week N+1.

### Fix
- The contract test's `_fixture_today` calls the shared pin.
- GL-05's assertions are unchanged: the freshness line still has to read what the sources say.

### Scan
- The only other "Current" assumption in the file is GL-05's reload_current chip check (same clock,
  same fix).
- `git grep 'built_at"][:10]' tests` finds no other naive pin.

### Checks
- Plain main: the test fails with the message above (local run, Python 3.12, headless Chromium).
- A page dump showed `today 2026-11-10`, `current_content_week 10` and every series `older` at week 9.
- With the fix: `tests.test_v2_contract_render` 6 tests OK (local).
