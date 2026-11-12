# 2026-11-11 JEG-1624: test_find_cards premise after the week 10 refresh

Jeremy, 2026-11-11: "Fix JEG-1624 now yourself in a separate PR (gated: CI green, independent review, PR CLEAN), merge it, confirm main's deploy goes green."

## What happened
Main's Pages deploy failed in `make test-core-shard-3` on every run from the data refresh a35a07c8c onward: `test_find_waiver_alternative.test_find_cards` reported "1440: no card for the long-named team". The test renamed `teams[3]` (Team 04) of the seeded league. After the refresh, Team 04 has no offer in the top list. The app code did not change: `find.html` and `find-engine.js` were last touched on 2026-11-08.

## Fix (PR #1436, squash 4946ac7f6)
The test reads the top offer's partner from the current data, renames that team to the long name, and runs the same checks. It fails with "fixture drifted" if there are no offers.

## Verified
- `tests.test_find_waiver_alternative`: 4 OK locally with `RENDER_TESTS_REQUIRED=1`, Chromium 1208, after `make reference && make sync`. Before the fix it failed with CI's message.
- Independent Opus review: MERGE. The old test passes on a35a07c8c~1 data and fails on current data. The new test passes on both. Card order is unchanged by the rename.
- PR #1436 CI: all checks green, including preview shards 1 to 5; PR CLEAN; bot report on head 941a4d8.

## Claimed, not confirmed
- This log landed with PR #1352 (JEG-1565), after #1436 merged, to answer Codex's review note that #1436 had no session log.
