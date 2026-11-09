# JEG-1603: manifest the forced weekly chain cron jobs (2026-11-09)

Run 42575484404 of health-artifacts failed "Audit monitoring coverage" with exactly two gaps: the active pg_cron jobs
`rebuild-chain-weekly-tue-evening` and `rebuild-chain-weekly-wed-morning` (JEG-1485 decision B, applied 2026-11-08) had no
manifest entry. Earlier red runs (since 2026-11-06) failed in the watch step with 0 coverage gaps; only runs after the
2026-11-08 cron change report these two.

- `config/monitoring_coverage.json`: both jobs map to `rebuild-chain.yml` / `rebuild_chain`, the same proof as
  `rebuild-chain-bake-live`. No new `monitoring.check_config` row, so no migration and nothing to apply to production.
- `tests/test_monitoring_coverage.py` pins both entries.
