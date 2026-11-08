# JEG-1572: waiver-aware Natural fit on Trade & Waiver Recommendations (2026-11-08)

A friend of Jeremy's tested find.html on his real league (2026-11-08): "A problem with the app I'm seeing is it is
willing to give away some of my good RBs to plug a QB hole that could better be filled via the waiver wire." The card:
you give Josh Jacobs and Jacoby Brissett, you get Tyler Shough and Bryce Young (QBs), "Natural fit", "Your starters
(DDF) +19.9". The search never looked at the available players before calling a trade a fit.

## The rule (`DDF.find.waiverAlternative` in `app/next/find-engine.js`)

No new value math: two `tradeFit` calls on engine rows, plus the Waivers tab's own results (`TradeValueWaivers.evaluateAll`,
already run by find.html for the pickup cards).

- Waiver alternative = the best available players at the positions the trade brings you: one per player you receive at
  that position, best first by the Waivers tab's starter gain (only pickups that improve your starters). They are added
  to your roster with no drop (a drop only touches the bench). Waivers are never a trade partner: the pickups only change
  your own roster for the comparison.
- `gain` = the trade's starters' change (the card number, `fit.us.starterDelta`); `gainAfter` = the same trade's
  starters' change once the pickups are on your roster; `covered = (gain - gainAfter) / gain`, clamped 0..1.
- Demoted when `covered >= WAIVER_SHARE` (0.5: a free pickup closes most of the gap) or your side of the Natural fit test
  fails with the pickups in (the trade's gain beyond the waiver option no longer beats what it costs you: the starters you
  send away count inside `tradeFit`'s net and construction test).
- A demoted Natural fit is listed under Partner neutral (their side already passed). Its numbers do not change; DDF Value
  and the ranking math are unchanged. Force fits are not checked (they are listed only on request).
- Why panel (`DDFWhy.waiverLine`, words only): "The best available QBs, X and Y, close 61% of the gap this trade fills,
  without giving up Josh Jacobs and Jacoby Brissett. With them added, this trade still adds +14.0 to your starters." (or
  "... no longer makes your team better."). A demoted offer leads with it and never shows the "Natural fit" tag; a kept
  offer carries it as a smaller reason. The card shows the same line under the tags of a demoted offer.
- The search signature includes the available players, so a new list on waivers.html re-runs the search. A typed list
  is only matched against your roster, so the search also drops any listed player who is on either roster in the pairing.
- Only the positions received are compared: a waiver WR who would fill FLEX when you receive an RB is not counted.

Review of b35dfc95 (independent agent, CHANGES NEEDED): pool not filtered against the partner's roster (fixed, test case
"stale list"); the line contradicted a demotion by the construction/value test ("no longer outweighs what you give up"
now); a gain under 0.05 skipped the value-test demotion (fixed); the parity test now asserts some offer is demoted.
Re-review of 96f68745: a small-gain demotion left an empty line (now "X is a pickup at the same position, with nothing
given up", every branch tested); the available list is also filtered against every roster in the league (find-page).
Left as is: the check runs on every Natural and Partner neutral trade found (the parity run time did not change, 56 s).

## Partner tag

The pill printed the partner team name in a monospace tag, with no label: a long name with a comma
("YoungLove,1 ina McMillian") read as tags run together and could wrap. It now reads "Trade with <team>" in the body
font, on one line (ellipsis), with the full name in the title. The page code never joins names (the pill is
`team.name` as read from the league), so the comma came from the league's own name as the paste or Sleeper import read
it; not reproducible without the friend's league.

## Effect on a sample league (synthetic: tests' seeded league, a snake draft of the frozen player table)

Natural-fit groups before -> after, 1-2 players each side, DDF / Analyst charts:

| League | ppr 10 | ppr 12 | half 10 | half 12 | std 10 | std 12 | (superflex: ppr 10/12, half 10/12, std 10/12) |
|---|---|---|---|---|---|---|---|
| my 2nd and 3rd round picks back on waivers (the parity test league) | 40 -> 18 | 60 -> 43 | 39 -> 12 | 58 -> 30 | 33 -> 6 | 67 -> 28 | 22->10, 31->25, 14->3, 29->14, 16->2, 33->12 |
| full draft (every good player rostered) | 51 -> 51 | 82 -> 82 | 49 -> 49 | 81 -> 81 | 44 -> 44 | 85 -> 85 | unchanged |

In a full league no available player improves the starters, so nothing moves; when good players sit on waivers, about
half to most of the Natural fits were trades a free pickup mostly matches.

## Review of other pages (same flaw)

- Partners (`partnerRank`, JEG-1560): ranks on position tiers ("You could get QB") without the available players. Not a
  Natural fit label; left unchanged, open decision for Jeremy.
- Build a Trade checks (`build-trade.js`, `fit.natural.ok`) run without the waiver comparison, so a demoted offer opened
  there still passes its checks. Not changed here (other lane's file); open decision.

## Tests

- `tests/test_find_waiver_alternative.py` (Makefile test-core + shard 3): the friend's trade on hand-made rows with two
  QB slots (good waiver QBs: moved to Partner neutral and the Why leads with the waiver line; a weak waiver QB, only a
  WR, or none: stays Natural), engine vs an independent recomputation; drift (threshold moved) caught; find.html cards at
  1440 / 390 with a long comma team name (one line, cut at 390, title), demoted cards' note and Why, 44px Why button.
- `tests/test_find_engine_parity.py`: the oracle applies the rule independently; 12 settings still match the page.
