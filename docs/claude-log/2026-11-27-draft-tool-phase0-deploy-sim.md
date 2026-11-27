## 2026-11-27 - Draft tool Phase 0: daily pull live, push floor rework, simulator (part of JEG-1667)

Contract: Jeremy's answers of 2026-11-27, relayed by the coordinator and
confirmed by Jeremy in this session for the deploy: deploy the daily pull,
public read with attribution, no Vegas scraping, rethink the push floor, and
test it in a seeded auction simulator. Later the same day Jeremy said to
ignore licensing and attribution for now and just build.

### Verified (check named)
- Supabase (project iskiybsimubiujwuchsl): migrations `draft_tool_phase0_20261127`
  and `draft_pull_schedule_20261127` applied; `draft-pull` deployed (v1,
  verify_jwt on); cron `draft-pull-daily` active at 11:15 UTC. Manual run
  2026-11-27 17:22 UTC: fantasypros_ecr ok 2,096 rows, espn ok 1,200 rows,
  `draft_pulls` pull_date 2026-11-27, `draft_market_latest` returns both
  (SQL count check). Second call skipped both; public key read 200, write 401
  (curl). The mcp function and existing tables were not touched.
- Push floor candidates, opponent model, personal inflation and nomination
  plays: `tests/test_draft_strategy.py` (12 tests); simulator determinism,
  roster fill and no above-value buys under the recommended policy.
- 300-draft simulation (`node tools/draft_sim.mjs ... --drafts 300 --seed 1`):
  starter value 159.6 (walk-away, room inflation) -> 229.1 (personal
  inflation) -> 233.5 (bid to roster value); see `docs/draft-tool/engine.md`.
- `make validate` exit 0 (3.12 venv, Chrome for render tests), run on the
  first head; generated `make sync` output restored, not committed.

### Claimed, not confirmed
- The first scheduled run (2026-11-28 11:15 UTC) succeeds like the manual run.
- Simulation bots resemble real rooms (no tendencies, simple nominations).
- Licensed odds-feed coverage of season player props: from vendor pages and
  third-party reviews, not samples.
