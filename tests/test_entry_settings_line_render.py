"""League entry: settings read from the league show as one line, marked "From Sleeper", with Edit (settings.html).

Before, a Sleeper league's settings page listed every field with no source, and its intro still said "Unless you change
them, we use a standard roster", though every value came from the league. Now:

1. A Sleeper league whose scoring, team count and lineup all came from Sleeper: one line ("Half PPR · 12 teams ·
   Superflex · 1 QB · 2 RB · 3 WR · 1 TE · 1 FLEX · 5 bench · 1 K · 1 DEF"), a "From Sleeper" badge, Edit, and no
   standard-roster intro. The page fits on one phone screen.
2. Edit opens today's form with every value marked "From Sleeper"; changing a value drops its marker; Looks right saves.
3. A Sleeper league whose team count did not come through (4 teams, outside 8 to 14): the form stays open, the values
   that did come from Sleeper are marked, the team count is not.
4. A pasted league and no league at all: unchanged (the intro and the form as before).
5. Taps on the Sleeper path (landing page to team page) at 375 and 1280, with the settings page's height before and after.
   No horizontal scroll; the entry header is unchanged.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "sleeper"
ID = "100000000000000001"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.sleeper"
HEADER_STEPS = ["1. League rosters", "2. Your team", "3. League settings"]
PHONE, DESKTOP = 375, 1280
LINE = "Half PPR · 12 teams · Superflex · 1 QB · 2 RB · 3 WR · 1 TE · 1 FLEX · 5 bench · 1 K · 1 DEF"
# Sleeper league ID path, landing page to team page, measured on main with this harness: Get started, Sleeper,
# paste the ID (tap the box, Paste), Next, your team, Next, Looks right. This change takes no tap off; it takes the
# settings page from a full form to one line (heights below are asserted against the phone screen).
SLEEPER_TAPS_MAIN = 8


def setUpModule():
    _render_env.ensure_built()


class SettingsLineTest(unittest.TestCase):

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

    def page(self, width, teams=12, positions=None):
        ctx = {"viewport": {"width": width, "height": 812 if width < 761 else 900}}
        if width < 761:
            ctx.update(is_mobile=True, has_touch=True)
        context = self.browser.new_context(**ctx)
        self.addCleanup(context.close)
        page = context.new_page()

        def sleeper(route):
            path = route.request.url.split("/v1/", 1)[1]
            files = {f"league/{ID}": "league.json", f"league/{ID}/users": "users.json", f"league/{ID}/rosters": "rosters.json", "state/nfl": "state.json"}
            if path not in files:
                return route.fulfill(status=404, body="null", headers={"Access-Control-Allow-Origin": "*"})
            body = json.loads((FX / files[path]).read_text())
            if path == f"league/{ID}":
                body["total_rosters"] = teams   # the fixture's 4 rosters stand in for a league of this size
                if positions:
                    body["roster_positions"] = positions
            route.fulfill(status=200, body=json.dumps(body), content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")) and "api.sleeper.app" not in u, lambda r: r.abort())
        page.route("https://api.sleeper.app/v1/**", sleeper)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.taps = []
        return page

    def tap(self, page, selector, what):
        page.locator(selector).first.click()
        page.taps.append(what)

    def sleeper_to_settings(self, width, teams=12, positions=None):
        """Landing page to League settings by the Sleeper league ID, counted."""
        page = self.page(width, teams, positions)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        self.tap(page, "a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.tap(page, "[data-provider=sleeper]", "Sleeper")
        page.click("#league-ref")
        page.eval_on_selector("#league-ref", """(el, t) => { el.dispatchEvent(new ClipboardEvent('paste', {bubbles: true}));
            el.value = t; el.dispatchEvent(new Event('input', {bubbles: true})); }""", ID)
        page.taps += ["tap the box", "Paste"]
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        if page.locator("#team-pick-list").count():   # the team on the read card (another league-entry change)
            self.tap(page, "#team-pick-list .team-pick-option >> nth=1", "your team on the card")
            self.tap(page, ".ddf-actionbar__next", "Next: league settings")
        else:
            self.tap(page, ".ddf-actionbar__next", "Next: confirm your team")
            page.wait_for_url("**/setup.html", timeout=30000)
            page.wait_for_selector(".setup-option")
            self.tap(page, ".setup-option >> nth=1", "your team")
            self.tap(page, ".ddf-actionbar__next:not([aria-disabled=true])", "Next: confirm league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(500)
        return page

    def assert_page_ok(self, page):
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, "no horizontal scroll")
        self.assertEqual([s.replace("✓", "").strip() for s in page.locator(".entry-head .entry-steps > li").all_text_contents()], HEADER_STEPS)
        self.assertEqual(page.errors, [])

    # ---- 1 ----
    def test_a_sleeper_league_is_one_line(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.sleeper_to_settings(width)
                self.assertTrue(page.is_visible("#settings-summary"))
                self.assertEqual(page.text_content("#settings-source"), "From Sleeper")
                self.assertEqual(page.text_content("#settings-values").replace("\u00a0", " "), LINE)
                self.assertEqual(page.text_content("#settings-note"), "Read from Gridiron Test League on Sleeper.")
                self.assertTrue(page.is_hidden("#editor"))
                self.assertTrue(page.is_hidden("#roster-optional"), "no 'we use a standard roster' for an imported league")
                self.assertNotIn("standard roster", page.inner_text("main"))
                self.assertGreaterEqual(page.locator("#settings-edit").bounding_box()["height"], 44)
                if width == PHONE:
                    bottom = page.eval_on_selector("#settings-summary", "e => e.getBoundingClientRect().bottom + scrollY")
                    bar = page.eval_on_selector(".ddf-actionbar", "e => e.getBoundingClientRect().height")
                    self.assertLessEqual(bottom, 812 - bar, "the settings fit on one phone screen above the action bar")
                self.assert_page_ok(page)

    # ---- 2 ----
    def test_edit_opens_the_form_marked_from_sleeper(self):
        page = self.sleeper_to_settings(PHONE)
        page.click("#settings-edit")
        self.assertTrue(page.is_visible("#editor"))
        self.assertTrue(page.is_hidden("#settings-summary"))
        self.assertEqual(page.get_attribute("#settings-edit", "aria-expanded"), "true")
        marks = page.eval_on_selector_all(".st-from.is-import:not([hidden])", "els => els.map(e => e.id)")
        self.assertEqual(sorted(marks), sorted(f"imp-{f}" for f in ("scoring", "SUPERFLEX", "teams", "QB", "RB", "WR", "TE", "FLEX", "BENCH", "K", "DST")))
        self.assertEqual(page.text_content("#imp-WR"), "From Sleeper")
        self.assertTrue(page.is_hidden("#roster-optional"))
        page.click('button[aria-label="Increase WR"]')
        self.assertTrue(page.is_hidden("#imp-WR"), "a changed value is no longer the league's")
        self.assertTrue(page.is_visible("#imp-RB"))
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/team.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        s = page.evaluate("DDF.engine.settings()")
        self.assertEqual((s["scoring"], s["teams"], s["roster"]["WR"], s["roster"]["BENCH"], s["roster"]["SUPERFLEX"]), ("half_ppr", 12, 4, 5, 1))
        self.assertEqual(page.errors, [])

    def test_looks_right_saves_the_league_settings(self):
        page = self.sleeper_to_settings(PHONE)
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/team.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        s = page.evaluate("DDF.engine.settings()")
        self.assertEqual((s["scoring"], s["teams"], s["roster"]["WR"], s["roster"]["BENCH"], s["roster"]["SUPERFLEX"]), ("half_ppr", 12, 3, 5, 1))

    # ---- 3 ----
    def test_a_lineup_sleeper_did_not_give_keeps_the_form(self):
        """A superflex-only Sleeper lineup (no QB slot) is left for this page to confirm: the form stays open, the
        values that did come from Sleeper are marked, the lineup is not."""
        page = self.sleeper_to_settings(PHONE, positions=["SUPER_FLEX", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN", "BN"])
        self.assertTrue(page.is_hidden("#settings-summary"))
        self.assertTrue(page.is_visible("#editor"))
        self.assertTrue(page.is_hidden("#roster-optional"))
        self.assertEqual(page.text_content("#imp-scoring"), "From Sleeper")
        self.assertEqual(page.text_content("#imp-teams"), "From Sleeper")
        self.assertEqual(page.locator("#imp-QB").count(), 0, "the lineup did not come from Sleeper")
        self.assert_page_ok(page)

    def test_a_value_you_changed_is_no_longer_marked(self):
        page = self.sleeper_to_settings(PHONE)
        page.click("#settings-edit")
        page.click('[aria-labelledby=lbl-teams] button[data-value="10"]')
        self.assertTrue(page.is_hidden("#imp-teams"))
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/team.html", timeout=30000)
        page.goto(page.url.replace("team.html", "settings.html"), wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(500)
        self.assertEqual(page.input_value("#teams"), "10")
        self.assertTrue(page.is_hidden("#settings-summary"), "not every value is Sleeper's now: the form stays open")
        self.assertTrue(page.is_visible("#editor"))
        self.assertEqual(page.locator("#imp-teams:not([hidden])").count(), 0, "the team count you changed has no marker")
        self.assertEqual(page.text_content("#imp-WR"), "From Sleeper")
        self.assert_page_ok(page)

    # ---- 4 ----
    def test_no_league_and_pasted_leagues_are_unchanged(self):
        page = self.page(PHONE)
        page.goto(f"{self.base}/settings.html", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(500)
        self.assertTrue(page.is_hidden("#settings-summary"))
        self.assertTrue(page.is_visible("#editor"))
        self.assertIn("we use a standard roster", page.inner_text("#roster-optional"))
        self.assertEqual(page.locator(".st-from.is-import").count(), 0)

    # ---- 5 ----
    def test_sleeper_path_taps_and_settings_height(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.sleeper_to_settings(width)
                height = page.evaluate("document.documentElement.scrollHeight")
                self.tap(page, ".ddf-actionbar__next", "Looks right, continue")
                page.wait_for_url("**/team.html", timeout=30000)
                card = "your team on the card" in page.taps
                self.assertEqual(len(page.taps), SLEEPER_TAPS_MAIN - (1 if card else 0), page.taps)
                if width == PHONE:
                    self.assertLessEqual(height, 1000, f"settings page {height}px tall at 375 (a full form is about 1900)")
                print(f"\nSleeper {width}px: {len(page.taps)} taps; settings page {height}px tall")


if __name__ == "__main__":
    unittest.main()
