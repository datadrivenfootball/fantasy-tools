"""JEG-1621: the Values player table is compact, positions are group rows, overrides sit in one end column.

Drives the real page: no per-row "Set your own value" text or position pill in the Player cell, a position group row
per position, an Override column last, the button still opens the Overrides tab on the same player and an applied
override still shows on the table row; at 375px the page does not scroll sideways and the buttons stay tappable.
"""
from __future__ import annotations

import contextlib
import unittest

from tests import _render_env
from tests._dist_server import serve

LIVE = "() => document.body.classList.contains('values-live') && !!window.DDF && !!DDF.engine.player('2227')"
FACTS = """() => {
  const heads = [...document.querySelectorAll('#head th')].map(t => t.textContent.trim());
  const groups = [...document.querySelectorAll('#rows tr.pos-grp th')].map(t => t.textContent.trim().split(/\\s+/)[0]);
  const rows = [...document.querySelectorAll('#rows tr[data-i]')];
  const first = rows[0];
  const own = first.querySelector('td.ovcol button[data-act=own]');
  return {
    heads, groups, nrows: rows.length,
    posPillInPlayerCell: !!document.querySelector('#rows td.pl .pos'),
    actsInPlayerCell: !!document.querySelector('#rows td.pl .vp-acts, #rows td.pl .vp-act'),
    ownButtons: document.querySelectorAll('#rows td.ovcol button[data-act=own]').length,
    ownText: own.textContent.trim(),
    rowH: Math.round(first.getBoundingClientRect().height),
    btnH: Math.round(own.getBoundingClientRect().height),
    btnW: Math.round(own.getBoundingClientRect().width),
    pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}"""


def setUpModule():
    _render_env.ensure_built()


class CompactValuesTableTest(unittest.TestCase):
    @contextlib.contextmanager
    def _session(self, width, height):
        try:
            from playwright.sync_api import Error as PlaywrightError, sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        with serve() as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except PlaywrightError as exc:
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                ctx = browser.new_context(viewport={"width": width, "height": height})
                ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{base}/values.html", wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function(LIVE, timeout=60000)
                page.wait_for_timeout(500)
                yield page, page.evaluate(FACTS)
                self.assertEqual([], errors)
            finally:
                browser.close()

    def _check_layout(self, f):
        self.assertEqual("Override", f["heads"][-1], "Override is the last column")
        self.assertEqual("Player", f["heads"][0])
        self.assertTrue({"QB", "RB", "WR", "TE"} <= set(f["groups"]), f["groups"])
        self.assertFalse(f["posPillInPlayerCell"], "positions are group rows, not a pill per row")
        self.assertFalse(f["actsInPlayerCell"], "no per-row action links in the Player cell")
        self.assertEqual(f["nrows"], f["ownButtons"], "one override button per player row")
        self.assertIn(f["ownText"], ("Set", "Edit"))

    def test_desktop_layout(self):
        with self._session(1440, 900) as (page, f):
            self._check_layout(f)
            self.assertLessEqual(f["rowH"], 36, "compact row height")

    def test_phone_layout_and_tap_targets(self):
        with self._session(375, 812) as (page, f):
            self._check_layout(f)
            self.assertEqual(0, f["pageScroll"], "no horizontal page scroll at 375px")
            self.assertGreaterEqual(f["btnH"], 44)
            self.assertGreaterEqual(f["btnW"], 44)

    def test_override_button_opens_overrides_and_applies(self):
        with self._session(1440, 900) as (page, f):
            page.click("#rows tr[data-i] td.ovcol button[data-act=own]")
            page.wait_for_function("() => !document.getElementById('panel-ov').hidden", timeout=15000)
            name = page.evaluate("() => document.getElementById('ov-name').textContent.trim()")
            self.assertTrue(name, "the Overrides tab opens on the clicked player")
            page.fill("#ov-num", "99")
            page.dispatch_event("#ov-num", "input")
            page.click("#ov-apply")
            page.wait_for_timeout(500)
            page.click("#tab-chart")
            page.wait_for_timeout(300)
            row = page.evaluate("(n) => { const t = [...document.querySelectorAll('#rows tr.ov-row')].find(r => r.textContent.includes(n)); return t ? t.querySelector('td.ovcol button[data-act=own]').textContent.trim() : null }", name)
            self.assertEqual("Edit", row, "an overridden row shows Edit and the ov-row marker")
            page.click("#tab-ov")
            page.click("#ov-reset")
            page.wait_for_timeout(300)
            page.click("#tab-chart")
            self.assertEqual(0, page.evaluate("() => document.querySelectorAll('#rows tr.ov-row').length"), "reset clears it")


if __name__ == "__main__":
    unittest.main()
