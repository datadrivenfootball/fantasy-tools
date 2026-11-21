"""Page speed (Jeremy, 2026-11-21): the hidden old comparison table does not redraw after each engine rebuild.

The redesign pages carry the old comparison dashboard inside the hidden engine block. It re-read the engine and
redrew its whole table after every rebuild (four times on a load with a saved league), though nobody can see it.
Now, while its panel has no layout box, a rebuild only marks it stale; it redraws when the panel is shown.

What we guard on values.html, with two hide/show cycles:
- while hidden, an engine rebuild makes no change to the table's DOM;
- once shown, the table redraws by itself, and it is byte-identical to the table on a second, separate page that
  was shown from the start and took the same settings changes while visible. A show that skipped re-reading the
  engine would draw a stale or empty table and fail here.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve

READY = "() => window.DDF && DDF.engine && DDF.engine.ready && window.TradeValueComparisonControls"
WATCH = """() => { window.__tableMutations = 0;
  new MutationObserver(ms => { window.__tableMutations += ms.length; })
    .observe(document.getElementById('tableWrap'), {subtree: true, childList: true, characterData: true}); }"""
SHOW = """() => { document.querySelectorAll('#legacyEngine, .legacy-engine-tail').forEach(el => {
  el.hidden = false; el.style.display = 'block'; }); }"""
HIDE = """() => { document.querySelectorAll('#legacyEngine, .legacy-engine-tail').forEach(el => {
  el.hidden = true; el.style.display = 'none'; }); }"""
TABLE = "() => document.getElementById('tableWrap').innerHTML"
# Two rounds of settings changes, each several fields (one engine rebuild each through DDF.engine.apply).
CHANGES = [{"scoring": "standard", "teams": 10}, {"scoring": "half_ppr", "teams": 12, "superflex": True}]


def setUpModule():
    _render_env.ensure_built()


def open_values(browser, base):
    pg = browser.new_context().new_page()
    pg.goto(f"{base}/values.html", wait_until="load")
    pg.wait_for_function(READY, timeout=90000)
    pg.evaluate("() => DDF.engine.ready")
    return pg


class HiddenDashboardTest(unittest.TestCase):
    def test_hidden_table_matches_a_visible_one_after_show(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "values.html").exists():
            raise _render_env.unavailable("dist/values.html is not built")
        with serve() as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except Exception as exc:  # noqa: BLE001
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                # Reference: a separate page, shown before any change, takes each change while visible.
                ref = open_values(browser, base)
                # refresh() forces a full engine read, so the reference does not depend on the show path under test.
                ref.evaluate(SHOW)
                ref.evaluate("() => TradeValueComparisonControls.refresh()")
                expected = []
                for change in CHANGES:
                    ref.evaluate("(p) => DDF.engine.apply(p)", change)
                    expected.append(ref.evaluate(TABLE))
                # Page under test: each change lands while hidden, then the table is shown.
                pg = open_values(browser, base)
                self.assertEqual(pg.evaluate("() => document.querySelector('.comparison-panel').getClientRects().length"), 0,
                                 "the comparison panel is hidden on values.html")
                pg.evaluate(WATCH)
                for round_no, change in enumerate(CHANGES, 1):
                    pg.evaluate("() => { window.__tableMutations = 0; }")
                    pg.evaluate("(p) => DDF.engine.apply(p)", change)
                    pg.wait_for_timeout(300)
                    self.assertEqual(pg.evaluate("() => window.__tableMutations"), 0,
                                     f"round {round_no}: a hidden table must not redraw on a rebuild")
                    pg.evaluate(SHOW)
                    try:   # the redraw on show is asynchronous (ResizeObserver); a missing redraw fails below
                        pg.wait_for_function("() => window.__tableMutations > 0", timeout=10000)
                    except Exception:  # noqa: BLE001
                        pass
                    pg.wait_for_timeout(200)
                    shown = pg.evaluate(TABLE)
                    self.assertGreater(len(expected[round_no - 1]), 1000, "the reference table has rows")
                    self.assertEqual(len(shown), len(expected[round_no - 1]), f"round {round_no}: shown table size")
                    self.assertTrue(shown == expected[round_no - 1],
                                    f"round {round_no}: the table shown after hidden rebuilds differs from a visible page's")
                    pg.evaluate(HIDE)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
