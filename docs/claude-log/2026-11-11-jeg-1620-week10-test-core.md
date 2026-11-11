## 2026-11-11 - JEG-1620: Week 10 test-core red on main

Contract: Pages run 42942807394 (main 676afdf18, Week 10) failed test-core shards 1, 2 and 3 on three tests. The deploy job still succeeded (JEG-1485 decision A lets an automated data commit deploy on its data checks). Get test-core green on Week 10 data without changing published numbers or the value model.

### Verified (check named)
- `tests.test_fractional_seats_stability` standard/14 (Lan Larison ESPN -1 moved Hunter Luepke 1.30) is the JEG-1336 fill-set step, not a seat move. A diagnostic run (`_source_lines` hook on cbs RB) showed the allocation mix unchanged and Luepke, whom no chart lists, entering the cbs fill set at the rostered-81 vertices once Larison's mean (1.08 to 0.76) fell below his (0.91). His cbs estimate counts only inside the fill set (VP-2.4). Jeremy kept that step (JEG-1336 option A, 2026-10-29, `docs/decisions.md`). The test now holds players some chart only estimates, whose fill-set share changed, to FILL_STEP_BOUND = 2.0 (the researched 1.4 to 1.95 step). Every other player keeps the 1.0 bound. Across the 14 settings the worst seat move is 0.36 and the worst fill-set step is 1.30 (standard/14).
- `tests.test_values_page_engine_parity` test_card_gap_label_names_its_charts: Rico Dowdle had one chart in Week 9 and both in Week 10. The examples now come from the data: the highest DDF Value player with both CBS and FantasyCalc numbers, and the highest with exactly one. The test passes locally.
- `tests.test_v2_phone_context_row_render` override test: a real layout defect. Week 10 has a held source, so the phone chip reads "Week 10 ⚠". At 375 px the summary clipped by 8 px in DejaVu Sans and 10 px in Verdana (measured with Playwright, Chromium 1208). Fix: the phone row drops the chip's dot while the warning mark shows (`is-flagged` in `app/v2/v2.js`, rule in `app/v2/v2.css`), which frees 12 px. The test passes for all three cases.
- Local runs used Python 3.12 with playwright 1.58.0. The system Python 3.9 cannot parse `+00` offsets in `make sync`.

### Claimed, not confirmed
- CI's default font behaves like DejaVu Sans (it failed both subtests). Confirmed only by the PR's preview shards.
- Phones narrower than 375 px (for example 360 px Android) may still clip the summary when a source is held. Not in the test's widths.
