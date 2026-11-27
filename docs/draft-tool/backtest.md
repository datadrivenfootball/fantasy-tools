# Draft tool price backtest (Phase 0, JEG-1667)

Script: [`tools/draft_backtest.mjs`](../../tools/draft_backtest.mjs). Run
2026-11-27. Inputs are kept out of the repo (third-party data); the commands
and the input query shapes are in the script header. All data is **2026 data**.

## What was tested

Each predictor priced every player for the auction's own league before the
first sale, then was inflated to the draft-start state (keepers already
sold). Error = predicted - paid, per player sold, QB/RB/WR/TE only (K and
DST are $1 slots in the engine and are left out).

| Predictor | Built from |
| --- | --- |
| Ours | DDF draft value: FantasyPros season projections (snapshot 2026-09-11, consensus of 2026-09-08) + Vegas season props (2026-09-12), with FantasyPros ECR as the market chart; expected-starts bench share |
| Market | FantasyPros 2026 draft ECR (last update 2026-09-10) mapped onto ESPN's published dollar curve |
| Platform | ESPN's published 2026 auction values |

Auctions:

1. **A 12-team ESPN keeper league**, auction on 2026-08-19, $200, standard
   scoring, QB/2RB/2WR/TE/FLEX/K/DST/5 bench. 168 sales, 27 keepers ($683)
   treated as sold; 116 skill players scored (25 K/DST unmatched by design,
   1 name fixed by alias). Draft-start inflation: ours +6.9%, market +5.6%,
   platform +5.1%.
2. **ESPN 2026 average auction values**: the mean price in real ESPN 2026
   auctions (ESPN's default 10-team $200 PPR room), 99 players at $1 or more.
   Platform is left out here: it would test ESPN's shown values against rooms
   that see them.

## Results

**Auction 1 (12-team ESPN keeper league), raw dollars**

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias | Platform MAE | Platform bias |
|---|---|---|---|---|---|---|---|
| QB | 16 | $5.8 | +3.3 | $5.5 | +3.9 | $2.5 | -1.1 |
| RB | 41 | $5.4 | -1.8 | $5.0 | -2.1 | $4.9 | -1.2 |
| WR | 46 | $5.0 | +1.2 | $3.8 | +1.2 | $3.5 | +1.7 |
| TE | 13 | $1.9 | -0.5 | $2.1 | -0.4 | $2.1 | +1.1 |
| All | 116 | $4.9 | +0.2 | $4.3 | +0.2 | $3.7 | +0.2 |

**Auction 2 (ESPN 2026 average auction values)**, shape only: predictions
scaled so their total matches what was paid, because ESPN's averages add up
to $1,474, not a $2,000 room (raw bias is +$4.6 for ours, mostly WR).

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias |
|---|---|---|---|---|---|
| QB | 16 | $4.0 | -0.1 | $3.8 | +0.4 |
| RB | 34 | $5.0 | -3.9 | $5.0 | -3.6 |
| WR | 38 | $6.6 | +3.7 | $6.6 | +3.2 |
| TE | 11 | $4.1 | -0.6 | $4.0 | -0.7 |
| All | 99 | $5.4 | 0.0 | $5.3 | 0.0 |

## What it says

- **Rooms pay close to what their platform shows.** In the ESPN league,
  ESPN's own values were the best predictor of the price paid ($3.7 per
  player; QB $2.5). Platform price is the right anchor for "what will this
  go for"; the gap between ours and platform is the opportunity.
- **Ours is a value, not a price forecast.** Ours sits near the market
  (the market chart sets DDF's position split), $0.1 to $0.6 per player
  further from the paid price than the market. Gaps are where we act, so a small
  extra error is expected.
- **Rooms pay more for RBs and less for QBs than the numbers say.** RB bias
  -$1.8 to -$3.9 in both auctions; QB +$3.3 in the 1-QB keeper league. This
  is the first league-tendency input (screen 8).
- **Stars cost less than ours in this room.** The 12 most expensive players
  went for $9.1 less than ours on average (platform: $7.5 less). The
  opponent model should cap stars at the clearing price, not at our value.

## Limits

- Look-ahead: projections and props are dated about three weeks after the
  keeper league's auction (2026-08-19).
- One real room plus one aggregate. A third auction would help:
  Jeremy's USO Season XVIII (Yahoo, 2026 auction) has picks but no prices
  in the league connector; pasting the Yahoo draft results page (with costs)
  adds it.
- ESPN values were read on 2026-11-27; ESPN's published values do not change
  after the preseason, but that is not confirmed for 2026.
