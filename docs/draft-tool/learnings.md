# Draft tool learnings (JEG-1667)

Methods tried, what held, what failed. One line each, newest last.

- Ours picks by source availability (Vegas prop per stat, else projection, else market); it does not average sources (Jeremy, 2026-11-27).
- With no chart source, `runValuePipeline`'s blended DDF Value is empty; read the projections version instead (2026-11-27).
- A Vegas source that lists only prop players distorts every other player through its own replacement line; Vegas must cover the projection's pool (review of f0fcfb1, 2026-11-27).
- Rooms pay close to their platform's shown values (ESPN keeper room: platform $3.7 MAE vs market $4.3), so price forecasts should lean on the platform (backtest, 2026-11-27).
- Walk-aways on the room's inflation strand cash when ours spreads value over more players than the market does; personal inflation fixes it (simulation, 2026-11-27).
- A simulation judged only by our own values cannot show our values are wrong; judge with a true value drawn first and independent errors (delta review of f0fcfb1, 2026-11-27).
- Without the market chart setting the position split, ours overprices RBs and underprices WRs against the keeper room (+$6.7 / -$6.5; backtest 2026-11-27, fallback build).
