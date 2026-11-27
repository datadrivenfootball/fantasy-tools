-- JEG-1732: Flaim as a stand-in source while Yahoo's Fantasy API approval is pending.
-- Jeremy, 2026-11-27: "I want to try out the new features and iterate on them by having flaim
-- populate the data while we are waiting for yahoo to allow the developer permissions."
--
-- A Flaim snapshot lands in the same ddf_accounts.leagues rows a direct Yahoo pull fills, in the
-- same summary shape (ddf-connected-league/0, docs/flaim-snapshot-schema.md), so features never
-- care which source it came from. leagues.source says how the data arrived; leagues.platform stays
-- where the league lives. A later direct pull of the same league overwrites the row and sets
-- source = 'direct'. Additive only.

alter table ddf_accounts.connections drop constraint if exists connections_platform_check;
alter table ddf_accounts.connections add constraint connections_platform_check
  check (platform in ('sleeper', 'yahoo', 'espn', 'flaim'));

alter table ddf_accounts.leagues add column if not exists source text not null default 'direct'
  check (source in ('direct', 'flaim'));

-- Admin-only import (service role / postgres, e.g. the Supabase MCP execute_sql). Never callable
-- by signed-in users or anonymously. Returns the league row id.
create or replace function ddf_accounts.import_flaim_snapshot(p_email text, p_snapshot jsonb)
returns uuid
language plpgsql
security definer
set search_path = ddf_accounts, pg_temp
as $$
declare
  v_user uuid;
  v_conn uuid;
  v_league uuid;
  v_platform text := p_snapshot->>'platform';
  v_key text := p_snapshot->>'league_key';
  v_pulled timestamptz;
begin
  select id into v_user from auth.users where lower(email) = lower(p_email);
  if v_user is null then raise exception 'No DDF account for that email yet: sign in on staging once first.'; end if;
  if coalesce(p_snapshot->>'shape', '') <> 'ddf-connected-league/0' then raise exception 'shape must be "ddf-connected-league/0"'; end if;
  if coalesce(p_snapshot#>>'{source,kind}', '') <> 'flaim' then raise exception 'source.kind must be "flaim"'; end if;
  if v_platform is null or v_platform not in ('yahoo', 'espn', 'sleeper') then raise exception 'platform must be yahoo, espn or sleeper (where the league lives)'; end if;
  if v_key is null or length(v_key) = 0 then raise exception 'league_key is required'; end if;
  if (p_snapshot->>'season') is null or (p_snapshot->>'season') !~ '^\d{4}$' then raise exception 'season must be a 4-digit year'; end if;
  if jsonb_typeof(p_snapshot->'settings') is distinct from 'object' then raise exception 'settings must be an object'; end if;
  if jsonb_typeof(p_snapshot->'teams') is distinct from 'array' or jsonb_array_length(p_snapshot->'teams') = 0 then raise exception 'teams must be a non-empty array'; end if;
  if jsonb_typeof(p_snapshot->'schedule') is distinct from 'array' then raise exception 'schedule must be an array (it may be empty)'; end if;
  if jsonb_typeof(p_snapshot->'missing') is distinct from 'array' then raise exception 'missing must be an array (it may be empty)'; end if;
  begin
    v_pulled := (p_snapshot->>'pulled_at')::timestamptz;
  exception when others then
    raise exception 'pulled_at must be an ISO 8601 date-time with zone';
  end;
  if v_pulled is null then raise exception 'pulled_at is required'; end if;

  insert into ddf_accounts.connections (user_id, platform, external_id, display_name)
  values (v_user, 'flaim', 'flaim', 'Flaim (stand-in until Yahoo is approved)')
  on conflict (user_id, platform, external_id) do update set updated_at = now()
  returning id into v_conn;

  insert into ddf_accounts.leagues (user_id, connection_id, platform, league_key, season, name, my_team_key, summary, raw, pulled_at, source)
  values (v_user, v_conn, v_platform, v_key, (p_snapshot->>'season')::int, p_snapshot->>'name',
          p_snapshot->>'my_team_key', p_snapshot, p_snapshot, v_pulled, 'flaim')
  on conflict (user_id, platform, league_key) do update set
    connection_id = excluded.connection_id, season = excluded.season, name = excluded.name,
    my_team_key = coalesce(ddf_accounts.leagues.my_team_key, excluded.my_team_key),
    summary = excluded.summary, raw = excluded.raw, pulled_at = excluded.pulled_at, source = 'flaim'
  returning id into v_league;
  return v_league;
end;
$$;

revoke all on function ddf_accounts.import_flaim_snapshot(text, jsonb) from public, anon, authenticated;

comment on function ddf_accounts.import_flaim_snapshot(text, jsonb) is
  'JEG-1732 admin-only: upsert one Flaim league snapshot (ddf-connected-league/0, source.kind=flaim) for a DDF user by email. Schema: docs/flaim-snapshot-schema.md.';
