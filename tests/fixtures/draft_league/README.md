# draft_league fixture provenance

## Sleeper fixtures (real API data, sanitized)

**sleeper_league.json**, **sleeper_users.json**, **sleeper_drafts.json**

Source: real Sleeper API responses from public league `1312112439055101952`
("The Boys", 2026 season, 8-team auction/linear draft, full PPR), captured
2026-11-28 via plain GET to `api.sleeper.app/v1`.

Sanitization applied:
- `league_id` replaced with fake ID `799999999999999999`
- All `user_id` values replaced with `u1`..`u8`
- All `display_name` values replaced with `user1`..`user8`
- All `team_name` metadata replaced with `Team N` or empty (alternating)
- `league_id` in users replaced with fake ID
- `name` replaced with `Draft League Test`
- Extraneous fields (avatar, shard, company_id, metadata mascots, etc.) dropped
- Draft `draft_id`, `league_id`, creator IDs replaced with fakes
- Draft `draft_order` and other per-user IDs removed
- Scoring settings trimmed to engine-relevant keys only

The league is a dynasty/keeper PPR auction (8 teams, `settings.type: 2`,
draft `type: "linear"`). No `budget` key appeared in the draft settings,
confirming Sleeper defaults to 200.

## ESPN fixture (reconstructed)

**espn_league.json**

Reconstructed: no real public ESPN league was accessible during capture.
All tested league IDs (including several known IDs) returned 401 or 404 from
`lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/<id>?view=mSettings&view=mTeam`.

Structure matches the documented ESPN Fantasy API v3 format:
- `settings.draftSettings.auctionBudget` for the auction budget
- `settings.rosterSettings.lineupSlotCounts` keyed by ESPN slot ID
- `settings.scoringSettings.scoringItems` array of `{statId, isReversal, points}`
- `teams` array with `location`, `nickname`, `abbrev`

ESPN stat ID mapping used (industry standard, documented across ESPN API references):
- 3 = passing yards, 4 = passing TDs, 20 = INTs thrown
- 24 = rushing yards, 25 = rushing TDs
- 42 = receptions, 53 = receiving yards, 43 = receiving TDs
- 72 = fumbles lost

ESPN lineup slot IDs:
- 0=QB, 2=RB, 4=WR, 6=TE, 7=OP(SuperFlex), 16=D/ST, 17=K, 20=BN, 23=FLEX(W/R/T)

## Settings page paste fixtures (all reconstructed)

**espn_settings_paste-reconstructed.txt**
**yahoo_settings_paste-reconstructed.txt**
**sleeper_settings_paste-reconstructed.txt**

These are faithful reconstructions of what a user gets from Select All + Copy
on each platform's league settings page. No login-wall-protected pages were
accessed during capture. The lead should capture real settings pages for
these platforms to replace these reconstructions with verified text.

Format notes based on observed platform layouts:
- ESPN: tab-separated label/value pairs under section headers
- Yahoo: label on one line, value on the next; roster positions as comma list
- Sleeper: similar pattern to Yahoo
