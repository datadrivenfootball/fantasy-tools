# Answers version of the site (/answers/)

The no-sources version of Data Driven Football (JEG-1543): the same engine and saved league, DDF numbers only. No
source name, per-source value, chart comparison or source-naming methodology reaches the browser on this path.
Status: phase 1 (page skeleton, static grid, privacy check). Owner JEG-1543. Last verified 2026-11-08.

Decisions (Jeremy, 2026-11-08, design in the handoff folder `06-audit/jeg1543-answers-site-design-2026-11-08.md`):
same repo at `/answers/`, built from the same engine; hybrid static tables plus a `get-answers` edge function (grid for
common settings, server for the rest); the other team's side also shows the percent; partner ties ordered on the
server; connector answers mode by default plus a full URL for Jeremy; full site stays public with noindex.

## How it is built
- `pipelines/answer_tables.cjs` runs get-values' own pipeline (`supabase/functions/get-values/league.ts`,
  `pipeline.ts` over `dist/assets/value-model.js`) for every grid cell and writes `dist/answers/data/<cell>.json`
  (`[key, ddf, sd, low]`, players above 0 only), `players.json` (every QB/RB/WR/TE player: name, position, team) and `grid.json`. Cell id
  `<scoring>-<teams>-sf<n>-q<n>w<n>f<n>-b<n>`; RB 2 and TE 1 fixed; 1,728 cells, about 47 s on 8 workers locally and about 210 s on a 4-core CI runner. Checked tables are cached in
  `build/answers-cache/` keyed on the build tag and every input file, so repeat syncs in one checkout (CI test shards run
  one per test module) reuse them instead of rebuilding.
  `sd` = |charts version - projections version| / 2 (the finder's DDF-side noise). A player in `players.json` absent
  from a cell is priced at 0 there.
- `pipelines/build_answers_pages.py` copies `app/answers/` (pages, `answers-engine.js`, `answers.css`), stamps the
  build tag, writes the tables and runs `pipelines/answers_privacy.py` over every file and every table. On any
  failure (a finding, or node that cannot load the edge function's .ts modules) the sync removes `dist/answers` and
  warns, so nothing unchecked is published and the full site still deploys; `tests/test_answers_site.py` then fails
  where the tree is required (CI). noindex comes from sync's last step and from the pages' own robots meta.
- The pages read the full site's stores read-only (`ddf.v2.league-settings`, `ddf-v2-value-overrides`). Overrides
  follow `value-model.js` normalizeOverride / applyDdfOverride exactly (tested against ValueModel). A saved
  non-default basis is ignored with a notice. Settings off the grid (other counts, season weeks, advanced, position
  shares) withhold the list with a notice until the server phase.

## Privacy check (`answers_privacy.py`)
Banned text (source and publisher names, "Analyst charts", "Live market", "trade chart", island and file names),
numbers with 3+ decimals, exact table/players schema, column fingerprints against every per-player column in the
source bundle, and a file allowlist. `tests/test_answers_site.py` adds the browser view: every request stays under
`/answers/`, every response body and the DOM pass the text checks, no engine globals, no overflow at 1280/390/320,
DDF Value equals the full site's for the same saved settings, nothing is written to storage, and three broken
variants (fetches the source file, loads the engine, hidden source name) fail.

## Next phases
2. `get-answers` edge function (Recommendations, opportunity tier, partner order, other side as a word and percent)
   and answers-mode get-values for off-grid settings; deploy by the lead after Jeremy's yes.
3. Connector answers mode (`DDF_LINK_BASE`, no per-source tool output) plus the full URL for Jeremy.
