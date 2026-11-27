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
| Ours | DDF draft value by availability, not averaged: Vegas season prop per stat (2026-09-12), else FantasyPros season projection (snapshot 2026-09-11, consensus of 2026-09-08), else market; expected-starts bench share |
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

## Results (ours by availability: Vegas, then projection, then market)

Re-run 2026-11-27 after Jeremy's decision: "Vegas when available is there,
then projections, then market. We are picking by what's available, not
averaging." Sources in the 2026 pool: 25 vegas, 88 vegas+proj, 286 proj,
0 market. Scored players: keeper room 19 / 57 / 40 / 0, ESPN averages
23 / 54 / 22 / 0.

**Auction 1 (12-team ESPN keeper league), raw dollars**

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias | Platform MAE | Platform bias |
|---|---|---|---|---|---|---|---|
| QB | 16 | $3.6 | +1.0 | $5.5 | +3.9 | $2.5 | -1.1 |
| RB | 41 | $7.9 | +6.7 | $5.0 | -2.1 | $4.9 | -1.2 |
| WR | 46 | $7.0 | -6.5 | $3.8 | +1.2 | $3.5 | +1.7 |
| TE | 13 | $3.8 | -0.4 | $2.1 | -0.4 | $2.1 | +1.1 |
| All | 116 | $6.5 | -0.1 | $4.3 | +0.2 | $3.7 | +0.2 |

**Auction 2 (ESPN 2026 average auction values)**, shape only (predictions
scaled to what was paid; ESPN's averages add up to $1,474):

| Position | n | Ours MAE | Ours bias | Market MAE | Market bias |
|---|---|---|---|---|---|
| QB | 16 | $3.9 | -1.1 | $3.8 | +0.4 |
| RB | 34 | $5.5 | +0.6 | $5.0 | -3.6 |
| WR | 38 | $6.2 | +0.6 | $6.6 | +3.2 |
| TE | 11 | $4.1 | -2.5 | $4.0 | -0.7 |
| All | 99 | $5.4 | +0.0 | $5.3 | +0.0 |

The blend-weight sensitivity table is retired with the blend.

## What it says

- **Picking by availability is further from what rooms paid** than the
  earlier blend: $6.5 per player in the keeper room (blend $4.0, market $4.3,
  platform $3.7) and $5.4 on ESPN's averages (blend $4.7, market $5.3).
  Ours is a value, not a forecast, but the gap is now large and one-sided.
- **The error is the position split.** Ours runs $6.7 high on RBs and $6.5
  low on WRs in the keeper room. With no market chart in the build, the
  pie's split across positions comes from projections alone, which in
  standard scoring favour RBs. (The trade chart's DDF Value takes its
  position split from the charts, JEG-1569.)
- **Rooms still track the platform:** ESPN's shown values priced the ESPN
  room best ($3.7 per player; QB $2.5).

Decision for Jeremy (does not average player values either way):

- **A (recommended): keep availability for each player's value, and let the
  market set only the position split of the pie,** as DDF Value does on the
  trade chart. Players are still priced from Vegas, then projection, then
  market; the market only decides how the pie divides between QB, RB, WR
  and TE.
- B: keep the pure fallback as built (projections set the position split).
- C: return to the 50 / 25 / 25 blend.

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
