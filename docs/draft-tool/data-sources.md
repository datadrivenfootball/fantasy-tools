# Draft tool data sources and the daily pull (Phase 0, JEG-1667)

Jeremy, 2026-11-27: "I want anything that is recurring data for all leagues
pulled in supabase. There is math to be applied to get to ours, market,
platform, and anything that varies by league settings should ideally be done
client side."

All test data is the **2026 season** and is labeled "2026 data". Every row
carries the season the source itself states; a page for another season fails
closed (`tests/test_draft_pull_parse.py`).

## The daily pull

| Piece | File | State |
| --- | --- | --- |
| Parsers (shared Node/Deno) | `supabase/functions/draft-pull/parse.js` | Tested |
| Edge function | `supabase/functions/draft-pull/index.ts` | Written, **not deployed** |
| Tables and view | `supabase/migrations/draft_tool_phase0_20261127.sql` (`draft_pulls`, `draft_market_values`, `draft_market_latest`) | Written, **not applied** |
| Daily schedule | `supabase/migrations/draft_pull_schedule_20261127.sql` (pg_cron 11:15 UTC) | Written, **not applied** |
| Local runner | `tools/draft_pull.mjs` | Ran once 2026-11-27 |

The function pulls each source at most once per UTC day, so a repeat call
costs nothing upstream and the public key is enough to trigger it. Every
attempt, ok or failed, writes a `draft_pulls` row with its pull date and the
source's own "last updated" time; a page reads the latest ok pull and shows
a stale warning when it is old. RLS is on with no policies: only the service
role reads or writes until Jeremy decides what the page may show.

Local run, 2026-11-27: FantasyPros ECR ok, 2,107 rows (Standard 554, Half PPR
985, PPR 568; source last updated 2026-09-10); ESPN ok, 1,200 rows (600
players x Standard and PPR).

## Sources

| Source | What | Access | When it publishes | Use |
| --- | --- | --- | --- | --- |
| FantasyPros draft ECR | Consensus rank, position rank, tier, rank spread, bye; Std, Half, PPR | Public HTML, full list embedded (`/nfl/rankings/*-cheatsheets.php`); robots.txt allows it, crawl delay 5 s | Spring through Week 1, daily; 2026 last update 2026-09-10, then frozen | Market rank; pulled daily |
| FantasyPros season projections | Stat lines per player | Logged-out page shows only the top 10 per position; the full table needs a signed-in account or the paid API (`/api-data/`). The 2026 rows in `public.fp_season_projections` came from Jeremy's signed-in export | June to Week 1; 2026 consensus last updated 2026-09-08 | Projection input to ours. **Not pulled automatically** (see flags) |
| FantasyPros ADP | Consensus of 5 sites, history to 2015 | Logged-out page shows only the top rows | Spring to Week 1 | Not used yet |
| FantasyPros auction values | Calculator only (computed in the browser from projections) | No public list | n/a | Not available |
| ESPN | Published auction values (Std, PPR), average auction value paid in ESPN auctions, ADP, projections | Public read API (the call ESPN's own draft room makes) | Values appear in summer; AAV and ADP move daily through drafts | Platform price (ESPN); AAV as market dollars and as the dollar curve for FP ranks; pulled daily |
| Vegas season props | Season over/unders: pass/rush/receiving yards and TDs, receptions (DraftKings Player Futures, FanDuel Regular Season) | Unofficial book JSON; the archived collector (`archive/2026-10-07/.../collectors/season_totals.py`) needed Chrome TLS impersonation to pass Akamai | Posted after the NFL schedule (May), filling in through August; 2026 snapshot in `public.vegas_season_totals` dated 2026-09-12 (372 lines; 113 players matched) | Projection input to ours. **Not pulled automatically** (see flags) |
| Vegas team markets | Win totals, team points | Same books | May | Phase 1 option: team-level adjustment |
| Yahoo | Average cost, projected $, league settings, draft results | OAuth (Fantasy Sports API); paste fallback | Summer | Platform price (Yahoo); needs the app and license request (`yahoo-app-request.md`) |
| Sleeper | Draft results by draft ID (auction amounts), league settings | Public API, no key | During drafts | Prior drafts by link; platform target values not confirmed |

## Flags (doubtful; not worked around)

1. **FantasyPros terms.** robots.txt allows the cheat sheet pages and its
   content signal says `ai-input=yes`. But the Terms of Use (fantasypros.com/about/legal,
   effective 2010) allow only "a single copy made for personal use" and bar
   using any portion of the site "for any commercial purposes". Pulling the
   public pages for private test data is within robots.txt; showing
   FantasyPros-derived numbers on a public page is doubtful. The tables stay
   service-role only. Decision for Jeremy (handback).
2. **Full FantasyPros projections need a sign-in or the paid API.** The daily
   pull does not sign in. Options: FantasyPros API (paid), Jeremy's signed-in
   export on a schedule, or ESPN's public projections only.
3. **Vegas props.** The book endpoints are unofficial and the old collector
   impersonated Chrome's TLS fingerprint to get past bot protection. That is
   working around a block, so it is not revived. Options: a licensed odds feed,
   Jeremy pastes the lines preseason, or skip player props.
4. **ESPN** is an unofficial public endpoint (no sign-in, no bot block).
   Low risk, but undocumented and can change.
