"""JEG-1595: the header Menu panel opened off the left edge of the screen on the homepage (iPhone, 2026-11-09).

Cause: body.home2 sets `.morewrap{position:relative}`, which beat the phone rule `.morewrap{position:static}`, so the
340px panel (right:18px) anchored to the small Menu button and spilled left of x=0. The fix spans the panel across the
header inside the viewport and safe areas. These tests pin, on every page that shares the header, at 320 and 375 wide
(and a landscape phone): panel left >= 0, right <= viewport width, labels not clipped, 44px rows, and the three ways
to close it (outside tap, Escape, second Menu tap).
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import serve

PAGES = ("index", "ai", "build", "explore", "find", "learn", "partners", "team", "values", "waivers")
VIEWPORTS = ((320, 640), (375, 812), (430, 932), (667, 375))
PANEL = ".morewrap .menu"
BUTTON = ".morewrap > button"


def setUpModule():
    _render_env.ensure_built()


class MobileMenuPanelTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._serve = serve()
        cls.base = cls._serve.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except Error as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def open_page(self, name, width, height):
        context = self.browser.new_context(viewport={"width": width, "height": height}, is_mobile=True, has_touch=True)
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
        page.goto(f"{self.base}/{name}.html", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(300)
        return page

    def is_open(self, page):
        return page.eval_on_selector(PANEL, "e => getComputedStyle(e).display !== 'none'")

    def test_panel_stays_inside_the_viewport_on_every_page(self):
        for name in PAGES:
            for width, height in VIEWPORTS:
                with self.subTest(page=name, width=width):
                    page = self.open_page(name, width, height)
                    closed_scroll_width = page.evaluate("document.documentElement.scrollWidth")
                    page.locator(BUTTON).first.tap()
                    page.wait_for_timeout(150)
                    self.assertTrue(self.is_open(page), "Menu tap opens the panel")
                    box = page.eval_on_selector(PANEL, "e => { const r = e.getBoundingClientRect(); return [r.left, r.right, r.bottom, innerHeight]; }")
                    self.assertGreaterEqual(box[0], 0, f"panel left edge off screen: {box}")
                    self.assertLessEqual(box[1], width, f"panel right edge off screen: {box}")
                    self.assertGreaterEqual(box[0], 8, f"panel flush with the left edge, no gutter: {box}")
                    self.assertLessEqual(box[1], width - 8, f"panel flush with the right edge, no gutter: {box}")
                    self.assertLessEqual(box[2], box[3], f"panel runs below the viewport: {box}")
                    # Opening the panel must not widen the page (values.html has its own wide table at 320, unrelated to the Menu).
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), closed_scroll_width, "panel widened the page")

    def test_labels_are_not_clipped_and_rows_are_44px(self):
        for name in ("index", "learn"):
            for width, height in VIEWPORTS[:2]:
                with self.subTest(page=name, width=width):
                    page = self.open_page(name, width, height)
                    page.locator(BUTTON).first.tap()
                    page.wait_for_timeout(150)
                    rows = page.eval_on_selector_all(f"{PANEL} a", "els => els.filter(e => e.getBoundingClientRect().width > 0).map(e => { const r = e.getBoundingClientRect(); return [e.textContent.trim(), r.left, r.right, r.height, e.scrollWidth - e.clientWidth]; })")
                    self.assertTrue(rows)
                    for text, left, right, rect_height, overflow in rows:
                        self.assertGreaterEqual(left, 0, text)
                        self.assertLessEqual(right, width, text)
                        self.assertGreaterEqual(rect_height, 44, f"{text} row under 44px")
                        self.assertLessEqual(overflow, 0, f"{text} label clipped")

    def test_menu_closes_on_outside_tap_escape_and_second_tap(self):
        for name in ("index", "build"):
            with self.subTest(page=name):
                page = self.open_page(name, 375, 812)
                button = page.locator(BUTTON).first
                button.tap(); page.wait_for_timeout(100)
                self.assertTrue(self.is_open(page))
                button.tap(); page.wait_for_timeout(100)
                self.assertFalse(self.is_open(page), "second Menu tap closes")
                button.tap(); page.wait_for_timeout(100)
                page.keyboard.press("Escape"); page.wait_for_timeout(100)
                self.assertFalse(self.is_open(page), "Escape closes")
                self.assertEqual(button.get_attribute("aria-expanded"), "false")
                button.tap(); page.wait_for_timeout(100)
                bottom = page.eval_on_selector(PANEL, "e => e.getBoundingClientRect().bottom")
                page.touchscreen.tap(187, min(bottom + 30, 800)); page.wait_for_timeout(100)
                self.assertFalse(self.is_open(page), "tap outside closes")
                self.assertEqual(button.get_attribute("aria-expanded"), "false")


if __name__ == "__main__":
    unittest.main()
