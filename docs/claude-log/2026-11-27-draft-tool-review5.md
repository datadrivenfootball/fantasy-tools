## 2026-11-27 - Draft tool: fourth Opus review of 31faf01 corrections (part of JEG-1667)

Contract: fix the fourth review's nine findings on top of 31faf01, each with a
test for its probe input, and push as one head. Draft PR only; nothing merges
or deploys without Jeremy's yes. d58c0d7 stays unpushed on
`claude/draft-position-split-d58`.

### Changes
1. A null, "", boolean or non-numeric Vegas line is missing, never 0
   (`num`/`hasNum` in the engine; the backtest drops such rows).
2. A season header may hold only stat words, season words and a year; a known
   player's name may lead it. Monthly, rest-of-season, home and conditional
   markets are refused.
3. A market's scale factor needs 10 players (`MIN_FACTOR_N`); below that the
   pooled same-type factor (yards / TDs / receptions), else 1. Each build
   reports `vegasFactorBasis` and the counts; the audit page shows them.
4. Factors are no longer stored: the paste tool's meta says the engine
   recomputes them, and the engine no longer reads an outside factor.
5. A market-only player takes his rescaled market dollars directly
   (`fixedDollars`, `pricesFromWeights(..., fixed)`); the rest of the
   surplus is split by weight.
6. `boardRow` throws when a priced player has no price source; unpriced rows
   read "unpriced". The simulator, worked-example driver and test states
   now pass a source.
7. Parser: "'25" years, "1375½", a whole number after a split side (unsigned
   odds), trailing text after an over/under line, unread number lines
   (Greek "Ο"), ambiguous names.
8. The outcome test scores every predictor on one set (market or realized
   above $1); `errors`/`commonSet` exported.
9. Docs: backtest.md inflation +0.2% and the $1.3 gap; engine.md A - B
   +3.2; learnings.md 7-19%; data-sources.md and engine.md rules above.

### Verified (check named)
- 140 draft tests pass (`tests.test_draft_*`). The 27 new probe tests were
  run against 31faf01's code: 24 fail there; the 3 that pass are guards
  for headers and odds that must keep reading.
- Backtest re-run: identical to 31faf01 (keeper room ours $5.55 / market
  $4.26 / platform $3.67; ESPN averages $6.18 / $6.66), since 2026 has no
  market-only player and no null lines.
- Outcome test on the common set (MAE $, ours / market / platform):
  keeper 9.84 / 11.32 / 11.60 (174 players), half PPR 8.92 / 9.96 / 10.12
  (182), ESPN PPR 8.16 / 8.95 / 8.75 (170). Vegas unscaled: ours 10.16 /
  9.04 / 8.40, market unchanged.
- 2026 factors are all on their own market's sample (basis "market").
- Simulator smoke run (3 drafts) completes with the source rule.

### Claimed, not confirmed
- The 300-draft simulation was not re-run; prices and policies are unchanged.
- Personal vs room inflation under the realized judge is not yet diagnosed.
