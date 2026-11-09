# JEG-1586 group G: article_discovery and endpoint_parity harnesses (2026-11-09)

No product or published-number change. Both were stale harnesses, not code defects.

- `test_article_discovery.WorkflowUrlInputTest`: since JEG-1458 (#1257) `trade-chart-ingest.yml` reads the week from the
  step env (`EVENT_WEEK`) instead of expanding the input into the script, so the harness's rendered script no longer saw
  it and `--week 5` was dropped. The harness now passes `EVENT_WEEK`. The assertion (`--week 5` before `--url`) is
  unchanged. The workflow was checked: `args+=(--week "$EVENT_WEEK")` is still there.
- `test_endpoint_parity.value_context_cases`: the page overrides dict had integer player keys; Playwright 1.58 rejects
  non-string keys in `Page.evaluate` arguments (older versions coerced them). JavaScript object keys are strings, so the
  page sees the same overrides. No assertion changed.

Checked after the change: `test_article_discovery` (25) and `test_endpoint_parity` (6) pass locally. `test_mcp_week`
(group D, node uncaught exception in the nightly) passed locally on main with no change, so it needs the nightly log
before anything can be fixed.
