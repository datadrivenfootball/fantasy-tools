# JEG-1597 scoring-aware DDF: research record (2026-11-09)

Research only; nothing here is live. Read in this order:

1. `data-inventory.md`: stat-level projections and actuals available (Razzball `pg_*` stats in
   Supabase are the best per-game set; no per-stat actuals before 2024).
2. `step1-scoring-assignment.md`: inferring a chart's scoring from its order and spacing fails
   its labelled test (3 of 20 on CBS Sports / USA Today known columns).
3. `fantasycalc-pegged-or-blend.md`: FantasyCalc `value == redraftValue` only at ppr=1, 12 teams;
   other ppr and numTeams settings are that list times one constant per position; numQbs=2 is a
   separate list. Which leagues' trades feed the base is not identifiable.
4. `step2-decomposition.md`, `step3-proposal.md`: chart value -> chart-implied points -> rescale
   by projected points ratio -> back to natives (position-scaled mapping), then the unmodified
   value reference. Current DDF reproduces exactly.
5. `step4-preregistration.md`, `step4-results.md`: primary claim (H2) not shown and not robust;
   labelled check and 2015-2025 mechanism test fail.
6. `page/how-we-got-to-the-values.html`: reader page draft; review rounds in
   `docs/claude-log/2026-11-09-jeg1597-round-log.md`.

## Durable learnings

- Do not infer a chart's scoring from its list; use what the publisher states, and label
  assumptions (FantasyPros states none).
- Publishers with real format columns move values about 0.3-0.4 of what projected stats imply,
  and reorder few same-position pairs (week 9: CBS Sports 4, USA Today 21 of 1,260 top-36 RB/WR
  pairs). A full projection-ratio rescale overshoots them.
- Over 2015-2025, trailing Full PPR points predict Standard rest-of-season points better than
  trailing Standard points: receptions carry usage signal beyond their scoring value. Rescoring
  by catches at full strength discards it.
- FantasyCalc's cached settings can serve different data refreshes in one pull (JEG-1602).
- A literal inverse through a convex chart curve (`native x ratio^b`, b 2-5) exaggerates
  position moves about 3.5x; scale position levels by projected points instead.
