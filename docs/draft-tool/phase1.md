# Draft tool Phase 1: the page (JEG-1667; tickets JEG-1672, 1673, 1674, 1671)

Auction mode, V1. Not live: the page is served from `app/draft/` only and
`make sync` does not copy it to `dist/` (hold, Jeremy 2026-11-16). Built
2026-11-28 on the Phase 0 engine; no engine math is edited. All test data is
2026 data.

| File | What it is |
| --- | --- |
| `app/draft/index.html`, `draft.css`, `draft-app.js` | The page: Board (home), Values, My roster, Setup; keyboard; link save. Tokens are the live site's (`app/next/styles.css`) |
| `app/draft/draft-core.js` | Pure: prices through the engine, tiers, team money and open slots from the sales, the board, tier cliffs, roster summary, link codec |
| `app/draft/draft-data.js` | Reads the public Supabase tables with the publishable key and assembles one bundle; the stale rule |
| `app/draft/draft-league.js` | League by ID or link (Sleeper public API, ESPN public league endpoint), settings-page paste, rosters-page paste through the live readers |
| `tools/draft_bundle.mjs`, `tools/draft_preview_build.mjs` | The bundle as a file; the one-file review preview (outputs hold third-party numbers, kept out of the repo) |
| `tests/test_draft_core.py`, `test_draft_league.py`, `test_draft_app_render.py` | Gates below |

## Data

The page reads, client side and read only: `draft_pulls`,
`draft_market_latest`, `fp_season_projections` (latest snapshot),
`draft_vegas_lines` (latest pasted snapshot; while it is empty,
`vegas_season_totals`). League math runs in the browser.

- Prices are shaped exactly as `tools/draft_backtest.mjs` `buildPrices` does:
  ours from `ddfDraftValues`, market = FantasyPros consensus rank on ESPN's
  dollar curve, platform = ESPN's published values, each rescaled to the
  league. The FantasyPros format follows the league's reception points (PPR
  from 0.75, Half from 0.25); ESPN publishes Standard and PPR only.
- Unequal budgets: the engine prices the league at the room's mean budget, so
  prices add up to the money actually in the room.
- Two books' lines for the same player and market are averaged (both are
  Vegas; no source is mixed). The Phase 0 backtest took whichever row came
  last.
- Projection rows carry no player name and `public.players` is not public, so
  names come from `app/next/players-table-1.json` (520 of 534 rows). A row
  with no name is named by the one market-only player of the same position
  and team, else left out and counted (11 left out on 2026 data).
- Stale: the warning shows when the oldest of the sources' latest ok pulls is
  more than 25 hours old (a day, plus an hour for the daily job).

## Board

Each row leads with walk-away, then push floor B and the buy limit as their
own numbers, straight from `DraftEngine.board`. Personal inflation is the
default; the room rate is shown beside it and a toggle switches. Max bid per
team, tier cliffs and the last sales sit beside the list.

- Slots: a team's players fill their own position's slots best first (by our
  pre-draft price), then FLEX, then SUPERFLEX, then the bench.
- Tiers are bands of our pre-draft prices: a tier holds every player at the
  position within the larger of $3 and 20% of its best player. A cliff is the
  count left in the best remaining tier and the dollar drop to the next.
- A sale recomputes and redraws in about 6 ms on 2026 data (1,035 players).

Keys: arrows move, `/` searches, digits type the bid, `W` bid walk-away, `P`
bid push floor, `M` my buy, `S` then the buyer's letter for a sale, `U` undo,
`B` `V` `R` `L` switch screens, `?` help. On a phone each is one tap.

## Link

`#s=<token>+<check>`, the LINK-FORMAT.md wrapper and check. Payload byte 0 is
format version 2, kind 1 (a draft state), then deflate-raw of the JSON state:
league, budgets, my team, every sale, overrides and the inflation choice. The
trade site's decoders refuse any version but 1, so a draft link fails closed
there, and this page refuses a version 1 token. The address bar is rewritten
after every change and the last link is kept on the device, so a reload mid
draft loses nothing. Nothing the user enters is sent to a server.

## Gates

| Gate | Test |
| --- | --- |
| Full 12-team mock auction from the keyboard | `test_draft_app_render.test_full_12_team_auction_from_the_keyboard` (180 sales) |
| Recompute under 200 ms | same test (every sale timed by the page) and `test_draft_core.BoardSpeed` |
| League-ID import, Sleeper and ESPN | `test_draft_league` (Sleeper: real API responses, names replaced; ESPN: reconstructed from the documented response shape, since no public ESPN league answered) |
| Paste fallback | `test_draft_league`: settings pages are reconstructions (the real pages need a sign-in); rosters pages use the live site's ESPN, Yahoo and Sleeper page fixtures |
| Mid-draft link reopens deep-equal | `test_draft_core.LinkRoundTrip`, `test_draft_app_render.test_mid_draft_link_reopens_identical` |
| Stale warning | `test_draft_core.Staleness`, `test_draft_app_render.test_stale_warning` |
| Worked example to the dollar | `test_draft_core.WorkedExample` (from a draft state), `test_draft_app_render.test_worked_example_on_the_board_to_the_dollar` (the drawn cells) |

## Not done, known limits

- Real settings-page text from ESPN, Yahoo and Sleeper has not been tested:
  those pages need a sign-in. Fixtures named `*-reconstructed.txt` are not
  real pages.
- The ESPN league endpoint is tested against a reconstructed response only.
- Platform prices are ESPN's for every league; Yahoo and Sleeper draft-room
  values are not loaded.
- TE premium, bonuses and other scoring the engine has no key for are read,
  listed and not applied.
- Pasting draft results into the board, snake mode, nominations and the
  opponent model are later phases.
