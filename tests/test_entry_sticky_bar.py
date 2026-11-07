"""JEG-1568 follow-up (Jeremy, 2026-11-07): one sticky Back/Next bar on every entry page (connect, setup, settings).

At 1440, 390 and 360: exactly one visible Next and one visible Back per page (the sticky bar's); Next is greyed until
its requirement is met and then enabled; the bar's Back goes to the previous step; the bar's controls have accessible
names and 44px targets and are reachable by keyboard; the Edit league / Start fresh controls on connect.html stay.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve
from tests.test_bookmark_freshness import seed_script

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls()"
# Visible Next-like primaries and Back controls; the tutorial carousel's and manual entry's own Back are not step Backs.
COUNT_NEXT = """() => [...document.querySelectorAll('a.button.primary, button.primary, .ddf-actionbar__next')]
  .filter(e => /Next|Looks right/.test(e.textContent) && e.getBoundingClientRect().width > 0).length"""
COUNT_BACK = """() => [...document.querySelectorAll('a, button')]
  .filter(e => e.textContent.trim() === 'Back' && !e.matches('[data-cprev], #manual-back') && e.getBoundingClientRect().width > 0).length"""


def setUpModule():
    _render_env.ensure_built()


class EntryStickyBarTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._serve = serve()
        cls.base = cls._serve.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def page(self, width, seed=None):
        context = self.browser.new_context(viewport={"width": width, "height": 900 if width > 760 else 800})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        if seed:
            page.add_init_script(seed)
        return page

    def check_bar(self, page, back_href):
        self.assertEqual(page.evaluate(COUNT_NEXT), 1, "one visible Next")
        self.assertEqual(page.evaluate(COUNT_BACK), 1, "one visible Back")
        back = page.locator(".ddf-actionbar a", has_text="Back").first
        self.assertEqual(back.get_attribute("href"), back_href)
        for sel in (".ddf-actionbar__next", ".ddf-actionbar a:has-text('Back')"):
            box = page.locator(sel).first.bounding_box()
            self.assertGreaterEqual(box["height"], 43.5, sel)
            self.assertTrue(page.locator(sel).first.inner_text().strip(), sel)
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)

    def test_connect_setup_settings(self):
        for width in (1440, 390, 360):
            with self.subTest(width=width):
                page = self.page(width)
                page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
                page.wait_for_function(ENGINE_READY, timeout=60000)
                page.wait_for_selector(".ddf-actionbar__next", timeout=10000)
                self.check_bar(page, "index.html")
                nxt = page.locator(".ddf-actionbar__next")
                self.assertEqual(nxt.get_attribute("aria-disabled"), "true", "greyed until rosters are read")
                page.fill("#rosters", (FIXTURES / "02-yahoo-markdown.txt").read_text(encoding="utf-8"))
                page.click("#recognize-button")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                page.wait_for_function("() => document.querySelector('.ddf-actionbar__next').getAttribute('aria-disabled') === 'false'", timeout=5000)
                self.assertEqual(page.evaluate(COUNT_NEXT), 1)
                nxt.click()
                page.wait_for_url("**/setup.html", timeout=20000)
                page.wait_for_selector(".ddf-actionbar__next", timeout=10000)
                self.check_bar(page, "connect.html")
                self.assertEqual(page.locator(".ddf-actionbar__next").get_attribute("aria-disabled"), "true")
                page.locator("input[name=team]").first.check(force=True)
                page.wait_for_function("() => document.querySelector('.ddf-actionbar__next').getAttribute('aria-disabled') === 'false'", timeout=5000)
                page.locator(".ddf-actionbar__next").click()
                page.wait_for_url("**/settings.html", timeout=20000)
                page.wait_for_selector(".ddf-actionbar__next", timeout=10000)
                self.check_bar(page, "setup.html")
                self.assertEqual(page.locator(".ddf-actionbar__next").get_attribute("aria-disabled"), "false", "default settings are complete")
                page.fill("#lineup-qb", "")
                page.dispatch_event("#lineup-qb", "input")
                page.wait_for_function("() => document.querySelector('.ddf-actionbar__next').getAttribute('aria-disabled') === 'true'", timeout=5000)
                page.fill("#lineup-qb", "1")
                page.dispatch_event("#lineup-qb", "input")
                page.wait_for_function("() => document.querySelector('.ddf-actionbar__next').getAttribute('aria-disabled') === 'false'", timeout=5000)
                page.locator(".ddf-actionbar__next").click()
                page.wait_for_url("**/team.html", timeout=20000)
                self.assertEqual(page.evaluate("sessionStorage.getItem('ddf:settingsok')"), "1", "the bar's Next still confirms the settings")
                self.assertEqual(page.errors, [])

    def test_keyboard_reaches_the_bar(self):
        page = self.page(390)
        page.goto(f"{self.base}/settings.html", wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".ddf-actionbar__next", timeout=10000)
        reached = False
        for _ in range(80):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement && document.activeElement.classList.contains('ddf-actionbar__next')"):
                reached = True
                break
        self.assertTrue(reached, "Tab reaches the bar's Next")

    def test_edit_league_and_start_fresh_stay(self):
        page = self.page(390, seed=seed_script(2))
        page.goto(f"{self.base}/connect.html?edit=1", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.assertTrue(page.is_visible("#entry-top [data-start-fresh]"))
        self.assertTrue(page.is_visible("#entry-keep"))
        self.assertEqual(page.evaluate(COUNT_BACK), 1)
        self.assertEqual(page.locator(".ddf-actionbar__next").get_attribute("aria-disabled"), "false", "the current league can go on")


if __name__ == "__main__":
    unittest.main()
