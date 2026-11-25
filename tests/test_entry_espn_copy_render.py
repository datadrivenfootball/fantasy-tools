"""League entry: the shorter ESPN copy path (connect.html), with tap counts at 375px and 1280px.

Before, an ESPN league ID gave a link to the rosters page: copy the busy page, paste it, then pick the scoring, pick
the team and fix the lineup, because a rosters page shows none of the league's settings. Now "Open my league on ESPN"
opens ESPN's own data view of the league (lm-api-reads.fantasy.espn.com, every roster, slot and setting as plain
text) in a new tab, where the reader's ESPN sign-in applies, so it works for private leagues too. Back on DDF, "Use
what I copied" reads the clipboard: ESPN's data is read with espn-import.js, so the scoring, lineup and team count come
with it. The rosters page stays one link away, and the button still reads a pasted rosters page as before.

ESPN is never called here: the data view's text is the fixture league (settings and teams in one object).
1. The ESPN Open button is ESPN's data view, with three short steps and the rosters page under it. Yahoo unchanged.
2. Use what I copied with ESPN's data: the read card from ESPN, no scoring question, the box left empty; League
   settings shows its one line From ESPN.
3. The same text pasted into the box reads the same way.
4. A cut-off copy, ESPN's "not authorized" answer and its "not found" answer each say what to do.
5. Coming back from the ESPN tab points at Use what I copied.
6. Tap count from the landing page to the team page against the rosters page copy path on this same build.
7. No horizontal scroll; the entry header is unchanged.

Counting as in the setup audit: one tap, click, key shortcut or app switch; pasting into a box is two (tap, Paste);
reading the clipboard is one tap, plus the phone's own Paste bubble; a page off this site (select all, copy, back) is
4 on a phone and 3 on a computer.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve
from tests.test_entry_platform_link_render import espn_data_view

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "espn"
SETTINGS = json.loads((FX / "settings.json").read_text())
TEAMS = json.loads((FX / "teams.json").read_text())
DATA_VIEW = json.dumps(dict(SETTINGS, **{"members": TEAMS["members"], "teams": TEAMS["teams"]}))
ESPN_ID = "1086064"
ESPN_LINK = f"https://fantasy.espn.com/football/league?leagueId={ESPN_ID}"
ESPN_ROSTERS = f"https://fantasy.espn.com/football/league/rosters?leagueId={ESPN_ID}"
YAHOO_LINK = "https://football.fantasysports.yahoo.com/f1/848938"
YAHOO_ROSTERS = "https://football.fantasysports.yahoo.com/f1/848938/starters"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste && DDF.espn"
HEADER_STEPS = ["1. League rosters", "2. Your team", "3. League settings"]
PHONE, DESKTOP = 375, 1280
OFFSITE = {PHONE: 4, DESKTOP: 3}
TEAM_NAMES = [t["name"] for t in TEAMS["teams"]]


def setUpModule():
    _render_env.ensure_built()


def rosters_page_text():
    """The same league as a copied rosters page (team name, then its players)."""
    pos = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
    return "\n\n".join("\n".join([t["name"]] + [f"{pos[e['playerPoolEntry']['player']['defaultPositionId']]} {e['playerPoolEntry']['player']['fullName']}"
                                                for e in t["roster"]["entries"]]) for t in TEAMS["teams"])


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


class EspnCopyPathTest(unittest.TestCase):

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
        ctx = {"viewport": {"width": width, "height": 812 if width < 761 else 900}, "permissions": ["clipboard-read", "clipboard-write"]}
        if width < 761:
            ctx.update(is_mobile=True, has_touch=True)
        context = self.browser.new_context(**ctx)
        self.addCleanup(context.close)
        page = context.new_page()
        page.offsite = []
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")),
                   lambda r: (page.offsite.append(r.request.url), r.abort()))
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        return page

    def connect(self, width):
        page = self.page(width)
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        return page

    def assert_page_ok(self, page):
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, "no horizontal scroll")
        self.assertEqual([s.replace("✓", "").strip() for s in page.locator(".entry-head .entry-steps > li").all_text_contents()], HEADER_STEPS, "header unchanged")
        self.assertEqual(page.errors, [])

    def copy(self, page, text):
        page.evaluate("t => navigator.clipboard.writeText(t)", text)

    def assert_read_from_espn(self, page):
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        self.assertEqual(page.text_content("#recognition-title"), "Here's what we read from ESPN")
        self.assertEqual(page.locator("#team-pick-list .team-pick-option strong").all_text_contents(), TEAM_NAMES)
        self.assertTrue(page.is_hidden("#scoring-pick"), "scoring comes with ESPN's data")
        self.assertEqual(page.text_content("#entry-status"), "Read from ESPN: check the list below, then pick your team.")
        kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
        self.assertEqual((kept["source"], kept["platform"], kept["leagueId"]), ("espn", "espn", ESPN_ID))
        self.assertEqual(kept["importSettings"]["roster"], {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 5, "K": 1, "DST": 1})
        self.assertEqual(kept["importSettings"]["scoring"], "half_ppr")
        stored = page.evaluate("JSON.stringify(Object.assign({}, localStorage)) + JSON.stringify(Object.assign({}, sessionStorage))")
        self.assertNotIn("lineupSlotCounts", stored, "ESPN's raw data is not stored")

    # ---- 1 ----
    def test_the_espn_button_opens_espns_data_view(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                Run(page, width).paste("#league-ref", ESPN_LINK)
                page.wait_for_selector("#link-result a.button")
                self.assertEqual(page.text_content("#link-result a.button"), "Open my league on ESPN")
                self.assertEqual(page.get_attribute("#link-result a.button", "href"), espn_data_view(ESPN_ID))
                self.assertEqual(page.get_attribute("#link-result a.button", "target"), "_blank")
                self.assertEqual(page.locator("#link-result .copy-steps li").count(), 3)
                self.assertIn("Use what I copied", page.text_content("#link-result .copy-steps"))
                self.assertEqual(page.get_attribute("#link-result a.rosters-instead", "href"), ESPN_ROSTERS)
                self.assertEqual(page.text_content("#paste-rosters"), "Use what I copied")
                if width == PHONE:
                    for sel in ("#link-result a.button", "#link-result a.rosters-instead", "#paste-rosters"):
                        self.assertGreaterEqual(page.locator(sel).bounding_box()["height"], 44, sel)
                self.assertEqual([u for u in page.offsite if "espn.com" in u], [], "nothing is asked of ESPN from the page")
                self.assert_page_ok(page)
                page.click("[data-provider=yahoo]")
                page.fill("#league-ref", YAHOO_LINK)
                page.wait_for_selector("#link-result a.button")
                self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS, "Yahoo keeps its rosters page")

    # ---- 2 ----
    def test_use_what_i_copied_reads_espns_data(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                self.copy(page, DATA_VIEW)
                page.click("#paste-rosters")
                self.assert_read_from_espn(page)
                self.assertEqual(page.input_value("#rosters"), "", "the box is not filled with ESPN's data")
                self.assert_page_ok(page)
                page.click('#team-pick-list .team-pick-option:has-text("Team Panettone")')
                page.click(".ddf-actionbar__next")
                page.wait_for_url("**/settings.html", timeout=30000)
                page.wait_for_selector("#settings-summary:not([hidden])", timeout=30000)
                self.assertEqual(page.text_content("#settings-source"), "From ESPN")
                values = page.text_content("#settings-values").replace(" ", " ")
                for want in ("Half PPR", "12 teams", "3 WR", "5 bench"):
                    self.assertIn(want, values)
                self.assert_page_ok(page)

    # ---- 3 ----
    def test_espns_data_pasted_into_the_box_reads_the_same(self):
        page = self.connect(PHONE)
        Run(page, PHONE).paste("#rosters", DATA_VIEW)
        self.assert_read_from_espn(page)
        self.assert_page_ok(page)

    # ---- 4 ----
    def test_a_bad_copy_says_what_to_do(self):
        cases = ((DATA_VIEW[: len(DATA_VIEW) // 2], "That copy looks cut off"),
                 (json.dumps({"messages": ["You are not authorized to view this League."], "details": [{"type": "AUTH_LEAGUE_NOT_VISIBLE"}]}), "you may not be signed in"),
                 (json.dumps({"messages": ["Not found"], "details": [{"type": "GENERAL_NOT_FOUND"}]}), "ESPN could not find that league"),
                 (json.dumps({"seasonId": 2026, "status": {}}), "not a league with rosters"))
        for text, want in cases:
            with self.subTest(want=want):
                page = self.connect(PHONE)
                self.copy(page, text)
                page.click("#paste-rosters")
                page.wait_for_function("w => document.getElementById('entry-status').textContent.includes(w)", arg=want, timeout=10000)
                self.assertTrue(page.is_hidden("#recognized"))
                self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"))
                self.assert_page_ok(page)
        page = self.connect(PHONE)
        self.copy(page, rosters_page_text())
        page.click("#paste-rosters")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        self.assertEqual(page.text_content("#recognition-title"), "Here's what we read from your paste", "a rosters page reads as before")

    # ---- 5 ----
    def test_coming_back_points_at_use_what_i_copied(self):
        page = self.connect(PHONE)
        Run(page, PHONE).paste("#league-ref", ESPN_LINK)
        page.wait_for_selector("#link-result a.button")
        with page.context.expect_page() as tab:
            page.click("#link-result a.button")
        tab.value.close()
        page.evaluate("""() => { Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'visible'});
                                document.dispatchEvent(new Event('visibilitychange')); }""")
        self.assertEqual(page.text_content("#paste-rosters-help"), "Welcome back. Copied it? Tap Use what I copied.")
        self.assertEqual(page.evaluate("document.activeElement.id"), "paste-rosters")
        self.assert_page_ok(page)

    # ---- 6 ----
    def start(self, width):
        page = self.page(width)
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        run.paste("#league-ref", ESPN_LINK, "paste the ESPN league link")
        page.wait_for_selector("#link-result a.button", timeout=10000)
        return page, run

    def use_copied(self, page, run, width, text):
        self.copy(page, text)
        run.tap("#paste-rosters", "Use what I copied")
        if width == PHONE:
            run.count(1, "the phone's own Paste bubble")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)

    def finish(self, page, run, fixes):
        run.tap('#team-pick-list .team-pick-option:has-text("Team Panettone")', "your team on the card")
        run.tap(".ddf-actionbar__next", "Next: league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(300)
        if fixes:
            if page.is_visible("#settings-edit") and page.is_hidden("#editor"):
                run.tap("#settings-edit", "Edit")
            for key, want in (("wr", 3), ("bench", 5), ("k", 1), ("def", 1)):
                cur = int(page.input_value(f"#lineup-{key}"))
                label = {"wr": "WR", "bench": "BENCH", "k": "K", "def": "DEF"}[key]
                for _ in range(abs(want - cur)):
                    run.tap(f'button[aria-label="{"Increase" if want > cur else "Decrease"} {label}"]', f"{key} to {want}")
        run.tap(".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)
        # settings() exists before the engine has loaded; it throws until then
        page.wait_for_function("() => { try { return !!(window.DDF && DDF.engine && DDF.engine.settings && DDF.engine.settings()); } catch (e) { return false; } }", timeout=60000)
        s = page.evaluate("DDF.engine.settings()")
        self.assertEqual((s["scoring"], s["teams"], s["roster"]["WR"], s["roster"]["BENCH"]), ("half_ppr", 12, 3, 5))

    def test_tap_count_against_the_rosters_page(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page, before = self.start(width)
                before.count(1, "Or copy the rosters page instead")
                before.count(OFFSITE[width], "on the rosters page: select all, copy, back")
                self.use_copied(page, before, width, rosters_page_text())
                before.tap("#scoring-pick [data-scoring=half_ppr]", "Half PPR on the card")
                self.finish(page, before, fixes=True)

                page, after = self.start(width)
                after.tap("#link-result a.button", "Open my league on ESPN")
                after.count(OFFSITE[width], "on ESPN's data view: select all, copy, back")
                self.use_copied(page, after, width, DATA_VIEW)
                self.finish(page, after, fixes=False)
                self.assertEqual(after.entry_pages(), ["connect.html", "settings.html"])
                self.assertEqual(after.taps, {PHONE: 13, DESKTOP: 11}[width], "\n".join(after.log))
                self.assertGreaterEqual(before.taps - after.taps, 4, "\n".join(before.log))
                print(f"\nESPN copy {width}px: {before.taps} taps by the rosters page, {after.taps} by ESPN's data view")
                self.assertEqual(page.errors, [])


if __name__ == "__main__":
    unittest.main()
