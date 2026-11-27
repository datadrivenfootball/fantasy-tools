# Draft tool (JEG-1667)

Live auction tool for season-long redraft leagues (snake in Phase 2). Brief:
the private Claude doc linked on JEG-1667. Hold (Jeremy, 2026-11-16): nothing
merges or deploys before Jeremy reviews it. Last updated 2026-11-27 (Phase 0).

| Doc | What it is |
| --- | --- |
| [engine.md](engine.md) | Price engine: ours, market, platform; inflation, max bid, walk-away, push floor (definition and argument); the hand-checked worked example |
| [data-sources.md](data-sources.md) | The daily pull (Supabase, `draft_` objects), every source and when it publishes, flags on terms and access |
| [backtest.md](backtest.md) | Price error by position against two real 2026 auctions |
| [research-nominations-opponents.md](research-nominations-opponents.md) | JEG-1668: opponent model and nomination plays, options A/B/C |
| [yahoo-app-request.md](yahoo-app-request.md) | Draft Yahoo developer app and license request for Jeremy to submit |
