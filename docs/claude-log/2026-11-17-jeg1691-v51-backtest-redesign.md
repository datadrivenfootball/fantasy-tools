## 2026-11-17 - JEG-1691 v5.1 redesigned as a backtest (PR #1478, draft)

Contract: apply Jeremy's answers of 2026-11-17 (D1 "It should reflect that player's historical
mix"; D2 "Focus on backtesting not forward results for now"; D3 "If the logic plays out that way,
that's ok") to the v5.1 pre-registration. No code and no run; the locked v5 files are untouched.

### Verified (check named)
- The nflverse weekly file has 2015-2025 player-weeks with gsis id and position (5,363-6,037 rows
  a season; WR 25,813, RB 16,382, TE 12,898, QB 6,884), per a header and count read of
  `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`.
- `git diff origin/claude/JEG-1691-v5-prereg --stat` shows only v5.1 docs, the diag script and logs.

### Claimed, not confirmed
- That PPR minus Standard equals receptions exactly in that file for every row (true by the
  scoring definition; no row-level check yet). The backtest's B0 exactness check is where this gets
  verified.

### Review round 1 fixes (2026-11-17)
- Applied the reviewer's eight points and Jeremy's D-a A and D-b A as dated amendments.
- Verified: the doc edits only (`git diff`); no code and no run. The figures 9,684 zero rows and
  87% / 96% keyed coverage are the reviewer's counts and were not re-counted here.
