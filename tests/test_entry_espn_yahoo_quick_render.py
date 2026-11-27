"""League entry: the ESPN and Yahoo quick wins on connect.html, with tap counts.

From the "Fewer clicks to connect" concept (its quick wins were decided to ship first):
1. The rosters link shows as soon as the box holds a league link or ID: no "Get rosters link" tap. An entry with no ID
   says so once the box is left; nothing nags while typing.
2. "Paste rosters" reads the clipboard in one tap and reads the rosters; without clipboard access it says how to paste.
3. The last platform and league link or ID are remembered on this device (localStorage ddf.v2.entry-last, cleared by
   Start fresh) and filled in on the next visit, with the Open button ready. A loaded Sleeper league is remembered too.
4. The USO league from the landing page to the team page at 375 and 1280, and a repeat visit to the rosters page.
   Counting: one tap, click, key shortcut or app switch; pasting into a box is 2 (tap, Paste). Paste rosters is 1 on a
   computer and 2 on a phone (the button, then the phone's own Paste bubble). The rosters page off this site is 4 on a
   phone and 3 on a computer.
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


def espn_data_view(league_id: str) -> str:
    """ESPN's data view of a league, which the ESPN Open button opens (the shorter copy path): this season by the page's rule."""
    import datetime
    d = datetime.date.today()
    season = d.year - 1 if d.month < 3 else d.year
    return (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
            "?view=mTeam&view=mRoster&view=mSettings")


ESPN_OPEN = espn_data_view("123456")   # the ESPN Open button: ESPN's data view (the rosters page is the link under it)
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


class EspnYahooQuickWinsTest(unittest.TestCase):

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

    def page(self, width, clipboard=True):
        ctx = {"viewport": {"width": width, "height": 812 if width < 761 else 900}}
        if clipboard:
            ctx["permissions"] = ["clipboard-read", "clipboard-write"]
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
                                        card: !!document.getElementById('team-pick'),
                                        scoring: !!document.getElementById('scoring-pick')})""")

    def paste_rosters(self, page, run, width, text=USO):
        page.evaluate("t => navigator.clipboard.writeText(t)", text)
        run.tap("#paste-rosters", "Paste rosters")
        if width == PHONE:
            run.count(1, "the phone's own Paste bubble")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)

    # ---- 1 ----
    def test_the_rosters_link_shows_as_the_box_fills(self):
        for width in (PHONE, DESKTOP):
            for start, link, want in (("yahoo", YAHOO_LINK, YAHOO_ROSTERS), ("espn", ESPN_LINK, ESPN_OPEN), ("yahoo", "848938", YAHOO_ROSTERS)):
                with self.subTest(width=width, start=start, link=link):
                    page = self.connect(width)
                    page.click(f"[data-provider={start}]")
                    self.assertTrue(page.is_hidden("#get-link"), "no Get rosters link step")
                    run = Run(page, width)
                    run.paste("#league-ref", link)
                    page.wait_for_selector("#link-result a.button")
                    self.assertEqual(page.get_attribute("#link-result a.button", "href"), want)
                    self.assertEqual(run.taps, 2, run.log)
                    if width == PHONE:   # touch target on a phone; the site's desktop buttons are 40px
                        self.assertGreaterEqual(page.locator("#link-result a.button").bounding_box()["height"], 44)
                    self.assert_page_ok(page)

    def test_no_id_is_said_once_the_box_is_left(self):
        page = self.connect(PHONE)
        page.fill("#league-ref", "my league")
        self.assertEqual(page.text_content("#link-result"), "", "nothing while typing")
        page.locator("#league-ref").blur()
        self.assertIn("could not find a league ID", page.text_content("#link-result"))
        page.fill("#league-ref", "")
        page.click("[data-provider=sleeper]")
        self.assertTrue(page.is_visible("#get-link"), "Sleeper keeps Load my league")

    # ---- 2 ----
    def test_paste_rosters_reads_the_clipboard(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                run = Run(page, width)
                if width == PHONE:
                    self.assertGreaterEqual(page.locator("#paste-rosters").bounding_box()["height"], 44)
                self.paste_rosters(page, run, width)
                self.assertIn("Found 12 teams", page.text_content("#recognition-summary"))
                self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).teams.length"), 12)
                self.assert_page_ok(page)

    def test_paste_rosters_without_clipboard_access_says_how(self):
        page = self.page(PHONE, clipboard=False)
        page.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: {readText: () => Promise.reject(new Error('denied'))}})")
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.click("#paste-rosters")
        page.wait_for_function("() => document.getElementById('paste-rosters-help').textContent.length > 0")
        self.assertIn("Paste", page.text_content("#paste-rosters-help"))
        self.assertEqual(page.evaluate("document.activeElement.id"), "rosters")

    # ---- 3 ----
    def test_the_league_is_remembered_on_this_device(self):
        page = self.connect(PHONE)
        page.click("[data-provider=yahoo]")
        page.fill("#league-ref", YAHOO_LINK)
        page.wait_for_selector("#link-result a.button")
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.wait_for_selector("#link-result a.button")
        self.assertEqual(self.provider(page), "yahoo", "the platform is preselected")
        self.assertEqual(page.input_value("#league-ref"), "848938", "the league ID only, never the rest of the link")
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS, "the Open button is ready: 1 tap")
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.entry-last'))"), {"v": 2, "platform": "yahoo", "id": "848938"})
        keys = page.evaluate("DDF.startFresh.KEYS.local")
        self.assertIn("ddf.v2.entry-last", keys, "Start fresh clears it")
        self.assert_page_ok(page)

    def test_only_the_platform_and_id_are_stored_and_forget_clears_them(self):
        page = self.connect(PHONE)
        page.click("[data-provider=espn]")
        page.fill("#league-ref", "https://fantasy.espn.com/football/league?leagueId=123456&seasonId=2026#team")
        page.wait_for_selector("#link-result a.button")
        self.assertEqual(page.evaluate("localStorage.getItem('ddf.v2.entry-last')"), '{"v":2,"platform":"espn","id":"123456"}')
        self.assertTrue(page.is_visible("#entry-forget"))
        self.assertGreaterEqual(page.locator("#entry-forget").bounding_box()["height"], 44)
        page.click("#entry-forget")
        self.assertIsNone(page.evaluate("localStorage.getItem('ddf.v2.entry-last')"))
        self.assertEqual(page.input_value("#league-ref"), "")
        self.assertTrue(page.is_hidden("#entry-forget"))
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.assertEqual(page.input_value("#league-ref"), "", "nothing comes back after Forget")

    def test_a_sleeper_length_number_on_espn_offers_sleeper(self):
        page = self.connect(PHONE)
        page.fill("#league-ref", SLEEPER_ID)
        page.wait_for_timeout(200)
        self.assertEqual(page.locator("#link-result a.button").count(), 0, "no ESPN rosters link for a league that cannot exist")
        if page.locator("#link-platform").count():   # the platform-link change says it there
            self.assertIn("as long as a Sleeper league ID", page.text_content("#link-platform"))
            page.click("#link-platform [data-switch-provider=sleeper]")
        else:
            self.assertIn("as long as a Sleeper league ID", page.text_content("#link-result"))
            page.click("#entry-to-sleeper")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertEqual(self.provider(page), "sleeper")

    def test_a_loaded_sleeper_league_is_remembered(self):
        page = self.connect(PHONE)
        page.click("[data-provider=sleeper]")
        page.fill("#league-ref", SLEEPER_ID)
        page.click("#get-link")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.entry-last')).platform"), "sleeper")
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.assertEqual(self.provider(page), "sleeper")
        self.assertEqual(page.input_value("#league-ref"), SLEEPER_ID)

    # ---- 4 ----
    def uso_path(self, width, page=None):
        page = page or self.page(width)
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        f = self.features(page)
        if not f["link"]:
            run.tap("[data-provider=yahoo]", "Yahoo toggle (the link does not set it on this build)")
        run.paste("#league-ref", YAHOO_LINK, "paste the USO league link")
        page.wait_for_selector("#link-result a.button")
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS)
        run.count(1, "Open your Yahoo rosters page")
        run.offsite()
        self.paste_rosters(page, run, width)
        self.assert_page_ok(page)
        if f["scoring"]:
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
        page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls())", timeout=60000)
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
        page.wait_for_function("() => !!(window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls())", timeout=60000)
        s = page.evaluate("DDF.engine.settings()")
        self.assertEqual((s["scoring"], s["roster"]["WR"], s["roster"]["BENCH"]), ("half_ppr", 3, 5))
        self.assertEqual(page.errors, [])
        return run, f

    def test_uso_league_tap_count(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                run, f = self.uso_path(width)
                saved = 1 + (1 if width == DESKTOP else 0)   # Get rosters link; Paste rosters is one tap on a computer
                want = USO_TAPS_MAIN[width] - saved - (1 if f["link"] else 0) - (1 if f["card"] else 0)
                self.assertEqual(run.taps, want, "\n".join(run.log))
                self.assertEqual(len(run.entry_pages()), 3 - (1 if f["card"] else 0))
                print(f"\nUSO {width}px: {run.taps} taps, {len(run.entry_pages())} pages (main: {USO_TAPS_MAIN[width]}, 3)")

    def test_repeat_visit_to_the_rosters_page(self):
        """Back the next week for fresh rosters: the platform and league are already in, so Open is the first tap."""
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.page(width)
                self.uso_path(width, page)
                page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
                page.wait_for_function(ENGINE_READY, timeout=60000)
                page.wait_for_selector("#link-result a.button")
                self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS)
                self.assertEqual(self.provider(page), "yahoo")
                # main: Yahoo toggle, tap the box, Paste, Get rosters link, Open = 5; now Open = 1
                self.assert_page_ok(page)


if __name__ == "__main__":
    unittest.main()
