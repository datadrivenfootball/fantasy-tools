-- JEG-1586 (E2): heartbeat for source-lateness.yml.
--
-- The hourly lateness watchdog is scheduled by GitHub (its own `schedule:`), not pg_cron, and since PR #1381 it also runs
-- the week-held tripwire (JEG-1512). Nothing watched it, so a silent stop would have silenced both. The workflow now ends
-- with the `Record monitored check` step (pipelines/record_monitor_check.py); this row lets the evaluator flag `missed`
-- when no run is recorded. Cadence 1 h (cron "50 * * * *"); grace 2 h because GitHub-scheduled runs are routinely
-- delayed or skipped for an hour under load, and a gap that long is the earliest signal worth paging on.
--
-- Idempotent. Apply BEFORE (or with) the merge of the PR that adds the manifest entry: until the row exists the audit in
-- health-artifacts.yml reports the check as having no check_config row. Pinned by tests/test_monitoring_coverage.py.
--
-- Rollback:
--   delete from monitoring.check_config where check_id = 'source_lateness';
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('source_lateness', 'http_status_and_content', 3600, 7200,
     'github_actions', 'source-lateness.yml',
     '{"severity": "warn", "what": "source-lateness.yml ran its hourly per-source lateness check and the week-held tripwire (GitHub schedule, 50 past each hour)", "label": "Source lateness watchdog"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
