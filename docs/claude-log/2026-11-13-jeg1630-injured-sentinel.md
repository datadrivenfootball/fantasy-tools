## 2026-11-13 - JEG-1630 injured sentinel excuse

Contract: stop the JEG-592 sentinel from red-holding ESPN and CBS ROS when a
sentinel star is priced below his band because he is on IR, without loosening
the check for healthy stars or column shifts. No value math changes.

### Verified (check named)
- Cause: ESPN projects 0 rest of season for Lamar Jackson and Puka Nacua, and
  CBS ROS prices Lamar at 10.1/g. The pulse (dist/modules/fidelity-pulse.json,
  checked 2026-11-13 21:40Z) shows publisher_vs_stored green for ESPN
  (1830/1830 exact), so the numbers are the publisher's, not a scrape gap.
- Both players are on IR: public.player_status_history 2026-11-13 (Lamar IR,
  thumb; Nacua IR, knee MCL); players.json carries injury_status IR / Out.
- `tests/test_sentinel_injury_excuse.py` (7 tests): 5 fail on origin/main's
  fidelity_pulse.py, all pass with the change (the 2 that pass on main are
  negatives that must stay red).
- `python3 -m unittest tests.test_sentinel_injury_excuse
  tests.test_sentinel_derived_floor tests.test_fidelity_sentinels
  tests.test_fidelity_hold`: 131 tests OK.
- Live-data replay (sentinel_failures on players.json 2026-11-13 values):
  ESPN and CBS ROS sentinel failures go to none; Lamar and Nacua listed as
  excused with their injury tag; Razzball unchanged (no failures).

### Claimed, not confirmed
- The next chain pulse after merge turns ESPN and CBS ROS scrape_validity
  green and fidelity_hold releases both red holds. Not yet observed.
- USA Today's amber is the publisher typo "Efton Chism IIII" (Efton Chism
  III). Amber is label-only (does not hide values); not changed here.
