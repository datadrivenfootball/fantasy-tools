# Draft tool learnings (JEG-1667)

Methods tried, what held, what failed. One line each, newest last.

- Ours picks by source availability (Vegas prop per stat, else projection, else market); it does not average sources (Jeremy, 2026-11-27).
- With no chart source, `runValuePipeline`'s blended DDF Value is empty; read the projections version instead (2026-11-27).
- A Vegas source that lists only prop players distorts every other player through its own replacement line; Vegas must cover the projection's pool (review of f0fcfb1, 2026-11-27).
- Rooms pay close to their platform's shown values (ESPN keeper room: platform $3.7 MAE vs market $4.3), so price forecasts should lean on the platform (backtest, 2026-11-27).
- Walk-aways on the room's inflation strand cash when ours spreads value over more players than the market does; personal inflation fixes it (simulation, 2026-11-27).
- A simulation judged only by our own values cannot show our values are wrong; judge with a true value drawn first and independent errors (delta review of f0fcfb1, 2026-11-27).
- Without the market chart setting the position split, ours overprices RBs and underprices WRs against the keeper room (+$6.7 / -$6.5; backtest 2026-11-27, fallback build).
- Vegas season lines sit 7-24% below FantasyPros 2026 projections by market (median ratio); scaling them to the projection level cut the keeper-room error $6.5 to $5.6 (2026-11-27).
- The market position split (two passes: chart weights, then `position_shares`) was tried and lost the 2026 outcome test against realized value; Jeremy chose the projection split (2026-11-27).
- Rooms pay closer to the market; realized 2026 value lands closer to ours (outcome test, `tools/draft_outcome.mjs`) (2026-11-27).
