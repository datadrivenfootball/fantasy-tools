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

## Results (engine default weights, 50 / 25 / 25)

Re-run 2026-11-27 after the review of f662c66: Vegas now covers the same
pool as FantasyPros (players without a prop take their FantasyPros line).

**Auction 1 (12-team ESPN keeper league), raw dollars**

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias | Platform MAE | Platform bias |
|---|---|---|---|---|---|---|---|
| QB | 16 | $3.4 | +1.8 | $5.5 | +3.9 | $2.5 | -1.1 |
| RB | 41 | $5.0 | +2.7 | $5.0 | -2.1 | $4.9 | -1.2 |
| WR | 46 | $3.7 | -2.7 | $3.8 | +1.2 | $3.5 | +1.7 |
| TE | 13 | $2.8 | -0.3 | $2.1 | -0.4 | $2.1 | +1.1 |
| All | 116 | $4.0 | +0.1 | $4.3 | +0.2 | $3.7 | +0.2 |

**Auction 2 (ESPN 2026 average auction values)**, shape only: predictions
scaled so their total matches what was paid, because ESPN's averages add up
to $1,474, not a $2,000 room.

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias |
|---|---|---|---|---|---|
| QB | 16 | $3.4 | -0.8 | $3.8 | +0.4 |
| RB | 34 | $4.5 | -1.3 | $5.0 | -3.6 |
| WR | 38 | $5.7 | +1.9 | $6.6 | +3.2 |
| TE | 11 | $3.2 | -1.3 | $4.0 | -0.7 |
| All | 99 | $4.7 | +0.0 | $5.3 | +0.0 |

## Blend weight sensitivity (ours, MAE per player)

The weights are one named setting, `DRAFT_BASIS_WEIGHTS` in
`app/draft/draft-engine.js` (percent: market / FantasyPros projections /
Vegas). "Market only" is the trade chart's default basis, under which a
player's own projections did not move ours.

| Weights (market / FP projections / Vegas) | Auction | QB | RB | WR | TE | All |
|---|---|---|---|---|---|---|
| market only (trade-chart basis) | 12-team keeper | $5.8 | $5.4 | $5.0 | $1.9 | $4.9 |
| market only (trade-chart basis) | ESPN avg prices (shape) | $4.0 | $5.0 | $6.6 | $4.1 | $5.4 |
| 70 / 15 / 15 | 12-team keeper | $4.4 | $4.5 | $3.4 | $2.5 | $3.8 |
| 70 / 15 / 15 | ESPN avg prices (shape) | $3.6 | $4.5 | $6.0 | $3.4 | $4.8 |
| 50 / 25 / 25 | 12-team keeper | $3.4 | $5.0 | $3.7 | $2.8 | $4.0 |
| 50 / 25 / 25 | ESPN avg prices (shape) | $3.4 | $4.5 | $5.7 | $3.2 | $4.7 |
| 34 / 33 / 33 | 12-team keeper | $3.0 | $5.6 | $4.5 | $3.2 | $4.5 |
| 34 / 33 / 33 | ESPN avg prices (shape) | $3.3 | $4.7 | $5.7 | $3.1 | $4.7 |

Decision for Jeremy (default blend; the engine keeps 50 / 25 / 25 until he
decides):

- **A (recommended): 70 / 15 / 15.** Best on the one independent room
  (keeper auction $3.8 vs $4.0), $0.2 behind on ESPN's averages, which share
  ESPN's curve with ours and are the weaker test.
- B: 50 / 25 / 25. Best on ESPN's averages ($4.7); $0.2 worse in the keeper room.
- C: 34 / 33 / 33. Best on QBs, worst overall in the keeper room ($4.5).

## What it says

- **Projections and Vegas still help.** Against the market-only basis, the
  blend cuts ours' error from $4.9 to $3.8-$4.0 in the keeper room and from
  $5.4 to $4.7 on ESPN's averages. With the Vegas fill the keeper-room gain
  is smaller than first reported ($3.5 before the fix, a figure inflated by
  the distortion the review found).
- **Rooms still track the platform on QBs.** ESPN's shown values priced QBs
  best ($2.5); ours is $1.8 high on QBs in the 1-QB keeper league.
- **RB and WR flip with the fix:** ours now runs $2.7 high on RBs and $2.7 low
  on WRs in the keeper room; the ESPN averages show the opposite sign on RBs.
  Two rooms disagree, so no position adjustment yet; the third auction
  (USO) is the tie-breaker.

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
