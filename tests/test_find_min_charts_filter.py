"""JEG-1647 (Max Logan's beta request): filter Trade & Waiver Recommendations offers by how many public trade charts
rate the trade even or better for the partner (Any, 2 or more, 3 or more, 4 of 4).

What we guard on find.html with the seeded league, at 1440x900 and 390x844:
- DDF.find.chartAgreement / meetsChartMin are the one calculation: a missing or held chart (not in rivalOkCount) never
  agrees, and the card's "n/m public trade charts" label equals chartAgreement for the same offer;
- the filter defaults to Any and the default list is unchanged by it;
- choosing 2+/3+/4 keeps exactly the baseline offers whose card count is at least that, hides the rest, and each
  section's "n offers" count equals the cards it lists;
- setting it back to Any brings the baseline list back; the filter shows in the chips and in the constraints text;
- on 390 the page does not scroll sideways and the select is at least 44px tall.
- Reset (JEG-1647 part 2) sets the filter back to Any and lists offers again (3+ listed none);
- a group whose selected variant is under the minimum stays listed when another variant meets it, and its card shows
  that variant; a variant picked by hand stays until the filter changes (synthetic groups, so the test does not depend on how many charts the week's data has);
- a non-empty "4 of 4" list: a synthetic 4/4 offer is listed at 4 of 4, a 3/4 one is not.
Discrimination: without the filter the control does not exist and the 3+ list equals the baseline (the test fails).
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_find_engine_parity import APPLY, READY, SET
from tests.test_team_engine_parity import seed_script, seeded_league

READ = r"""() => {
  const cards = [...document.querySelectorAll('[data-offer]')].map(c => ({id: c.dataset.partner + '|' + c.dataset.give + '>' + c.dataset.receive,
    text: c.querySelector('a[data-charts]').textContent.trim()}));
  const counts = ['natural-count', 'neutral-count', 'force-count'].map(i => document.getElementById(i).textContent.trim());
  const per = [['natural-count', '#natural-table'], ['neutral-count', '#all-table'], ['force-count', '#force-table']]
    .map(([c, t]) => [document.getElementById(c).textContent.trim(), document.querySelectorAll(t + ' [data-offer]').length]);
  const sel = document.getElementById('min-charts');
  return {cards, per, value: sel ? sel.value : null, selHeight: sel ? sel.getBoundingClientRect().height : 0,
    wide: document.documentElement.scrollWidth - window.innerWidth,
    chips: document.getElementById('filter-chips').textContent, note: (document.getElementById('min-charts-note') || {}).textContent || ''};
}"""

UNIT = r"""() => { const f = DDF.find, t = (ok, n) => ({rivalOkCount: ok, chartCount: n});
  return {a: f.chartAgreement(t(3, 4)), none: f.chartAgreement(t(undefined, 3)), any: f.meetsChartMin(t(0, 4), 0),
    c2: [f.meetsChartMin(t(1, 4), 2), f.meetsChartMin(t(2, 4), 2)], c4: [f.meetsChartMin(t(3, 4), 4), f.meetsChartMin(t(4, 4), 4)],
    short: f.meetsChartMin(t(3, 3), 4)}; }"""


# Synthetic groups on the page's own state (the seeded league has 3 charts, so no real offer reaches 4 of 4).
INJECT = r"""() => {
  // Any listed (non-force) group is a template. 'unjudged' counts: with an analyst chart left out of the week (2026-11-17:
  // USA Today still on Week 10) every offer's fit is unjudged and there is no natural or neutral group.
  const S = DDF.findPage.state, g0 = ['natural', 'neutral', 'unjudged'].map(c => S.groups.find(g => g.cls === c)).find(Boolean);
  const mk = (id, oks) => Object.assign({}, g0, {id, partner: 'SynTeam', trades: oks.map(ok => Object.assign({}, g0.trades[0], {rivalOkCount: ok, chartCount: 4})),
    best: Object.assign({}, g0.trades[0], {rivalOkCount: oks[0], chartCount: 4})});
  S.groups = S.groups.concat([mk('syn|variants', [1, 3]), mk('syn|four', [4]), mk('syn|three', [3])]);
}"""
SYN = r"""() => [...document.querySelectorAll('[data-offer]')].filter(c => c.dataset.partner === 'SynTeam')
  .map(c => ({text: c.querySelector('a[data-charts]').textContent.trim()}))"""


def league():
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:3]
    return lg


def agree(card):
    return int(re.match(r"(\d+)/", card["text"])[1])


class FindMinChartsFilterTest(unittest.TestCase):
    def test_filter(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists():
            raise _render_env.unavailable("dist/find.html is not built")
        with serve(DIST) as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except Exception as exc:  # noqa: BLE001
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                for w, h in ((1440, 900), (390, 844)):
                    page = browser.new_page(viewport={"width": w, "height": h})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda u: not u.startswith(base), lambda r: r.abort())
                    page.add_init_script(seed_script(league()))
                    page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
                    page.evaluate(APPLY, ["ppr", 12, False])
                    page.wait_for_timeout(300)
                    page.wait_for_function(READY, timeout=120000)
                    page.evaluate("() => { const f = document.getElementById('fit'); f.value = 'all'; f.dispatchEvent(new Event('change', {bubbles: true})); }")
                    page.evaluate("() => document.querySelector('[data-page-size=\"200\"]').click()")
                    page.evaluate("() => { const s = document.getElementById('repeat'); s.value = 1000; s.dispatchEvent(new Event('change', {bubbles: true})); }")
                    base_read = page.evaluate(READ)
                    tag = f"{w}: "
                    self.assertEqual(base_read["value"], "0", tag + "the filter must exist and default to Any")
                    cards = base_read["cards"]
                    self.assertTrue(cards, tag + "no offer cards for the seeded league")
                    unit = page.evaluate(UNIT)
                    self.assertEqual(unit["a"], {"agree": 3, "total": 4})
                    self.assertEqual(unit["none"], {"agree": 0, "total": 3})
                    self.assertTrue(unit["any"])
                    self.assertEqual(unit["c2"], [False, True])
                    self.assertEqual(unit["c4"], [False, True])
                    self.assertFalse(unit["short"], tag + "3 of 3 charts must not satisfy 4 of 4")
                    seen_cut = False
                    for minimum in (2, 3, 4):
                        page.evaluate(SET, ["min-charts", str(minimum)])
                        got = page.evaluate(READ)
                        # a group stays when any of its variants has the minimum; its card shows a variant that does
                        want = page.evaluate("(m) => DDF.findPage.state.groups.filter(g => g.cls !== 'force' && g.trades.some(t => t.rivalOkCount >= m)).length", minimum)
                        self.assertEqual(len(got["cards"]), want, tag + f"min {minimum}")
                        self.assertTrue(all(agree(c) >= minimum for c in got["cards"]))
                        for shown, listed in got["per"]:
                            self.assertEqual(shown, f"{listed} {'offer' if listed == 1 else 'offers'}", tag + f"section count at {minimum}")
                        self.assertIn("Charts:", got["chips"])
                        seen_cut = seen_cut or want < len(cards)
                        if w == 390:
                            self.assertLessEqual(got["wide"], 0, tag + "page scrolls sideways")
                            self.assertGreaterEqual(round(got["selHeight"], 1), 44, tag + f"select {got['selHeight']}px tall")
                    self.assertTrue(seen_cut, tag + "seeded league never has an offer under 4/4; the filter was not exercised")
                    page.evaluate(SET, ["min-charts", "0"])
                    back = page.evaluate(READ)
                    self.assertEqual([c["id"] for c in back["cards"]], [c["id"] for c in cards])
                    self.assertIn("missing or on hold", back["note"])
                    total = page.evaluate("() => DDF.findPage.state.chartTotal")
                    if total < 4:  # how many public charts the week's data makes available is not fixed by the seed
                        self.assertIn(f"Only {total} of 4 public charts are available this week", back["note"])
                    else:
                        self.assertNotIn("are available this week", back["note"])
                    page.evaluate(SET, ["min-charts", "3"])
                    page.evaluate("() => document.getElementById('reset').click()")
                    page.wait_for_timeout(300)
                    page.wait_for_function(READY, timeout=120000)
                    reset = page.evaluate(READ)
                    self.assertEqual(reset["value"], "0", tag + "Reset must set the filter back to Any")
                    self.assertGreater(len(reset["cards"]), 0, tag + "Reset brings offers back (3+ listed none)")
                    page.evaluate("() => document.querySelector('[data-page-size=\"200\"]').click()")
                    page.evaluate("() => { const s = document.getElementById('repeat'); s.value = 1000; s.dispatchEvent(new Event('change', {bubbles: true})); }")
                    page.evaluate(INJECT)
                    page.evaluate(SET, ["min-charts", "0"])
                    page.evaluate(SET, ["min-charts", "3"])
                    got = [c["text"] for c in page.evaluate(SYN)]
                    # the [1/4, 3/4] group stays and shows its 3/4 variant; the 3/4 and 4/4 groups stay
                    self.assertEqual(sorted(got), ["3/4 public trade charts"] * 2 + ["4/4 public trade charts"], tag + f"3+ synthetic cards {got}")
                    page.evaluate("""() => { const sel = document.querySelector('select[data-group="syn|variants"]');
                      sel.value = '0'; sel.dispatchEvent(new Event('change', {bubbles: true})); }""")
                    got = sorted(c["text"] for c in page.evaluate(SYN))
                    self.assertEqual(got, ["1/4 public trade charts", "3/4 public trade charts", "4/4 public trade charts"], tag + f"hand-picked variant stays {got}")
                    page.evaluate(SET, ["min-charts", "3"])
                    page.evaluate(SET, ["min-charts", "4"])
                    got = [c["text"] for c in page.evaluate(SYN)]
                    self.assertEqual(got, ["4/4 public trade charts"], tag + f"4 of 4 list {got}")
                    page.evaluate(SET, ["min-charts", "0"])
                    got = sorted(c["text"] for c in page.evaluate(SYN))
                    self.assertEqual(got, ["1/4 public trade charts", "3/4 public trade charts", "4/4 public trade charts"], tag + f"Any {got}")
                    self.assertEqual(errors, [])
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
