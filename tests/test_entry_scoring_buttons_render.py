"""League entry: scoring as three buttons on the read card for pasted leagues (connect.html), no silent PPR.

A rosters page never shows scoring, so every paste started as PPR and nothing said it was a guess (the USO league is
Half PPR and showed PPR with no warning). Now:

1. A paste asks "Scoring" on the read card: PPR, Half PPR, Standard, none pressed, and Next waits for the answer
   ("Pick your league's scoring to continue.").
2. A pick applies to the league: League settings opens on it and the team page values use it.
3. Preselected only when known: the same league read again, or the league being edited. Sleeper and chat leagues bring
   their own scoring and are not asked.
4. The USO league at 375 and 1280: the Half PPR tap moves from the settings page to the card, so the count is
   unchanged (phone 20 taps on main) and a PPR league can no longer slip through as a guess.
5. No horizontal scroll; the entry header is unchanged.
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


class ScoringButtonsTest(unittest.TestCase):

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

    def paste_uso(self, page, width):
        run = Run(page, width)
        run.paste("#rosters", USO, "paste every team's roster")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        return run

    def pressed(self, page):
        return page.eval_on_selector_all("#scoring-pick [aria-pressed=true]", "els => els.map(e => e.dataset.scoring)")

    # ---- 1 ----
    def test_a_paste_asks_its_scoring(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                self.paste_uso(page, width)
                self.assertTrue(page.is_visible("#scoring-pick"))
                self.assertEqual(page.locator("#scoring-pick [data-scoring]").all_text_contents(), ["PPR", "Half PPR", "Standard"])
                self.assertEqual(self.pressed(page), [], "nothing preselected: no guessed PPR")
                self.assertEqual(page.text_content("#scoring-pick-help"), "A rosters page does not show scoring. Pick your league's.")
                self.assertEqual(page.get_attribute(".ddf-actionbar__next", "aria-disabled"), "true")
                self.assertEqual(page.text_content(".ddf-actionbar__sum").strip(), "Pick your league's scoring to continue.")
                for b in page.locator("#scoring-pick [data-scoring]").all():
                    self.assertGreaterEqual(b.bounding_box()["height"], 44)
                page.click("#scoring-pick [data-scoring=half_ppr]")
                self.assertEqual(self.pressed(page), ["half_ppr"])
                self.assertEqual(page.get_attribute(".ddf-actionbar__next", "aria-disabled"), "false")
                self.assertEqual(page.evaluate("DDF.engine.settings().scoring"), "half_ppr")
                self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).scoring"), "half_ppr")
                self.assert_page_ok(page)

    # ---- 2 ----
    def test_the_pick_reaches_league_settings(self):
        page = self.connect(PHONE)
        self.paste_uso(page, PHONE)
        page.click("#scoring-pick [data-scoring=standard]")
        page.click(".ddf-actionbar__next")
        page.wait_for_url(lambda u: u.endswith("setup.html") or u.endswith("settings.html"), timeout=30000)
        page.goto(f"{self.base}/settings.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(400)
        self.assertEqual(page.eval_on_selector("#scoring", "e => e.value"), "Standard")

    # ---- 3 ----
    def test_known_scoring_is_kept_and_sleeper_is_not_asked(self):
        page = self.connect(PHONE)
        self.paste_uso(page, PHONE)
        page.click("#scoring-pick [data-scoring=half_ppr]")
        page.fill("#rosters", "")
        self.paste_uso(page, PHONE)
        self.assertEqual(self.pressed(page), ["half_ppr"], "the same league read again keeps its scoring")
        self.assertEqual(page.get_attribute(".ddf-actionbar__next", "aria-disabled"), "false")
        page = self.connect(PHONE)
        page.click("[data-provider=sleeper]")
        page.fill("#league-ref", SLEEPER_ID)
        page.click("#get-link")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertTrue(page.is_hidden("#scoring-pick"), "Sleeper gives its scoring")
        self.assertEqual(page.get_attribute(".ddf-actionbar__next", "aria-disabled"), "false")

    # ---- 4 ----
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
        run.tap("#get-link", "Get rosters link")
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS)
        run.count(1, "Open your rosters page")
        run.offsite()
        run.paste("#rosters", USO, "paste every team's roster")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        self.assert_page_ok(page)
        run.tap("#scoring-pick [data-scoring=half_ppr]", "Half PPR on the card")
        if f["card"]:
            run.tap('#team-pick-list .team-pick-option:has-text("Team 3")', "Team 3 on the card")
            run.tap(".ddf-actionbar__next", "Next: league settings")
        else:
            run.tap(".ddf-actionbar__next", "Next: confirm your team")
            page.wait_for_url("**/setup.html", timeout=30000)
            page.wait_for_selector(".setup-option")
            run.tap('.setup-option:has(input[value="Team 3"])', "Team 3")
            run.tap(".ddf-actionbar__next:not([aria-disabled=true])", "Next: confirm league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(300)
        self.assertEqual(page.eval_on_selector("#scoring", "e => e.value"), "Half PPR", "the card's pick, no second tap")
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
        self.assertEqual(page.errors, [])
        return run, f

    def test_uso_league_tap_count(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                run, f = self.uso_path(width)
                want = USO_TAPS_MAIN[width] - (1 if f["link"] else 0) - (1 if f["card"] else 0)
                self.assertEqual(run.taps, want, "\n".join(run.log))
                self.assertEqual(len(run.entry_pages()), 3 - (1 if f["card"] else 0))
                print(f"\nUSO {width}px: {run.taps} taps, {len(run.entry_pages())} pages (main: {USO_TAPS_MAIN[width]}, 3)")


if __name__ == "__main__":
    unittest.main()
