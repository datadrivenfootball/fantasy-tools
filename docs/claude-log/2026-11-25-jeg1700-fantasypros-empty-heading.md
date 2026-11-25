## 2026-11-25 - FantasyPros Week 12 ingest failed closed on an empty heading / JEG-1700

Contract: find why the FantasyPros Week 12 ingest failed and fix it so Week 12 FantasyPros reaches the site.
PR #1538, branch `claude/project-thread-n8nb42`. Jeremy, 2026-11-25 03:25 UTC: "Don't wait for me, don't wait for
6 am. Fix it".

### What failed
`trade-chart-ingest.yml` (fantasypros, probe-dispatched) failed at 18:10, 19:10, 20:10 and 21:10 UTC on 2026-11-24
with `FantasyPros position tables found: ['RB', 'WR', 'TE'] (need QB, RB, WR, TE once each)` on
`.../fantasy-football-trade-value-chart-week-12-2026/` (week validated 12). After four failures on the same content
the source probe stops re-dispatching, so a rerun alone would have changed nothing.

### Root cause
Dry run 45539703581 (this branch, commit 5e99f562) printed the page outline: `h3 'Quarterback Fantasy Football
Trade Value Chart'`, then an empty `h3 ''`, then the QB `<table>`. `parse_tables` reset its position on every
h2/h3, so the empty heading cleared "QB" and the QB table was skipped. RB, WR and TE have no empty heading.

### Fix
`ops/watchdog/pull_fantasypros.py`: one walker (`_position_tables`) for `parse_tables` and `parse_superflex`.
An empty heading (no text after stripping tags, whitespace, soft hyphens and zero-width characters) keeps the
position; a heading with text still resets it. Hardening in the same walker: a table opens only on `<table`
followed by whitespace or `>`, and a heading closes at its own level. A failed parse prints `page_outline()`.

### Verified (check named)
- `tests/test_pull_fantasypros_parse.py` + `test_pull_fantasypros.py` + `test_weekly_fantasypros_contract.py` +
  `test_jeg1172_fantasypros_w8_trace.py`: 55 pass, 1 skipped. The four new parse tests fail on main's parser.
- Dry run of the fix head against the live page: see PR #1538.

### Claimed, not confirmed
- FantasyPros Week 12 on the live site: needs the write ingest, the chain and the deploy after merge.

### Same cause in the fidelity pulse (added 14:40 UTC)
After the FantasyPros Week 12 write ingest (04:01) the fidelity pulse held FantasyPros **red** on
`publisher_vs_stored` from 06:40: "438/438 values match exactly ... 32 stored players not on the page; parse notes:
no table found for QB". The pulse has its own table reader (`pipelines/fidelity_pulse.py` `_TableParser`). It
already skipped a whitespace-only heading, but zero-width characters and soft hyphens are not whitespace to
`str.split()`, so the empty `<h3>` replaced the QB heading and the QB table had no position. A red hold hides the
source's curves on the page, so the next deploy of main would hide FantasyPros. Fix: strip the same invisible
characters before the empty check. Test: `tests/test_fidelity_pulse.py`
`Parsers.test_empty_heading_keeps_the_position` (fails on main's reader; 58 pass with the fix).

### Why USA Today Week 12 stayed off the live site (added 15:10 UTC)
USA Today published Week 12 at 10:10 UTC; it was ingested at 12:35 and built into main at 13:48 (df072631,
data-gate and rendered gate passed). The live site stayed on the 04:24 build because no deploy finished:
test-core shard 1 now runs 22 to 30+ minutes with setup, and its job limit is 30. Deploy run 45627372353
(df072631, a data commit that may deploy on its data checks) had shard 1 cut at 30:12; the run was then cancelled
before its deploy job got a runner. Run 45630372379 (84be8ac2) hit the same limit at 14:55. Fix:
`timeout-minutes: 45` for `validate-shard` (pages.yml) and `preview-shard` (preview.yml), within
`test_ci_speedup_workflows`' bound of 45; that test's removal check names the new value.
