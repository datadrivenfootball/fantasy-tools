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

## Vegas season player props: pasted by Jeremy

Jeremy, 2026-11-27: "I'll paste the lines." No scraping and no
bot-protection workarounds. A licensed odds feed (TheRundown, The Odds API,
SportsDataIO, OpticOdds) remains an option if pasting gets tedious; none
confirmed season player stat totals in its published plans.

Parser: `app/draft/vegas-paste.js` (pure, runs in the browser or Node).
Snapshot tool: `tools/draft_vegas_paste.mjs`. Tests:
`tests/test_draft_vegas_paste.py`. One pasted snapshot is dated and is the
same for every league; it has the row shape of the 2026-09-12 export, so it
feeds ours through the same path (`--vegas` in the backtest and simulator;
`vegas` in `DraftEngine.ddfDraftValues`, through `vegasStatLine`).

### How to paste

1. In your own browser, open a sportsbook's NFL **season** player props:
   DraftKings "Player Futures" or FanDuel "Regular Season" player stats. One
   market per page is fine (for example "Regular Season Receiving Yards").
2. Select all (Cmd+A), copy (Cmd+C), and paste into a text file, one or more
   markets in one file. Keep the market header ("Regular Season Passing
   Yards") in what you copy; the parser reads the market from it.
3. Run:
   `node tools/draft_vegas_paste.mjs --in paste.txt --players <FantasyPros projection export> --season 2026 --date YYYY-MM-DD --out <folder>`
   (`--date` = the day you copied the lines; `--season` = the season the
   lines are for).
4. If it prints "Saved N lines", the snapshot is
   `<folder>/vegas_<date>.json` (and `vegas_<date>.sql` with `--sql`). If it prints "Not saved", fix or remove the
   listed lines (or add a missing player name) and run it again. Nothing is
   saved while any line is unreadable.

What it reads: passing, rushing and receiving yards and TDs, and receptions,
in three layouts: a market header then name / "O 4100.5" lines; a
"Player - Regular Season Passing Yards" header then Over / Under; or one line
"Player Over 104.5 Receptions -115". It uses the over line (the under only
when there is no over), ignores odds and page chrome, reads "3,875.5", and
strips team tags like "(SEA)".

It refuses, and lists, every line it cannot trust (tightened after the reviews
of f662c66 and f0fcfb1):

- **Season only, per market.** Each market needs its own season marker, in
  its header ("Regular Season Receiving Yards") or on a line in its section
  before the first player ("2026 Regular Season"). A page that says "season"
  somewhere else (a "Season Futures" menu link) does not count. A "Week 12",
  "Game Lines" or "Lions vs Bears" line starts a weekly or game section, and
  every line under it is refused.
- **The right year on every line.** Any line naming another year ("2025
  Receiving Yards", "'25 Regular Season", "25/26") is refused, and so is its
  section.
- **A header is a stat, season words and a year, nothing else.** Any other
  word refuses the market: "September Receiving Yards (Regular Season)",
  "Rest of Regular Season ...", "... at Home", "... if Burrow Misses Time"
  (fourth review of 31faf01). A known player's name may lead the header
  ("Jahmyr Gibbs - Regular Season Rushing Yards").
- **One stat per market.** A header that names two stats in any order or
  joiner ("Receiving and Rushing Yards", "Receiving Yds plus Rushing Yds",
  "Rush + Rec", "Rushing and Passing Yards") is refused as combined.
- **No partial or extended markets:** half, quarter, playoffs, "incl."
  markets; longest play, attempts, carries, targets, completions,
  interceptions, sacks, fumbles, points, leaders, awards.
- **No guessing the player.** A name it does not know clears the selected
  player, so its lines are listed ("unknown player") instead of going to the
  player above. A name two players share ("Mike Williams") is refused and
  listed. Any line it cannot read clears the player too.
- **Whole lines only.** An over/under line is the side, the number and
  optional odds: "O 1375.5 Receiving Yards (Week 1)" is listed, not read.
  "1375½" reads as 1375.5. Under a split "Over" a whole number ("110") may be
  unsigned odds and is listed. A line in a market section with a number it
  cannot read (a Greek "Ο 1375.5") is listed, never dropped.
- **Consistent lines.** Two different over (or under) lines for the same
  player and market, an over and under more than 5% apart, a number outside
  a plausible season range, or an over/under it cannot read.

Each snapshot's meta file records its pull date (`snapshot_date`,
`pulled_at`). It stores no scale factors: the engine recomputes them on
every build from the projection it prices (`vegas_scale` says so); see
engine.md "Vegas level".

Storage: `public.draft_vegas_lines` (applied 2026-11-27 on Jeremy's yes;
public read, server-only write; one snapshot per date, the same for every
league). Add `--sql` to step 3 and the tool also writes
`<folder>/vegas_<date>.sql`; run it in the Supabase SQL editor (or ask
Claude to run it) to load that snapshot. It replaces any rows already saved
for that date, so re-running is safe.
