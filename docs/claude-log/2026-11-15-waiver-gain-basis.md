# JEG-1648: waiver pickups by gain basis (2026-11-15)

Max Logan's request: filter pickups by gain over bench players, not only starters.
Decision (Jeremy, 2026-11-15): bench players are already discounted per the DDF scoring methodology; use the engine's existing bench value. No new discount, no value math change.

## What changed
- `app/next/find-engine.js`: `DDF.find.pickupsByBasis(results, basis, min)` and `DDF.find.BASES`. Starter gain = `starterDelta` (default, same filter and sort as before). Bench gain = the Waivers evaluation's `benchDelta` (weighted bench change, with the drop it suggests) for pickups that do not improve a starter. Both = starter list, then bench list.
- `waivers.html` / `waivers-page.js`, `find.html` / `find-page.js`: a "Gain basis" select, a basis label on each card, bench cards show "Depth value (bench)".
- Trade-search waiver alternative (`waiverPool`) is unchanged: starter gain only.

## Verified (check named)
- `tests.test_waiver_gain_basis` (4 tests): synthetic full roster where one free agent beats a bench player and no starter; default list equals the old filter; 390px no sideways scroll on both pages; drift guard.
- `tests.test_build_waiver_handoff`, `test_find_engine_parity`, `test_find_waiver_alternative`, `test_build_any_waivers` still pass.

## Claimed, not verified
- `make validate` and the full suite were not run locally. Bench gain with the Any players list and K/DEF seats: K/DEF rows carry no deltas so are never listed; the Any list uses the same candidate entries as Starter gain.
- Not checked on a physical phone; 390px emulation only.
