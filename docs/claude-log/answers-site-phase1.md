## 2026-11-08 - JEG-1543 answers version phase 1: skeleton, static grid, privacy check

Contract: the parallel no-sources version at /answers/ (Jeremy's 2026-11-08 decisions D1-D6). Phase 1 is the page
skeleton (front door, DDF Values list), the pre-built grid of answer tables and the privacy check, behind the existing
noindex and linked from no public page. No value math change, no Supabase change.

Files: `pipelines/answer_tables.cjs`, `pipelines/build_answers_pages.py`, `pipelines/answers_privacy.py`, the sync
hook in `pipelines/sync_dashboard_artifacts.py`, `app/answers/*`, `tests/test_answers_site.py`, `docs/answers-site.md`,
a Makefile line (test-unit-modules) and a .gitignore line (`/dist/answers/`).

Verified (named checks): `python3.12 -m unittest tests.test_answers_site` (13 tests: checker broken variants, full
tree check with every table fingerprinted, 1,728 cells, parity with tests/_edge_pipeline_runner.cjs on 5 cells incl.
2 QB-eligible flex and bench 5/10, override rule vs ValueModel.applyDdfOverride on 56 cases, every page x 4 states x
1280/390/320 with request allowlist, body/DOM scans, globals, overflow and storage writes, DDF Value equal to the full
site's values.html on 2 settings, 3 broken page variants fail). Assumed: CI's node runs --experimental-strip-types
(other unit tests already need it); the preview run shows it.
