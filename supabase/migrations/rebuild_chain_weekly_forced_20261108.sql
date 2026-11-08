-- APPLIED 2026-11-08 by the JEG-1485 coordinator on Jeremy's yes (decision B): the pre-check
-- matched the 8 existing jobs; both jobs below verified active with these commands. This
-- file is the record of what is in cron.job; cron.schedule upserts by name, so re-running
-- is safe.
-- JEG-1485 decision B (Jeremy, 2026-11-08): forced rebuild-chain runs Tuesday 20:00
-- and Wednesday 06:00 Central. pg_cron runs in UTC. Central is CST (UTC-6) from
-- 2026-11-01 to 2027-03-14, which covers the rest of the season, so:
--   Tue 20:00 CST = Wed 02:00 UTC -> '0 2 * * 3'
--   Wed 06:00 CST = Wed 12:00 UTC -> '0 12 * * 3'
-- (From 2027-03-14 under CDT these fire at 21:00 / 07:00 local; re-time before Week 1 of 2027.)
--
-- No new mechanism: the same dispatcher as rebuild-chain-bake-live. bake_players
-- is left false (the chain still bakes when a projection input changed). The
-- source input is provenance only (rebuild-chain.yml declares it).
--
-- PRE-CHECK (read-only). Expect exactly the 8 rows seen on 2026-11-08 and no row named
-- rebuild-chain-weekly-*:
--   select jobname, schedule, active from cron.job
--   where command ilike '%rebuild-chain%' or jobname ilike '%chain%' or jobname ilike '%vintage%'
--      or command ilike '%source-probe%' or command ilike '%pages.yml%' order by jobname;
--
-- APPLY. cron.schedule(name, ...) upserts by name, so re-running is safe.
select cron.schedule(
    'rebuild-chain-weekly-tue-evening',
    '0 2 * * 3',
    $$SELECT public.dispatch_gha_workflow('rebuild-chain.yml', '{"source": "pg_cron-weekly-tue-2000ct"}'::jsonb)$$
);
select cron.schedule(
    'rebuild-chain-weekly-wed-morning',
    '0 12 * * 3',
    $$SELECT public.dispatch_gha_workflow('rebuild-chain.yml', '{"source": "pg_cron-weekly-wed-0600ct"}'::jsonb)$$
);
--
-- VERIFY.
-- 1. Schedule present (2 rows, active):
--      select jobname, schedule, active, command from cron.job where jobname like 'rebuild-chain-weekly-%';
-- 2. After the first fire (Wed 2026-11-11 02:00 UTC = Tue 11-10 20:00 CST):
--      select j.jobname, d.status, d.return_message, d.start_time from cron.job_run_details d
--      join cron.job j using (jobid) where j.jobname like 'rebuild-chain-weekly-%'
--      order by d.start_time desc limit 4;
--    expect status 'succeeded'. Also check the dispatch row in monitoring.dispatch_log for rebuild-chain.yml
--    near that time, and run: gh run list -R datadrivenfootball/fantasy-tools -w rebuild-chain.yml
--    --event workflow_dispatch --limit 5 (a run starting ~02:00Z whose "Record workflow start time" step
--    names source pg_cron-weekly-tue-2000ct).
--
-- DOUBLE-FIRE ANALYSIS (cron.job as read 2026-11-08):
-- - vintage-check-live '0 * * * *' also fires at 02:00 and 12:00 UTC and dispatches the chain only
--   when DB vintage differs from the fixture. If both dispatch in the same minute, rebuild-chain.yml's
--   concurrency group (one running, newest pending replaces older pending, never cancels a running
--   one) leaves at most one extra queued run. Its commit step is a no-op when nothing changed
--   ("No changes to commit"), so a duplicate never double-publishes.
-- - rebuild-chain-bake-live '45 11 * * *' (Wed 05:45 CST) is usually still running at 12:00 UTC
--   (the chain takes ~25-60 min). The 06:00 CT forced run then queues behind it and starts when it ends:
--   a second pass right after the safety run. That is redundant on a day when 05:45 already published
--   the week, but harmless and cheap. It is also what Jeremy asked for.
-- - source-probe-* jobs (:05, :25, :35) dispatch through source_probe.py dispatch-chain, which skips
--   when a chain run is already waiting, so they do not stack on these.
--
-- ROLLBACK:
--   select cron.unschedule('rebuild-chain-weekly-tue-evening');
--   select cron.unschedule('rebuild-chain-weekly-wed-morning');
--   (then the verify query in 1. returns 0 rows). Nothing else changes; no table or function is touched.
