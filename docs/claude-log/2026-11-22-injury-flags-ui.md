## 2026-11-22 - Injury flags on trade players (Find, Why, Build a Trade)

Contract: Jeremy, 2026-11-22: "We should denote injured players on the trade recommendations, as our trade suggestion
may not work perfectly. It is a flag, not a stopper." A chip beside each flagged player's name in Find's offer cards
and Build a Trade (You give / You get, the roster picker, the lineup card's starters), one line on the card ("Injury
flag on 1 player"), one line per flagged player in the Why panel ("Injury flag: X is Out (hamstring); the trade may
not work as planned."). Display only: no label, rule, count, order or value reads it.

One shared module, `app/next/injury-flag.js` (`window.DDFInjury`): the severity map (Out, IR, PUP, Suspended -> "out";
Doubtful -> "doubtful"; Questionable -> "questionable"; anything else no flag) and the lines. The status comes only
through the Waivers rule (`TradeValueWaivers.statusOf`: dated Sleeper copy at most 6 days old, same Sleeper id, team
and position). The body part is the copy's `injury_body_part` (data PR "Injury body part in the daily Sleeper
status"); without it the chip shows the status alone.

### Verified (check named)
- `tests.test_injury_flag` (node): the severity map, aliases (Yahoo's O/Q/D), no flag for Active/NA/DNR/empty, the
  freshness, id, team and position gates, aria-label "Injury: Out, hamstring", the card and Why lines, escaping, the
  row is unchanged; every trade page loads the module after the status copy and the Waivers rule.
- `tests.test_injury_flag_render` on the USO 10-29 fixture, Team 3: Find's full offer list (every section in page
  order: class, partner, packages, values, trade value, label, tags, lineup blocks, counts, status line) is identical
  with no status file, a fresh copy with no flags, and a copy flagging every other offer player; chips, card line and
  Why lines at 375 and 1440; Build at 320/360/375/1440: chips in the names, picker and lineup card, the line, the Why
  lines, and the names, lineup, totals, checks and Why words unchanged; no horizontal scroll; picker rows >= 44px.
- Discrimination: a copy of find-page.js that sorts flagged offers last fails the offer-list comparison (run by hand).
- Existing suites still pass locally: test_build_lineup_card_render, test_build_pin_selected_render,
  test_find_natural_fit2_render, test_ddf_why, test_build_root_pages, test_build_offer_render, test_player_flags,
  test_find_engine_parity, test_build_page_engine_parity, test_validate_shards.

### Claimed, not confirmed
- Not done: Buy / Sell, the bye marker (the new pages have no calendar week loaded) and the connector answers
  (get-values sends no status; it would need get-values to read v2/player-status.js and the MCP tools to print it).
