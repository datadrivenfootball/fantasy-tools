"""Build 'Pick players' table (Jeremy, 2026-11-22): selected players pin to the top, at 375px and 1440px.

On the seeded league in My league mode: selecting three players puts them first in selection order; deselecting one
returns it to its normal place; the search keeps selected rows visible though they do not match; the box scrolls back to
the top on a toggle but not when typing; the + buttons stay 44px at 375px; the page has no horizontal overflow.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests._served_weeks import pinned_documents
from tests.test_build_offer_render import KEYS_JS, LIVE, SEED_JS

ROWS = """() => [...document.querySelectorAll('#give-picker tr')].map(r => ({key: r.dataset.key, selected: r.classList.contains('selected'),
  hidden: r.hidden, h: Math.round(r.getBoundingClientRect().height), name: r.cells[0].firstChild.textContent}))"""
BTN = "document.querySelector('#give-picker tr[data-key=\"' + k + '\"] button')"


def setUpModule():
    _render_env.ensure_built()


class BuildPinSelectedRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._serve = serve(DIST, {path: text.encode() for path, text in pinned_documents(DIST).items()})
        cls.base = cls._serve.__enter__()
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(cls._pw))
        except PlaywrightError as exc:
            cls._pw.stop(); cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        page = cls.browser.new_page()
        page.add_init_script(f"({SEED_JS})(null)")
        page.goto(f"{cls.base}/build.html", wait_until="load", timeout=60000)
        cls.players = page.evaluate(KEYS_JS)
        page.close()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls._pw.stop(); cls._serve.__exit__(None, None, None)

    def run_at(self, width):
        keys = [p["key"] for p in self.players[:32]]
        ctx = self.browser.new_context(viewport={"width": width, "height": 900})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"({SEED_JS})({keys!r})".replace("'", '"'))
        page.goto(f"{self.base}/build.html?mode=league", wait_until="load", timeout=60000)
        page.wait_for_function(LIVE, timeout=60000)
        page.wait_for_selector("#give-picker tr[data-key]", timeout=20000)
        base = [r["key"] for r in page.evaluate(ROWS)]
        self.assertGreaterEqual(len(base), 8)
        pick = [base[6], base[2], base[4]]
        for k in pick:
            page.evaluate(f"(k) => {BTN}.scrollIntoView()", k)
            page.evaluate("() => { document.querySelector('#give-picker').closest('.player-scroll').scrollTop = 200; }")
            page.evaluate(f"(k) => {BTN}.click()", k)
        rows = page.evaluate(ROWS)
        self.assertEqual([r["key"] for r in rows[:3]], pick, "selected rows first, in selection order")
        self.assertTrue(all(r["selected"] for r in rows[:3]) and not any(r["selected"] for r in rows[3:]))
        self.assertEqual([r["key"] for r in rows[3:]], [k for k in base if k not in pick], "rest keep roster order")
        self.assertEqual(page.evaluate("() => document.querySelector('#give-picker').closest('.player-scroll').scrollTop"), 0)
        self.assertEqual(page.inner_text("#give-sel-count").split()[0], "3")
        # The toggled button is a labelled pressed control.
        self.assertEqual(page.evaluate(f"(k) => {BTN}.getAttribute('aria-pressed')", pick[0]), "true")
        if width <= 600:
            for r in rows:
                self.assertGreaterEqual(r["h"], 44, r)
            self.assertGreaterEqual(page.evaluate(f"(k) => {BTN}.getBoundingClientRect().height", base[0]), 43.5)
            self.assertGreaterEqual(page.evaluate(f"(k) => {BTN}.getBoundingClientRect().width", base[0]), 43.5)
        # Search for a name no selected row matches: selected stay visible, unmatched unselected hide, no scroll jump.
        other = next(p for p in self.players if p["key"] in base and p["key"] not in pick)
        page.evaluate("() => { document.querySelector('#give-picker').closest('.player-scroll').scrollTop = 0; }")
        page.fill("#give-search", other["n"].split()[-1])
        rows = page.evaluate(ROWS)
        self.assertEqual([r["key"] for r in rows[:3]], pick)
        self.assertFalse(any(r["hidden"] for r in rows[:3]), "a selection never disappears")
        self.assertTrue(any(not r["hidden"] for r in rows[3:]))
        self.assertTrue(all(r["hidden"] for r in rows[3:] if other["n"].split()[-1].lower() not in r["name"].lower()))
        page.fill("#give-search", "")
        # Deselect the middle pick: it leaves the pinned group; focus stays on that row's control.
        page.evaluate(f"(k) => {BTN}.focus()", pick[1])
        page.keyboard.press("Enter")
        rows = page.evaluate(ROWS)
        self.assertEqual([r["key"] for r in rows[:2]], [pick[0], pick[2]])
        self.assertEqual([r["key"] for r in rows[2:]], [k for k in base if k not in (pick[0], pick[2])])
        self.assertEqual(page.evaluate("() => document.activeElement.closest('tr').dataset.key"), pick[1])
        self.assertFalse(page.evaluate("() => Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) > innerWidth + 1"), "horizontal overflow")
        self.assertEqual(errors, [])

    def test_phone_375(self):
        self.run_at(375)

    def test_desktop_1440(self):
        self.run_at(1440)


if __name__ == "__main__":
    unittest.main()
