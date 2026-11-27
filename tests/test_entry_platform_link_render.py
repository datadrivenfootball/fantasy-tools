"""League entry: a pasted league link sets the platform (connect.html), with tap counts for the main paths.

The bug: ESPN is preselected, so a pasted Sleeper or Yahoo link built an ESPN rosters address from the wrong ID
(sleeper.com/leagues/1387...968 -> fantasy.espn.com/football/league/rosters?leagueId=1387...968, a page that does not
exist). Now the link names its platform and the toggle follows it; a bare number keeps the platform as chosen.

1. A Yahoo, ESPN or Sleeper link switches the toggle and says so; the rosters address is the right site's.
2. A Sleeper link pasted while ESPN is selected loads the league (Sleeper API answered by fixtures).
3. A bare number keeps the chosen platform; one as long as a Sleeper ID offers Sleeper in one tap (no dead end).
4. The USO league (Yahoo 848938, Half PPR, WR 3, bench 5, Team 3) from the landing page to the team page, counted
   tap by tap at 375 and 1280. Before this change the phone path was 20 taps and 3 pages (the Yahoo toggle tap first,
   or a dead end); after, 19 and 3.
5. No horizontal scroll at 375 and 1280; the entry header is unchanged.

Counting (the setup audit's rule): one count is one tap, click, key shortcut or app switch. Pasting into a box is two
(tap the box, then Paste or Cmd+V). The rosters page itself is off this site: on a phone long-press, Select All, Copy
and back (4); on a computer select all, copy and back to the tab (3).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
USO = (ROOT / "tests" / "fixtures" / "entry_flow" / "uso-rosters.txt").read_text()
SLEEPER_FX = ROOT / "tests" / "fixtures" / "sleeper"
SLEEPER_ID = "100000000000000001"
YAHOO_LINK = "https://football.fantasysports.yahoo.com/f1/848938"
YAHOO_ROSTERS = "https://football.fantasysports.yahoo.com/f1/848938/starters"
ESPN_LINK = "https://fantasy.espn.com/football/league?leagueId=123456"
ESPN_ROSTERS = "https://fantasy.espn.com/football/league/rosters?leagueId=123456"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste && DDF.sleeper"
HEADER_STEPS = ["1. League rosters", "2. Your team", "3. League settings"]
PHONE, DESKTOP = 375, 1280
OFFSITE = {PHONE: 4, DESKTOP: 3}
# the USO path on main before this fix, measured with this harness (Yahoo toggle first): 20 taps on a phone, 19 on a
# computer, 3 pages (connect, setup, settings). This fix takes the toggle tap off. The other league-entry changes take
# their own share (the team picked on the read card: 1 tap and the team page), so the count holds in any merge order.
USO_TAPS_BEFORE = {PHONE: 20, DESKTOP: 19}


def setUpModule():
    _render_env.ensure_built()


class Run:
    """One user's path, counted. Every on-page action goes through tap() or paste()."""

    def __init__(self, page, width):
        self.page, self.width, self.taps, self.log, self.pages = page, width, 0, [], []
        self.skipped_get_link = False
        page.on("framenavigated", lambda f: f == page.main_frame and self.pages.append(f.url.split("/")[-1].split("?")[0].split("#")[0]))

    def count(self, n, what):
        self.taps += n
        self.log.append(f"{n} {what}")

    def tap(self, selector, what=None):
        self.page.locator(selector).first.click()
        self.count(1, what or selector)

    def paste(self, selector, text, what=None):
        """Tap the box, then Paste: a real paste event, then the text, then input (the browser's order)."""
        self.page.locator(selector).first.click()
        self.page.eval_on_selector(selector, """(el, text) => {
            el.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true}));
            el.value = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }""", text)
        self.count(2, what or f"paste into {selector}")

    def offsite(self):
        self.count(OFFSITE[self.width], "on the rosters page: select all, copy, back")

    def get_link(self, what="Get rosters link"):
        """Tap Get rosters link where it is shown. The ESPN and Yahoo quick wins (another league-entry change) show the
        rosters link as soon as the box holds an ID and hide that button; then there is nothing to tap."""
        if self.page.is_visible("#get-link"):
            self.tap("#get-link", what)
        else:
            self.page.wait_for_selector("#link-result a.button")
            self.skipped_get_link = True

    def entry_pages(self):
        seen = []
        for p in self.pages:
            if p in ("connect.html", "setup.html", "settings.html") and p not in seen:
                seen.append(p)
        return seen


class PlatformLinkTest(unittest.TestCase):

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

    def page(self, width):
        ctx = {"viewport": {"width": width, "height": 812 if width < 761 else 900}}
        if width < 761:
            ctx.update(is_mobile=True, has_touch=True)
        context = self.browser.new_context(**ctx)
        self.addCleanup(context.close)
        page = context.new_page()
        page.sleeper_calls = []

        def sleeper(route):
            url = route.request.url
            page.sleeper_calls.append(url)
            path = url.split("/v1/", 1)[1]
            files = {f"league/{SLEEPER_ID}": "league.json", f"league/{SLEEPER_ID}/users": "users.json",
                     f"league/{SLEEPER_ID}/rosters": "rosters.json", "state/nfl": "state.json"}
            if path not in files:
                return route.fulfill(status=404, body="null", headers={"Access-Control-Allow-Origin": "*"})
            route.fulfill(status=200, body=(SLEEPER_FX / files[path]).read_text(), content_type="application/json",
                          headers={"Access-Control-Allow-Origin": "*"})

        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")) and "api.sleeper.app" not in u,
                   lambda r: r.abort())
        page.route("https://api.sleeper.app/v1/**", sleeper)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        return page

    def connect(self, width):
        page = self.page(width)
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        return page

    def provider(self, page):
        return page.get_attribute("[data-provider][aria-pressed=true]", "data-provider")

    def assert_page_ok(self, page):
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, "no horizontal scroll")
        self.assertEqual([s.replace("\u2713", "").strip() for s in page.locator(".entry-head .entry-steps > li").all_text_contents()], HEADER_STEPS, "header unchanged")
        self.assertEqual(page.errors, [])

    # ---- 1 ----
    def test_a_link_sets_its_platform(self):
        cases = [("espn", YAHOO_LINK, "yahoo", YAHOO_ROSTERS, "That is a Yahoo link, so we switched to Yahoo."),
                 ("yahoo", ESPN_LINK, "espn", ESPN_ROSTERS, "That is an ESPN link, so we switched to ESPN."),
                 ("sleeper", YAHOO_LINK, "yahoo", YAHOO_ROSTERS, "That is a Yahoo link, so we switched to Yahoo.")]
        for width in (PHONE, DESKTOP):
            for start, link, want, rosters, note in cases:
                with self.subTest(width=width, start=start, link=link):
                    page = self.connect(width)
                    page.click(f"[data-provider={start}]")
                    run = Run(page, width)
                    run.paste("#league-ref", link)
                    self.assertEqual(self.provider(page), want)
                    self.assertEqual(page.text_content("#link-platform"), note)
                    self.assertTrue(page.is_visible("#link-platform"))
                    self.assertIsNone(page.get_attribute(f'[data-idhelp="{want}"]', "hidden"), "the ID help follows")
                    run.get_link()
                    self.assertEqual(page.get_attribute("#link-result a.button", "href"), rosters)
                    self.assertEqual(run.taps, 2 if run.skipped_get_link else 3, run.log)   # tap box, Paste, (Get rosters link): no toggle tap
                    self.assertEqual(page.sleeper_calls, [], "a Yahoo or ESPN link never asks Sleeper")
                    self.assertNotIn("is-error", page.get_attribute("#link-result", "class") or "")
                    self.assert_page_ok(page)

    def test_the_old_dead_end_is_gone(self):
        """ESPN preselected, the USO Yahoo link pasted, Get rosters link: before, fantasy.espn.com/...leagueId=848938."""
        page = self.connect(PHONE)
        self.assertEqual(self.provider(page), "espn", "ESPN stays the default")
        page.fill("#league-ref", YAHOO_LINK)
        Run(page, PHONE).get_link()
        href = page.get_attribute("#link-result a.button", "href")
        self.assertEqual(href, YAHOO_ROSTERS)
        self.assertNotIn("espn", href)

    # ---- 2 ----
    def test_a_sleeper_link_with_espn_selected_loads_the_league(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                self.assertEqual(self.provider(page), "espn")
                run = Run(page, width)
                run.paste("#league-ref", f"https://sleeper.com/leagues/{SLEEPER_ID}/team")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.assertEqual(self.provider(page), "sleeper")
                self.assertEqual(page.text_content("#link-platform"), "That is a Sleeper link, so we switched to Sleeper.")
                self.assertTrue(page.text_content("#link-result").startswith("We found: Gridiron Test League, 4 teams, "))
                self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).source"), "sleeper")
                self.assertEqual(run.taps, 2, run.log)   # tap box, Paste: the league loads by itself
                self.assertFalse(any("espn" in u for u in page.sleeper_calls))
                self.assert_page_ok(page)

    # ---- 3 ----
    def test_a_bare_number_keeps_the_chosen_platform(self):
        for width in (PHONE, DESKTOP):
            for start, want in (("yahoo", YAHOO_ROSTERS), ("espn", "https://fantasy.espn.com/football/league/rosters?leagueId=848938")):
                with self.subTest(width=width, start=start):
                    page = self.connect(width)
                    page.click(f"[data-provider={start}]")
                    page.fill("#league-ref", "848938")
                    self.assertEqual(self.provider(page), start)
                    self.assertTrue(page.is_hidden("#link-platform"))
                    Run(page, width).get_link()
                    self.assertEqual(page.get_attribute("#link-result a.button", "href"), want)
                    self.assert_page_ok(page)

    def test_a_sleeper_length_number_offers_sleeper(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                page.fill("#league-ref", SLEEPER_ID)
                self.assertEqual(self.provider(page), "espn", "a number alone does not switch")
                self.assertIn("as long as a Sleeper league ID", page.text_content("#link-platform"))
                button = page.locator("#link-platform [data-switch-provider=sleeper]")
                self.assertGreaterEqual(button.bounding_box()["height"], 44)
                button.click()
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.assertEqual(self.provider(page), "sleeper")
                self.assert_page_ok(page)

    def test_platform_of(self):
        page = self.connect(DESKTOP)
        cases = {"https://sleeper.com/leagues/123456789012345678/team": "sleeper", "sleeper.app/leagues/1234567": "sleeper",
                 "fantasy.espn.com/football/league/rosters?leagueId=1": "espn", "https://espn.com/fantasy": "espn",
                 "https://football.fantasysports.yahoo.com/f1/848938/3": "yahoo", "yahoo.com/f1/1": "yahoo",
                 "848938": None, "notespn.com/x": None, "": None}
        got = page.evaluate("cs => Object.fromEntries(Object.keys(cs).map(k => [k, DDF.connectEntry.platformOf(k)]))", cases)
        self.assertEqual(got, cases)

    # ---- 4 ----
    def uso_path(self, width):
        page = self.page(width)
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.assertEqual(self.provider(page), "espn")
        run.paste("#league-ref", YAHOO_LINK, "paste the USO league link")
        self.assertEqual(self.provider(page), "yahoo", "the link sets Yahoo: no toggle tap")
        run.get_link()
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS)
        run.count(1, "Open your rosters page")   # opens Yahoo in a new tab; not followed here
        run.offsite()
        run.paste("#rosters", USO, "paste every team's roster")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        self.assertIn("Found 12 teams", page.text_content("#recognition-summary"))
        self.assert_page_ok(page)
        if page.locator("#scoring-pick").count() and page.is_visible("#scoring-pick"):   # scoring asked on the card (another league-entry change)
            run.tap("#scoring-pick [data-scoring=half_ppr]", "Half PPR on the card")
        card = page.locator("#team-pick-list").count() > 0
        if card:   # the team is picked on the read card (another league-entry change); setup.html is skipped
            run.tap('#team-pick-list .team-pick-option:has-text("Team 3")', "Team 3 on the card")
            run.tap(".ddf-actionbar__next", "Next: league settings")
        else:
            run.tap(".ddf-actionbar__next", "Next: confirm your team")
            page.wait_for_url("**/setup.html", timeout=30000)
            page.wait_for_selector(".setup-option")
            run.tap('.setup-option:has(input[value="Team 3"])', "Team 3")
            run.tap(".ddf-actionbar__next:not([aria-disabled=true])", "Next: confirm league settings")
        run.card = card
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls())", timeout=60000)
        page.wait_for_timeout(300)
        if page.eval_on_selector("#scoring", "e => e.value") != "Half PPR":
            run.tap('[aria-labelledby=lbl-scoring] button[data-value="Half PPR"]', "Half PPR")
        for key, want in (("wr", 3), ("bench", 5)):
            cur = int(page.input_value(f"#lineup-{key}"))
            label = {"wr": "WR", "bench": "BENCH"}[key]
            for _ in range(abs(want - cur)):
                run.tap(f'button[aria-label="{"Increase" if want > cur else "Decrease"} {label}"]', f"{key} to {want}")
            self.assertEqual(int(page.input_value(f"#lineup-{key}")), want)
        run.tap(".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)
        page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls())", timeout=60000)
        s = page.evaluate("DDF.engine.settings()")
        self.assertEqual((s["scoring"], s["roster"]["WR"], s["roster"]["BENCH"]), ("half_ppr", 3, 5))
        self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).me"), 2, "Team 3 is yours")
        self.assertEqual(page.errors, [])
        return run

    def test_uso_league_tap_count(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                run = self.uso_path(width)
                pages = ["connect.html", "settings.html"] if run.card else ["connect.html", "setup.html", "settings.html"]
                self.assertEqual(run.entry_pages(), pages)
                want = USO_TAPS_BEFORE[width] - 1 - (1 if run.card else 0) - (1 if run.skipped_get_link else 0)   # the Yahoo toggle tap is gone
                self.assertEqual(run.taps, want, "\n".join(run.log))


if __name__ == "__main__":
    unittest.main()
