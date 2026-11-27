# Draft tool price backtest (Phase 0, JEG-1667)

Script: [`tools/draft_backtest.mjs`](../../tools/draft_backtest.mjs). Run
2026-11-27, re-run after the Opus math review the same day. Inputs are kept
out of the repo (third-party data); the commands and the input shapes are in
the script header. All data is **2026 data**.

## What was tested

Each predictor priced every player for the auction's own league before the
first sale, then was inflated to the draft-start state (keepers already
sold). Error = predicted - paid, per player sold, QB/RB/WR/TE only (K and
DST are $1 slots in the engine and are left out).

| Predictor | Built from |
| --- | --- |
| Ours | DDF draft value: the value build blends market (FantasyPros ECR on ESPN's dollar curve), FantasyPros season projections (snapshot 2026-09-11, consensus of 2026-09-08) and Vegas season props (2026-09-12), weights 50 / 25 / 25; expected-starts bench share |
| Market | FantasyPros 2026 draft ECR (last update 2026-09-10) mapped onto ESPN's published dollar curve |
| Platform | ESPN's published 2026 auction values |

Auctions:

1. **A 12-team ESPN keeper league**, auction on 2026-08-19, $200, standard
   scoring, QB/2RB/2WR/TE/FLEX/K/DST/5 bench. 168 sales, 27 keepers ($683)
   treated as sold; 116 skill players scored (25 K/DST unmatched by design,
   1 name fixed by alias). Draft-start inflation: ours +3.6%, market +5.6%,
   platform +5.1%.
2. **ESPN 2026 average auction values**: the mean price in real ESPN 2026
   auctions (ESPN's default 10-team $200 PPR room), 99 players at $1 or more.

**Not independent for auction 2.** Ours (through its market chart) and
market both map FantasyPros ranks onto ESPN's published dollar curve, so
against ESPN's own average prices they share ESPN's curve shape. Platform is
left out of auction 2 for the same reason. Auction 1 is a separate room.

## Results (recommended weights, 50 / 25 / 25)

**Auction 1 (12-team ESPN keeper league), raw dollars**

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias | Platform MAE | Platform bias |
|---|---|---|---|---|---|---|---|
| QB | 16 | $4.1 | +3.1 | $5.5 | +3.9 | $2.5 | -1.1 |
| RB | 41 | $4.1 | -0.5 | $5.0 | -2.1 | $4.9 | -1.2 |
| WR | 46 | $3.0 | -0.5 | $3.8 | +1.2 | $3.5 | +1.7 |
| TE | 13 | $3.0 | +0.8 | $2.1 | -0.4 | $2.1 | +1.1 |
| All | 116 | $3.5 | +0.1 | $4.3 | +0.2 | $3.7 | +0.2 |

**Auction 2 (ESPN 2026 average auction values)**, shape only: predictions
scaled so their total matches what was paid, because ESPN's averages add up
to $1,474, not a $2,000 room.

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias |
|---|---|---|---|---|---|
| QB | 16 | $3.5 | -0.3 | $3.8 | +0.4 |
| RB | 34 | $4.5 | -2.7 | $5.0 | -3.6 |
| WR | 38 | $6.3 | +2.9 | $6.6 | +3.2 |
| TE | 11 | $3.5 | -1.2 | $4.0 | -0.7 |
| All | 99 | $4.9 | +0.0 | $5.3 | +0.0 |

## Blend weight sensitivity (ours, MAE per player)

The weights are one named setting, `DRAFT_BASIS_WEIGHTS` in
`app/draft/draft-engine.js` (percent: market / FantasyPros projections /
Vegas). "Market only" is the trade chart's default basis, under which a
player's own projections did not move ours (the review finding).

| Weights (market / FP projections / Vegas) | Auction | QB | RB | WR | TE | All |
|---|---|---|---|---|---|---|
| market only (trade-chart basis) | 12-team keeper | $5.8 | $5.4 | $5.0 | $1.9 | $4.9 |
| market only (trade-chart basis) | ESPN avg prices (shape) | $4.0 | $5.0 | $6.6 | $4.1 | $5.4 |
| 70 / 15 / 15 | 12-team keeper | $4.6 | $4.5 | $3.3 | $2.4 | $3.8 |
| 70 / 15 / 15 | ESPN avg prices (shape) | $3.6 | $4.7 | $6.3 | $3.5 | $5.0 |
| 50 / 25 / 25 | 12-team keeper | $4.1 | $4.1 | $3.0 | $3.0 | $3.5 |
| 50 / 25 / 25 | ESPN avg prices (shape) | $3.5 | $4.5 | $6.3 | $3.5 | $4.9 |
| 34 / 33 / 33 | 12-team keeper | $3.6 | $3.8 | $3.2 | $3.6 | $3.5 |
| 34 / 33 / 33 | ESPN avg prices (shape) | $3.4 | $4.6 | $6.3 | $3.5 | $4.9 |

Decision for Jeremy (default blend):

- **A (recommended): 50 / 25 / 25.** Ties the best all-player error in both
  auctions ($3.5, $4.9), keeps the market as the anchor, and is better than
  equal weights on WR and TE.
- B: 34 / 33 / 33. Same all-player error; better on QB and RB, worse on TE.
- C: 70 / 15 / 15. Closer to the market; $0.1 to $0.3 more error.

## What it says

- **Projections and Vegas make ours better, not just different.** With the
  blend, ours has the lowest all-player error in the keeper auction ($3.5 vs
  market $4.3 and platform $3.7) and in the ESPN averages ($4.9 vs $5.3).
- **Rooms still pay close to what their platform shows on QBs.** ESPN's own
  values priced QBs best ($2.5); ours is $3.1 high on QBs in the 1-QB keeper
  league. That is the first league-tendency input (screen 8).
- **RBs:** rooms pay a little more than ours (-$0.5 keeper, -$2.7 ESPN).
- **Stars:** the 12 most expensive players went for $3.2 less than ours on
  average (platform: $7.5 less). The opponent model should still cap stars
  at the clearing price.

## Third auction: USO Season XVIII (waiting for the paste)

Jeremy, 2026-11-27: "Paste USO XVIII (Recommended)". The backtest is ready
to take it:

1. On Yahoo, open the league's 2026 Draft Results (the view with each
   player's cost), select all, copy, and paste into a text file.
2. `node tools/draft_auction_paste.mjs --in paste.txt --players <FantasyPros projection export> --league tools/draft_leagues/uso-season-xviii-2026.json --out uso_2026.json`
   It reads each sale's player (the live site's roster matcher), cost and
   keeper mark, drops team and manager names, and saves nothing if any sale
   is unreadable, listing those lines. It warns when the count is not a full
   draft (180 sales) or the total is over 12 x $200.
3. Add `--auction "uso=uso_2026.json:tools/draft_leagues/uso-season-xviii-2026.json"`
   to the backtest command above and re-run.

League settings come from the Yahoo league connector (12 teams, half PPR,
QB/2RB/3WR/TE/FLEX/K/DEF/5 bench); the $200 budget is assumed.

## Limits

- Look-ahead: projections and props are dated about three weeks after the
  keeper league's auction (2026-08-19), so ours had information that room
  did not. Part of ours' edge over market may come from that.
- One real room plus one aggregate, and the aggregate shares ESPN's curve.
  A third auction would help: Jeremy's USO Season XVIII (Yahoo, 2026
  auction) has picks but no prices in the league connector; pasting the
  Yahoo draft results page (with costs) adds it.
- ESPN values were read on 2026-11-27; that they match draft time is
  assumed.
