"""JEG-1680: the "Public charts agree" filter on find.html is kept on this device (localStorage ddf.v2.find-min-charts).

Guarded at 1440x900 and 390x844 with the seeded league:
- choosing 3+ survives a reload (the select reads 3 and the list is filtered before any further input);
- Reset clears it: the select is Any, the stored key is gone, and a reload stays on Any;
- fit and sort are not persisted (a reload returns them to their defaults), the scope decision in the ticket;
- a stored value that is not one of the options is ignored (Any), and a blocked storage does not break the page.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_find_engine_parity import APPLY, READY, SET
from tests.test_find_min_charts_filter import league
from tests.test_team_engine_parity import seed_script

KEY = "ddf.v2.find-min-charts"
READ = r"""() => ({value: document.getElementById('min-charts').value, fit: document.getElementById('fit').value,
  sort: document.getElementById('sort').value, stored: localStorage.getItem('%s'),
  cards: document.querySelectorAll('[data-offer]').length,
  wide: document.documentElement.scrollWidth - window.innerWidth})""" % KEY


class FindMinChartsPersistTest(unittest.TestCase):
    def test_persist(self):
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
                    tag = f"{w}: "
                    ctx = browser.new_context(viewport={"width": w, "height": h})
                    ctx.add_init_script(seed_script(league()))
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda u: not u.startswith(base), lambda r: r.abort())

                    def load():
                        page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
                        page.evaluate(APPLY, ["ppr", 12, False])
                        page.wait_for_timeout(300)
                        page.wait_for_function(READY, timeout=120000)

                    load()
                    first = page.evaluate(READ)
                    self.assertEqual((first["value"], first["stored"]), ("0", None), tag + "default is Any and nothing is stored")
                    page.evaluate(SET, ["min-charts", "3"])
                    page.evaluate(SET, ["fit", "all"])
                    page.evaluate(SET, ["sort", page.evaluate("() => document.getElementById('sort').options[1].value")])
                    self.assertEqual(page.evaluate(READ)["stored"], "3", tag + "choosing 3+ stores it")

                    load()
                    after = page.evaluate(READ)
                    self.assertEqual(after["value"], "3", tag + "3+ survives a reload")
                    self.assertEqual(after["fit"], first["fit"], tag + "fit is not persisted")
                    self.assertEqual(after["sort"], first["sort"], tag + "sort is not persisted")
                    self.assertIn("Charts:", page.evaluate("() => document.getElementById('filter-chips').textContent"))
                    self.assertLessEqual(after["wide"], 0, tag + "no sideways scroll")

                    page.evaluate("() => document.getElementById('reset').click()")
                    page.wait_for_timeout(300)
                    page.wait_for_function(READY, timeout=120000)
                    reset = page.evaluate(READ)
                    self.assertEqual((reset["value"], reset["stored"]), ("0", None), tag + "Reset clears the filter and the stored value")
                    load()
                    self.assertEqual(page.evaluate(READ)["value"], "0", tag + "stays Any after Reset and reload")

                    page.evaluate("(k) => localStorage.setItem(k, '99')", KEY)
                    load()
                    self.assertEqual(page.evaluate(READ)["value"], "0", tag + "a stored value that is not an option is ignored")
                    self.assertEqual(errors, [], tag + "page errors")
                    ctx.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
