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
  without a prop from the FantasyPros line for the same player. A player with
  no prop is left out of the Vegas source and the build's fill-in handles him,
  as it does for any source that skips a player.
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
| Push floor | Below. |

The inflation factor itself is not bounded: late in a draft it can be large
(review probe: $20 and 2 open slots against a rival with $3 for 1 slot and
one $2 player left gives a factor of 20). The rival cap on walk-away is what
keeps the bid sane there ($4 in that probe); the factor is still shown as is.

Scoring presets: `standard`, `half`, `ppr` use ESPN's defaults
(interception -2); `yahoo_standard`, `yahoo_half`, `yahoo_ppr` use Yahoo's
(-1). Any per-stat override can be passed instead of a preset.

### Push floor

**Definition (recommended, option A):** the highest whole-dollar bid that is
the lowest of

1. our walk-away price,
2. the market clearing price (inflated market price, rounded down) minus $1,
3. the best max bid among rivals with a slot that can take the player, minus $1.

If that is below $1, there is no push floor: let him go.

**Why this one.** A push bid must pass two tests. It has to be safe: if
nobody tops it we own the player, so it can never exceed what we would pay
(rule 1). And it has to make someone else pay: it only works if a rival will
and can still top it. Rule 2 stops where the room is expected to stop, so we
do not end up as the high bidder on a player the room values less than we
pushed. Rule 3 stops when no rival can legally top us, the case where a push
turns into a forced buy.

For a player we like more than the market (a target), the push floor sits
below the walk-away: bidding to there is free, above it we are paying over
market. For a player we like less (a fade), the push floor is our walk-away:
whoever wins pays more than he is worth to us. One key on the board enters
it.

Options considered:

- **A (recommended): lowest of walk-away, market - $1 and rival max - $1.**
  Never leaves us stuck above our value; never bids past what any rival can
  pay.
- B: market - $1 only. Simpler, but can push past our own value on a fade and
  leave us holding a player we do not want at more than he is worth to us.
- C: walk-away minus a fixed margin ($2 or 10%). Ignores what the room and
  the rivals can actually pay.

Phase 1 refinement (not built): rule 1 should use the player's value to our
roster as it stands (starter value when he fills a starting slot, bench value
when he only fills the bench), not his league-wide price.

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

The review cases (tests `ReviewCases`) add the late-draft probe (walk-away
$4, push floor $2), the outside-pool $1 walk-away, per-slot and IR handling,
a draft-start inflation of exactly 1.0 with K and DST slots, FLEX,
superflex and bench eligibility, and a pool-size check that fails if the
pool is one player too large.

The test also proves it can fail: three mutations (max bid without the $1
reserve, push floor without the rival cap, inflation over the whole board)
each break the worked example.
