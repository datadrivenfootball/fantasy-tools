# Flaky or real? A runbook for red tests (JEG-1546, 2026-11-08)

Read `README.md` and `registry.json` in this folder first. A registry entry attributes a red; it never excuses one.

## 1. Get the whole log, not a truncated one
- `gh run view --job N --log` can cut a long job log off partway. On the nightly it stopped at about 12 minutes of
  a 2-hour job and made the run look hung (JEG-1547). Fetch the complete log with
  `gh api --allow-escape-sequences repos/datadrivenfootball/fantasy-tools/actions/jobs/N/logs`.
- A `make` recipe stops at its first red module, so the modules after it never ran. `run_suite.py` targets keep
  going and print `run_suite: failed:` for each red one. The render sweep runs through run_suite since JEG-1546.

## 2. Classify in this order
1. **Stale harness after a page move.** The traceback names a missing element or a patch anchor, or a
   `wait_for_function` times out on a global (`TradeValueV2`, `TradeValueCurveControls`) at a URL that moved.
   Example: since JEG-1539, `dist/v2/index.html` is a redirect stub. The v2 shell is `build/v2/index.html` and
   is served at `/v2-app.html` (`tests/_dist_server.py`: `V2_SHELL_PAGE`, `V2_URL`). Any harness that copies
   `dist/` and serves `/v2/` loads the stub and times out. Fix the harness, not the assertion.
2. **Stale oracle after an engine change.** The page and the test oracle read two different engine outputs that
   used to agree. Example: since JEG-1335, a source's estimates are the union over allocations (inspection),
   while a row's estimated label is the heaviest allocation's. Find the change with `git log -S` and the date the
   red started. Repoint the oracle at what the page is documented to show, keep a check that ties the two outputs
   together, and log it in docs/claude-log.
3. **Product conflict.** Two approved changes contradict each other. Example: the JEG-890 Team value summary
   pushed results below the fold, breaking JEG-1237. File a ticket with options for Jeremy. Tolerate exactly that
   one message, and make the test go red once it is fixed. Never skip the whole test.
4. **Data drift.** A fixture or committed artifact no longer matches today's synced data: a byte-for-byte
   rebuild check, a count threshold, a week number. Regenerate it only when the generator is the source of truth.
   If the number itself changed (a published value, a week), it is Jeremy's call: file a ticket.
5. **Environment.** The red needs a missing credential, the network, a browser binary or a Python version (the
   system Python 3.9 rejects `+00` ISO timestamps; use the 3.12 shim). Register it as `local` in
   registry.json, never as CI.
6. **Flake.** It passes on an immediate rerun of the same SHA, alone, and the failure is a timeout or a
   timing-sensitive measurement. Rerun it once alone before you call it a flake. If it fails twice in a row, it is
   not a flake.

## 3. Rerun discipline
- Rerun only the failing module: `python3 -m unittest tests.<module>`, with PATH on the 3.12 shim and
  `CHROMIUM_PATH` set. Do not rerun a whole shard to chase one red.
- On a shared Mac, run render modules one at a time per worktree. Parallel runs in one worktree race in
  `_render_env.ensure_built()`, which removes `app/trade-value-chart/assets/history` (a local-only
  `FileNotFoundError` in setUpModule).
- Check free disk space first. Each render harness copies `dist/` (35 MB) to a temp dir, and a full disk fails
  everything with ENOSPC.

## 4. Known flakes and look-alikes (keep this list current)
| Test | Symptom | Status |
| --- | --- | --- |
| `tests.test_values_zero_override` | `Page.goto` timeout on `networkidle` | Fixed: waits for readiness (61a3da59, JEG-1535) |
| `tests.test_entry_pages` | `networkidle` waits (6 sites) can outlast the timeout on a loaded runner | Open: switch to `domcontentloaded` plus readiness |
| 44 px tap-target checks (`a.v2-srclink` at 43.0px, fieldnotes targets) | sub-pixel heights under 44 at some widths | Real by the test's rule, not a flake: check the CSS |
| `tests.test_v2_chart_fit_render` | 60 s `wait_for_function` timeout | Not a flake: stale `/v2/` harness, fixed in JEG-1546 |
| `tests.test_team_opportunity_render.test_guard_fails_on_shifted_threshold`, `tests.test_short_chart_waiver.test_chart_never_short_is_unchanged` | mutant not caught / `n_imputed` 1 != 0 after a data bake | Data drift in the test premise, fixed in JEG-1609 (mutant and chart choice derived from the synced data) |
