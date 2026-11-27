## 2026-11-27 - EDDF alternate value version (JEG-1735, part of JEG-1733)

Contract: build EDDF, an off-by-default alternate value version (equal-weight mean of the charts'
Adjusted values plus one rank-implied value per fresh ranker), with a registry, Python reference,
JS twin, tests and evidence on real Adjusted values. DDF Value must not change. Jeremy, 2026-11-27:
"every stable source is a separate EQUAL-WEIGHT source in the average, NOT pooled into one 1/5th
source"; answered "A" (relayed by the lead session) to amend `docs/pipeline-rules.md` section 7 and
to wire the JS engine only after PR 1332 merges or the hot-file slot is released.

### Verified (check named)
- Isotonic curve, anchors, stale boundary (14 in, 15 out), QB switch, equal weight with each ranker
  its own source, chart-down and all-stale cases, registry rows, 12-team/1-QB availability:
  `tests.test_eddf` (16 tests).
- DDF Value unchanged: `tests.test_eddf.DdfUnchanged` recomputes the visible-chart mean from the
  reference's own Adjusted rows (half PPR, 12 teams) and matches `ddf.blended` to 9 places, and
  asserts `value_reference.py` never mentions eddf.
- JS twin equals the Python module on `tests/fixtures/eddf_parity.json` (node, 9 places):
  `tests.test_eddf.JsParity`.
- Evidence numbers in `docs/research/jeg-1735-eddf.md`: `tools/research/eddf_evidence.py` run on
  2026-11-27, written to `docs/research/data/jeg1735/evidence.json`.
- `make validate` (local, exit 0) ran on the branch before the Tuesday-rule commit; `value_check compare
  --rerun-engine --strict` (0 differences) and `check_rank_guard.py` (12 checks, 0 inversions) ran after it.
  This PR touches no DDF code path. The Tuesday-rule commit was re-checked with `tests.test_eddf` and
  `tests.test_validate_shards` only, not a second full `make validate`.
- Makefile shard parity after adding the test to test-core and shard 2: `tests.test_validate_shards`.

- Variants (per_expert default, site_once, grouped) and weights: `tests.test_eddf.Variants`.
- Correction inside the session: the first scramble-robustness figure (EDDF 14 to 26% less moved)
  came from one random permutation; `tools/research/eddf_variants.py` and `eddf_evidence.py` now
  average 15 shared permutations and show about 0 to 4% under the Tuesday rule (3 to 8% under the first 14-day run). Both numbers are in this branch's history only
  as this note; the write-up carries the corrected one.
- Tuesday reset (Jeremy, 2026-11-27): `tests.test_eddf` pins that a list dated before the most recent
  Tuesday is stale inside the 14-day backstop and that a Tuesday-dated list is fresh; the JS twin
  and `tests/fixtures/eddf_parity.json` (regenerated) agree. Evidence reruns: 9 fresh lists in Half
  PPR instead of 14; the numbers in `docs/research/jeg-1735-eddf.md` are the Tuesday-rule run.
- Review fixes (db2e50315 review): JS twin moved out of app/ to `pipelines/eddf_model.js` so it is not
  published; `tests.test_eddf` now covers a disabled row and the all-candidates-disabled check;
  amendment date corrected to 2026-11-28; `docs/decisions.md` entry added; league value total and
  weight-vs-independence added to the write-up.
- Candidate-file study: `tools/research/eddf_candidates.py` -> `candidate_study.json`
  (seven files, all disabled registry rows).

### Claimed, not confirmed
- CI: the PR is a draft, and the repo skips the expensive checks (preview, v2-render) on drafts, so
  they show red by design; there is no green CI on this head. Marking it ready would make 10 ready
  PRs against the cap of 8.
- Hot files were not edited (value-model.js, value_reference.py, curve-widget.js, v2.js): the
  slot is held by PR 1332 (value-model.js) and PR 1473 (v2.js). Only new files plus Makefile,
  `docs/pipeline-rules.md`, `docs/README.md`.
- Supabase `ros_rankings` was not read (anon key refused, no auth store read). Lists come from
  `pipelines/pull_ros_rankings.py` run on 2026-11-27. One list date only; no ranker history.
- The JS engine hook, a live feed, and publishing any EDDF number: not built; each needs the slot
  and Jeremy's yes.
- Five private evidence pages were published from `docs/research/data/jeg1735/*.json` by a
  scratch script that is not in the repo.
- The relayed "A" and the 2026-11-28 "One per expert" ruling came through the lead session, not typed here.
