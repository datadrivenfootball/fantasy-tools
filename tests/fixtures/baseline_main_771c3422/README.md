Frozen copies of the value engine as it was on origin/main at 771c3422 (engine files last changed in 4c17ee6b,
JEG-1176). Until 2026-10-28 this was baseline_main_61ecb39e: the engine at 61ecb39e (JEG-1035, before JEG-1044 added
the value basis). tests/test_basis_overrides_render.py serves these in place of the live engine files and requires the current
engine, on the default basis, to give the same values at every league setting (the default path is byte-identical).

When a later change deliberately changes our default values, re-freeze: copy the engine files from main with that
change over these, and say so in its docs/claude-log entry. Do not edit them to make a test pass.

JEG-1073 (Jeremy, 2026-10-25: "Keep adj trade chart avg as the main ddf and projections as an alt"): our default values
changed deliberately (DDF Value is the four charts' Adjusted average). These frozen engines are pre-basis, so they were
not re-copied from a parent; instead the same default-rule edits as the live engine were applied to them
(value-model.js `blendedI = chartsI`; curve-widget.js `COMPOSITE_INPUT_KEYS`, `OVERRIDE_VERSIONS`, `COMPOSITE_VERSIONS.ddf_value`).
Nothing else in them changed, so the test still proves the basis feature leaves the default path untouched.

Re-frozen 2026-10-28 (render sweep, JEG-1121): JEG-1121's bench-seat allocation (merged in #957, 47fd50ca, with the
Python and spec references) deliberately changed default values at every league setting, so the pre-basis copies no
longer matched. Porting each later value change into the pre-basis engine (as was done for JEG-1073) does not scale,
and JEG-1044 is merged, so the copies were replaced with the engine files of origin/main at 771c3422, byte for byte.
Checked in Node with the widget on the committed data (12 combos): the 61ecb39e copies equal main's engine through
d377e659 and differ from #957 on; main's engine gives the same rows on the default, setBasis(null),
{mode: "default"} and the equal four-chart blend. The test is now a regression lock on the default path since 771c3422:
a later deliberate value change re-freezes it again from main after that change merges (copy
app/trade-value-chart/assets/value-model.js and curve-widget.js here) and says so in its claude-log entry.

Re-frozen 2026-10-28 (JEG-1142, PR #1044): switching off the promotion/demotion model (PROMOTION_MODEL_ENABLED = false)
deliberately changes default values at every league setting, so value-model.js and curve-widget.js were copied here
byte for byte from the PR head, which is main's engine once it merges. The folder keeps its old name so the test's path
does not move.

Re-frozen 2026-11-08 (JEG-1588, Jeremy 2026-11-08: "re-freeze the baseline engine in test_basis_overrides_render from
current main"): value-model.js and curve-widget.js copied byte for byte from origin/main at 1292e8fa (engine files last
changed in e1bebdf8, JEG-1571). Deliberate engine changes since the JEG-1142 freeze, among them JEG-1335 fractional seats
and JEG-1571 QB-eligible flex, had made 476 players differ at half_ppr/10.

How to re-freeze (only after a merged, deliberate default-value change; never to make a red pass):
  git show origin/main:app/trade-value-chart/assets/value-model.js > tests/fixtures/baseline_main_771c3422/value-model.js
  git show origin/main:app/trade-value-chart/assets/curve-widget.js > tests/fixtures/baseline_main_771c3422/curve-widget.js
then add a dated paragraph here (commit, reason, decision) and a docs/claude-log entry, and check that the Broken* tests
in tests/test_basis_overrides_render.py still fail.
