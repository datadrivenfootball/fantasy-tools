## 2026-11-14 - JEG-1641 weekly projection warehouse

Contract: append every future week's projection (ESPN, Sleeper; CBS and FantasyPros current week) plus nflverse schedule and injury snapshots to new append-only tables every day, with a freshness and size check. Storage only; no value or published number changes. Decision A (Jeremy 2026-11-14, relayed by the coordinator): daily full copies, no deletion.

### Verified (check named)
- Row builders, savers' write order and floors, freshness and size judgments, alert open/close, migration columns vs builders: `python3 -m unittest tests.test_projection_warehouse` (28 tests).
- Existing workflow, monitoring and ESPN store guards still pass: `tests.test_monitoring_coverage`, `test_workflow_*`, `test_no_failopen_workflows`, `test_main_writer_workflows`, `test_espn_weekly_store`, `test_source_lateness`, `check_supabase_naming.py`.
- Live dry run 2026-11-14 (no database, identity off): `save_projection_warehouse.py --dry-run --no-identity`: Sleeper 3,655 rows weeks 10-18 (351, 345, 427, 376, 411, 435, 436, 437, 437), CBS 704 (weeks 10 and 11; week 12 not offered), FantasyPros 40 (week 10, about 10 per position), schedule 272 games, injuries 112 (report week 10).
- ESPN live pull through `espn_rows`: 5,490 rows, 610 per week 10-18, `appliedTotal` present on every row.

### Claimed, not confirmed
- Size estimate (about 4 to 5 MB a day, about 150 MB to week 18): from row counts and JSON size, not a measured table size. Replace after a week of runs.
- Live write runs, append-only proof and the first scheduled run: recorded on JEG-1641 once the migration is applied and the PR merges.

## 2026-11-14 - JEG-1641 FantasyPros dropped (correction, new entry)

Jeremy, 2026-11-14 (relayed): "We don't need 10 rows per day of anything." FantasyPros was removed from the saver, the freshness check (no rule, so it never alerts), the tests and the doc. The applied migration is unchanged: its check constraint still allows 'fantasypros', and nothing writes that value. The FantasyPros dry-run count above (40 rows) no longer applies.

### Verified (check named)
- `python3 -m unittest tests.test_projection_warehouse`, including `test_fantasypros_dropped_never_checked_or_saved`.
