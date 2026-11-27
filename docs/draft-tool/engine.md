# Draft tool price engine (Phase 0, JEG-1667)

Code: [`app/draft/draft-engine.js`](../../app/draft/draft-engine.js). Tests:
[`tests/test_draft_engine.py`](../../tests/test_draft_engine.py) with the
worked example in
[`tests/fixtures/draft_worked_example.json`](../../tests/fixtures/draft_worked_example.json).
No live page loads it (the hold of 2026-11-16; `NotLive` test).

Every function is pure and runs client side. League settings never leave the
browser; only the recurring data (the daily pull) comes from Supabase.

## Three prices

| Price | Built from | Function |
| --- | --- | --- |
| Ours (DDF draft value) | Market values, FantasyPros season projections and Vegas props, blended by the existing value build `ValueModel.runValuePipeline` | `ddfDraftValues`, then `ourPrices` |
| Market | FantasyPros consensus rank mapped onto a dollar curve, plus any market dollar source (ESPN average auction value), rescaled to the league | `rankImpliedDollars`, `blendDollars`, `rescaleDollars` |
| Platform | The dollars ESPN, Yahoo or Sleeper shows in its draft room, rescaled to the league | `rescaleDollars` |

### Ours: the existing value build, not a fork

`ddfDraftValues` shapes inputs and calls `ValueModel.runValuePipeline` once:

- Setting from the league: teams, QB/RB/WR/TE slots, FLEX, SUPERFLEX, bench.
- Projections enter as `projection` sources in points per game (season
  points / 17), scored with the league's own scoring (`fantasyPoints`).
- Vegas enters as one more projection: `vegasStatLine` takes the season prop
  lines (pass/rush/receiving yards and TDs, receptions) and fills any stat
  without a prop from the FantasyPros line for the same player. **A player
  with no prop takes his FantasyPros line** in the Vegas source, so Vegas
  covers the same pool as FantasyPros. (Review of f662c66: a Vegas source
  listing only the ~113 prop players drew its replacement line from the
  weakest prop player and gave its whole pie to them, so ours moved even
  when every line agreed with FantasyPros; McCaffrey, no prop, $58.8 to
  $53.2. Test `test_vegas_equal_to_fp_leaves_ours_unchanged`: Vegas equal to
  FantasyPros prices exactly like FantasyPros carrying the Vegas weight.)
- Market values enter as a `chart` source; with the live `charts` split they
  set the position split of the pie.
- **The blend.** DDF Value's default basis averages the chart sources only
  (JEG-1073), so on that basis a player's own projections or Vegas lines do
  not move ours (review, 2026-11-27: a 1.6x projection moved a test RB
  $15.04 to $15.04). Jeremy, 2026-11-27: "Our values are going to be informed
  by market + vegas projected performance outcomes, calculated up in to DDF
  draft values." So ours uses the value build's own `blend` basis (VP-6.3,
  `basisConfig`): the weighted mean of each source's Adjusted value, over the
  sources that price the player. No new math.
- **One named setting:** `DRAFT_BASIS_WEIGHTS` = market 50, FantasyPros
  projections 25, Vegas 25 (percent; each group's weight is split evenly
  across its sources). A caller can pass `basisWeights`. The backtest
  sensitivity table and the A/B/C decision are in `backtest.md`. Test: a
  1.6x projection now moves the test RB $15.73 to $25.43; 2x Vegas $16.39 to
  $27.64; 1.6x market $15.73 to $21.68.
- The live page's expected-starts parameters (`config/lineup_parameters.json`)
  set the bench share, so ours uses DDF's bench share. `lineupConfig` is
  required: without it the build would fall back to a fixed 15% share. At
  draft time the window opens at week 1 (`preseasonLineup`).
- Overrides replace a player's DDF Value after the build.

The result is DDF Value, a share of a fixed pie, read from
`rows[key].ddfByVersion.blended.value`.

### Dollars and snake rank

`pricesFromWeights(weights, league)`:

- Pool: the top `teams x valued slots` players by weight, where valued slots
  are every roster slot except K and DST (IR is filled after the draft).
- Surplus: `teams x budget - teams x roster size x min bid`. K and DST are
  priced at the minimum bid and their dollars stay in the floor.
- Price: `min bid + weight / total weight x surplus`.
- So prices plus $1 for each empty pool slot and each K/DST slot add up to
  exactly `teams x budget` (tested).

`snakeRanks` orders by draft value (ties by key). Market and platform
dollars quoted for a reference league are rescaled the same way: each
player's dollars above the minimum keep their share of the league's surplus.

## Live auction math

State: each team's money left and open slots as counts per slot type (QB,
RB, WR, TE, FLEX, SUPERFLEX, K, DST, BN; a plain count is refused because it
cannot tell K/DST slots from valued ones; IR and other keys are ignored), the
available players, and the three pre-draft price maps.

| Quantity | Definition |
| --- | --- |
| Inflation factor | `(money left - $1 x open slots) / (value left)`, where value left is the sum of `price - $1` over the best available players who fill the open valued slots. Computed separately for ours, market and platform. Inflation = factor - 1. |
| Inflated price | `$1 + (price - $1) x factor` |
| Max bid (per team) | `money left - $1 x (open slots - 1)` |
| Walk-away | Our inflated price rounded down to whole dollars, capped at our max bid and at the best max bid among rivals who can roster him + $1 (no rival can force us past that). $1 when he is outside our priced pool but we have a slot; $0 when we have no slot. |
| Push floor | Below. **What the board does today:** walk-aways use **personal inflation by default** (Jeremy, 2026-11-27: "Personal by default (Recommended)"); each row also carries `oursInflatedRoom`, the room-factor price, for reference, and `state.ourFactor = "room"` switches back. The push floor shown is still rule A; the candidates below are in `pushFloors()` until Jeremy decides. |

The inflation factor itself is not bounded: late in a draft it can be large
(review probe: $20 and 2 open slots against a rival with $3 for 1 slot and
one $2 player left gives a factor of 20). The rival cap on walk-away is what
keeps the bid sane there ($4 in that probe); the factor is still shown as is.

Scoring presets: `standard`, `half`, `ppr` use ESPN's defaults
(interception -2); `yahoo_standard`, `yahoo_half`, `yahoo_ppr` use Yahoo's
(-1). Any per-stat override can be passed instead of a preset.

### Push floor, thought through

Jeremy (2026-11-27) judged the first three definitions not good enough. This
is the deeper pass, tested in the auction simulator (`tools/draft_sim.mjs`).

**What it is for.** The push floor is the highest bid we will make on a
player. It has two jobs: make the winner pay as much as possible, and never
leave us owning a player we did not want at a price we regret.

**How an auction actually clears.** The winner pays about the runner-up's
limit + $1. So the price of any player is set by the second-highest limit in
the room. If our bid is the runner-up's, every dollar we bid is a dollar the
winner pays; above the top rival's limit, we win instead.

**What the opponent model gives us** (`opponentModel`):

| Estimate | Definition |
| --- | --- |
| Room price | Inflated market price blended 50/50 with the inflated platform price (rooms track the platform's numbers: backtest) |
| Rival limit (w) | `min(max bid, room price x need)`; need 1 with an open starting slot, 0.6 bench only, 0 none; spread +/-20% |
| w1, w2 | The highest and second-highest rival limits |
| Clearing price | `min(w1, w2 + $1)`: what the winner pays if we stay out |
| Cost to win | `w1 + $1`: what we pay if we want him |
| Roster value | Our inflated price if he starts for us; half of it if he only fits the bench; 0 if nothing fits |

**Targets, fades and neutral players** (`pushFloors`):

- **Target**: roster value at least $2 over the cost to win. We are buying;
  bid to the buy limit (roster value, capped by walk-away). No push logic.
- **Fade**: roster value at least $2 under the cost to win. We will not win
  him at a fair price, so every dollar we bid only moves the winner's price.
- **Neutral**: within $2. Buy at value, else push.

**The risk we accept.** Getting stuck means our bid is the highest. If the
bid is at or under our roster value, getting stuck costs nothing: we own a
player at a price we are glad to pay. Above roster value, the loss is
`bid - roster value`, times the chance the top rival stops short of our bid.

**Candidates.**

- **A (first draft):** lowest of walk-away, market - $1, best rival max - $1.
  Stops at market - $1 even when we would gladly pay more. It also uses the
  league price, not roster value, so it can overpay for a bench-only player.
- **B: our roster value.** Bid to exactly what he is worth to our roster as
  it stands, on every player. In an English auction this is the strongest
  safe push: the winner pays at least our value, and getting stuck never
  costs anything. Two numbers, kept apart: the **buy limit** (roster value,
  capped at walk-away) is what we bid when we would own him, and may exceed
  every rival's max bid (then we simply win); **push floor B** is the buy
  limit capped at the best rival max bid - $1, because above that no rival
  can top us and the bid is a purchase, not a push (late probe: buy limit
  $4, push floor B $2).
- **C: roster value plus a bounded overreach.** On fades and neutrals, go
  above roster value only while `(chance the top rival tops us) x (dollars
  drained) x 0.5` beats `(chance we are stuck) x (overpay)`, and keep the
  expected overpay under $1 per player. The 0.5 says a rival's wasted dollar
  is worth half of one of ours.

**Simulation** (`tools/draft_sim.mjs`, 300 seeded drafts per policy, seed
2, re-run 2026-11-27 after the review of f662c66). 12 teams, Jeremy's league
settings at $200, 2026 data. Rival bots bid their need-weighted room price
with +/-20% noise centred so rooms pay market on average, and they are not
the engine's opponent model: each bot has its own market/platform blend
(uniform 0-1; the model assumes 0.5) and its own position tendencies
(+/-10%). Same seeds for every policy.

Our starting lineup is scored by three judges, so no result rests on our own
values alone: **ours** (DDF Value), **market** (market dollars), and
**noisy** (DDF Value times a hidden +/-30% per player per draft that no
bidder sees). Mean per draft:

| Policy | Ours | Market | Noisy | Unspent | Bench buys at starter price |
| --- | --- | --- | --- | --- | --- |
| Walk-away, room inflation (first engine) | 164.9 | 124.6 | 177.2 | $55 | 5.0 ($24) |
| Walk-away, personal inflation | 216.5 | 182.3 | 227.7 | $0 | 5.2 ($20) |
| A, personal | 218.0 | 184.2 | 229.6 | $0 | 5.0 ($19) |
| B (buy limit), personal | 221.4 | 186.5 | 231.8 | $1 | 0 |
| C, personal | 220.6 | 186.2 | 231.9 | $0 | 2.6 ($6) |

Each policy minus B, paired by seed (mean +/- standard error):

| Policy | Ours judge | Market judge | Noisy judge |
| --- | --- | --- | --- |
| Walk-away, room inflation | -56.5 +/- 1.7 | -62.0 +/- 1.9 | -54.6 +/- 2.6 |
| Walk-away, personal | -4.9 +/- 0.6 | -4.3 +/- 0.6 | -4.1 +/- 1.0 |
| A, personal | -3.4 +/- 0.5 | -2.4 +/- 0.5 | -2.3 +/- 1.0 |
| C, personal | -0.9 +/- 0.2 | -0.4 +/- 0.3 | +0.1 +/- 0.5 |

"Bench buys at starter price" counts players we won above their value to our
roster as it stood; B is 0 by construction (it bids that value), so it is
reported, not used to rank.

What it shows:

1. **Spending our money matters most.** Under every judge, personal
   inflation is worth 52-58 starter points: the room's inflation sinks as
   rivals overpay for stars, our walk-aways shrink, and $55 is left unused.
2. **B beats A and plain walk-away under all three judges,** by more than
   two standard errors (A: 2.3-3.4 points; walk-away: 4.1-4.9).
3. **B and C tie** under the independent judges (market -0.4 +/- 0.3, noisy
   +0.1 +/- 0.5); C only loses under our own values. Pushing past our value
   neither helps nor clearly hurts, and it gets us stuck 2.6 times a draft.

Personal inflation is the board default since 2026-11-27 (Jeremy:
"Personal by default (Recommended)"). Recommendation for the push floor,
still Jeremy's call (the board shows rule A until then): **B.** Limits: bots do not nominate
strategically; one league shape; the noisy judge still centres on DDF Value.
(The reviewer's probe on the earlier code, 100 drafts on seed 2, found
B - A = -1.7 +/- 0.9 under the market judge; this run, after the Vegas fill
and with misspecified bots, finds B ahead by 2.4 +/- 0.5. The sign depends
on the setup, so treat B's edge over A as modest and worth re-checking with
the USO auction and real-room tendencies.)

## Worked example (hand-checked; the test matches it to the dollar)

**Pricing.** 2 teams, $10 each, slots RB, WR, BN (3), min $1. Weights a 30,
b 20, c 10, d 5, e 5, f 0. Pool = 6, surplus = 20 - 6 = 14, total weight 70.
a = 1 + 30/70 x 14 = **$7**, b = **$5**, c = **$3**, d = **$2**, e = **$2**;
f has no weight, so one pool slot goes for $1. 7+5+3+2+2+1 = $20.

**Auction state.** 3 teams, $30 each, slots QB, RB, WR, TE. We are A.
Sold: A paid $15 (RB); B paid $10 (WR) and $6 (QB); C paid $1 (TE).

| Team | Money left | Open slots | Max bid |
| --- | --- | --- | --- |
| A (us) | $15 | QB, WR, TE | 15 - 2 = **$13** |
| B | $14 | RB, TE | 14 - 1 = **$13** |
| C | $29 | QB, RB, WR | 29 - 2 = **$27** |

Money left $58, open slots 8, surplus left 58 - 8 = **$50**.
Value left (ours): best 8 available are P5 12, P6 10, P7 8, P8 6, P9 6, then
three $2 players (P10, P11, P12; P13 is the 9th): 11+9+7+5+5+1+1+1 = **$40**.
Factor 50/40 = **1.25** (inflation **+25%**). Market value left is also $40
(16, 11, 8, 5, 4, 2, 1, 1 less $1 each), so market factor is also 1.25.

| Player | Pos | Ours | Mkt | Ours infl. | Mkt infl. | Walk-away | Best rival max | Push floor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P5 | QB | 12 | 16 | 14.75 | 19.75 | min(13, 14) = **13** | C 27 | min(13, 18, 26) = **13** |
| P6 | WR | 10 | 8 | 12.25 | 9.75 | **12** | C 27 | min(12, 8, 26) = **8** |
| P7 | RB | 8 | 11 | 9.75 | 13.5 | **0** (no RB slot) | 27 | **none** |
| P8 | TE | 6 | 4 | 7.25 | 4.75 | **7** | B 13 | min(7, 3, 12) = **3** |
| P9 | WR | 6 | 5 | 7.25 | 6.0 | **7** | C 27 | min(7, 5, 26) = **5** |
| P11 | TE | 2 | 2 | 2.25 | 2.25 | **2** | B 13 | min(2, 1, 12) = **1** |
| P12 | QB | 2 | 1 | 2.25 | 1.0 | **2** | C 27 | min(2, 0, 26) < 1: **none** |

Each rule binds at least once: our max bid caps P5's walk-away, the market
caps P6's push, the walk-away caps P5's push, the missing slot zeroes P7.

**Variant (rival cap).** Same money and counts, but only B has an open QB
slot (B: QB, WR; C: RB, WR, TE). P5's best rival is now B at $13, so his
push floor is min(13, 18, 12) = **$12**.

The tables above use the room factor (`ourFactor: "room"`). **With the
default personal inflation** (since 2026-11-27): A holds $12 of the room's
$50 surplus but 3 of its 8 open valued slots, so A's factor is
12 / (40 x 3/8) = **0.8**; market prices stay on the room factor (1.25).
Ours inflated = 1 + (ours - 1) x 0.8:

| Player | Ours | Ours infl. (personal) | Room, for reference | Walk-away | Push floor (rule A) |
| --- | --- | --- | --- | --- | --- |
| P5 | 12 | 9.8 | 14.75 | **9** | min(9, 18, 26) = **9** |
| P6 | 10 | 8.2 | 12.25 | **8** | min(8, 8, 26) = **8** |
| P7 | 8 | 6.6 | 9.75 | **0** (no RB slot) | none |
| P8 | 6 | 5.0 | 7.25 | **5** | min(5, 3, 12) = **3** |
| P9 | 6 | 5.0 | 7.25 | **5** | min(5, 5, 26) = **5** |
| P11 | 2 | 1.8 | 2.25 | **1** | min(1, 1, 12) = **1** |
| P12 | 2 | 1.8 | 2.25 | **1** | min(1, 0, 26) < 1: **none** |

A is short of money for its open slots (it overspent on P1), so personal
inflation lowers its bids; a team holding more than its share bids higher.
Both tables are tests (`test_board_matches_hand_check_to_the_dollar` for the
room factor, `test_default_personal_inflation_matches_hand_check`).

The review cases (tests `ReviewCases`) add the late-draft probe (walk-away
$4, push floor $2), the outside-pool $1 walk-away, per-slot and IR handling,
a draft-start inflation of exactly 1.0 with K and DST slots, FLEX,
superflex and bench eligibility, and a pool-size check that fails if the
pool is one player too large.

The test also proves it can fail: three mutations (max bid without the $1
reserve, push floor without the rival cap, inflation over the whole board)
each break the worked example.
