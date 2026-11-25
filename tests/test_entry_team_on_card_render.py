"""League entry: pick your team on the "Here's what we read" card (connect.html), with tap counts.

Before, the read card listed every team, then Next opened a separate page (setup.html) to pick yours, with its own
Next. Now "Which team is yours?" is on the card; once a team is picked, Next goes straight to League settings. The team
page stays for switching later, and is still where Next goes if no team was picked on the card.

1. A paste and a Sleeper league both show the pick on the card; nothing is preselected for a new league.
2. Picking a team keeps it (ddf:pasted me and own, Viewing as) and Next goes to League settings; setup.html is skipped.
3. The team is preselected when it is known: editing a league (the team you had) or the same league read again.
4. No team picked: Next still goes to setup.html, as today.
5. The USO league from the landing page to the team page at 375 and 1280: one tap and one page fewer
   (phone 20 taps and 3 pages before; 19 and 2 with this change alone).
6. No horizontal scroll; the entry header is unchanged.

Counting as in the setup audit: one tap, click, key shortcut or app switch; pasting into a box is two (tap, Paste);
the rosters page off this site is 4 on a phone and 3 on a computer.
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
# The USO path on main before the league-entry quick wins: 20 taps on a phone, 19 on a computer, 3 pages
# (connect, setup, settings). Each quick win that has shipped takes its share off (expected_uso below), so this test
# holds whichever order the changes merge in.
USO_TAPS_MAIN = {PHONE: 20, DESKTOP: 19}


def setUpModule():
    _render_env.ensure_built()


class Run:
    """One user's path, counted. Every on-page action goes through tap() or paste()."""

    def __init__(self, page, width):
        self.page, self.width, self.taps, self.log, self.pages = page, width, 0, [], []
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

    def entry_pages(self):
        seen = []
        for p in self.pages:
            if p in ("connect.html", "setup.html", "settings.html") and p not in seen:
                seen.append(p)
        return seen


class TeamOnCardTest(unittest.TestCase):

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


    def features(self, page):
        return page.evaluate("""() => ({link: !!(DDF.connectEntry && DDF.connectEntry.platformOf),
                                        card: !!document.getElementById('team-pick')})""")

    def expected_uso(self, width, f):
        """main's count less each shipped quick win: the link sets Yahoo (1), the team on the card (1 tap, 1 page)"""
        return USO_TAPS_MAIN[width] - (1 if f["link"] else 0) - (1 if f["card"] else 0), 3 - (1 if f["card"] else 0)

    def paste_uso(self, page, width):
        run = Run(page, width)
        run.paste("#rosters", USO, "paste every team's roster")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        return run

    # ---- 1 ----
    def test_the_card_asks_which_team_is_yours(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                self.paste_uso(page, width)
                self.assertTrue(page.is_visible("#team-pick"))
                self.assertEqual(page.text_content("#team-pick-title"), "Which team is yours?")
                names = page.locator("#team-pick-list .team-pick-option strong").all_text_contents()
                self.assertEqual(names, [f"Team {i}" for i in range(1, 13)])
                self.assertEqual(page.locator("#team-pick-list input:checked").count(), 0, "nothing preselected for a new league")
                self.assertIn("matched", page.locator("#team-pick-list .team-pick-option small").first.text_content())
                for box in page.locator("#team-pick-list .team-pick-option").all():
                    self.assertGreaterEqual(box.bounding_box()["height"], 44)
                self.assertEqual(page.text_content("#entry-status").strip(), "Check the list below, then pick your team.")
                self.assertEqual(page.get_attribute("#connect-next", "href"), "setup.html", "no team yet: Next still picks it on setup.html")
                self.assert_page_ok(page)

    def test_a_sleeper_league_shows_the_pick_too(self):
        page = self.connect(PHONE)
        page.click("[data-provider=sleeper]")
        page.fill("#league-ref", SLEEPER_ID)
        page.click("#get-link")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertTrue(page.is_visible("#team-pick"))
        self.assertEqual(page.locator("#team-pick-list .team-pick-option").count(), 4)
        self.assertTrue(page.text_content("#link-result").endswith("Check the list below, then pick your team."))
        page.locator("#team-pick-list .team-pick-option").nth(1).click()
        self.assertEqual(page.get_attribute("#connect-next", "href"), "settings.html")
        self.assert_page_ok(page)

    # ---- 2 ----
    def test_picking_on_the_card_skips_the_team_page(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                self.paste_uso(page, width)
                page.click('#team-pick-list .team-pick-option:has-text("Team 3")')
                self.assertEqual(page.locator("#team-pick-list .team-pick-option.selected strong").all_text_contents(), ["Team 3"])
                kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
                self.assertEqual((kept["me"], kept["own"]), (2, 2))
                self.assertEqual(page.get_attribute("#connect-next", "href"), "settings.html")
                self.assertEqual(page.text_content(".ddf-actionbar__next").strip(), "Next: league settings")
                self.assertEqual(page.text_content(".ddf-actionbar__sum").strip(), "Your team: Team 3. Next: check your league settings.")
                page.click(".ddf-actionbar__next")
                page.wait_for_url("**/settings.html", timeout=30000)
                page.wait_for_function("() => window.DDF && DDF.viewAs && DDF.viewAs.read()", timeout=30000)
                va = page.evaluate("DDF.viewAs.read()")
                self.assertEqual((va["me"], va["own"]), (2, 2))
                saved = page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces'))")
                ws = saved["workspaces"][0]
                self.assertEqual([t["id"] for t in ws["teams"]].index(ws["myTeamId"]), 2, "the saved league knows your team")
                self.assert_page_ok(page)

    # ---- 3 ----
    def test_the_same_league_read_again_keeps_your_team(self):
        page = self.connect(PHONE)
        self.paste_uso(page, PHONE)
        page.click('#team-pick-list .team-pick-option:has-text("Team 3")')
        page.fill("#rosters", "")
        self.paste_uso(page, PHONE)
        self.assertEqual(page.locator("#team-pick-list input:checked").evaluate("e => e.closest('label').textContent"), page.locator('#team-pick-list .team-pick-option:has-text("Team 3")').text_content())
        self.assertEqual(page.get_attribute("#connect-next", "href"), "settings.html")

    def test_editing_a_league_preselects_the_team_you_had(self):
        page = self.connect(PHONE)
        self.paste_uso(page, PHONE)
        page.click('#team-pick-list .team-pick-option:has-text("Team 5")')
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.goto(f"{self.base}/connect.html?edit=1", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.fill("#rosters", "")
        self.paste_uso(page, PHONE)
        self.assertEqual(page.locator("#team-pick-list .team-pick-option.selected strong").all_text_contents(), ["Team 5"])
        self.assertEqual(page.get_attribute("#connect-next", "href"), "settings.html")

    # ---- 4 ----
    def test_without_a_pick_next_goes_to_the_team_page(self):
        page = self.connect(PHONE)
        self.paste_uso(page, PHONE)
        self.assertEqual(page.text_content(".ddf-actionbar__next").strip(), "Next: confirm your team")
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/setup.html", timeout=30000)
        self.assertEqual(page.locator(".setup-option").count(), 12)

    # ---- 5 ----
    def uso_path(self, width):
        page = self.page(width)
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        f = self.features(page)
        if not f["link"]:
            run.tap("[data-provider=yahoo]", "Yahoo toggle (the link does not set it on this build)")
        run.paste("#league-ref", YAHOO_LINK, "paste the USO league link")
        self.assertEqual(self.provider(page), "yahoo")
        run.tap("#get-link", "Get rosters link")
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS)
        run.count(1, "Open your rosters page")
        run.offsite()
        run.paste("#rosters", USO, "paste every team's roster")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        self.assert_page_ok(page)
        run.tap('#team-pick-list .team-pick-option:has-text("Team 3")', "Team 3 on the card")
        run.tap(".ddf-actionbar__next", "Next: league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(300)
        if page.eval_on_selector("#scoring", "e => e.value") != "Half PPR":
            run.tap('[aria-labelledby=lbl-scoring] button[data-value="Half PPR"]', "Half PPR")
        for key, want in (("wr", 3), ("bench", 5)):
            cur = int(page.input_value(f"#lineup-{key}"))
            label = {"wr": "WR", "bench": "BENCH"}[key]
            for _ in range(abs(want - cur)):
                run.tap(f'button[aria-label="{"Increase" if want > cur else "Decrease"} {label}"]', f"{key} to {want}")
        run.tap(".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        s = page.evaluate("DDF.engine.settings()")
        self.assertEqual((s["scoring"], s["roster"]["WR"], s["roster"]["BENCH"]), ("half_ppr", 3, 5))
        self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).me"), 2, "Team 3 is yours")
        self.assertEqual(page.errors, [])
        return run, f

    def test_uso_league_tap_count(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                run, f = self.uso_path(width)
                taps, pages = self.expected_uso(width, f)
                self.assertEqual(run.entry_pages(), ["connect.html", "settings.html"], "the team page is skipped")
                self.assertEqual(len(run.entry_pages()), pages)
                self.assertEqual(run.taps, taps, "\n".join(run.log))
                print(f"\nUSO {width}px: {run.taps} taps, {len(run.entry_pages())} pages (main: {USO_TAPS_MAIN[width]}, 3)")


if __name__ == "__main__":
    unittest.main()
