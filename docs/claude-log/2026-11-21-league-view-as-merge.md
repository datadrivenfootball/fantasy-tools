## 2026-11-21 - JEG-1696 merge of origin/main into PR 1489, header fit at 320/360/375

Contract: bring PR 1489 up to date with main (after PR 1486's freshness dot in the header, 1496/1497/1501) by a
merge commit, keep both sides, and prove the header still fits on small phones with every control showing.

Jeremy's decisions (2026-11-21, via the coordinator): switching team reloads the page; switching clears the waiver
moves; copy "Viewing as X. Not your team." / "Back to <your team>" / "(yours)" in the picker. All as built.

### Verified (check named)
- styles.css conflict (both sides appended at the end): kept both blocks, no other conflict.
- tests/test_league_view_as_render.py test_header_fits_on_small_phones_with_every_control (new): at 320, 360 and 375
  with a seeded league, on team.html, Bookmark, the freshness dot, Menu and the league chip are inside the viewport and
  the header does not overflow, also while viewing as another team.
- Related suites run with Python 3.12 and RENDER_TESTS_REQUIRED=1: see the PR comment for this head.

### Claimed, not confirmed
- values.html overflows 17px at 320 (range thumb and table in the chart body, not the header); not from this branch,
  not checked against main.
