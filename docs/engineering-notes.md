# Engineering notes (moved from AGENTS.md, 2026-10-09)

Dated incident and design notes that used to live in `AGENTS.md`. Moved verbatim
under JEG-524 so agents load them only when a task touches these areas.
Older briefs cite `AGENTS.md:<line>` for these sections; the content is here now.

## FantasyCalc drift auto-trigger (2026-09-30)
- Standing rule (Jeremy): the project reruns the FantasyCalc pipelines when
  native doesn't match live. `pipelines/check_fantasycalc_drift.py` compares
  the live API (top-25 by value) against the snapshot's native_value; if >20%
  moved by >5%, it exits 1. With `--trigger` it refreshes the snapshot from
  the live API and runs match -> reference -> section -> reindex -> fixture
  -> monitors automatically. (Thresholds tuned 2026-09-30: FantasyCalc updates
  through the day, so 1-3% intraday moves are normal noise — the 5%/20%
  bands prevent constant refresh churn while still catching real corruption
  like the JSN defect.)
- Live-verification bypass (Jeremy 2026-10-04): when the review stage's
  `native_drift` check fails for a source with a live API (currently only
  FantasyCalc), it verifies the top-25 candidate natives against the live
  site before failing. If 80%+ match within 5%, the drift is genuine (source
  moved, not a pipeline bug) and the check passes as "live-verified". Network
  failures fail closed (no pass on unverifiable). `--no-live-verify` skips
  the check for CI/offline (drift fails hard). Sources without a live API
  keep the hard fail. Regression: 4 new tests in test_review_candidate.py.
- The 2026-09-30 JSN defect proved why: `match_source_snapshot.py` was
  dropping `native_value`, so the pipeline used the flattened `value` (50.7)
  instead of the raw FantasyCalc number (9914). The matcher and
  `build_source_reference.py` now carry `native_value` through every stage.
- Regression tests: `tests/test_fantasycalc_drift.py` (5 tests).
- Refresh (updated 2026-10-08): the scheduled FantasyCalc producer is
  `.github/workflows/fantasycalc-weekly-save.yml` (pg_cron
  `trigger-fantasycalc-weekly-save`, Tue + Fri 13:07 UTC): pulls the 12-team
  lists and saves a reindexed bake via `save_fantasycalc_references.py`.
  `fantasycalc-drift.yml` is a manual-only drift check now.
  `refresh_fantasycalc_supabase.py` (wrote raw natives into `value`, hardcoded
  Week 4, no bake_id) was deleted; see docs/watchdog.md "Producer schedules".

## As-published indexing: proportional scaling (2026-09-30)
- User directive: "there is no need for rounding like this, so figure out a logic that applies to all the ones sourced from trade value charts." The per-position quantile mapping was destroying real value differences (Jeanty 6365 vs Cook 7157 → both 41.4) and scrambling cross-position rank.
- New logic in `pipelines/reindex_comparison_section.py`: sources with `value_provenance == "published"` (FantasyCalc, USA Today, FantasyPros, CBS) use GLOBAL proportional scaling instead of per-position quantile mapping.
- Formula: `indexed = native × (anchor_total / native_total)` over shared players. This preserves exact value ratios (Cook 12.4% above Jeanty stays 12.4% above), cross-position order, and all differences. No quantile mapping, no rounding in storage.
- Fixed-pie invariant holds: sum(indexed) = anchor_total by construction.
- DDF-methodology sources (ESPN) keep the per-position quantile mapping.
- Verified: Jeanty 6365→42.36, Cook 7157→47.63 (ratio 1.1244 preserved); Taylor 70.0→51.71, Walker 57.9→42.77 (ratio 1.209 preserved).

## VORP>0 overlap calibration (2026-09-30 PM)
- Refinement to as-published proportional scaling (Jeremy): "players with vorp>0 should all add up to the same amount. Some trade charts don't go as deep into vorp>0, but they'll all have overlapping players for the first 50-150, so we can set the index on that set and then use the relative values on the remainder of the chart for the balance."
- Implementation: scale is calibrated on the VORP>0 overlap set (players with anchor_value > 0, typically 150-170 players), not all shared players. The deep tail varies in depth by source and shouldn't drive the scale.
- Formula: scale = sum(anchor_overlap) / sum(native_overlap); indexed = native * scale for ALL priced players.
- Fixed-pie target is the anchor's overlap total; the source's overlap players sum to it.
- Method name: `proportional_scaling_vorp_overlap`. Overlap slugs stored in fit metadata for test verification.

## Lineage rebuild must not run in CI without snapshots (2026-10-01)
- The 09-30 "auto-rebuild source value lineage on every deploy" step runs `build_source_value_lineage.py` in CI, where the gitignored `data/raw` snapshots are ABSENT. The builder silently fell back to TRANSFORMED combo natives and compared live raw values against them: served FantasyPros showed 0/25 live matches (live Gibbs 75.1 vs transformed 88.8) — a monitor false-red caused by the build environment, not the data.
- Fix: `require_snapshot_natives()` in the builder now raises SystemExit when any SNAPSHOT_PATHS source loads zero natives. The write happens at end-of-main, so a CI failure leaves the committed (locally built, correct) `dist/modules/source-value-lineage.json` untouched and the deploy proceeds (step is continue-on-error).
- Rule: any committed `dist/modules/*.json` that CI regenerates must be buildable from repo inputs alone, or the rebuild step must fail closed instead of writing degraded output. Same class as the import-health staleness bug.
- Regression: `tests/test_lineage_snapshot_guard.py` (4 tests: empty refuses, partial refuses, full passes, real local snapshots satisfy — the last is `skipUnless` the gitignored snapshots exist, because a test asserting their presence can never pass in CI; the first version of it failed CI validation and blocked the 3c2136bf deploy). Rebuilt locally 2026-10-01: FantasyPros 25/25, CBS 25/25, FantasyCalc 22/25 (3 genuine intraday moves), USA Today 19/25 + 6 no-live (scrape 402, recorded in live_stale_sources), ESPN N/A-by-design.
- Oddity found during the fix: `data/raw/sources/fantasycalc/week-4/snapshot.json` is force-added to git despite `.gitignore` carrying `data/raw/`; the fantasypros/usatoday snapshots are properly ignored. That's why CI loaded 196 fantasycalc natives while fp/usa loaded 0. Left as-is (removing it would change FantasyCalc lineage behavior); flagging for the next snapshot-management pass.

- Retired 2026-10-08 (chore/retire-extras): the lineage builder, its CI step and `tests/test_lineage_snapshot_guard.py` are gone (last present at `aefb8f7`). The rule above still stands for every other CI-regenerated artifact.

## CI sync must prefer the freshest health file, not the fixture (2026-10-01)
- The 30-min health cron pushes a fresh `dist/modules/source-import-health.json` with every run, but CI's `make sync` (where the gitignored `output/` runtime file is absent) unconditionally fell back to the committed fixture `data/fixtures/current/source-import-health.json` and OVERWROTE the fresh pushed copy before upload. On 2026-10-01 the served monitor read `checked_at` 08:37Z while main held 10:07Z, because the last three health pushes (4e035da, 46638ad, 28b346f) had stopped including the fixture copy.
- Fix in `pipelines/sync_dashboard_artifacts.py::import_health_source()`: candidates (runtime, checked-in dist copy, fixture) are now ranked by `checked_at` and the freshest valid payload wins; the write step skips the self-copy when the source IS the dist file. Regression: `tests/test_sync_health_freshest.py` (4 tests, incl. a simulation proving the OLD code chose the stale fixture against the broken state), wired into `make validate`'s test-unit list.
- Rule: any committed `dist/modules/*.json` that CI rewrites must resolve to the freshest valid input, never a hardcoded fallback. Both candidates must remain committed: the fixture copy is refreshed by the health runs so the fallback path never drifts by more than one cycle. Note the 30-min cron body itself never contained the fixture-copy step -- the fix makes that omission harmless.
- The fixture was also refreshed to the 10:37Z green gate (6/6 ok) in the same push.

## Watchdog: status marker before content words; repo pulls before legacy cache (2026-10-01)
- `ops/watchdog/_common.py::classify_run_line` used to match the standalone word FAILED before checking the run's status marker (`| OK |`, `SUCCESS`, `no-update`). Razzball's pull log legitimately writes detail notes like "1 rows failed PPG consistency" on an OK run (a tolerated single-row anomaly under the gate threshold), which false-tripped `failed` and then cascaded into a false "CRITICAL: artifact rewritten AFTER the failed run". Rule: status marker wins over detail-text words; genuine `| FAILED |` lines are unaffected. Regression test uses the real 2026-10-01 log line.
- Weekly-article watchdog checks (`check_weekly_article`) read the newest `ops/watchdog/pulls/<src>-<date>.json` first and fall back to the legacy goal-workspace cache. The legacy cache (`lottery/data/sources_cache/*.json`) went dead after the repo ingest pipelines replaced the old lottery pullers (Sep 21); reading it first false-alarmed STALE on CBS/USA Today while Supabase already held fresh rows. When a watchdog source false-alarms stale, check which cache path the watchdog reads before assuming the ingest is broken.
- USA Today 2026-09-29 week-3 article layout note: the QB table sits under the generic "Week N fantasy trade charts" h2 (lazy h2->table pairing); `pull_usatoday.py::_clean_title_position` infers the QB title from the 1QB/6-TD/SFLEX header signature. Also 2026-10-01: curl fetches of usatoday.com article pages now return persistent 402 while sitemap + browser render still work. FIXED same day: the 402 is header-based blocking — adding full browser `Accept`, `Accept-Language`, and `Upgrade-Insecure-Requests` headers to `ops/watchdog/_common.py::fetch` restores 200 (verified on the week-3 article). This is the shared fetch, so CBS and any other watchdog puller get the headers too. The 2026-10-01 fresh pull (238 rows, content-identical to 2026-09-30) used this path.

## cbsros wired through Supabase (2026-10-01)
- `public.cbs_ros_projections` table created (DDL: `sql/migrations/002_cbs_ros_projections.sql` — run in Supabase SQL editor; PostgREST cannot DDL). Grain: (player_key, cbs_snapshot_date). Modeled on `espn_season_projections`.
- DDL was run via the browser SQL editor; afterward PostgREST still 404'd the table (PGRST205) until `NOTIFY pgrst, 'reload schema';` was run in the SQL editor. Expect the schema-cache lag on every future DDL.
- PostgREST table-name rule: sbclient builds `/rest/v1/<table>`, so pass the BARE table name (`cbs_ros_projections`). The first save_cbsros run passed `"public.cbs_ros_projections"` and PostgREST looked for a table literally named that (error: "Could not find the table 'public.public.cbs_ros_projections'"). All working savers use bare names; SOURCE_TABLES keeps schema-qualified names only as manifest labels.
- `pipelines/save_cbsros_references.py` uploads snapshot data to the table (fail-closed identity via public.players, same ALIASES as the DDF leg). 2026-09-30: 363 rows (4 fail-closed identity exclusions: Trubisky, Brooks, Knight, Okonkwo).
- `pipelines/import_supabase_references.py`: cbsros added to DB_SOURCES/SOURCE_TABLES. `build_cbsros_snapshot()` emits the NATIVE shape (schema `trade-value-cbsros-snapshot-v1`, top-level `vintage_date`, rows with ros_*/per_game_*/gp/receptions/raw_stats) — NOT the generic comparison shape. cbsros's production chain is snapshot -> DDF leg -> section (rebuild_comparison_chain.py run_cbsros_source); the DDF leg fail-closes on a missing vintage_date, so the first DB-backed import (comparison-shaped) would have broken the chain. pos from public.players.position, team from the fixture players.json map.
- Round-trip verified 2026-10-01: Supabase table -> import -> native snapshot -> build_cbsros_ddf_leg.py (half_ppr, 12t) produces byte-identical values/ppg for all 329 players common with the old file-backed leg, plus 4 previously-unresolvable fullbacks (Juszczyk, Heyward, Beck, Burton) now resolving at 0.0 via canonical names.
- `.github/workflows/rebuild-chain.yml`: cbsros added to the import loop.
- `pipelines/verify_import_health.py`: cbsros moved from SNAPSHOT_ONLY to DB-backed with table config. Health gate GREEN 2026-10-01 (6/6).
- The force-added `data/raw/sources/cbsros/2026-09-30/snapshot.json` (commit ec4f3986) is retired: archived under `_superseded/` after the DB-backed import was verified live (health gate GREEN, DDF-leg round-trip byte-identical).

## razzball wired through Supabase: code landed, table created 2026-10-02 but EMPTY (JEG-18)
- `public.razzball_projections` was created 2026-10-02 from `sql/migrations/003_razzball_projections.sql` (Jeremy's explicit yes in the Claude session; applied with the Supabase `apply_migration` tool, followed by `NOTIFY pgrst, 'reload schema'`). Verified read-only afterwards: 21 columns, primary key plus the two indexes, RLS off like `cbs_ros_projections`, **0 rows**. No row has been written yet: the first real save has to run on the machine that has `data/raw/sources/razzball/`.
- `pipelines/save_razzball_references.py`: snapshot -> table. Per-game columns `rz_std_ppg/rz_half_ppr_ppg/rz_ppr_ppg` -> `per_game_standard/half_ppr/ppr`; every other row field verbatim in `raw_stats`; stamped from the snapshot's `vintage_date`. Upsert key `(player_key, razzball_snapshot_date)`.
- `pipelines/import_supabase_references.py`: `razzball` in `DB_SOURCES`/`SOURCE_TABLES`, removed from `HARD_EXCLUSIONS` (ecr/vegas/prediction markets stay). `build_razzball_snapshot()` rebuilds the native shape (schema `trade-value-razzball-snapshot-v1`) the DDF leg reads.
- `pipelines/verify_import_health.py`: razzball is DB-backed, judged on the dated daily rule (not week-designated). `.github/workflows/rebuild-chain.yml`: razzball added to the import loop.
- **Merge order matters:** with this merged, the import-health gate needs a Razzball snapshot from Supabase. Until the table exists and holds a vintage, the gate reports `MISSING razzball` and the 6-hourly chain goes red. Run the migration and the first real save (on the machine that has `data/raw/sources/razzball/`) BEFORE merging.
- Tested with synthetic rows only (the real snapshot lives on the owner's machine). The puller named in JEG-18 (`pipelines/pull_razzball_ros.py`) is not in this repo, so the snapshot row shape is inferred from `data/inputs/razzball_projections.csv` and from what `build_razzball_ddf_leg.py` reads.

## Worked-example tests pin the engine defaults; flags forced off go stale (2026-10-25, JEG-1057)

- `tests/fixtures/value_pipeline_worked_example.json`'s expected-starts variants are generated by `tools/worked_example_expected_starts.py` from `pipelines/value_reference.py` at its defaults. Since #867 (JEG-969, Jeremy 2026-10-23) `flex_bench_seats` is on. `promotion_model` defaults to on but has no effect: the `PROMOTION_MODEL_ENABLED` master switch is off since JEG-1142 (Jeremy, 2026-10-27), so the variants carry no promotion/demotion adjustment.
- #867 regenerated the fixture and dropped the forced-off flags from the spec-reference variant test, but `ExpectedStartsVariantTest` in `tests/test_value_pipeline_engine.py` still forced both off. That test ran in no Makefile target, so it went red unseen. While it was red, its four mutation guards passed vacuously, because the unmutated engine already failed.
- Rule: a test that compares against a regenerated fixture runs every implementation (engine, Python reference, spec reference) at the same settings as the generator. A mutation guard first asserts that the unmutated code passes. The base worked example does not depend on either flag, so its forced-off calls are harmless.
- `tests.test_value_pipeline_engine` is now in `test-core`.

## Week transition: per-source weeks and week views (2026-10-27, JEG-1175 / JEG-1177)

- Sources publish week N+1 at different times. Each source's served week is the history index's `served.<source>.week` (content matched by fingerprint, not the section label). The published fixture copy carries it as `week_state.sources.<source>.served_week` with `published_at`; the chain status carries `source_weeks`.
- The rule lives in one place per language: `ValueModel.weekState` / `defaultWeek` (value-model.js, also loaded by the edge functions) and `pipelines/week_state.py`, pinned to `tests/fixtures/week_state_vectors.json`. Default = N+1 only when more than half of a setting's DDF Value sources (eligible, not hidden) serve it; exactly half stays on N.
- A week view never mixes weeks: a source on an earlier week is left out (named in `missing_sources`); a source on a later week is priced on its own saved copy of the view's week. `curve-widget.js resolveWeekView`/`computePipeline` and `value_reference.Setting.week_view`/`state` must stay twins (value_check compare). `setWeek(w)` / `getWeekState()` on `TradeValueCurveControls` select and report the view.
- Week-history validation checks every source in the view of its own served week (`tests/test_week_history.py by_served_week`). Lag is not a failure; a served file that differs from its own saved week still is. Before this fix the page priced lagging charts against the other week's blend, and the guard failed with one constant factor across the source (0.99946 for CBS on 2026-10-27): a constant ratio means a blend/anchor difference, not a corrupted file.
- One calendar: `nfl_week.today_ny()` (America/New_York) with `set_clock()` / `DDF_NOW` for tests and replays. Never use the UTC date for a content week.

## Week 10 rollover retro: where the hours went (2026-11-12, JEG-1625)

- Week 10 went live Tue 2026-11-10 20:37 Central (Pages deployment of 676afdf18 at 02:37 UTC 11-11). Sources: FantasyPros 08:00, CBS 16:07, USA Today 17:45 Central (`public.source_probe_log.signals` date_modified / lastmod are the publish evidence).
- Largest cause: the chain's data gate was red about 39 hours on replay tests whose premises depended on the week's data (rank guard transition replay, seeded FantasyCalc lagging, view invariants), each fixed by its own PR after the data landed. FantasyPros waited 12.6 hours. A data-gate test that builds a synthetic scenario from live data is a code test in disguise (JEG-1628).
- JEG-1626 root cause (reproduced 2026-11-12 by overlaying run 43187634152's `candidate-evidence` tarball, `data/` `app/` `config/`, on a detached worktree at its head bb633f3db): the fidelity pulse held FantasyCalc red (`publisher_vs_stored`, measured on the 02:05Z save). A chain run that imported that save got the hold (identity match, JEG-799); a run that imported a later save (09:05Z) skipped it. `TestEngineKeepsOrderWhenTheDefaultFallsBack` keeps live holds, so FantasyCalc was hidden and the replay was 1 of 3 charts on the newest week, not 2 of 4. Same sha, red or green by which save was imported. Fix: replays pin their holds (`tests/_holds.without_holds` then the class's own). The previous attempt injected a hold into a locally built dist and did not reproduce; replay the run's own inputs instead.
- JEG-1628 replay proof found one more week premise left in the gate: `TestEngineKeepsOrderEverySetting.test_native_rank_is_the_publishers` compared FantasyCalc's page ranks with its served week, but on a Tuesday when FantasyCalc alone has moved the default view is the previous week and the page ranks it on its saved previous week (JEG-1606). On chain run 42779961289's inputs it failed; it now reads the publisher order for the week the page read the chart in.
- JEG-1628 (Jeremy, 2026-11-12): synthetic replays moved out of `data-gate` to test-core only; the list and the rule are in `docs/week-held-runbook.md` and `tests/test_chain_data_gate.py` (`REPLAYS`).
- Detection: the trade-chart probe runs every 3 hours (`35 */3 * * 1-4`), so CBS waited 2 h 28 min (JEG-1627).
- Publish conflict: a finished Week 10 build was discarded because the Fidelity pulse bot committed `dist/modules/fidelity-pulse.json` during the run (cost 42 min, JEG-1522).
- Read a Pages run by its `deploy` job, not its conclusion: under decision A an automated data commit deploys with red test-core shards, so `gh run list` shows "failure" for runs that published.
- Decision B pg_cron jobs (`rebuild-chain-weekly-*`, jobids 51/52) are applied and fired on 11-11. `net._http_response` keeps rows only hours, so dispatch HTTP status is gone by the next day; use GitHub run lists as the record.
- Floor with today's runtimes: probe interval + chain (about 40 min) + Pages (about 35 min). Even with a 20-minute probe that is about 1.5 hours from publish to live.
- Tuesday pre-flight: `python3 pipelines/rollover_preflight.py` (runbooks/weekly-refresh.md step 0).
- Local render tests on this Mac need the repo venv (Python 3.12; the system 3.9 cannot parse Supabase offset timestamps) and `CHROMIUM_PATH` set to the cached chromium_headless_shell-1208 (risk register GAP-PLAYWRIGHT-BROWSER-MISMATCH).

## K and DEF slots: roster spots, not values (2026-11-13, JEG-1632)

- The engine's roster shape carries `K` and `DST` (curve-widget.js, 0-3, default 1 and 1). Only roster-space rules read them: `v2/waivers.js` `rosterSizeOf` (open spots = QB..SUPERFLEX + BENCH + K + DST less players held) and `isRequiredSpecial` (a required kicker or defense is not a drop), and v2 league problems. The value pipeline never sees them: `curve-widget.js pipelineSetting()` passes QB/RB/WR/TE slots and `bench_per_team = BENCH`, and `value-model.js` / `value_reference.py` give all teams x Bench seats to skill players (default-roster-001). `roster_convention.py/.js bench_seats` does give DEF D'Hondt seats, but no live value path calls it.
- The JEG-1539 swap dropped the K/DEF steppers; JEG-1632 restored them on settings.html. Link format: `settings.kdef: [k, def]` in the JSON body, written only when not [1, 1] (absent = 1 and 1), so old links and 1/1 leagues keep their exact token. `DDF.link.kdefSlots(settings)` -> `{K, DST}` is the one mapping; every adapter (ddf-league.js toEngine, ddf-engine.js chat league, connect-entry.js, legacy-routes.js, team.html) uses it. Sleeper imports `K` and `DEF` roster positions.
- A whole league's settings (a link) with no kdef means 1 K and 1 DEF, so a link league resets K/DST; a partial engine apply without K/DST leaves them alone.

## Build a Trade must read the league and the waiver list the workspace pages read (2026-11-13, JEG-1633)

- Symptom (Jeremy, live, phone): "Evaluate pickup" on a Waivers Best add card opened Build a Trade in Add from waivers + My league showing "No rosters entered yet" and the "Add your roster" lock card.
- Cause 1: confirming League settings (site.js `confirmSettings`) on a pasted or saved league stores `ddf:league` = {settings} with no teams and `ddf:link` = {source:'manual'}, so `DDF.link.current()` returns a teamless state. ddf-league.js `build()` skips a link with no teams (or a manual one with no players); `build-trade.js readLeague` took it as the league. It now applies the same rule and only falls back to the teamless link when no other league exists.
- Cause 2: Build a Trade's available players came only from its own `ddf:waivers` store, a chat link's list or the old v2 `ddf.v2.waiverCandidates`. It now falls back to the list Waivers and Recommendations judge pickups on (`ddf:available` names, else `DDF.league.current().waivers`), and a saved list that lacks the link's `?add=` is skipped.
- Rule: any page that reads the league or the available players reads them through ddf-league.js (or mirrors its rules exactly). Guard: `tests/test_build_waiver_handoff.py` (clicks Evaluate pickup from both pages, with and without confirmed settings, 1440 and 375).

## Natural fit and the Why percent read one number (2026-11-14, JEG-1639)

The Natural fit test and the Why text's "Theirs -3.2%, clearly worse" used to be two measures: tradeFit allowed their
loss up to the noise floor in points (often wider than 3% of a roster), while the Why text bands the percent of roster
worth. The percent (`rosterChangePct`, its bands and MIN_BASE) now lives in `app/v2/finder.js`, because the connector and
pages without `ddf-opportunity.js` (Partners, Values) evaluate finder.js alone; `rosterImprovementPct` is a wrapper that
adds the wording. Do not re-derive the percent elsewhere: call one of the two. Natural counts moved by under 4% on the
seeded and two real league rosters (PR for JEG-1639).

