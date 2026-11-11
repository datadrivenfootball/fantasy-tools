# Week held: runbook (JEG-1512)

A **week-held** alert means Supabase has a newer content week for one or more
sources than the site serves, and the rebuild chain has not published it. The
alert is a GitHub issue labelled `week-held` (GitHub emails the owner) and an
Urgent Linear sub-issue of JEG-1512 titled `Week N is held: the site still shows
week M [week-held:<season>:wN]`, labelled owner:claude.

Why it exists: Week 9, 2026. Every source had Week 9 in Supabase by
2026-11-04 00:38Z; the chain failed every run from 2026-11-01 to 2026-11-05
17:54Z (a week-history clock bug, JEG-1479, then the JEG-1511 waiver-band
tests), and the site served Week 8 for about 41 hours after Week 9 was complete.
The JEG-1194 `chain-stuck` issue never opened (it read the history index that
`make sync` had just rewritten from the unpublished candidate), and the 12-hour
generic ops-alert sat among about 20 fidelity alerts. Jeremy, 2026-11-05: "You
can not let data go late ever again."

## Where it fires

| Path | When | File |
|---|---|---|
| Chain | end of every main `rebuild-chain.yml` run that leaves a newer week unpublished (no wait) | `pipelines/week_held_alert.py --mode chain` |
| Tripwire | hourly at :50 (`source-lateness.yml`, its own schedule) when the committed chain status showing the hold is 2 h old: the chain stopped running or stopped committing its status | `--mode tripwire` |
| Drill | `source-lateness.yml` dispatched with `week_held_drill=true`: opens a `[drill]` issue and Linear sub-issue, then closes and archives both | `--mode drill` |

A run that succeeds but does not push (push failed, release guard paused it,
conflict handoff) compares with its checkout commit, so it alerts too; a
handoff's next run normally publishes and closes the GitHub issue. If the
GitHub or Linear call fails, the step prints an `::error` annotation naming
which one was NOT DELIVERED, on every run until it works.

Not week-held (other alerts own these): a source whose own publisher is late
(`source-late`, docs/source-lateness.md); a source held for its own fidelity
problem (the fidelity `ops-alert` issues); a chain red with no new week
(`chain-stuck` after 6 h, JEG-1194).

## Who and how fast

Owner: the Claude lane (coordinator). Response: same hour in waking hours
(America/Chicago). Jeremy rules on any test bar or value-model question.

## What to do

1. **Acknowledge** on the Linear sub-issue (comment: who is on it, start time),
   move it to In Progress.
2. **Diagnose** from the issue body: the failing step and tests are named. Open
   the run link. Classify:
   - *Infra / clock / import bug* (e.g. JEG-1479 history capture): fix it on a
     branch, prove with a branch dispatch of `rebuild-chain.yml`, merge.
   - *Data-sensitive test on new data* (e.g. JEG-1511 waiver band): reproduce
     locally on the new bake, then bring Jeremy the ruling as options
     (narrow exemption, move the test out of the blocking gate, or hold). Do not
     relax a bar without his ruling, quoted with the date.
   - *Code regression on main* (a merge broke a test the chain runs): revert or
     fix forward; main CI should have caught it, so link the PR.
   - *Per-source validation hold on a published run*: the rest of the week is
     live; fix that source's cause.
3. **Publish**: the next chain run publishes. Confirm `output/comparison-chain-status.json`
   (`success: true`), `data/history/index.json` served weeks, and the live site
   (`verify_live.py`). The GitHub issue closes itself; the Linear sub-issue gets a
   comment and is closed by a person after the live check.
4. **Record** the timeline and cause in a `docs/claude-log/` entry and on JEG-1485.

## What the chain checks before publishing (JEG-1485 decision A)

Jeremy, 2026-11-08: the chain checks **data** only before publishing; code
tests keep gating PRs and run nightly; a held week still alerts within 2 hours.

- The rebuild chain runs `make validate-data` = `validate-base` + `data-gate`,
  before it commits anything. It fails closed: if any data check fails, only the
  status is published and the week-held alert fires.
- `pages.yml` needs its build job (`validate-base` + `data-gate`) for every
  deploy. An automated data commit (author `github-actions[bot]`, message
  `Automated ...`, from the chain and the other data writers, including the
  status-only "chain failed" commits) deploys on that alone. Every other commit,
  and a dispatched deploy, also needs the test-core matrix. Data is never held
  by a code test. Known limit: a data deploy ships the tip of main, so code
  merged while its tests were red reaches the site with the next data commit.
  main's ruleset requires a PR but no status checks, so make the preview checks
  required to close this (Jeremy's call).
- `preview.yml` (PRs) runs `validate-base`, `data-gate` and all of test-core.
  That is the code gate.

**A data check** asserts something about this build's own artifacts (the fixture,
players.json, the history index, dist/), so a failure means the numbers or the
site would be wrong. It covers:

- **Engine vs reference on the data and the build itself** (`validate-base`):
  `reference`, `sync` (its history no-relabel guard stops the sync on a bad week
  file), `guard-harness` (the ESPN anchor guard), `value-check-compare --strict`
  (engine vs Python reference on every value) and `test-integration`.
- **Shape and published-number protection**: `test_static_export`,
  `test_seeded_hold_build`, `test_rank_guard` (published order),
  `test_view_invariants` (equal pies and same-scale views), `test_kdst_removed`,
  `test_player_scenario_matrix` (starter, bench and waiver boundaries ordered on
  current players).
- **Source coverage and identity joins**: `test_comparison_source_integrity`,
  `test_cbsros_bake_identity`, `test_suffix_identity`, `test_player_aliases`.
- **Bake-to-section consistency**: `test_games_remaining`, `test_ppg_tie_parity`,
  `test_bake_on_change`, `test_razzball_refresh`, `test_razzball_one_save`.
- **Week label, freshness and history**: `test_lineup_content_week_advance`,
  `test_week_history` (the engine-side check of the prior-week values and the
  week-over-week change the site shows).
- **The built site**: `test_published_surfaces`, `test_verify_live`,
  `test_page_load_no_404`, `test_site_noindex`.

**A code test** checks the behaviour of code, on synthetic inputs or with
current data used only as sample input. These stay in test-core and gate PRs:
page and render parity (`test_team_opportunity_render`, `test_learn_engine_parity`,
`test_*_engine_parity`, phone layouts), worked examples (`test_value_pipeline_engine`,
`test_spec_reference_value_pipeline`), and property or perturbation tests that
search the live data for a scenario (`test_fractional_seats_stability`; the
waiver-band perturbation tests are already non-blocking). Left out on purpose
(reviewed 2026-11-08): `test_superflex` and `test_two_qb_direction` read
published numbers in a browser but have often failed on new data for code
reasons; `test_market_bench` checks config, not build output; and
`test_spec_reference_value_pipeline` is a worked example. Engine-vs-reference
agreement on the data is not lost when these move out of the gate: it is
`value-check-compare --strict`.

**Synthetic replays inside data tests must not inherit live holds**
(JEG-1606, 2026-11-09). The week-transition replay
(`test_week_history.transition_overrides`, used by `test_rank_guard`,
`test_week_history` and `test_bench_budget_cut_render`) clears every
`validationHold`/`promotionHold` before it builds the transition. A red hold
hides a chart from DDF Value, so with three projection holds only 2 of 4
counted charts served the newest week, the default view fell back a week and
the replay failed on its own premise (chain runs 42704839004, 42720406111).
The same fallen-back view also showed a real page defect: charts already on
the newest week are priced on their saved previous week, but
`getNativeRanks` ranked them on the served week (a newer rank next to an older
value). JEG-1606 fixes `nativeRanksFor`, and
`TestEngineKeepsOrderWhenTheDefaultFallsBack` keeps that view covered. If a
replay sentinel fails, check its premise (`week`, `on_newest`, `total` in the
assertion) against the live holds in `dist/modules/fidelity-pulse.json`. Also
check whether the failing state is one a reader can reach.
The replay's newest week is the week most non-lagging charts serve, not the
max (JEG-1618, 2026-11-10). On Tuesday morning CBS ROS alone was on Week 10,
the max made the replay "lag" CBS and USA Today to their real week, and every
sentinel failed (chain runs 42765640563, 42769574724). Charts off the replay
week are hidden with a red hold whose reason starts "transition replay:".

Rules for the list: every `data-gate` line is also in test-core, and
`tests/test_chain_data_gate.py` pins the exact list (change the test, this
section and the Makefile together). Move a test into
`data-gate` only if it reads the build's artifacts and its failure means
published numbers or the site would be wrong. If a code test is red on main,
data commits keep deploying and they ship the code at the tip of main, so fix
main the same day.

## Forced weekly chain runs (JEG-1485 decision B)

pg_cron jobs `rebuild-chain-weekly-tue-evening` (`0 2 * * 3` UTC = Tue 20:00 CST) and
`rebuild-chain-weekly-wed-morning` (`0 12 * * 3` UTC = Wed 06:00 CST) dispatch
rebuild-chain.yml with source `pg_cron-weekly-tue-2000ct` / `pg_cron-weekly-wed-0600ct`.
They were applied 2026-11-08; the record, verify and rollback are in
`supabase/migrations/rebuild_chain_weekly_forced_20261108.sql`.

- **First-fire check (Tue 2026-11-10 20:00 CST = 11-11 02:00Z):**
  `cron.job_run_details` shows status `succeeded` for `rebuild-chain-weekly-tue-evening`;
  `monitoring.dispatch_log` has a rebuild-chain.yml dispatch at ~02:00Z; and
  `gh run list -R datadrivenfootball/fantasy-tools -w rebuild-chain.yml --event workflow_dispatch --limit 5`
  shows a run created within a minute or two of 02:00Z. Match it by time: the `source`
  input (`pg_cron-weekly-tue-2000ct`) is not shown in the run list, its log, or dispatch_log
  (adding a `run-name` to rebuild-chain.yml would make it visible; follow-up). A
  vintage-check dispatch at the same minute looks the same; either one counts as the
  forced run. Repeat for the Wednesday 12:00Z job.
- **Re-time for CDT:** pg_cron runs in UTC. From 2027-03-14 (CDT, UTC-5) these fire at
  21:00 / 07:00 local. Before Week 1 of 2027, re-schedule to `0 1 * * 3` and `0 11 * * 3`
  (cron.schedule upserts by name), or back again in November.
- An overlap with the hourly vintage check or the 05:45 CST safety run adds at most one
  queued run; an unchanged run commits nothing.

## Testing the alert

Dispatch `Source lateness check` with `week_held_drill=true` once (any branch),
not within a few minutes of :50 (the hourly run cancels it and could leave the
`[drill]` issue open; close it by hand if so).
The run log shows `github: opened #N`, `linear: opened and archived drill JEG-…`
and `github: closed #N`. Unit tests: `python3 -m unittest tests.test_week_held_alert`.
