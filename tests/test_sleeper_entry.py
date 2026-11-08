"""JEG-1570: connect.html with Sleeper selected loads the league from its link or ID (Sleeper API answered by fixtures).

1. Sleeper view: one field ("Sleeper league link or ID") with the league ID help; no paste step, no rosters-page
   button, no copy-the-page tutorial; the paste box stays one tap away. ESPN and Yahoo views unchanged.
2. A league ID loads every team: recognition card, "We found: <name>, N teams, M players", ddf:pasted (source sleeper,
   suggestedName, leagueId on the device), league settings saved for settings.html, the sticky Next enabled, setup lists
   the teams.
3. Plain-words errors (not found, old season, network) with the paste fallback; no calls anywhere but Sleeper.
4. No overflow at 1440, 390 and 360.
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


def setUpModule():
    _render_env.ensure_built()


class SleeperEntryTest(unittest.TestCase):

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

    def page(self, width=1440, league="league", fail=None):
        context = self.browser.new_context(viewport={"width": width, "height": 900 if width > 760 else 800})
        self.addCleanup(context.close)
        page = context.new_page()
        calls = []
        page.calls = calls

        def sleeper(route):
            url = route.request.url
            calls.append(url)
            if fail == "network":
                return route.abort()
            path = url.split("/v1/", 1)[1]
            body = None
            if path == f"league/{ID}":
                body = json.loads((FX / "league.json").read_text()) if league == "league" else json.loads((FX / "old-league.json").read_text())["league"]
            elif path == f"league/{ID}/users":
                body = json.loads((FX / "users.json").read_text())
            elif path == f"league/{ID}/rosters":
                body = json.loads((FX / "rosters.json").read_text())
            elif path == "state/nfl":
                body = json.loads((FX / "state.json").read_text())
            if body is None or fail == "notfound" and path.startswith("league/"):
                return route.fulfill(status=404, body="null", headers={"Access-Control-Allow-Origin": "*"})
            route.fulfill(status=200, body=json.dumps(body), content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

        def other(route):
            if route.request.resource_type in ("fetch", "xhr"):
                calls.append(route.request.url)   # data calls only (page fonts are not data)
            route.abort()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")) and "api.sleeper.app" not in u, other)
        page.route("https://api.sleeper.app/v1/**", sleeper)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        return page

    def overflow(self, page):
        return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")

    def test_sleeper_view_is_one_field(self):
        for width in (1440, 390, 360):
            with self.subTest(width=width):
                page = self.page(width)
                self.assertTrue(page.is_visible("#entry"), "ESPN: paste step shown")
                espn_label = page.text_content("label[for=league-ref]")
                page.click('[data-provider="sleeper"]')
                self.assertEqual(page.text_content("label[for=league-ref]"), "Sleeper league link or ID")
                self.assertEqual(page.text_content("#get-link"), "Load my league")
                self.assertTrue(page.is_hidden("#entry"), "no paste step")
                self.assertTrue(page.is_hidden("#step1-title .step-num"), "one step, no numbering")
                self.assertTrue(page.text_content("#step1-title").endswith("Add your Sleeper league"))
                self.assertIn("No copying needed", page.text_content(".way-link h3 + p"))
                self.assertIn("sleeper.com/leagues/", page.text_content("#sleeper-example"))
                self.assertEqual(page.locator(".ddf-actionbar__next").get_attribute("aria-disabled"), "true", "Next waits for the league")
                order = page.evaluate("[...document.querySelectorAll('#id-help, #sleeper-paste')].map(e => e.id)")
                self.assertEqual(order, ["id-help", "sleeper-paste"], "the ID help comes before the paste fallback")
                self.assertTrue(page.is_hidden(".way-how"), "no copy-the-page tutorial")
                self.assertTrue(page.is_hidden(".jump-paste"))
                self.assertNotIn("copy it", page.text_content("#connect-intro"))
                self.assertTrue(page.is_visible("#id-help"))
                self.assertTrue(page.is_visible("#sleeper-paste-instead"))
                self.assertEqual(self.overflow(page), 0)
                page.click("#id-help > summary")
                self.assertTrue(page.is_visible('[data-idhelp="sleeper"]'))
                page.click("#sleeper-paste-instead")
                self.assertTrue(page.is_visible("#entry"), "the paste box stays one tap away")
                page.click('[data-provider="yahoo"]')
                self.assertEqual(page.text_content("label[for=league-ref]"), espn_label)
                self.assertTrue(page.is_visible("#entry"))
                self.assertTrue(page.is_visible(".way-how"))
                self.assertEqual(page.errors, [])

    def test_league_id_loads_every_team(self):
        page = self.page(390)
        page.click('[data-provider="sleeper"]')
        self.assertEqual(page.locator(".ddf-actionbar__next").get_attribute("aria-disabled"), "true")
        page.fill("#league-ref", f"https://sleeper.com/leagues/{ID}/team")
        page.click("#get-link")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        msg = page.text_content("#link-result")
        self.assertTrue(msg.startswith("We found: Gridiron Test League, 4 teams, "), msg)
        kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
        self.assertEqual(kept["source"], "sleeper")
        self.assertEqual(kept["suggestedName"], "Gridiron Test League")
        self.assertEqual(kept["leagueId"], ID)
        self.assertEqual([t["name"] for t in kept["teams"]], ["Alpha Squad", "beta_user", "🔥🔥🔥", "Alpha-Squad"])
        self.assertEqual(page.text_content("#recognition-title"), "Here's what we read from Sleeper")
        self.assertTrue(page.is_hidden("#edit-team-names"), "Sleeper team names come from the league; no rename box")
        self.assertTrue(all(t["players"] for t in kept["teams"]))
        saved = page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.league-settings'))")
        self.assertEqual(saved["scoring"], "half_ppr")
        page.wait_for_function("() => document.querySelector('.ddf-actionbar__next').getAttribute('aria-disabled') === 'false'", timeout=5000)
        self.assertTrue(all("api.sleeper.app/v1/" in u for u in page.calls), page.calls)
        self.assertEqual(len([u for u in page.calls if "api.sleeper.app" in u]), 4)
        self.assertEqual(self.overflow(page), 0)
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/setup.html", timeout=20000)
        self.assertEqual(page.input_value("#league-name"), "Gridiron Test League")
        self.assertEqual(len(page.locator("input[name=team]").all()), 4)
        self.assertEqual(page.errors, [])

    def test_switching_away_mid_load_drops_the_answer(self):
        page = self.page(1440)
        page.route("https://api.sleeper.app/v1/state/nfl", lambda route: (page.wait_for_timeout(1500), route.fulfill(status=200, body=(FX / "state.json").read_text(), content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})))
        page.click('[data-provider="sleeper"]')
        page.fill("#league-ref", ID)
        page.click("#get-link")
        page.click('[data-provider="espn"]')
        page.wait_for_timeout(2500)
        self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"), "an answer for a provider no longer selected is dropped")
        self.assertTrue(page.is_hidden("#recognized"))
        self.assertFalse(page.is_disabled("#get-link"))

    def test_errors_in_plain_words(self):
        cases = (("notfound", "league", "could not find a Sleeper league"), (None, "old", "from the 2025 season"),
                 ("network", "league", "could not reach Sleeper"))
        for fail, league, text in cases:
            with self.subTest(case=text):
                page = self.page(1440, league=league, fail=fail)
                page.click('[data-provider="sleeper"]')
                page.fill("#league-ref", ID)
                page.press("#league-ref", "Enter")
                page.wait_for_function("() => document.getElementById('link-result').classList.contains('is-error')", timeout=20000)
                self.assertIn(text, page.text_content("#link-result"))
                self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"))
                self.assertTrue(page.is_visible("#sleeper-paste-instead"))
        page = self.page(390)
        page.click('[data-provider="sleeper"]')
        page.fill("#league-ref", "not a league")
        page.click("#get-link")
        self.assertIn("could not find a Sleeper league ID", page.text_content("#link-result"))
        self.assertEqual(page.calls, [], "no call without an ID")


if __name__ == "__main__":
    unittest.main()
