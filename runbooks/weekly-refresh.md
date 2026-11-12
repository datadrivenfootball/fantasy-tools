# Weekly refresh

The site is static. Scheduled jobs bake JSON into the repo and GitHub Pages serves it. Supabase pg_cron dispatches the producer workflows (producer table: `docs/watchdog.md`; cron list: `docs/architecture-current.md`). Nothing needs a hand dispatch in a normal week. This page is the check that it happened.

## 0. Tuesday pre-flight (before the articles land)

Run every Tuesday around 14:00 Central, before CBS and USA Today publish (Week 10: FantasyPros 08:00, CBS 16:07, USA Today 17:45 Central):

```
python3 pipelines/rollover_preflight.py
```

Read-only. It checks that the newest finished Pages deploy on main deployed, that the chain on main is green and not flapping (more than two failed runs in 12 hours is a FAIL), that the live site and the connector (get-values) serve the same week with no source more than a week behind, and prints the pg_cron SQL to run with Supabase `execute_sql` (expect 8 active rows, including `rebuild-chain-weekly-tue-evening` and `rebuild-chain-weekly-wed-morning`). Any FAIL is fixed that afternoon: a red chain on Tuesday holds every source that publishes that day (Week 10 retro, 2026-11-12, `docs/engineering-notes.md`).

## 1. What week is it

```
python3 pipelines/nfl_week.py
```

Prints the content week the pipeline builds for: an integer (2026-10-12 printed `5`). The calendar lives in `pipelines/nfl_week.py`; bump `SEASON`, `CONTENT_WEEK_1_START` and `GAME_WEEK_1_START` there each August.

## 2. Did every source land

```
make import-health NFL_WEEK=<week>
```

Verifies the seven import sources against Supabase (needs Supabase credentials; in CI the chain runs it). Expected: every source `ok` for the week. A `stale` source means its producer has not written this week; go to step 4.

## 3. Did the chain publish

```
gh run list --workflow=rebuild-chain.yml --limit 5
python3 -c "import json;d=json.load(open('dist/modules/comparison-chain-status.json'));print(d['run_at'],d['nfl_week'],d['success'],d['outcome'],d.get('held'))"
```

Expected: the newest run is `completed success` and under about 6 hours old (pg_cron `rebuild-chain-live` runs at :17 every 6 hours). In the status file `success` is `True` and `outcome` is `published` or `published_with_holds`. On 2026-10-12 the committed status was `True`, `published_with_holds`, with FantasyCalc, CBS rest of season and Razzball held; see [source-held.md](source-held.md).

## 4. A producer missed

Re-dispatch only the missed producer (production writes):

```
gh workflow run espn-supabase-sync.yml
gh workflow run razzball-supabase-sync.yml -f mode=write
gh workflow run cbsros-supabase-sync.yml
gh workflow run trade-chart-ingest.yml -f mode=write -f source=usatoday
gh workflow run fantasycalc-weekly-save.yml -f mode=write
```

A dry run is the same dispatch without the write input (or a push to a `*/dry-*` branch). Then repeat step 2 and dispatch the chain ([run-the-chain.md](run-the-chain.md)).

## 5. Verify live

[verify-live.md](verify-live.md).

## Known noise

- USA Today answers GitHub runners with 402. The Supabase relay is the primary fallback (`docs/watchdog.md`, "USA Today fetch chain"). `SOURCE_BLOCKED` is a warning and the last good week stays published.
- CBS rest of season publishes Wednesdays; a retry runs at 17:00 UTC if there is no row that day.


## Validation-bound exemption decisions

For a designed mechanism that breaches a global validation bound, follow the
[exemption decision policy](../docs/exemption-decision-policy.md). Record the
authorized signature and decision-ticket link in the week-transition runbook's
[exemption decision records](../docs/week-transition-runbook.md#exemption-decision-records),
using its template. An unchanged signature needs an incident record on the
ticket; a new or expanded signature needs the policy's decision owner.
Independent exact-head review and green CI remain mandatory before merge.
