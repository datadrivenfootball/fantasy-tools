"""League entry: a Sleeper username finds your leagues and your team (connect.html), with tap counts at 375px and 1280px.

Before, a Sleeper league needed its 18-digit ID: leave for the Sleeper app, copy the ID, come back, paste it, then
find your team among every team. Now the same box takes a Sleeper username. Sleeper's public lookup lists that
person's leagues for the season (one loads at once, several are listed), and the roster they own is preselected on
the read card. League settings shows its one line From Sleeper. The username is never stored.

Sleeper is faked here (Playwright routes for api.sleeper.app); nothing leaves the test.
1. One league: username, Find my league, the read card with your team preselected; Next goes straight to League
   settings (From Sleeper), Looks right. Three Sleeper lookups and the four league calls; the username is not stored.
2. Several leagues: a list to pick from (44px rows on a phone), then the same.
3. An unknown username, a user with no leagues this season, and no network say so in plain words.
4. A league link or ID still loads as before (no team preselected: the ID alone does not say which is yours).
5. Tap count from the landing page to the team page, against the league ID path on this same build.
6. No horizontal scroll; the entry header is unchanged.

Counting as in the setup audit: one tap, click, key shortcut or app switch; typing or pasting into a box is two (tap,
then type or Paste); copying a league ID in the Sleeper app is 6 on a phone (open the app, league, settings, scroll,
Copy League ID, back) and 3 on a computer (open the league on sleeper.com, copy the address, back).
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
USER = "alpha_user"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste && DDF.sleeper"
HEADER_STEPS = ["1. League rosters", "2. Your team", "3. League settings"]
PHONE, DESKTOP = 375, 1280
OFFSITE_ID = {PHONE: 6, DESKTOP: 3}


def setUpModule():
    _render_env.ensure_built()


class Run:
    def __init__(self, page, width):
        self.page, self.width, self.taps, self.log, self.pages = page, width, 0, [], []
        page.on("framenavigated", lambda f: f == page.main_frame and self.pages.append(f.url.split("/")[-1].split("?")[0].split("#")[0]))

    def count(self, n, what):
        self.taps += n
        self.log.append(f"{n} {what}")

    def tap(self, selector, what=None):
        self.page.locator(selector).first.click()
        self.count(1, what or selector)

    def type(self, selector, text, what=None):
        self.page.locator(selector).first.click()
        self.page.keyboard.type(text)
        self.count(2, what or f"type into {selector}")

    def paste(self, selector, text, what=None):
        self.page.locator(selector).first.click()
        self.page.eval_on_selector(selector, """(el, text) => {
            el.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true}));
            el.value = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }""", text)
        self.count(2, what or f"paste into {selector}")

    def entry_pages(self):
        seen = []
        for p in self.pages:
            if p in ("connect.html", "setup.html", "settings.html") and p not in seen:
                seen.append(p)
        return seen


class SleeperUsernameTest(unittest.TestCase):

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

    def page(self, width, leagues="one"):
        """A page with Sleeper faked. leagues: one | two | none; mode 'down' aborts every Sleeper call."""
        ctx = {"viewport": {"width": width, "height": 812 if width < 761 else 900}}
        if width < 761:
            ctx.update(is_mobile=True, has_touch=True)
        context = self.browser.new_context(**ctx)
        self.addCleanup(context.close)
        page = context.new_page()
        page.calls, page.down = [], False
        listed = json.loads((FX / "user-leagues.json").read_text())
        listed = {"one": listed[:1], "two": listed, "none": []}[leagues]

        def sleeper(route):
            url = route.request.url
            page.calls.append(url)
            if page.down:
                return route.abort()
            path = url.split("/v1/", 1)[1]
            bodies = {f"league/{ID}": "league.json", f"league/{ID}/users": "users.json", f"league/{ID}/rosters": "rosters.json",
                      "state/nfl": "state.json", f"user/{USER}": "user.json"}
            hdr = {"Access-Control-Allow-Origin": "*"}
            if path == "user/u1/leagues/nfl/2026":
                return route.fulfill(status=200, body=json.dumps(listed), content_type="application/json", headers=hdr)
            if path not in bodies:
                return route.fulfill(status=404, body="null", content_type="application/json", headers=hdr)
            route.fulfill(status=200, body=(FX / bodies[path]).read_text(), content_type="application/json", headers=hdr)

        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")) and "api.sleeper.app" not in u,
                   lambda r: r.abort())
        page.route("https://api.sleeper.app/v1/**", sleeper)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        return page

    def connect(self, width, leagues="one"):
        page = self.page(width, leagues)
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        return page

    def assert_page_ok(self, page):
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, "no horizontal scroll")
        self.assertEqual([s.replace("✓", "").strip() for s in page.locator(".entry-head .entry-steps > li").all_text_contents()], HEADER_STEPS, "header unchanged")
        self.assertEqual(page.errors, [])

    def team_names(self):
        users = {u["user_id"]: u for u in json.loads((FX / "users.json").read_text())}
        rosters = sorted(json.loads((FX / "rosters.json").read_text()), key=lambda r: r["roster_id"])
        return rosters, users

    # ---- 1 ----
    def test_a_username_with_one_league_loads_it_with_your_team_picked(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                page.click("[data-provider=sleeper]")
                self.assertEqual(page.text_content("label[for=league-ref]"), "Sleeper username or league ID")
                self.assertEqual(page.text_content("#get-link"), "Find my league")
                Run(page, width).type("#league-ref", USER)
                page.click("#get-link")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.assertEqual(page.text_content("#recognition-title"), "Here's what we read from Sleeper")
                self.assertEqual(page.locator("#team-pick-list .team-pick-option.selected strong").all_text_contents(), ["Alpha Squad"])
                self.assertEqual(page.locator("#team-pick-list input:checked").count(), 1)
                msg = page.text_content("#link-result")
                self.assertTrue(msg.startswith("We found: Gridiron Test League, 4 teams, "), msg)
                self.assertIn("Your team: Alpha Squad, matched to alpha_user.", msg)
                kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
                self.assertEqual((kept["source"], kept["leagueId"], kept["me"], kept["own"]), ("sleeper", ID, 0, 0))
                self.assertEqual(page.get_attribute("#connect-next", "href"), "settings.html", "your team is known: Next goes to League settings")
                self.assertEqual(page.text_content(".ddf-actionbar__next").strip(), "Next: league settings")
                paths = sorted(set(u.split("/v1/", 1)[1] for u in page.calls))
                self.assertEqual(paths, sorted([f"user/{USER}", "state/nfl", "user/u1/leagues/nfl/2026", f"league/{ID}", f"league/{ID}/users", f"league/{ID}/rosters"]))
                self.assertEqual(sum(1 for u in page.calls if u.endswith(f"user/{USER}")), 1, "one lookup, even after leaving the box")
                stored = page.evaluate("JSON.stringify(Object.assign({}, localStorage)) + JSON.stringify(Object.assign({}, sessionStorage))")
                self.assertNotIn(USER, stored, "the username is not stored")
                self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.entry-last'))"), {"v": 2, "platform": "sleeper", "id": ID})
                self.assert_page_ok(page)
                page.click(".ddf-actionbar__next")
                page.wait_for_url("**/settings.html", timeout=30000)
                page.wait_for_selector("#settings-summary:not([hidden])", timeout=30000)
                self.assertEqual(page.text_content("#settings-source"), "From Sleeper")
                self.assert_page_ok(page)

    # ---- 2 ----
    def test_several_leagues_are_listed_to_pick_from(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width, "two")
                page.click("[data-provider=sleeper]")
                page.fill("#league-ref", USER)
                page.press("#league-ref", "Enter")
                page.wait_for_selector("#link-result [data-sleeper-league]", timeout=20000)
                self.assertEqual(page.text_content("#link-result .sleeper-leagues-head"), "Found 2 leagues for alpha_user this season. Which one?")
                rows = page.locator("#link-result [data-sleeper-league]")
                self.assertEqual(rows.locator("strong").all_text_contents(), ["Gridiron Test League", "Office League"])
                self.assertEqual(rows.locator("small").all_text_contents(), ["4 teams · Half PPR", "10 teams · PPR"])
                if width == PHONE:
                    for b in rows.all():
                        self.assertGreaterEqual(b.bounding_box()["height"], 44)
                self.assertTrue(page.is_hidden("#recognized"))
                self.assert_page_ok(page)
                rows.first.click()
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.assertEqual(page.locator("#team-pick-list .team-pick-option.selected strong").all_text_contents(), ["Alpha Squad"])
                self.assertEqual(page.get_attribute("#connect-next", "href"), "settings.html")
                self.assert_page_ok(page)

    # ---- 3 ----
    def test_problems_are_said_plainly(self):
        cases = (("nobody_here", "one", False, "We could not find a Sleeper user named nobody_here."),
                 (USER, "none", False, "but no football leagues for the 2026 season"),
                 (USER, "one", True, "We could not reach Sleeper just now."))
        for name, leagues, down, text in cases:
            with self.subTest(name=name, leagues=leagues, down=down):
                page = self.connect(PHONE, leagues)
                page.down = down
                page.click("[data-provider=sleeper]")
                page.fill("#league-ref", name)
                page.click("#get-link")
                page.wait_for_function("() => document.getElementById('link-result').classList.contains('is-error')", timeout=20000)
                self.assertIn(text, page.text_content("#link-result"))
                self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"))
                self.assertFalse(page.is_disabled("#get-link"), "Find my league works again")
                self.assert_page_ok(page)

    # ---- 4 ----
    def test_a_league_id_still_loads_without_a_team_picked(self):
        page = self.connect(PHONE)
        page.click("[data-provider=sleeper]")
        Run(page, PHONE).paste("#league-ref", f"https://sleeper.com/leagues/{ID}")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertEqual(page.locator("#team-pick-list input:checked").count(), 0)
        self.assertTrue(page.text_content("#link-result").endswith("Check the list below, then pick your team."))
        self.assertFalse(any("/user/" in u for u in page.calls), "no username lookup for an ID")
        self.assert_page_ok(page)

    # ---- 5 ----
    def finish(self, page, run, pick=True):
        if pick:
            run.tap("#team-pick-list .team-pick-option >> nth=0", "your team on the card")
        run.tap(".ddf-actionbar__next", "Next: league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_selector("#settings-summary:not([hidden])", timeout=30000)
        run.tap(".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)

    def start(self, width, leagues="one"):
        page = self.page(width, leagues)
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        run.tap("[data-provider=sleeper]", "Sleeper")
        return page, run

    def test_tap_count_against_the_league_id_path(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page, before = self.start(width)
                before.count(OFFSITE_ID[width], "copy the league ID off this site")
                before.paste("#league-ref", ID, "paste the league ID")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.finish(page, before, pick=True)

                page, after = self.start(width)
                after.type("#league-ref", USER, "type your Sleeper username")
                after.tap("#get-link", "Find my league")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.finish(page, after, pick=False)
                self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).me"), 0, "your team")
                self.assertEqual(after.entry_pages(), ["connect.html", "settings.html"])
                self.assertEqual(after.taps, 7, "\n".join(after.log))
                self.assertEqual(before.taps - after.taps, OFFSITE_ID[width], "\n".join(before.log))   # Find my league replaces picking the team

                page, several = self.start(width, "two")
                several.type("#league-ref", USER, "type your Sleeper username")
                several.tap("#get-link", "Find my league")
                page.wait_for_selector("#link-result [data-sleeper-league]", timeout=20000)
                several.tap("#link-result [data-sleeper-league] >> nth=0", "your league")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.finish(page, several, pick=False)
                self.assertEqual(several.taps, 8, "\n".join(several.log))
                print(f"\nSleeper {width}px: {before.taps} taps by league ID, {after.taps} by username (one league), {several.taps} (several)")
                self.assertEqual(page.errors, [])


if __name__ == "__main__":
    unittest.main()
