# Nominations and the opponent model (JEG-1668 research, Phase 0)

Recommendations only; nothing here is built. Every option list has A as the
recommendation. Inputs are the engine's board (`docs/draft-tool/engine.md`):
inflation, max bids, walk-away, push floor.

Jeremy's goals, in his words: drain rivals' capital "without getting caught
in a player we don't want", "bid in a player we want that other rosters
aren't constructed to take", and "think through the incentives of every other
roster at any given time to find opportunistic bids ... that give us
arbitrage value and genuinely help our roster construction".

## 1. Opponent model (build first: nominations read from it)

For every rival, at every sale:

| Field | Meaning |
| --- | --- |
| Money left, open slots, max bid | From the engine |
| Need by position | Open starting slots (QB, RB, WR, TE, FLEX) still to fill |
| Dollars per open slot | Money left / open slots: who can still spend big |
| Willingness for a player | `min(max bid, inflated market price x need factor x tendency)` |
| Clearing price for a player | The second-highest willingness in the room, plus $1 (the winner pays just over the runner-up) |

From those, four flags per available player:

- **Bid**: our walk-away is at least $2 over the clearing price. A real
  discount.
- **Uncontested**: one rival or none has both a starting need and the money
  for him. Nominate him when we want him (section 2, play 2).
- **Drain**: two or more rivals with a starting need can pay over our
  walk-away. Nominating him makes them spend.
- **Scarcity**: rivals needing a starter at a position vs starters left in the
  current tier. Over 1.0, the tier will be overpaid; the cliff is close.

Decisions:

- **O1 Rival willingness.** A) Inflated market x need factor (1 for an open
  starting slot, 0.6 bench only, 0 no slot), capped at max bid. B) Max bid
  only (treats every rival as willing to spend everything). C) Inflated
  market only (ignores need).
- **O2 Which market sets willingness.** A) Platform price blended with market
  (the backtest: rooms paid closest to the platform's shown values, $3.7 MAE
  vs $4.3). B) Market only. C) Platform only.
- **O3 League tendencies.** A) A per-position multiplier from prior drafts
  (paid / market at sale), shrunk halfway to 1 unless two or more years agree.
  B) One league-wide multiplier. C) Off.

## 2. Nomination plays

The tool scores every available player for each play and shows the top three
nominations with the play, the reason and the risk.

| Play | When | Pick | Risk and guard |
| --- | --- | --- | --- |
| 1. Drain | Early, and whenever rivals are flush | A fade (market over ours) with a Drain flag, highest (clearing price - our walk-away) first | Stuck with him: we only bid to the push floor, which is never above our walk-away |
| 2. Uncontested buy | Any time a target has the Uncontested flag | A target whose likely second bidder is weak; nominate before those rivals fill the need or get money back by others' spending | Someone with a bench slot bids him up: we stop at walk-away |
| 3. Tier cliff | Scarcity over 1.0 at a position we have filled | The second-to-last starter in the tier; rivals who need the position overpay for him, then the last one | We do not need him, so push floor only |
| 4. Price discovery | First nominations | A mid-priced player we do not want at a position many rivals need | Tells us the room's inflation before our targets come up |
| 5. Endgame $1 | When rivals' max bids collapse | Our $1-$3 targets once every rival who can roster him is at max bid $1 or $2 | None; nominate at the bid that wins outright |

Decisions:

- **N1 Default mode.** A) Automatic mix: Drain and Price discovery early,
  Uncontested buy whenever it fires, Tier cliff mid-draft, Endgame late; each
  suggestion labeled with its play. B) Jeremy picks the play by key. C) Drain
  only.
- **N2 When to switch from draining to buying.** A) Buy as soon as a target
  shows the Uncontested flag, and from the moment a third of the room's money
  is spent drain only when it does not delay a target. B) After a fixed number
  of nominations (for example 2 rounds). C) Never automatically.
- **N3 What counts as a drain.** A) Clearing price at least $3 over our
  walk-away and at least two rivals with a starting need who can pay it.
  B) Simply the most expensive player left. C) Any fade.
- **N4 How many suggestions.** A) Top three, one per play where possible.
  B) One. C) A full ranked list.

## 3. What shows live (fast enough mid-draft)

All of it recomputes from the board after each sale: per rival a row with
money left, max bid, needs; per player the four flags, the clearing price
and our walk-away and push floor. One key accepts a nomination suggestion.
No server call: it is the same client-side state the link saves.

## 4. Snake mode (Phase 2)

Same opponent model; the clearing price becomes the chance a player is gone
before our next pick (from ADP and its spread, adjusted by each team's needs
between our picks). Uncontested becomes "will still be there next pick".
