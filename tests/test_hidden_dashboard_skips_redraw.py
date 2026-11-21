"""Page speed (Jeremy, 2026-11-21): the hidden old comparison table does not redraw after each engine rebuild.

The redesign pages carry the old comparison dashboard inside the hidden engine block. It re-read the engine and
redrew its whole table after every rebuild (four times on a load with a saved league), though nobody can see it.
Now, while its panel has no layout box, a rebuild only marks it stale; it redraws when the panel is shown.

What we guard on values.html:
- while hidden, an engine rebuild (a scoring change) makes no change to the table's DOM;
- once the engine block is shown, the table redraws by itself, and what it shows equals a forced full redraw
  (TradeValueComparisonControls.refresh()), so nothing is lost by skipping the hidden work.
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


def setUpModule():
    _render_env.ensure_built()


class HiddenDashboardTest(unittest.TestCase):
    def test_hidden_table_waits_until_shown(self):
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
                pg = browser.new_page()
                pg.goto(f"{base}/values.html", wait_until="load")
                pg.wait_for_function(READY, timeout=90000)
                pg.evaluate("() => DDF.engine.ready")
                self.assertEqual(pg.evaluate("() => document.querySelector('.comparison-panel').getClientRects().length"), 0,
                                 "the comparison panel is hidden on values.html")
                pg.evaluate(WATCH)
                pg.evaluate("() => DDF.engine.apply({scoring: 'standard'})")
                pg.wait_for_timeout(300)
                self.assertEqual(pg.evaluate("() => window.__tableMutations"), 0, "a hidden table must not redraw on a rebuild")
                pg.evaluate(SHOW)
                pg.wait_for_function("() => window.__tableMutations > 0", timeout=10000)
                shown = pg.evaluate("() => document.getElementById('tableWrap').innerHTML")
                pg.evaluate("() => TradeValueComparisonControls.refresh()")
                self.assertEqual(shown, pg.evaluate("() => document.getElementById('tableWrap').innerHTML"),
                                 "the redraw on show must equal a full redraw")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
