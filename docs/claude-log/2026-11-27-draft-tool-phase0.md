## 2026-11-27 - Draft tool Phase 0 (part of JEG-1667; research JEG-1668)

Contract: Phase 0 of the draft tool, engine, data and research only, no UI.
Price engine on the existing value build, daily pull of recurring data,
backtest against real auctions, hand-checked worked example, nomination and
opponent research, Yahoo request draft. Hold (Jeremy, 2026-11-16): draft PR
only, nothing merges or deploys.

### Verified (check named)
- Worked example matches to the dollar: inflation, max bids, walk-away, push
  floor, rival-cap variant (`tests/test_draft_engine.py::WorkedExample`).
- The test discriminates: three engine mutations each fail it
  (`GuardsCatchMutations`).
- Ours goes through `ValueModel.runValuePipeline` in expected-starts mode, and
  prices spend exactly the budget (`FullLeagueBuild`).
- Pull parsers keep the stated season (2026) and fail closed on another
  season, format, ranking type or a short table (`tests/test_draft_pull_parse.py`).
- No live page, app file or pipeline references the engine (`NotLive`).
- Daily pull ran once locally, 2026-11-27: FantasyPros ECR 2,107 rows (source
  last updated 2026-09-10), ESPN 1,200 rows; file carries pull_date
  (`node tools/draft_pull.mjs --out <scratch>`).
- Backtest produced (`node tools/draft_backtest.mjs ...`): all-player MAE ours
  $4.9 / market $4.3 / platform $3.7 in the 12-team ESPN keeper auction;
  ours $5.4 / market $5.3 shape-only vs ESPN 2026 average auction values.
- FantasyPros robots.txt and Terms of Use read 2026-11-27 (quoted in
  `docs/draft-tool/data-sources.md`).

### Claimed, not confirmed
- The edge function `draft-pull` works under Deno in Supabase: not deployed
  (needs Jeremy's yes); only the shared parsers and the Node runner ran.
- The two `draft_` migrations apply cleanly: not applied (needs Jeremy's yes).
- ESPN's published 2026 auction values were the same at draft time as on
  2026-11-27.
- Push floor rule A is the right definition: argued in `engine.md`, for
  Jeremy and the Opus math review.
