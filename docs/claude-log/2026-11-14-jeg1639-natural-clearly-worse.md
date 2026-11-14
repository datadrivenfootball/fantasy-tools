## 2026-11-14 - JEG-1639: Natural fit never contradicts the Why text

Contract: Jeremy, 2026-11-14 ("A"): Natural fit also requires their roster change better than -3% (not "clearly worse"),
on the same measure and rounding as the Why text; offers that fail move to Partner neutral.

Root cause: two tests. `tradeFit` passed their side when their bench-weighted chart-average change was within the noise
floor in points (`theirNet >= -tau`); the Why text bands the percent of roster worth (`rosterImprovementPct`). The noise
floor is often wider than 3% of a roster, so an offer could be Natural while the Why said "clearly worse ... unlikely to
accept" (screenshot: Adams + Kamara for Corum + Etienne, Theirs -3.2%). Both read the same view and chart keys on
find.html (`ddf-why.js` passes `ctx.analyst` to both), so the gap was the measure, not the inputs.

Change:
- `app/v2/finder.js`: the percent (`rosterChangePct`, `rosterWorth`, `shownPct`, `pctBand`, `PCT_MIN_BASE`,
  `PCT_BANDS`) moved here verbatim from `ddf-opportunity.js`, because the connector and Partners / Values evaluate
  finder.js without `ddf-opportunity.js`. `tradeFit` computes their percent in their valuation (`ctx.marketKey`,
  `ctx.chartKeys`) and `naturalFit` fails their side when the band is `clearly_worse`. Unsized (base under 20) does not
  block. `fitText` says why. FIT_TIPS natural updated.
- `app/next/ddf-opportunity.js`: `rosterImprovementPct`, `worth`, `shownPct`, `bandOf` delegate to finder.js (wording
  only here).
- `app/next/ddf-why.js`: the headline no longer says "stays about even" when the percent is clearly worse.
- `app/next/find-page.js`, `find.html`: natural-def, neutral-def and fit-note wording. Learn page and llms/skill text
  have no Natural fit definition to update (checked by search).

### Verified (check named)
- `tests/test_v2_finder_fit.py` checks 20 to 22: -3.2% (screenshot shape) and -3.0% are not Natural, -2.95% (shows
  -2.9) and -2.9% are; the text names the cause. New mutants: clearly worse allowed, -3.0 counted slightly worse, pct on
  your roster. Updated two mutant anchors ("projections ignored", "missing projection read as level") because the
  predicate line gained `&& pctOk` (rule changed by Jeremy).
- `tests/test_natural_pct_agree.py` (node `tests/node/natural_pct_agree_check.cjs`): over every pairing of the league
  fixtures, 8216 trades, no Natural fit with a clearly worse percent and the fit's percent equals the Why's; fails on a
  finder.js without the test.
- `tests/test_ddf_opportunity.py`: constants equal finder.js; partner percent equals `rosterChangePct`.
- Before/after Natural offers (scratch Playwright run on the built dist, find-engine `searchPartner`, every team vs every
  team, DDF vs Analyst charts, 1-2 players, no waiver list): seeded 12-team 5981 -> 5943; USO real rosters 1023 -> 991;
  Charlotte real rosters 1246 -> 1235; 0 label/text disagreements, 0 percent mismatches. Moved offers land in Partner
  neutral by `classify` (their side was inside the noise floor); samples checked were `neutral`.

### Claimed, not confirmed
- Live site behavior after deploy (checked at merge).
