## 2026-11-22 - Build a Trade lineup card (DDFLineup)

Contract: implement Jeremy's decisions (2026-11-21/22) on the lineup concept page: one card "Starting lineup after this
trade" under You give / You get, both teams' starter totals before and after, changed slots open, unchanged starters and
bench folded, flags as chips, K and DEF rows marked "not valued", no sticky bar; the Why on Build loses its lineup tables;
one shared renderer (DDFLineup: line / changes / full) used by Build, the Find card and the Why. No value math changes.

### Verified (check named)
- Card position, default folds, totals equal to an independent best-lineup computation in the test (not finder.js),
  every player entering a starting slot has an open row, K/DEF rows "not valued", Why on Build has no lineup tables,
  shop / Any players (partial league) / no-league states, no horizontal scroll, header unchanged, at 375 and 1440:
  `tests.test_build_lineup_card_render` (USO fixture).
- Find card numbers, data attributes, In / Out line unchanged and at most one flag chip per side; Why panel tables still
  drawn on Find: `tests.test_find_natural_fit2_render`, `tests.test_ddf_why`.
- Related suites green locally (86 tests): build offer, partner handoff, page engine parity, any waivers, waiver
  handoff, root pages, swap routes, find engine parity, chart links, waiver alternative, held chart, min charts filter,
  values page parity, team engine parity, validate shards.

### Claimed, not confirmed
- K and DEF names on the card: the USO paste has no keyed kicker or defense, so the rows show a dash; a league whose K /
  DEF rows exist in the engine should show names (not exercised).
- Live site look with the real web fonts (tests block external fonts).
