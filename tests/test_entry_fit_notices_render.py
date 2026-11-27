"""League entry: say so when a league does not fit the values (settings.html), instead of a silent default.

Before: an 18-team Sleeper league showed 12 teams with no notice (the site values 8, 10, 12 and 14 teams; any other
size fell back to 12), and a Sleeper league's TE premium (extra points per catch for tight ends) was dropped without a
word. Now:

1. 18 teams: "Your league has 18 teams. Values are for 8, 10, 12 or 14 teams, so we use 14." Settings use 14.
2. TE premium 0.5: "Your league gives tight ends 0.5 extra points per catch. Values do not include that yet."
3. Both at once: both lines. A league that fits (12 teams, no TE premium), a pasted league and no league: no notice.
4. No tap added on the Sleeper path; no horizontal scroll at 375 and 1280; the entry header is unchanged.
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


class FitNoticeTest(unittest.TestCase):

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

    def page(self, width, teams=12, te=0):
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
                if te:
                    body["scoring_settings"]["bonus_rec_te"] = te
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

    def sleeper_to_settings(self, width, teams=12, te=0):
        """Landing page to League settings by the Sleeper league ID, counted."""
        page = self.page(width, teams, te)
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
        page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls())", timeout=60000)
        page.wait_for_timeout(500)
        return page

    def assert_page_ok(self, page):
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, "no horizontal scroll")
        self.assertEqual([s.replace("\u2713", "").strip() for s in page.locator(".entry-head .entry-steps > li").all_text_contents()], HEADER_STEPS)
        self.assertEqual(page.errors, [])

    def notice(self, page):
        return page.locator("#fit-notice p").all_text_contents() if page.is_visible("#fit-notice") else []

    # ---- 1 ----
    def test_eighteen_teams_says_what_is_used(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.sleeper_to_settings(width, teams=18)
                self.assertEqual(self.notice(page), ["Your league has 18 teams. Values are for 8, 10, 12 or 14 teams, so we use 14."])
                self.assertEqual(page.input_value("#teams"), "14")
                self.assertEqual(page.evaluate("DDF.engine.settings().teams"), 14)
                self.assert_page_ok(page)

    def test_odd_and_small_leagues_use_the_closest_size(self):
        """Behavior change: a 4-team league used to get no team count from Sleeper (12 by default); now 8, and it says so.
        A count between sizes rounds up (9 -> 10, 13 -> 14), Jeremy 2026-11-24."""
        for teams, used in ((4, 8), (9, 10), (13, 14)):
            with self.subTest(teams=teams):
                page = self.sleeper_to_settings(PHONE, teams=teams)
                self.assertEqual(self.notice(page), [f"Your league has {teams} teams. Values are for 8, 10, 12 or 14 teams, so we use {used}, the closest size at or above yours."])
                self.assertEqual(page.input_value("#teams"), str(used))

    # ---- 2 ----
    def test_te_premium_is_named(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.sleeper_to_settings(width, te=0.5)
                self.assertEqual(self.notice(page), ["Your league gives tight ends 0.5 extra points per catch. Values do not include that yet."])
                self.assertEqual(page.input_value("#teams"), "12")
                self.assert_page_ok(page)

    # ---- 3 ----
    def test_both_and_neither(self):
        page = self.sleeper_to_settings(PHONE, teams=18, te=1)
        self.assertEqual(len(self.notice(page)), 2)
        self.assertIn("1 extra point per catch", self.notice(page)[1])
        page = self.sleeper_to_settings(PHONE)
        self.assertEqual(self.notice(page), [], "a league that fits gets no notice")
        page = self.page(PHONE)
        page.goto(f"{self.base}/settings.html", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(500)
        self.assertTrue(page.is_hidden("#fit-notice"), "no league, no notice")

    def test_a_link_with_an_odd_team_count_rounds_up(self):
        """A page link's ?teams=9 used to be dropped (the league kept its own size); it now uses 10, like the import."""
        for teams, used in (("9", 10), ("13", 14), ("18", 14), ("6", 8)):
            with self.subTest(teams=teams):
                page = self.page(DESKTOP)
                page.goto(f"{self.base}/team.html#?scoring=ppr&teams={teams}", wait_until="networkidle", timeout=60000)
                page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls()) && DDF.engine.settings().teams", timeout=60000)
                page.wait_for_timeout(500)
                self.assertEqual(page.evaluate("DDF.engine.settings().teams"), used)

    # ---- 4 ----
    def test_no_tap_added(self):
        page = self.sleeper_to_settings(PHONE, teams=18, te=0.5)
        self.tap(page, ".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)
        card = "your team on the card" in page.taps
        self.assertEqual(len(page.taps), SLEEPER_TAPS_MAIN - (1 if card else 0), page.taps)
        page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls())", timeout=60000)
        self.assertEqual(page.evaluate("DDF.engine.settings().teams"), 14)


if __name__ == "__main__":
    unittest.main()
