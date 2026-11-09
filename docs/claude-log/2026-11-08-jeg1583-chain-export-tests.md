## 2026-11-08 - Chain red on main: export and rounding tests / JEG-1583

Related: JEG-1485 (weekly rollover audit), JEG-1512 (never-late guardrail).

### What failed (rebuild-chain.yml on main, 2026-11-08)
- 15:00Z to 18:00Z (4 runs): `tests.test_team_opportunity_render` "16.82 ÷ 178.44 = 9.42% shown 9.4% does not recompute".
- 18:41Z, run 42511248498: the first `make validate` failed `tests.test_learn_engine_parity` "half_ppr/10/sf0: build-up cbs shown totals do not divide to the shown factor". post-validate held CBS and ran validate again. That pass failed `tests.test_seeded_hold_build.test_static_export_passes_on_the_held_build`, whose subprocess `tests.test_static_export.test_published_indexed_is_one_factor_on_the_anchor_pie` reported "cbs full_12: Indexed pie 2421.4 != anchor pie 2407.5".
- 20:45Z, run 42514998797: `test_learn_engine_parity` failed on two CBS combos plus `test_round6_waiver_line_and_notes` (usatoday). "recovery declined: validation failures name multiple sources", so nothing was held or published.

### Root causes (all are test arithmetic or test setup. No export, page or value-model bug.)
1. **Seeded hold build un-held the real holds.** `seeded_build()` removed every `validationHold`/`promotionHold` before it added its seeds. When the chain holds a chart after an ESPN re-bake, that chart's section is the last promoted one, which is indexed on the previous ESPN anchor. With the hold stripped, the gate checked old data against the new anchor. Every held build failed, which defeats "hold a source, never take the whole site down" (JEG-520/569). Reproduced on the run's candidate-evidence tree (candidate 2e7a3af9): the CBS combos in the candidate are byte-identical to main's, and the ESPN combos differ. Fix: keep the build's own holds and add the seeds on top. The direct `test_static_export` run already skips the real holds (`tests/_holds.py`), so the seeded run now matches the direct run. The seeded FantasyCalc and Razzball checks are unchanged.
2. **Factor-divide tolerance was below the display rounding.** The page shows the DDF total to 2 dp and the factor to 6 significant figures. The factor is exactly DDF total ÷ chart total (jeg-685). The worst case is 0.005 / chart total + half a unit in the 6th figure. The old bar of 5e-6 x factor is smaller than that worst case. Reproduced in the candidate tree (8a93a6e3) with diagnostics: anchor 1932.561898, chart 1705.5, factor 1.13313509, shown 1.13314. 1932.56 / 1705.5 = 1.1331340, which is 6.0e-6 from the shown factor, against a bar of 5.67e-6 and an exact bound of 7.9e-6. **This loosens the check** to the exact rounding bound (`factor_rounding_bound`). A wrong factor still fails beyond about 8e-6 relative. `test_guard_catches_a_wrong_number` is unchanged.
3. **Waiver-line wording when every allocation rosters the same count.** `numbers.js` prints "(34 rostered, read at QB35)" when lo == hi, by design. The test only expected "34 to 34 ... QB35 to QB35". The test now builds the same collapsed form. This is not a loosening.
4. **Team gain ÷ total tolerance was below the display rounding.** The page prints gain and total to 2 dp and the percent from the exact values to 2 dp. Recomputing from the rounded operands can differ by 0.005 + 100 x 0.005 x (1/total + gain/total²), which is 0.0081 at 16.82 / 178.44. The old bar was 0.006 and the observed difference was 0.0061. **This loosens the check** to that exact bound (`ratio_rounding_bound`). The cut-to-1-decimal shown check and the gain check (0.006) are unchanged.

5. **R6-OP-07 example pinned to one player.** On the newest candidate (adaf9505), USA Today rosters 34 QBs in all 6 superflex allocations. Josh Allen's "published − waiver line" therefore equals the engine's value above the waiver line at 2 dp, and the premise guard failed with "the check proves nothing". The example now stays Josh Allen when his subtraction differs. Otherwise it is the highest-DDF USA Today player above the waiver line whose subtraction does differ. Every R6-OP-07 assertion and the premise guard are unchanged. It still fails if no such player exists. This is not a loosening.

None of these changes touch a published number, the engine or an export. Items 2 and 4 recur whenever new data lands near a rounding edge, which explains why they came and went across today's runs.

### Verified (check named)
- Reproduced each failure on the downloaded candidate-evidence trees (runs 42511248498 and 42514998797) before the fix.
- See the PR for the post-fix checks on the newest candidate's data (candidate adaf9505) and for CI.

### Left open
- The class remains: any display-precision check with a hand-picked tolerance can go red on new data. Decision A in the JEG-1485 audit (data gates only in the chain) removes that coupling.

### Follow-up, 2026-11-09 (second PR)
- The first post-fix chain run (42535166048, which checked out main with #1384) failed only `test_round6_waiver_line_and_notes`: "no USA Today player's subtraction differs at this setting". On that candidate (ba7a75fb, USA Today fidelity-held), a browser probe over 12 settings found 0 of 151 USA Today players above the waiver line whose subtraction differs at half PPR/10/SF, 17 of 148 for CBS, and 0 for USA Today at 4 other settings. That is data, not a page bug: the page's restatement branch renders for CBS.
- Fix: the R6-OP-07 example searches USA Today first and then CBS at the same setting. The assertions and the premise guard are unchanged, and the guard still fails if neither chart has such a player. Not a loosening.
- Checks: `tests.test_learn_engine_parity` (11 tests) OK on candidate ba7a75fb's data and on main's committed data.
