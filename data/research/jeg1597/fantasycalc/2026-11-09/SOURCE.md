# FantasyCalc live values, 24 redraft settings (JEG-1598 sub-question 1, part of JEG-1597)

Public values endpoint, the same one the pipeline uses (`pipelines/pull_fantasycalc_full_feed.py`),
no credentials, User-Agent `Mozilla/5.0`, one request per setting, 2.5 s apart:

    https://api.fantasycalc.com/values/current?isDynasty=false&numQbs={1,2}&numTeams={8,10,12,14}&ppr={0,0.5,1}

- `ppr{ppr}_qb{q}_t{t}.json`: raw response bodies, 2026-11-09 06:42:38Z to 06:43:43Z UTC
  (`fetch_log.json` has each URL, time, HTTP status, row count). 196 rows each.
- `headers_check/`: four settings fetched again at 06:44:31-39Z with response headers
  (`Cache-Control: max-age=1200`); bodies identical to the first pull.
- `recheck/`: six settings fetched again at 07:02:30Z, after the cache window. The settings
  that had served the second base (`ppr0_qb1_t14`, `ppr0_qb1_t8`, `ppr0_qb2_t8`) were unchanged.
  The others had moved to that same base, so the first pull mixed two data refreshes (see the
  research note, section 2).

Fields used: `player.name`, `player.position`, `value`, `redraftValue`, `maybeTradeFrequency`.
Research only; not read by any pipeline. Analysis: `tools/research/jeg1597/fantasycalc_scoring.py`,
note `docs/research/jeg1597/fantasycalc-pegged-or-blend.md`.
