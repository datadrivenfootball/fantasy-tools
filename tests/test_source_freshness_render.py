"""Source freshness: the menu dot (green all / orange some / red none / absent when the status file is unreadable)
and the details page, driven by overriding modules/comparison-chain-status.json in the browser."""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._dist_server import serve

SOURCES = ("cbs", "usatoday", "fantasypros", "fantasycalc", "espn", "cbsros", "razzball")
STATUS_GLOB = "**/modules/comparison-chain-status.json"


LEAGUE_SEED = ("(() => { sessionStorage.setItem('ddf:pasted', JSON.stringify({v: 1, source: 'paste', site: 'yahoo', me: 1, name: 'USO Season XVIII',"
               " teams: [{name: 'Fourth Down Club', players: [{name: 'Josh Allen', key: '869', pos: 'QB', team: 'BUF', id: null}], unmatched: []},"
               " {name: 'Hail Marys', players: [{name: 'Jahmyr Gibbs', key: '2227', pos: 'RB', team: 'DET', id: 0}], unmatched: []}]})); })()")


def setUpModule():
    _render_env.ensure_built()


# Fixed far from any real date so the page's live clock never moves a fixture across the Thursday-noon line.
NOT_YET_STALE = "2099-01-01T12:00:00-06:00"
ALREADY_STALE = "2000-01-01T12:00:00-06:00"


def status(served, held=(), stale_after=NOT_YET_STALE, expected=11):
    weeks = {}
    for key in SOURCES:
        week = served.get(key, expected)
        weeks[key] = {"served_week": week, "expected_week": expected, "published_at": "2026-11-17",
                      "stale_after": None if week >= expected else stale_after}
    return {"run_at": "2026-11-18T00:43:23+00:00", "nfl_week": expected, "source_weeks": weeks,
            "held": list(held), "held_detail": {k: {"week": expected} for k in held}}


class SourceFreshnessTest(unittest.TestCase):

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

    def open(self, name, body, width=375, code=200, seed=None):
        context = self.browser.new_context(viewport={"width": width, "height": 812})
        self.addCleanup(context.close)
        page = context.new_page()
        if seed:
            page.add_init_script(seed)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
        page.route(STATUS_GLOB, lambda r: r.fulfill(status=code, content_type="application/json", body=json.dumps(body)))
        page.goto(f"{self.base}/{name}.html", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(300)
        return page

    def dot(self, page):
        page.click(".morewrap > button")
        loc = page.locator('.morewrap .menu a[href="freshness.html"] .ddf-fresh-dot')
        if not loc.count():
            return None
        return loc.get_attribute("data-state"), loc.get_attribute("aria-label")

    def test_dot_states_on_every_kind_of_page(self):
        cases = {
            "all": (status({}), "All sources fresh"),
            "some": (status({"usatoday": 10}, held=["usatoday"]), "Some sources fresh (6 of 7)"),
            "none": (status({k: 10 for k in SOURCES}), "No sources fresh"),
        }
        for state, (body, label) in cases.items():
            for name in ("values", "freshness"):
                with self.subTest(state=state, page=name):
                    self.assertEqual(self.dot(self.open(name, body)), (state, label))

    def test_header_dot_is_the_entry_beside_the_menu_button(self):
        cases = {"all": status({}), "some": status({"usatoday": 10}), "none": status({k: 10 for k in SOURCES})}
        words = {"all": "All sources fresh", "some": "Some sources fresh", "none": "No sources fresh"}
        for width in (375, 1280):
            for state, body in cases.items():
                for name in ("index", "values"):
                    with self.subTest(width=width, state=state, page=name):
                        page = self.open(name, body, width=width)
                        link = page.locator("header .ddf-fresh-hdr a")
                        self.assertEqual(link.count(), 1)
                        self.assertEqual(link.get_attribute("href"), "freshness.html")
                        self.assertIn(words[state], link.get_attribute("aria-label"))
                        self.assertEqual(link.locator(".ddf-fresh-dot").get_attribute("data-state"), state)
                        box = link.bounding_box()
                        self.assertGreaterEqual(box["height"], 44)
                        self.assertGreaterEqual(box["width"], 44)
                        self.assertLessEqual(box["x"] + box["width"], width)
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
        page = self.open("values", cases["some"])
        page.click("header .ddf-fresh-hdr a")
        page.wait_for_url("**/freshness.html")
        self.assertIn("Source freshness", page.inner_text("h1"))
        page = self.open("values", cases["some"])
        page.click(".morewrap > button")
        self.assertTrue(page.locator(".morewrap.open .menu").count())

    def test_header_fits_with_league_chip_and_bookmark(self):
        """Values with a seeded league (chip) and the Bookmark button showing, plus the dot and Menu, at phone widths."""
        body = status({"usatoday": 10})
        for width in (320, 360, 375, 390):
            with self.subTest(width=width):
                page = self.open("values", body, width=width, seed=LEAGUE_SEED)
                page.wait_for_selector("header .ddf-fresh-hdr a")
                shown = page.evaluate("""() => ['header .ddf-bm-wrap', 'header .ddf-chip, header [class*=chip]']
                    .map(q => { const e = document.querySelector(q); return !!(e && e.getClientRects().length); })""")
                page.wait_for_timeout(600)
                self.assertTrue(shown[0], "Bookmark button must be showing for this case")
                self.assertTrue(shown[1], "league chip must be showing for this case")
                box = page.locator("header .ddf-fresh-hdr a").bounding_box()
                self.assertGreaterEqual(box["height"], 44)
                self.assertGreaterEqual(box["width"], 44)
                self.assertIn("Source freshness", page.locator("header .ddf-fresh-hdr a").get_attribute("aria-label"))
                over = page.evaluate("""(w) => [...document.querySelectorAll('header *')].filter(e => e.getClientRects().length
                    && e.getBoundingClientRect().right > w + 0.5).map(e => e.tagName + '.' + e.className)""", width)
                self.assertEqual(over, [])
                if width >= 360:  # at 320 the Values rank controls (not the header) are wider than the screen on main too
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)

    def test_no_header_dot_when_status_unreadable(self):
        page = self.open("values", {}, code=404)
        self.assertEqual(page.locator("header .ddf-fresh-hdr").count(), 0)

    def test_no_dot_when_status_unreadable(self):
        for name in ("values", "freshness"):
            with self.subTest(page=name):
                self.assertIsNone(self.dot(self.open(name, {}, code=404)))
        page = self.open("freshness", {}, code=404)
        self.assertIn("not available", page.inner_text("#fresh-sum-t"))
        self.assertEqual(page.locator(".fresh-item").count(), 0)

    def test_menu_link_and_footer_sitemap(self):
        page = self.open("values", status({}))
        page.click(".morewrap > button")
        self.assertEqual(page.locator('.morewrap .menu a[href="freshness.html"]').inner_text().strip(), "Source freshness")
        self.assertEqual(page.locator('footer.sitemap a[href="freshness.html"]').count(), 1)

    def test_page_lists_every_source_with_reason(self):
        page = self.open("freshness", status({"usatoday": 10}, held=["usatoday"]))
        self.assertEqual(page.locator(".fresh-item").count(), 7)
        self.assertEqual(page.locator(".fresh-item h2").all_inner_texts(),
                         ["CBS Sports", "USA Today", "FantasyPros", "FantasyCalc", "ESPN", "CBS rest-of-season", "Razzball"])
        usa = page.locator('.fresh-item[data-source="usatoday"]')
        text = usa.inner_text()
        for part in ("Behind", "Week 10", "Week 11", "held back", "Still on Week 10"):
            self.assertIn(part, text)
        self.assertIn("Fresh", page.locator('.fresh-item[data-source="cbs"] .fresh-chip').inner_text())
        self.assertIn("newest expected week", page.inner_text(".fresh-rule"))
        self.assertIn("6 of 7", page.inner_text("#fresh-sum"))
        page.set_viewport_size({"width": 375, "height": 812})
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 375)

    def test_behind_wording_before_and_after_thursday_noon(self):
        before = self.open("freshness", status({"razzball": 10}))
        self.assertIn("Not yet published for Week 11.", before.locator('.fresh-item[data-source="razzball"]').inner_text())
        after = self.open("freshness", status({"razzball": 10}, stale_after=ALREADY_STALE))
        item = after.locator('.fresh-item[data-source="razzball"]')
        self.assertIn("Stale", item.inner_text())
        self.assertIn("Still on Week 10 after Thursday 12:00 CT.", item.inner_text())


if __name__ == "__main__":
    unittest.main()
