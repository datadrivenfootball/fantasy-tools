## 2026-11-22 - Injury body part in the daily Sleeper status

Contract: Jeremy, 2026-11-22: "We should denote injured players on the trade recommendations, as our trade suggestion
may not work perfectly. It is a flag, not a stopper." The trade pages' injury chip needs a short reason ("Out,
hamstring"). The daily status copy (`data/inputs/player_status.json`, `pipelines/pull_player_status.py`) already
carried Sleeper's `injury_status`; this adds Sleeper's `injury_body_part` beside it, from the same public players
pull (no new source, no new request). Display only: nothing in the identity bake, players.json, the roster universe or
any value reads it.

Refresh: the existing `player-status-history.yml` run (Supabase pg_cron, daily 13:10 UTC and Sunday 16:30 UTC) writes
the file, commits it and requests a Pages build; `build_v2_page.player_status_js` ships it as `v2/player-status.js`.
The pages hide the copy when it is undated or more than 6 days old (the Waivers rule, `TradeValueWaivers.statusFreshness`).

### Verified (check named)
- `python3.12 -m unittest tests.test_daily_player_status` (7 tests): the body part rides only with a status, is
  whitespace-trimmed and capped at 40 characters, a non-text value is dropped, and `check_snapshot` rejects a long or
  non-text body part.
- A live `pipelines/pull_player_status.py --out <scratch>` on 2026-11-22 14:48 UTC: 877 team-backed players, 166 with a
  status, 164 of them with a body part (IR 98/98, Out 35/35, Questionable 24/25, PUP 5/5, Doubtful 2/2). Not committed:
  the daily run writes the file.

### Claimed, not confirmed
- The next scheduled run (2026-11-23 13:10 UTC) publishes the field; until then the chips show the status without a
  body part.
