# JEG-1586 group A: stale nav, connector and source_probe assertions (2026-11-09)

Nightly full suite (run 42527592077, main 09cbb1fc8) had 65 red modules. This PR is group A plus the
entry-page waits. No product or published number changes; every assertion change below is logged with its reason.

## Assertions changed (and why each was wrong, not the code)

- `tests/test_v2_nav_render.py`: the exact tab list now ignores the "Simplified site" entry and requires it exactly once.
  JEG-1263 added that nav entry on 2026-11-02; the grouped order JEG-1106 pins is unchanged. Same pattern as
  `test_waivers_render` (PR #1389, neighbours instead of a fixed index). `waivers_render` and
  `waivers_mutation_specificity` were already fixed by #1389 (not re-run to completion locally: the mutation harness outran 5 minutes; CI decides).
- `tests/test_source_probe.py::ChainConcurrencyTest`: the regex expected a literal `rebuild-chain` group. JEG-1522
  (9897dfee, 2026-11-06) deliberately renamed it to `rebuild-chain-${{ github.ref }}` so a branch proof does not hold
  main's slot. It now pins that exact per-ref group (main runs still share one) and keeps `cancel-in-progress: false`.
  Not a config regression (checked on JEG-1586, 2026-11-08).
- `tests/test_connector_inventory.py`: `#simplified-site` gets an exception, `by design`. The section is the Trade ideas
  output, rest-of-season only, drawn answer first, and computes nothing of its own; `find_trades` and
  `find_trades_league` return the same ideas, so a tool for the route would duplicate them. Lead decision 2026-11-09;
  Jeremy can reverse it by replacing the exception with a tool.
- `tests/test_entry_pages.py`: six `wait_until="networkidle"` navigations replaced by `domcontentloaded` plus the page's
  own readiness signal (`wait_for_url` for the redirects, `wait_for_selector` for `#setup-empty`, `#paste-link`,
  `input[name=team]`). Same reason as PR #1358: the engine pages are 1.3 MB and keep fetching, so network idle can
  outlast the timeout on a loaded runner. The assertions after the waits are unchanged.
