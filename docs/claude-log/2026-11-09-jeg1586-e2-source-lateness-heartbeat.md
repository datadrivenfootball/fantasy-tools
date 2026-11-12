# JEG-1586 E2: heartbeat for source-lateness.yml (2026-11-09)

The watchdog is scheduled by GitHub, not pg_cron, and since PR #1381 it also runs the week-held tripwire, so a silent
stop would silence that tripwire. It was in `unmonitored_workflows` ("a missed hour only delays a signal"), which no
longer holds. Now:

- `source-lateness.yml` ends with a `Record monitored check` step (`if: always()`, main only, scheduled or dispatched, not
  the week-held drill) calling `record_monitor_check.py --check-id source_lateness`.
- `config/monitoring_coverage.json` lists it as `github_schedule` and drops the exemption.
- `supabase/migrations/source_lateness_check_20261109.sql` adds the `monitoring.check_config` row (cadence 1 h, grace 2 h).
  Not applied by this PR. Apply it before or with the merge, or the live coverage audit reports a missing row.
- `tests/test_monitoring_coverage.py` pins the step conditions.
