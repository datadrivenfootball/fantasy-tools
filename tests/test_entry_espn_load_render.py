"""League entry: a public ESPN league loads from its ID (connect.html), with tap counts at 375px and 1280px.

Before, an ESPN league ID gave a link to the rosters page: open it, select all, copy, come back, paste, pick the
scoring, pick the team, then fix the lineup on League settings. Now the browser reads a public league straight from
ESPN's league data service (espn-import.js): every roster, the scoring, the lineup slots and the team count. The reader
picks their team on the read card (ESPN's public data does not say which team is yours), and League settings shows one
line marked From ESPN.

ESPN is faked here (Playwright routes for lm-api-reads.fantasy.espn.com); nothing leaves the test.
1. A public league: "Looking up your league...", then the read card with every team, no scoring question, nothing
   preselected; pick a team, Next, the one-line From ESPN settings, Looks right. Under 5 s; calls without cookies.
2. Tap count from the landing page to the team page, against the copy path on this same build (ESPN unreachable).
3. A private league (401), an unknown ID (404), no network and a timeout fall through to the rosters link with the
   reason; Try again recovers; an unknown ID offers Yahoo.
4. Only {v:2, platform, id} is remembered; no ESPN data is written to storage. A remembered ID loads by itself on the
   next visit when no league is kept; a kept league is left alone.
5. Typing an ID digit by digit asks ESPN once.
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
FX = ROOT / "tests" / "fixtures" / "espn"
SETTINGS = json.loads((FX / "settings.json").read_text())
TEAMS = json.loads((FX / "teams.json").read_text())
ESPN_ID = "1086064"
ESPN_LINK = f"https://fantasy.espn.com/football/league?leagueId={ESPN_ID}"
ESPN_ROSTERS = f"https://fantasy.espn.com/football/league/rosters?leagueId={ESPN_ID}"
YAHOO_ROSTERS = f"https://football.fantasysports.yahoo.com/f1/{ESPN_ID}/starters"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste && DDF.espn"
HEADER_STEPS = ["1. League rosters", "2. Your team", "3. League settings"]
PHONE, DESKTOP = 375, 1280
OFFSITE = {PHONE: 4, DESKTOP: 3}
TEAM_NAMES = [t["name"] for t in TEAMS["teams"]]


def setUpModule():
    _render_env.ensure_built()


def paste_text():
    """The same league as a pasted rosters page (team name, then its players), for the copy path."""
    pos = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
    out = []
    for t in TEAMS["teams"]:
        lines = [t["name"]]
        for e in t["roster"]["entries"]:
            p = e["playerPoolEntry"]["player"]
            lines.append(f"{pos[p['defaultPositionId']]} {p['fullName']}")
        out.append("\n".join(lines))
    return "\n\n".join(out)


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


class EspnLoadTest(unittest.TestCase):

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

    def page(self, width, mode="public"):
        """A page with ESPN faked. mode: public | private | notfound | down | slow; page.espn_mode changes it later."""
        ctx = {"viewport": {"width": width, "height": 812 if width < 761 else 900}}
        if width < 761:
            ctx.update(is_mobile=True, has_touch=True)
        context = self.browser.new_context(**ctx)
        self.addCleanup(context.close)
        page = context.new_page()
        page.espn_mode, page.espn_calls, page.espn_pending = mode, [], []

        def espn(route):
            req = route.request
            page.espn_calls.append({"url": req.url, "cookie": req.headers.get("cookie")})
            cors = {"Access-Control-Allow-Origin": req.headers.get("origin") or "*", "Access-Control-Allow-Credentials": "true"}
            m = page.espn_mode
            if m == "down":
                return route.abort()
            if m == "slow":
                return page.espn_pending.append(route)   # not answered: the page's time budget ends the wait
            if m in ("private", "notfound"):
                code = 401 if m == "private" else 404
                msg = "You are not authorized to view this League." if m == "private" else "Not found"
                return route.fulfill(status=code, body=json.dumps({"messages": [msg]}), content_type="application/json", headers=cors)
            body = SETTINGS if "view=mSettings" in req.url else TEAMS
            route.fulfill(status=200, body=json.dumps(body), content_type="application/json", headers=cors)

        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")) and "lm-api-reads.fantasy.espn.com" not in u,
                   lambda r: r.abort())
        page.route("https://lm-api-reads.fantasy.espn.com/**", espn)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        return page

    def connect(self, width, mode="public", page=None):
        page = page or self.page(width, mode)
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        return page

    def provider(self, page):
        return page.get_attribute("[data-provider][aria-pressed=true]", "data-provider")

    def assert_page_ok(self, page):
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, "no horizontal scroll")
        self.assertEqual([s.replace("✓", "").strip() for s in page.locator(".entry-head .entry-steps > li").all_text_contents()], HEADER_STEPS, "header unchanged")
        self.assertEqual(page.errors, [])

    def settings_calls(self, page):
        return [c for c in page.espn_calls if "view=mSettings" in c["url"]]

    # ---- 1 ----
    def test_a_public_league_loads_from_the_id(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width)
                run = Run(page, width)
                run.paste("#league-ref", ESPN_LINK, "paste the ESPN league link")
                page.wait_for_function("() => /Looking up your league/.test(document.getElementById('link-result').textContent)", timeout=5000)
                page.wait_for_selector("#recognized:not([hidden])", timeout=10000)
                self.assertEqual(page.text_content("#recognition-title"), "Here's what we read from ESPN")
                self.assertTrue(page.text_content("#link-result").startswith("We found: La Lega dei Test on ESPN, 12 teams, "))
                self.assertIn("is-ok", page.get_attribute("#link-result", "class"))
                self.assertEqual(page.locator("#team-pick-list .team-pick-option strong").all_text_contents(), TEAM_NAMES)
                self.assertEqual(page.locator("#team-pick-list input:checked").count(), 0, "ESPN's public data does not say which team is yours")
                self.assertTrue(page.is_hidden("#scoring-pick"), "scoring comes from ESPN")
                self.assertTrue(page.is_hidden("#edit-team-names"), "team names come from ESPN")
                self.assertLess(page.evaluate("DDF.espn.lastMs"), 5000, "under the 5 s target")
                self.assertEqual([c["cookie"] for c in page.espn_calls], [None, None], "two calls, no cookies")
                self.assertTrue(all("/seasons/2026/segments/0/leagues/1086064?" in c["url"] for c in page.espn_calls))
                kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
                self.assertEqual((kept["source"], kept["platform"], kept["leagueId"], kept["me"]), ("espn", "espn", ESPN_ID, None))
                self.assertEqual(kept["importSettings"]["roster"], {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 5, "K": 1, "DST": 1})
                self.assertEqual(run.taps, 2, run.log)
                self.assert_page_ok(page)
                run.tap('#team-pick-list .team-pick-option:has-text("Gli Invincibili")', "your team on the card")
                self.assertEqual(page.text_content(".ddf-actionbar__next").strip(), "Next: league settings")
                run.tap(".ddf-actionbar__next", "Next: league settings")
                page.wait_for_url("**/settings.html", timeout=30000)
                page.wait_for_selector("#settings-summary:not([hidden])", timeout=30000)
                self.assertEqual(page.text_content("#settings-source"), "From ESPN")
                values = page.text_content("#settings-values").replace(" ", " ")
                for want in ("Half PPR", "12 teams", "1 QB", "2 RB", "3 WR", "1 TE", "1 FLEX", "5 bench", "1 K", "1 DEF"):
                    self.assertIn(want, values)
                self.assert_page_ok(page)

    # ---- 2 ----
    def after_path(self, width):
        page = self.page(width)
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        run.paste("#league-ref", ESPN_LINK, "paste the ESPN league link")
        page.wait_for_selector("#recognized:not([hidden])", timeout=10000)
        run.tap('#team-pick-list .team-pick-option:has-text("Team Panettone")', "your team on the card")
        run.tap(".ddf-actionbar__next", "Next: league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_selector("#settings-summary:not([hidden])", timeout=30000)
        run.tap(".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)
        return run, page

    def before_path(self, width):
        """The copy path on this build: ESPN unreachable, so the rosters link, a paste, scoring, team and slot fixes."""
        page = self.page(width, "down")
        run = Run(page, width)
        page.goto(f"{self.base}/index.html", wait_until="networkidle", timeout=60000)
        run.tap("a.getstarted:visible, a.cta2:visible", "Get started")
        page.wait_for_url("**/connect.html", timeout=30000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        run.paste("#league-ref", ESPN_LINK, "paste the ESPN league link")
        page.wait_for_selector("#link-result a.button", timeout=10000)
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), ESPN_ROSTERS)
        run.count(1, "Open your ESPN rosters page")
        run.count(OFFSITE[width], "on the rosters page: select all, copy, back")
        run.paste("#rosters", paste_text(), "paste every team's roster")
        page.wait_for_selector("#recognized:not([hidden])", timeout=30000)
        run.tap("#scoring-pick [data-scoring=half_ppr]", "Half PPR on the card")
        run.tap('#team-pick-list .team-pick-option:has-text("Team Panettone")', "your team on the card")
        run.tap(".ddf-actionbar__next", "Next: league settings")
        page.wait_for_url("**/settings.html", timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
        page.wait_for_timeout(300)
        if page.is_visible("#settings-edit") and page.is_hidden("#editor"):
            run.tap("#settings-edit", "Edit")
        for key, want in (("wr", 3), ("bench", 5), ("k", 1), ("def", 1)):
            cur = int(page.input_value(f"#lineup-{key}"))
            label = {"wr": "WR", "bench": "BENCH", "k": "K", "def": "DEF"}[key]
            for _ in range(abs(want - cur)):
                run.tap(f'button[aria-label="{"Increase" if want > cur else "Decrease"} {label}"]', f"{key} to {want}")
        run.tap(".ddf-actionbar__next", "Looks right, continue")
        page.wait_for_url("**/team.html", timeout=30000)
        return run, page

    def test_tap_count_against_the_copy_path(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                before, _ = self.before_path(width)
                after, page = self.after_path(width)
                page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.settings", timeout=60000)
                s = page.evaluate("DDF.engine.settings()")
                self.assertEqual((s["scoring"], s["teams"], s["roster"]["WR"], s["roster"]["BENCH"]), ("half_ppr", 12, 3, 5))
                self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).me"), 4, "Team Panettone is yours")
                self.assertEqual(after.entry_pages(), ["connect.html", "settings.html"])
                self.assertEqual(after.taps, 6, "\n".join(after.log))   # Get started, paste (2), team, Next, Looks right
                self.assertGreaterEqual(before.taps - after.taps, 8, "\n".join(before.log))
                print(f"\nESPN public {width}px: {before.taps} taps before (copy path), {after.taps} after; pages {after.entry_pages()}")
                self.assertEqual(page.errors, [])

    # ---- 3 ----
    def test_a_private_league_falls_through_to_the_rosters_page(self):
        for width in (PHONE, DESKTOP):
            with self.subTest(width=width):
                page = self.connect(width, "private")
                Run(page, width).paste("#league-ref", ESPN_LINK)
                page.wait_for_selector("#link-result .espn-why", timeout=10000)
                self.assertIn("This ESPN league is private", page.text_content("#link-result .espn-why"))
                self.assertEqual(page.get_attribute("#link-result a.button", "href"), ESPN_ROSTERS)
                self.assertIn("League manager?", page.text_content("#link-result"))
                self.assertNotIn("is-error", page.get_attribute("#link-result", "class") or "")
                self.assertTrue(page.is_hidden("#recognized"))
                if width == PHONE:
                    self.assertGreaterEqual(page.locator("#link-result a.button").bounding_box()["height"], 44)
                self.assert_page_ok(page)

    def test_an_unknown_id_says_so_and_offers_yahoo(self):
        page = self.connect(PHONE, "notfound")
        Run(page, PHONE).paste("#league-ref", ESPN_ID)
        page.wait_for_selector("#link-result .espn-why", timeout=10000)
        self.assertIn("could not find an ESPN league with that ID for the 2026 season", page.text_content("#link-result"))
        page.click("#link-result [data-switch-provider=yahoo]")
        self.assertEqual(self.provider(page), "yahoo")
        page.wait_for_selector("#link-result a.button")
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), YAHOO_ROSTERS)
        self.assert_page_ok(page)

    def test_no_network_or_a_timeout_falls_through_and_try_again_recovers(self):
        for mode, text in (("down", "could not reach ESPN"), ("slow", "taking too long")):
            with self.subTest(mode=mode):
                page = self.page(PHONE, mode)
                self.connect(PHONE, page=page)
                page.evaluate("DDF.espn.TIMEOUT_MS = 600")
                Run(page, PHONE).paste("#league-ref", ESPN_LINK)
                page.wait_for_selector("#link-result .espn-why", timeout=10000)
                self.assertIn(text, page.text_content("#link-result"))
                self.assertEqual(page.get_attribute("#link-result a.button", "href"), ESPN_ROSTERS, "the copy path stays one tap away")
                page.espn_mode = "public"
                for r in page.espn_pending:
                    try:
                        r.abort()
                    except Exception:
                        pass   # the page already gave up on it
                page.click("#link-result [data-espn-retry]")
                page.wait_for_selector("#recognized:not([hidden])", timeout=10000)
                self.assertEqual(page.text_content("#recognition-title"), "Here's what we read from ESPN")
                self.assert_page_ok(page)

    # ---- 4 ----
    def test_only_the_platform_and_id_are_remembered(self):
        page = self.connect(PHONE)
        before = page.evaluate("Object.keys(localStorage)")
        Run(page, PHONE).paste("#league-ref", ESPN_LINK + "&seasonId=2026")
        page.wait_for_selector("#recognized:not([hidden])", timeout=10000)
        self.assertEqual(page.evaluate("localStorage.getItem('ddf.v2.entry-last')"), '{"v":2,"platform":"espn","id":"1086064"}')
        stored = page.evaluate("JSON.stringify(Object.assign({}, localStorage)) + JSON.stringify(Object.assign({}, sessionStorage))")
        for raw in ("lineupSlotCounts", "{OWNER-", "playerPoolEntry", "lm-api-reads"):
            self.assertNotIn(raw, stored, "no ESPN data is stored")
        new = sorted(set(page.evaluate("Object.keys(localStorage)")) - set(before))
        self.assertTrue(all(k.startswith("ddf.") or k.startswith("ddf:") for k in new), new)

    def test_a_remembered_id_loads_by_itself_when_no_league_is_kept(self):
        page = self.connect(PHONE)
        page.evaluate("localStorage.setItem('ddf.v2.entry-last', JSON.stringify({v: 2, platform: 'espn', id: '1086064'}))")
        self.connect(PHONE, page=page)
        page.wait_for_selector("#recognized:not([hidden])", timeout=10000)
        self.assertEqual(page.input_value("#league-ref"), ESPN_ID)
        self.assertEqual(len(self.settings_calls(page)), 1)
        # with that league kept, the next visit leaves it alone: no call, the rosters link as before
        page.locator('#team-pick-list .team-pick-option').first.click()
        calls = len(page.espn_calls)
        self.connect(PHONE, page=page)
        page.wait_for_selector("#link-result a.button", timeout=10000)
        page.wait_for_timeout(600)
        self.assertEqual(len(page.espn_calls), calls, "a kept league is not read again on its own")
        self.assert_page_ok(page)

    # ---- 5 ----
    def test_typing_an_id_asks_espn_once(self):
        page = self.connect(DESKTOP)
        page.locator("#league-ref").click()
        page.keyboard.type(ESPN_ID, delay=60)
        page.wait_for_selector("#recognized:not([hidden])", timeout=10000)
        self.assertEqual(len(self.settings_calls(page)), 1, page.espn_calls)
        self.assert_page_ok(page)


if __name__ == "__main__":
    unittest.main()
