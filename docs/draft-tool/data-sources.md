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
| Edge function | `supabase/functions/draft-pull/index.ts` | Deployed 2026-11-27 (v1, verify_jwt on) |
| Tables and view | `supabase/migrations/draft_tool_phase0_20261127.sql` (`draft_pulls`, `draft_market_values`, `draft_market_latest`) | Applied 2026-11-27 |
| Daily schedule | `supabase/migrations/draft_pull_schedule_20261127.sql` (pg_cron `draft-pull-daily`, 11:15 UTC = 5:15 AM CST) | Applied 2026-11-27 |
| Local runner | `tools/draft_pull.mjs` | Ran once 2026-11-27 |

The function pulls each source at most once per UTC day, so a repeat call
costs nothing upstream and the public key is enough to trigger it. Every
attempt, ok or failed, writes a `draft_pulls` row with its pull date and the
source's own "last updated" time; a page reads the latest ok pull and shows
a stale warning when it is old. Anyone may read; only the service role
writes. Every row carries `credit` (for example "Rankings: FantasyPros
consensus (fantasypros.com)"), and every page or audit table that shows these
numbers shows that credit next to them. No live page reads them yet.

Supabase run, 2026-11-27 17:22 UTC (Jeremy's yes the same day): FantasyPros
ECR ok, 2,096 rows; ESPN ok, 1,200 rows; `draft_pulls` holds pull date
2026-11-27 for both, and `draft_market_latest` returns them. A second call
the same day skipped both sources. The public key reads (HTTP 200) and
cannot write (HTTP 401).

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

1. **FantasyPros terms: decided.** Jeremy, 2026-11-27: show FantasyPros
   numbers "with attribution". robots.txt allows the cheat sheet pages
   (`ai-input=yes`), but the Terms of Use (fantasypros.com/about/legal,
   effective 2010) allow only "a single copy made for personal use" and bar
   using any portion of the site "for any commercial purposes". The risk
   stays: FantasyPros could object to republished numbers, more so if the
   site earns money. Mitigation: a visible FantasyPros credit wherever its
   numbers appear, the public pages only (no sign-in, no `/api/`), one pull a
   day with the crawl delay, and drop or license the source if FantasyPros
   asks.
2. **Full FantasyPros projections need a sign-in or the paid API.** The daily
   pull does not sign in. Options: FantasyPros API (paid), Jeremy's signed-in
   export on a schedule, or ESPN's public projections only.
3. **Vegas props.** The book endpoints are unofficial and the old collector
   impersonated Chrome's TLS fingerprint to get past bot protection. That is
   working around a block, so it is not revived (coordinator, 2026-11-27: no
   browser impersonation or fingerprint spoofing). The 2026 snapshot dated
   2026-09-12 in `public.vegas_season_totals` stays the test input. Back with
   Jeremy: licensed feed or paste (below).
4. **ESPN** is an unofficial public endpoint (no sign-in, no bot block).
   Low risk, but undocumented and can change.

## Vegas season player props: licensed feeds and the paste path

Searched 2026-11-27. No provider's published plan clearly states that it
carries NFL regular-season player stat totals (passing, rushing and
receiving yards and TDs, receptions). Ask each for a sample of the
DraftKings/FanDuel "season totals" markets before buying. Prices are as
published, or as reported by third parties where marked.

| Provider | Season player props | Price | Notes |
| --- | --- | --- | --- |
| TheRundown (therundown.io) | Its docs list season-long NFL yardage under futures; futures are "early access" on Ultra and up | Ultra $399/mo on one page, $599/mo on its pricing page (conflict); player props from $69/mo (Starter) | Self-serve; closest match found |
| The Odds API (the-odds-api.com) | Futures/outrights for selected competitions; player season totals not confirmed | Free 500 credits; $30 (20K), $59 (100K), $119 (5M), $249 (15M) per month | Cheapest self-serve; credits per market x region |
| SportsDataIO | Futures and props, including season win totals; separate props/futures endpoints and key | Not published (contact) | Enterprise; history moves to a warehouse after 30 days |
| OpticOdds / OddsJam | Outrights and player props for NFL | Not published; one third-party review reports about $5,000/mo (unverified) | Enterprise |
| Prop Professor (enterprise) | Futures boards per league | From $500/mo (published) | Coverage of season stat totals not stated |

**Paste path (no license, no scraping).** Preseason, Jeremy (or any user)
opens a sportsbook's NFL season player props page in their own browser
(DraftKings "Player Futures", FanDuel "Regular Season" player stats), selects
all, copies and pastes into the tool. A parser (Phase 1, not built) reads
lines of the form "Player, market, over/under line" for the seven markets in
`VEGAS_MARKETS` and feeds `vegasStatLine`. The paste is the user's own copy
for their own use; nothing is fetched by us. Optional: Jeremy pastes once a
week from May to Week 1 and the pull stores it as recurring data.

Sources: [TheRundown player props API](https://therundown.io/player-props-api),
[TheRundown pricing](https://therundown.io/pricing/api),
[The Odds API](https://the-odds-api.com/),
[SportsDataIO betting data](https://sportsdata.io/betting-data),
[OpticOdds NFL API](https://opticodds.com/sports/nfl),
[Prop Professor enterprise](https://www.propprofessor.com/enterprise),
[odds API comparison (SportsGameOdds)](https://sportsgameodds.com/comparing-odds-api-providers/).
