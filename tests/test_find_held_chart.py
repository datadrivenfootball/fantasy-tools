"""Trade & Waiver Recommendations when an analyst chart is on hold (Jeremy 2026-11-18, option A, plus the empty text).

The default "Their valuation" is the analyst charts (the mean of CBS Sports, USA Today and FantasyPros). Before this
change one chart on hold (a mixed week) turned that average off, so no offer got a fit label and every team showed zero
Natural fits under "No offers clear the bar". What we guard on find.html with the seeded league, holding charts the way
the page sees a hold (TradeValueCurveControls.getSourceInfo reports them unavailable), at 1440x900 and 375x812:
- all three charts: context().analyst is all three, no hold note;
- USA Today on hold (2 of 3): context().analyst is CBS Sports and FantasyPros, Natural fits are listed, no offer is
  "Fit not judged", the note names USA Today and the two charts fit uses, and every Natural fit card's "Them" number
  equals tradeFit recomputed here on an average of those two charts computed in this test (not withChartAverage);
- the same hold with DDF on both sides: no note (no analyst chart is read);
- USA Today and FantasyPros on hold (1 of 3): fails closed: no Natural fits, every listed offer is "Fit not judged", and
  the Natural fit empty text says fit can't be judged and names both charts instead of "No offers clear the bar";
- on 375 the page does not scroll sideways and the empty text is on screen.
The charts held are picked from the served week (plan()): in a week that already has one on hold, the 2-of-3 case is the
week as served and the expected copy names whichever charts are held.
Discrimination: with the old all-three rule served (MIN_ANALYST = 3) the 2-of-3 case has no Natural fits (the test fails).
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_find_engine_parity import APPLY, READY, SET
from tests.test_team_engine_parity import seed_script, seeded_league

# Report the given charts as unavailable (what the page reads for a chart on hold) and search again.
HOLD = r"""async (keys) => {
  const C = window.TradeValueCurveControls;
  if (!C.__orig) C.__orig = C.getSourceInfo;
  C.getSourceInfo = o => C.__orig(o).map(i => keys.includes(i.key) ? Object.assign({}, i, {available: false}) : i);
  await DDF.findPage.run(true);
  return true;
}"""

READ = r"""() => {
  const ctx = DDF.find.context(), note = document.getElementById('analyst-note');
  const cards = sel => [...document.querySelectorAll(sel + ' [data-offer]')];
  const empty = document.querySelector('#natural-table .empty');
  const r = empty ? empty.getBoundingClientRect() : null;
  return {analyst: ctx.analyst, missing: ctx.analystMissing, natural: cards('#natural-table').length, neutral: cards('#all-table').length,
    unjudged: DDF.findPage.state.groups.filter(g => g.cls === 'unjudged').length, groups: DDF.findPage.state.groups.length,
    note: note.hidden ? '' : note.textContent.trim(), empty: empty ? empty.textContent.trim() : '',
    emptyOnScreen: r ? r.width > 0 && r.left >= 0 && r.right <= window.innerWidth : false,
    wide: document.documentElement.scrollWidth - window.innerWidth};
}"""

# Every Natural fit card's "Them" number, recomputed with tradeFit on rows whose chart_avg this test computes itself.
RECOMPUTE = r"""(keys) => {
  const F = window.TradeValueFinder, finite = v => typeof v === 'number' && isFinite(v);
  const avg = rows => rows.map(r => {
    const vals = keys.map(k => r.values ? r.values[k] : undefined);
    return Object.assign({}, r, {values: Object.assign({}, r.values, {chart_avg: vals.every(finite) ? vals.reduce((a, b) => a + b, 0) / vals.length : null})});
  });
  const ctx = DDF.find.context(), out = [];
  DDF.findPage.visible().filter(g => g.cls === 'natural').forEach(g => {
    const t = DDF.findPage.selected(g), mine = avg(g.mineRows), theirs = avg(g.theirRows);
    const by = new Map(mine.concat(theirs).map(r => [String(r.player_key), r]));
    const w = rs => rs.map(r => by.get(String(r.player_key)));
    const fit = F.tradeFit({mine: {roster: mine, leaving: w(t.give), arriving: w(t.receive)}, theirs: {roster: theirs, leaving: w(t.receive), arriving: w(t.give)}},
      {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: 'ddf_value', marketKey: 'chart_avg', chartKeys: keys, z: F.FIT_Z});
    const card = [...document.querySelectorAll('#natural-table [data-offer]')].find(c => c.dataset.partner === g.partner
      && c.dataset.give === t.give.map(r => String(r.player_key)).join(',') && c.dataset.receive === t.receive.map(r => String(r.player_key)).join(','));
    out.push({id: g.id, want: DDF.find.shown(fit.them.starterDelta), page: card && card.querySelector('[data-lineup="them"] .lm-d') ? card.querySelector('[data-lineup="them"] .lm-d').textContent.trim() : null});
  });
  return out;
}"""

ANALYST = ["cbs", "usatoday", "fantasypros"]
NAMES = {"cbs": "CBS Sports", "usatoday": "USA Today", "fantasypros": "FantasyPros"}


def names(keys):
    n = [NAMES[k] for k in keys]
    return "".join(n) if len(n) < 2 else ", ".join(n[:-1]) + " and " + n[-1]


def held_text(keys):
    return names(keys) + (" is" if len(keys) == 1 else " are") + " on hold"


def plan(available):
    """Which charts to hold for the 2-of-3 and 1-of-3 cases, from what the served week already has: with all three,
    USA Today is held (then FantasyPros too); in a week with one already on hold, the 2-of-3 case is the week as served."""
    missing = [k for k in ANALYST if k not in available]
    two = missing if missing else ["usatoday"]
    left = [k for k in ANALYST if k not in two]
    one = [k for k in ANALYST if k in two or k == left[-1]]
    return two, one


def _league():
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:3]
    return lg


def _run(viewport, overrides=None, full=True):
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    if not (DIST / "find.html").exists():
        raise _render_env.unavailable("dist/find.html is not built")
    out, errors = {}, []
    with serve(overrides=overrides) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        try:
            ctx = browser.new_context(viewport=viewport)
            ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
            ctx.add_init_script(seed_script(_league()))
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
            page.evaluate(APPLY, ["half_ppr", 12, False])
            page.wait_for_timeout(300)
            page.wait_for_function(READY, timeout=120000)
            out["all"] = page.evaluate(READ)
            # From the charts the week is missing, not context().analyst (null under the old rule in a hold week).
            available = [k for k in ANALYST if k not in out["all"]["missing"]]
            if len(available) < 2:
                raise unittest.SkipTest(f"the served week has fewer than two analyst charts: {out['all']['missing']}")
            two_hold, one_hold = plan(available)
            out["plan"] = (two_hold, one_hold)
            page.evaluate(HOLD, two_hold)
            page.wait_for_function(READY, timeout=120000)
            out["two"] = page.evaluate(READ)
            if full:
                out["two_fit"] = page.evaluate(RECOMPUTE, [k for k in ANALYST if k not in two_hold])
                page.evaluate(SET, ["their-valuation", "DDF"])
                page.wait_for_timeout(300)
                page.wait_for_function(READY, timeout=120000)
                out["two_ddf"] = page.evaluate(READ)
                page.evaluate(SET, ["their-valuation", "Market"])
                page.wait_for_timeout(300)
                page.wait_for_function(READY, timeout=120000)
                page.evaluate(HOLD, one_hold)
                page.wait_for_function(READY, timeout=120000)
                out["one"] = page.evaluate(READ)
            ctx.close()
        finally:
            browser.close()
    out["errors"] = errors
    return out


def setUpModule():
    _render_env.ensure_built()


class FindHeldChartTest(unittest.TestCase):

    def check(self, viewport):
        r = _run(viewport)
        self.assertEqual(r["errors"], [])
        a, two, ddf, one = r["all"], r["two"], r["two_ddf"], r["one"]
        two_hold, one_hold = r["plan"]
        if a["analyst"] == ANALYST:
            self.assertEqual(a["note"], "")
            self.assertGreater(a["natural"], 0, a)
        # 2 of 3: fit is judged on the other two and said so.
        kept = [k for k in ANALYST if k not in two_hold]
        self.assertEqual(two["analyst"], kept)
        self.assertEqual(two["missing"], two_hold)
        self.assertGreater(two["natural"], 0, two)
        self.assertEqual(two["unjudged"], 0, two)
        self.assertEqual(two["note"], held_text(two_hold) + " this week, so fit on the analyst charts uses " + names(kept) + ".")
        self.assertTrue(r["two_fit"])
        self.assertEqual([x for x in r["two_fit"] if x["page"] != x["want"]], [], r["two_fit"][:3])
        self.assertEqual(ddf["note"], "", "no note when neither side reads the analyst charts")
        # 1 of 3: fails closed, and the empty text says why.
        self.assertIsNone(one["analyst"])
        self.assertEqual(one["natural"], 0, one)
        self.assertGreater(one["neutral"], 0, one)
        self.assertEqual(one["unjudged"], one["groups"], one)
        self.assertEqual(one["note"], "")
        self.assertEqual(one["empty"], "Fit can’t be judged this week: " + held_text(one_hold)
                         + ". Offers are listed under Partner neutral as “Fit not judged”.")
        self.assertNotIn("clear the bar", one["empty"])
        return one

    def test_desktop(self):
        self.check({"width": 1440, "height": 900})

    def test_phone_375(self):
        one = self.check({"width": 375, "height": 812})
        self.assertLessEqual(one["wide"], 0, "the page scrolls sideways at 375")
        self.assertTrue(one["emptyOnScreen"], "the empty text is not within the 375 viewport width")

    def test_guard_fails_with_the_old_all_three_rule(self):
        path = DIST / "find-engine.js"
        if not path.exists():
            raise _render_env.unavailable("dist/find-engine.js is not built")
        src = path.read_text(encoding="utf-8")
        anchor = "var MIN_ANALYST = 2;"
        self.assertIn(anchor, src, "anchor not found in find-engine.js")
        r = _run({"width": 1440, "height": 900}, overrides={"find-engine.js": src.replace(anchor, "var MIN_ANALYST = 3;").encode("utf-8")}, full=False)
        self.assertEqual(r["two"]["natural"], 0, "the old rule should leave no Natural fits with one chart on hold")
        self.assertGreater(r["two"]["unjudged"], 0)


if __name__ == "__main__":
    unittest.main()
