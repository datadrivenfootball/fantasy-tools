-- JEG-1667 Phase 0: daily schedule for the draft-pull edge function.
-- Applied 2026-11-27 via the Supabase MCP on Jeremy's yes, after
-- draft_tool_phase0_20261127.sql and the draft-pull deploy.
-- 11:15 UTC daily (05:15 CST; 06:15 CDT in summer). The function pulls each source at
-- most once per UTC day, so the public key is enough and a repeat is free.
-- Replace <publishable key> with the project's public key (the same key the
-- site ships); no secret is needed. Idempotent: cron.schedule replaces a job
-- of the same name.
begin;

select cron.schedule('draft-pull-daily', '15 11 * * *', $$
  select net.http_post(
    url := 'https://iskiybsimubiujwuchsl.supabase.co/functions/v1/draft-pull',
    headers := jsonb_build_object(
      'Authorization', 'Bearer <publishable key>',
      'Content-Type', 'application/json'),
    body := '{}'::jsonb,
    timeout_milliseconds := 60000)
$$);

commit;
