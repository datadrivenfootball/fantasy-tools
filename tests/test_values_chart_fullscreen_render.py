"""JEG-1636: the Values chart pops out to a full-screen landscape view on phones; phone sliders are usable; chart-average series.

Drives the real page with a touch phone context: open/close (button, Close, Back, Escape), page scroll locked while open and restored,
CSS rotation in portrait and natural layout in landscape, tap/drag readout naming player, rank and each source value, pinch/drag zoom
inputs, 44px slider targets and nudge buttons, handles that stay separable when together, and the Trade chart average series.
Desktop keeps the chart as it was (no pop-out button).
"""
from __future__ import annotations

import contextlib
import unittest

from tests import _render_env
from tests._dist_server import serve

LIVE = "() => document.body.classList.contains('values-live') && !!window.DDF && !!DDF.engine.player('2227')"


def setUpModule():
    _render_env.ensure_built()


class FullScreenChartTest(unittest.TestCase):
    @contextlib.contextmanager
    def _page(self, width, height, mobile=True):
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
                ctx = browser.new_context(viewport={"width": width, "height": height}, has_touch=mobile, is_mobile=mobile)
                ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{base}/values.html", wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function(LIVE, timeout=60000)
                page.wait_for_timeout(500)
                yield page
                self.assertEqual([], errors)
            finally:
                browser.close()

    STATE = """() => { const o = document.getElementById('vfs'), b = document.body;
      const c = document.getElementById('vchart').getBoundingClientRect();
      return {hidden: o.hidden, bodyPos: b.style.position, htmlLock: document.documentElement.classList.contains('vfs-lock'),
        rot: o.classList.contains('vfs-rot'), scrollY: Math.round(window.scrollY),
        chartInOverlay: !!o.querySelector('#vchart'), seriesInOverlay: !!o.querySelector('.series'),
        chartInSection: !!document.querySelector('.values-section #vchart'),
        chartW: Math.round(c.width), chartH: Math.round(c.height), ow: Math.round(o.getBoundingClientRect().width),
        oh: Math.round(o.getBoundingClientRect().height), vb: document.getElementById('vchart').getAttribute('viewBox'),
        pages: document.documentElement.scrollWidth - document.documentElement.clientWidth}; }"""

    def test_open_close_and_scroll_lock_portrait(self):
        with self._page(375, 667) as page:
            self.assertTrue(page.is_visible("#vfs-open"), "pop-out button shows on a phone")
            page.evaluate("window.scrollTo(0, 260)")
            page.wait_for_timeout(200)
            before = page.evaluate("Math.round(window.scrollY)")
            self.assertGreater(before, 100)
            page.click("#vfs-open")
            page.wait_for_timeout(500)
            s = page.evaluate(self.STATE)
            self.assertFalse(s["hidden"])
            self.assertEqual("fixed", s["bodyPos"], "page scroll is locked")
            self.assertTrue(s["htmlLock"])
            self.assertTrue(s["rot"], "portrait phone gets the CSS-rotated landscape view")
            self.assertTrue(s["chartInOverlay"] and s["seriesInOverlay"] and not s["chartInSection"])
            self.assertEqual((667, 375), (s["oh"], s["ow"]), "overlay is the screen turned a quarter turn")
            self.assertGreater(max(s["chartW"], s["chartH"]), 400, "chart fills the long side")
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(150)
            self.assertEqual(0, page.evaluate("Math.round(window.scrollY)"), "wheel/drag cannot scroll the page behind")
            page.click("#vfs-close")
            page.wait_for_timeout(500)
            s = page.evaluate(self.STATE)
            self.assertTrue(s["hidden"])
            self.assertEqual("", s["bodyPos"])
            self.assertFalse(s["htmlLock"])
            self.assertTrue(s["chartInSection"] and not s["chartInOverlay"], "chart is back in the page")
            self.assertLess(abs(s["scrollY"] - before), 3, "scroll position restored")
            self.assertEqual(0, s["pages"], "no sideways scroll at 375px")

    def test_back_button_and_escape_close(self):
        with self._page(375, 667) as page:
            page.click("#vfs-open")
            page.wait_for_timeout(300)
            self.assertFalse(page.evaluate("document.getElementById('vfs').hidden"))
            page.go_back()
            page.wait_for_timeout(400)
            self.assertTrue(page.evaluate("document.getElementById('vfs').hidden"), "Back exits the full-screen view")
            self.assertIn("values.html", page.url, "Back stays on the Values page")
            page.click("#vfs-open")
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self.assertTrue(page.evaluate("document.getElementById('vfs').hidden"))

    def test_landscape_readout_names_player_rank_and_sources(self):
        with self._page(667, 375) as page:
            page.click("#vfs-open")
            page.wait_for_timeout(500)
            s = page.evaluate(self.STATE)
            self.assertFalse(s["rot"], "already landscape: no rotation")
            self.assertGreater(s["chartW"], 450)
            self.assertGreater(s["chartH"], 120)
            b = page.evaluate("(() => { const r = document.getElementById('vchart').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            page.mouse.click(b[0] + b[2] * 0.3, b[1] + b[3] * 0.5)
            page.wait_for_timeout(200)
            txt = page.inner_text("#vfs-readout")
            self.assertRegex(txt, r"rank \d+")
            self.assertIn("DDF", txt)
            self.assertIn("CBS", txt)
            first = txt.split("\n")[0]
            page.mouse.click(b[0] + b[2] * 0.8, b[1] + b[3] * 0.5)
            page.wait_for_timeout(200)
            self.assertNotEqual(first, page.inner_text("#vfs-readout").split("\n")[0], "a different tap names a different player")
            # Zoom tool: a drag narrows the rank range; Reset restores it.
            page.click("[data-tool=zoom]")
            wide = page.evaluate("+document.getElementById('high').value - +document.getElementById('low').value")
            page.mouse.move(b[0] + b[2] * 0.3, b[1] + b[3] * 0.5)
            page.mouse.down()
            page.mouse.move(b[0] + b[2] * 0.6, b[1] + b[3] * 0.5, steps=6)
            page.mouse.up()
            page.wait_for_timeout(200)
            narrow = page.evaluate("+document.getElementById('high').value - +document.getElementById('low').value")
            self.assertLess(narrow, wide)
            page.click("#vfs-reset")
            page.wait_for_timeout(200)
            self.assertEqual(wide, page.evaluate("+document.getElementById('high').value - +document.getElementById('low').value"))
            # Sources and range stay reachable in the drawer.
            page.click("#vfs-ctrl")
            for sel in ("#ddf", "#cbs", "#low", "#low-number", "#group-pos", "#src-avg", "[data-count='50']"):
                self.assertTrue(page.is_visible(sel), sel + " reachable inside the full-screen view")

    def test_sliders_375_targets_nudge_and_close_handles(self):
        with self._page(375, 667) as page:
            hs = page.evaluate("""() => ['.dual-h', '.dual-v', '#low-number', '#max-value'].map(q => { const r = document.querySelector(q).getBoundingClientRect(); return [q, Math.round(r.width), Math.round(r.height)]; })""")
            self.assertGreaterEqual(hs[0][2], 44, "horizontal slider track is 44px tall")
            self.assertGreaterEqual(hs[1][1], 44, "vertical slider track is 44px wide")
            for sel in ('[data-t="low-number"][data-d="1"]', '[data-t="high-number"][data-d="-1"]'):
                bb = page.locator(sel).bounding_box()
                self.assertGreaterEqual(min(bb["width"], bb["height"]), 44, sel)
            page.click("[data-count='All']")
            page.wait_for_timeout(300)
            hi0 = page.evaluate("+document.getElementById('high').value")
            self.assertGreater(hi0, 100)
            page.click('[data-t="high-number"][data-d="-1"]')
            self.assertEqual(hi0 - 1, page.evaluate("+document.getElementById('high').value"), "nudge moves one rank")
            page.click('[data-t="low-number"][data-d="1"]')
            self.assertEqual(2, page.evaluate("+document.getElementById('low').value"))
            # Handles together: a touch drag to the right moves the high handle, to the left the low one.
            page.evaluate("""() => { const l = document.getElementById('low'), h = document.getElementById('high');
              l.value = 200; l.dispatchEvent(new Event('input', {bubbles: true})); h.value = 200; h.dispatchEvent(new Event('input', {bubbles: true})); }""")
            r = page.evaluate("(() => { const r = document.querySelector('.dual-h').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            f = (200 - 1) / (+page.evaluate("+document.getElementById('high').max") - 1)
            x = r[0] + 13 + f * (r[2] - 26)
            y = r[1] + r[3] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 40, y, steps=5)
            page.mouse.up()
            lo, hi = page.evaluate("[+document.getElementById('low').value, +document.getElementById('high').value]")
            self.assertEqual(200, lo)
            self.assertGreater(hi, 200, "dragging right from stacked handles moves the high handle")
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x - 30, y, steps=5)
            page.mouse.up()
            lo2, hi2 = page.evaluate("[+document.getElementById('low').value, +document.getElementById('high').value]")
            self.assertLess(lo2, 200, "dragging left moves a handle below the stack")
            self.assertEqual(0, page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"))

    def test_trade_chart_average_series(self):
        with self._page(375, 667) as page:
            self.assertTrue(page.is_visible("#src-avg"), "Trade chart average is a visible series choice")
            self.assertEqual(1, page.locator("#rank option[value=avg]").count())
            self.assertTrue(page.is_checked("#src-avg"), "visible by default next to DDF Value")
            page.wait_for_timeout(300)
            self.assertIn("trade chart average", page.inner_text("#head").lower())
            vals = page.evaluate("""() => { const r = DDFValues.D.find(p => [p.cbs, p.usat, p.fp, p.fc].every(v => typeof v === 'number'));
              return [r.avg, (r.cbs + r.usat + r.fp + r.fc) / 4, r.avgN]; }""")
            self.assertAlmostEqual(vals[0], vals[1], places=6)
            self.assertEqual(4, vals[2], "n/4 badge counts the charts that went in")
            self.assertRegex(page.inner_text('#rows tr[data-i]'), r"4/4")

    def test_desktop_has_no_popout(self):
        with self._page(1440, 900, mobile=False) as page:
            self.assertFalse(page.is_visible("#vfs-open"))
            self.assertFalse(page.is_visible(".rank-nudge"))
            self.assertTrue(page.evaluate("document.getElementById('vfs').hidden"))


if __name__ == "__main__":
    unittest.main()
