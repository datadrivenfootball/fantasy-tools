"""JEG-1685 (part of JEG-1653): a Sleeper import stores league-state/1 in the league workspace and fills the ES-12 weeks
(built dist/, Chromium, Sleeper API answered from tests/fixtures/sleeper-live; nothing leaves the machine).

Pinned on the real connect.html -> setup.html -> settings.html flow:
  * Sleeper import: ddf:pasted carries a valid league-state/1 and the weeks it filled; the engine runs those weeks and the
    saved league settings keep them (survive a reload); confirming a team writes both to the live workspace store.
  * League settings says where the weeks came from and as of when (Source / as of line), only while they still match.
  * A reader-set week wins: an import over weeks the reader changed leaves them and records nothing as filled.
  * A pasted league has no season state: null with a reason in the pasted record and the workspace, no weeks line.
Pure rules (fill, round trips, bad input) are in tests/test_league_state_wiring.js.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _render_env  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
START = 14   # playoffs start in week 14 (the site standard is 15): last regular week 13


def sleeper_fixture(start=START, league_id=None):
    d = json.loads((FIX / "sleeper-live" / "full.json").read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    ids = list(json.loads((ROOT / "dist" / "sleeper-players.json").read_text(encoding="utf-8"))["p"].keys())[:60]
    for i, r in enumerate(d["rosters"]):
        r["players"] = ids[i * 4:i * 4 + 4]
    d["league"]["settings"]["playoff_week_start"] = start
    d["matchups"] = {k: v for k, v in d["matchups"].items() if int(k) <= start - 1}
    if league_id:
        old = d["league"]["league_id"]
        d["league"]["league_id"] = league_id
        for r in d["rosters"]:
            if "league_id" in r:
                r["league_id"] = league_id
    return d


class LeagueStateRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        from tests._dist_server import serve
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
        cls.fx = sleeper_fixture()
        cls.fx_b = sleeper_fixture(16, "900000000000000002")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def sleeper_api(self, route, fx=None):
        fx = fx or self.fx
        lid = fx["league"]["league_id"]
        path = route.request.url.split("/v1/", 1)[1].split("?")[0]
        table = {f"league/{lid}": fx["league"], f"league/{lid}/users": fx["users"], f"league/{lid}/rosters": fx["rosters"], "state/nfl": fx["state"]}
        for wk, rows in fx["matchups"].items():
            table[f"league/{lid}/matchups/{wk}"] = rows
        if path in table:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(table[path]))
        else:
            route.fulfill(status=404, content_type="application/json", body="null")

    def context(self):
        ctx = self.browser.new_context(viewport={"width": 1000, "height": 900})
        self.addCleanup(ctx.close)
        return ctx

    def page(self, ctx=None, fx=None):
        """A tab. Tabs of one context share localStorage and not sessionStorage, like tabs of one browser."""
        page = (ctx or self.context()).new_page()
        page.fx = fx or self.fx
        page.route("https://api.sleeper.app/v1/**", lambda route: self.sleeper_api(route, page.fx))
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost") or u.startswith("https://api.sleeper.app/")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        return page

    def go(self, page, path):
        page.goto(f"{self.base}/{path}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls()", timeout=60000)
        page.evaluate("() => DDF.engine.ready")
        if path.startswith("settings"):
            page.evaluate("() => DDF.league.ready")

    def sleeper_import(self, page):
        self.go(page, "connect.html")
        page.click("button[data-provider=sleeper]")
        page.fill("#league-ref", page.fx["league"]["league_id"])
        page.click("#get-link")
        page.wait_for_function("(id) => { const p = DDF.state.get('pasted', null); return p && p.source === 'sleeper' && p.leagueId === id; }", arg=page.fx["league"]["league_id"], timeout=30000)

    def weeks(self, page):
        return page.evaluate("() => DDF.engine.weeks()")

    def test_import_stores_state_fills_weeks_and_settings_names_the_source(self):
        page = self.page()
        self.go(page, "connect.html")
        self.assertEqual(self.weeks(page), {"regularEnd": 14, "playoffLo": 15, "playoffHi": 17}, "the site standard before the import")
        self.sleeper_import(page)
        rec = page.evaluate("() => DDF.state.get('pasted')")
        self.assertEqual(rec["leagueState"]["version"], "league-state/1")
        self.assertIsNone(rec["leagueStateReason"])
        self.assertTrue(page.evaluate("(s) => DDF.leagueState.validate(s).ok", rec["leagueState"]))
        self.assertEqual(rec["weeksFilled"], {"regularEnd": START - 1, "playoffLo": START, "playoffHi": 17})
        self.assertEqual(self.weeks(page), rec["weeksFilled"])
        saved = page.evaluate("() => JSON.parse(localStorage.getItem('ddf.v2.league-settings')).weeks")
        self.assertEqual((saved["regularEnd"], saved["playoffLo"], saved["playoffHi"]), (START - 1, START, 17))

        # confirming a team writes the league-state and the weeks to the live workspace store
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/setup.html", timeout=20000)
        page.click("label.setup-option >> nth=0")
        ws = page.evaluate("() => JSON.parse(localStorage.getItem('ddf.v2.workspaces')).workspaces[0]")
        self.assertEqual(ws["leagueState"], rec["leagueState"])
        self.assertIsNone(ws["leagueStateReason"])
        self.assertEqual(ws["weeksFilled"], rec["weeksFilled"])

        self.go(page, "settings.html")
        note = page.inner_text("#weeks-note")
        self.assertIn(f"Last regular-season week {START - 1}, playoffs start week {START}", note)
        self.assertRegex(note, r"From Sleeper, as of [A-Z][a-z]{2} \d{1,2}\.$")
        self.assertEqual(self.weeks(page), rec["weeksFilled"], "the weeks survive a reload")

        # a week changed elsewhere is the reader's: the line goes away rather than claim the league
        page.evaluate("() => DDF.engine.apply({weeks: {regularEnd: 12, playoffLo: 13, playoffHi: 16}})")
        self.go(page, "settings.html")
        self.assertTrue(page.locator("#weeks-note").is_hidden())
        self.assertEqual(page.errors, [])

    def test_settings_line_is_plain_words(self):
        page = self.page()
        self.sleeper_import(page)
        self.go(page, "settings.html")
        self.assertRegex(page.inner_text("#weeks-note"), rf"^Last regular-season week {START - 1}, playoffs start week {START}\. ")
        self.assertRegex(page.inner_text("#weeks-note"), r"From Sleeper, as of [A-Z][a-z]{2} \d{1,2}\.$")
        self.assertNotIn("sleeper:", page.inner_text("#weeks-note"))

    def test_new_tab_import_replaces_the_weeks_the_last_import_filled(self):
        ctx = self.context()
        a = self.page(ctx)
        self.sleeper_import(a)
        self.assertEqual(self.weeks(a), {"regularEnd": 13, "playoffLo": 14, "playoffHi": 17})
        saved = a.evaluate("() => JSON.parse(localStorage.getItem('ddf.v2.league-settings')).weeksFilled")
        self.assertEqual(saved, {"regularEnd": 13, "playoffLo": 14, "playoffHi": 17}, "the marker travels with the weeks")
        # a new tab: its sessionStorage is empty, the weeks and the marker are in localStorage
        b = self.page(ctx, self.fx_b)
        self.sleeper_import(b)
        self.assertEqual(self.weeks(b), {"regularEnd": 15, "playoffLo": 16, "playoffHi": 17})
        rec = b.evaluate("() => DDF.state.get('pasted')")
        self.assertEqual(rec["weeksFilled"], {"regularEnd": 15, "playoffLo": 16, "playoffHi": 17})
        self.assertEqual(b.evaluate("() => DDF.engine.weeksFilled()"), rec["weeksFilled"])
        self.assertEqual(a.errors + b.errors, [])

    def test_a_later_paste_or_manual_league_does_not_inherit_import_weeks(self):
        ctx = self.context()
        a = self.page(ctx)
        self.sleeper_import(a)
        self.assertEqual(self.weeks(a), {"regularEnd": 13, "playoffLo": 14, "playoffHi": 17})
        std = {"regularEnd": 14, "playoffLo": 15, "playoffHi": 17}
        # a paste in a new tab
        b = self.page(ctx)
        self.go(b, "connect.html")
        self.assertEqual(self.weeks(b), {"regularEnd": 13, "playoffLo": 14, "playoffHi": 17})
        b.fill("#rosters", (FIX / "paste_defaults" / "espn-10team.txt").read_text(encoding="utf-8"))
        b.evaluate("() => DDF.connectEntry.check(false, false)")
        b.wait_for_function("() => { const p = DDF.state.get('pasted', null); return p && p.source === 'paste'; }", timeout=20000)
        self.assertEqual(self.weeks(b), std)
        self.assertIsNone(b.evaluate("() => DDF.engine.weeksFilled()"))
        self.assertIsNone(b.evaluate("() => DDF.state.get('pasted').leagueState"))
        # a manual league in another new tab, after another import
        c = self.page(ctx)
        self.sleeper_import(c)
        self.assertEqual(self.weeks(c), {"regularEnd": 13, "playoffLo": 14, "playoffHi": 17})
        d = self.page(ctx)
        self.go(d, "connect.html")
        d.evaluate("() => { const t = document.getElementById('manual-names'); t.value = 'A\\nB'; t.dispatchEvent(new Event('input', {bubbles: true})); }")
        d.wait_for_function("() => { const p = DDF.state.get('pasted', null); return p && p.source === 'manual'; }", timeout=20000)
        self.assertEqual(self.weeks(d), std)
        self.assertIsNone(d.evaluate("() => DDF.engine.weeksFilled()"))
        self.assertIsNone(d.evaluate("() => DDF.state.get('pasted').leagueState"))
        self.assertEqual(a.errors + b.errors + c.errors + d.errors, [])

    def test_a_paste_keeps_weeks_the_reader_set(self):
        ctx = self.context()
        a = self.page(ctx)
        self.sleeper_import(a)
        a.evaluate("() => DDF.engine.apply({weeks: {regularEnd: 12, playoffLo: 13, playoffHi: 16}})")
        b = self.page(ctx)
        self.go(b, "connect.html")
        b.fill("#rosters", (FIX / "paste_defaults" / "espn-10team.txt").read_text(encoding="utf-8"))
        b.evaluate("() => DDF.connectEntry.check(false, false)")
        b.wait_for_function("() => { const p = DDF.state.get('pasted', null); return p && p.source === 'paste'; }", timeout=20000)
        self.assertEqual(self.weeks(b), {"regularEnd": 12, "playoffLo": 13, "playoffHi": 16})

    def test_standard_weeks_after_a_nonstandard_import_are_the_readers_choice(self):
        ctx = self.context()
        a = self.page(ctx)
        self.sleeper_import(a)
        self.assertEqual(self.weeks(a), {"regularEnd": 13, "playoffLo": 14, "playoffHi": 17})
        a.evaluate("() => DDF.engine.apply({weeks: {regularEnd: 14, playoffLo: 15, playoffHi: 17}})")   # back to the site standard
        b = self.page(ctx, self.fx_b)
        self.sleeper_import(b)
        self.assertEqual(self.weeks(b), {"regularEnd": 14, "playoffLo": 15, "playoffHi": 17}, "the deliberate standard weeks stay")
        self.assertIsNone(b.evaluate("() => DDF.state.get('pasted').weeksFilled"))
        self.assertEqual(b.errors, [])

    def test_weeks_the_reader_set_win(self):
        page = self.page()
        self.go(page, "connect.html")
        page.evaluate("() => DDF.engine.apply({weeks: {regularEnd: 12, playoffLo: 13, playoffHi: 16}})")
        self.sleeper_import(page)
        rec = page.evaluate("() => DDF.state.get('pasted')")
        self.assertEqual(self.weeks(page), {"regularEnd": 12, "playoffLo": 13, "playoffHi": 16})
        self.assertIsNone(rec["weeksFilled"])
        self.assertEqual(rec["leagueState"]["version"], "league-state/1", "the state is still stored")
        self.go(page, "settings.html")
        self.assertTrue(page.locator("#weeks-note").is_hidden())
        self.assertEqual(page.errors, [])

    def test_refused_fill_records_null_weeksFilled_when_plan_matches_reader_weeks(self):
        # P2 regression (ceb9ebc): when weekFill refuses to patch but fill.plan happens to agree with
        # the reader's regularEnd and playoffLo, the last return in fillWeeks still returned the tuple
        # as weeksFilled. That marker caused a later paste to trigger releaseWeeks() and overwrite
        # the reader-owned weeks with the site defaults.
        # fixture with start=15 -> plan = {regularEnd:14, playoffLo:15}; reader sets playoffHi:16 so
        # sameWeeks(cur, def) fails (def.playoffHi=17 != 16) -> weekFill refuses; plan still matches
        # cur on regularEnd and playoffLo, triggering the bug if unfixed.
        fx15 = sleeper_fixture(15, "900000000000000015")
        page = self.page(fx=fx15)
        self.go(page, "connect.html")
        page.evaluate("() => DDF.engine.apply({weeks: {regularEnd: 14, playoffLo: 15, playoffHi: 16}})")
        self.sleeper_import(page)
        rec = page.evaluate("() => DDF.state.get('pasted')")
        self.assertEqual(self.weeks(page), {"regularEnd": 14, "playoffLo": 15, "playoffHi": 16}, "reader weeks stay")
        self.assertIsNone(rec["weeksFilled"], "refused fill must not save a weeksFilled marker")
        self.assertEqual(rec["leagueState"]["version"], "league-state/1", "state still stored")
        # second import (paste league) must NOT release the reader-owned weeks
        page.evaluate("""() => {
          DDF.state.set('pasted', DDF.leaguePaste.record({teams: [{name: 'A', players: [], unmatched: []}, {name: 'B', players: [], unmatched: []}], league: {}}, 'paste'));
        }""")
        self.assertEqual(self.weeks(page), {"regularEnd": 14, "playoffLo": 15, "playoffHi": 16}, "paste must not reset reader weeks")
        self.assertEqual(page.errors, [])

    def test_a_pasted_league_has_no_state_and_fills_nothing(self):
        page = self.page()
        self.go(page, "connect.html")
        page.evaluate("""() => {
          DDF.state.set('pasted', DDF.leaguePaste.record({teams: [{name: 'A', players: [], unmatched: []}, {name: 'B', players: [], unmatched: []}], league: {}}, 'paste'));
        }""")
        rec = page.evaluate("() => DDF.state.get('pasted')")
        self.assertIsNone(rec["leagueState"])
        self.assertIn("paste", rec["leagueStateReason"])
        self.assertIsNone(rec["weeksFilled"])
        self.assertEqual(self.weeks(page), {"regularEnd": 14, "playoffLo": 15, "playoffHi": 17})
        self.go(page, "settings.html")
        self.assertTrue(page.locator("#weeks-note").is_hidden())
        cur = page.evaluate("() => DDF.league.current()")
        self.assertIsNone(cur["leagueState"])
        self.assertTrue(cur["leagueStateReason"])


class AssistStateGuard(unittest.TestCase):
    """v2.js: the ddf-state block carries the reader's saved league-state, and not on a page showing a shared link's league."""

    def test_link_league_page_carries_no_state(self):
        _render_env.ensure_built()
        from playwright.sync_api import sync_playwright
        from tests._dist_server import serve, V2_URL
        ls = json.loads((FIX / "league-state" / "sleeper.json").read_text(encoding="utf-8"))
        ws = {"v": 1, "activeId": "league_1", "workspaces": [{"id": "league_1", "name": "L", "teams": [], "myTeamId": None, "leagueState": ls}]}
        with serve() as base, sync_playwright() as pw:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            ctx = browser.new_context(viewport={"width": 1200, "height": 900})
            ctx.add_init_script("localStorage.setItem('ddf.v2.workspaces', %s)" % json.dumps(json.dumps(ws)))
            page = ctx.new_page()
            page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
            build = "() => { const r = DDFAssist.buildState(); return r.state && r.state.leagueState ? r.state.leagueState.version : null; }"
            page.goto(f"{base}/{V2_URL}#compare-trade", wait_until="networkidle", timeout=90000)
            page.wait_for_function("() => window.DDFAssist && window.TradeValueV2 && window.TradeValueV2.leagueInputs", timeout=60000)
            self.assertEqual(page.evaluate("() => TradeValueV2.leagueInputs().source !== 'link'"), True)
            self.assertEqual(page.evaluate(build), "league-state/1", "the reader's own saved league carries its state")
            page.goto(f"{base}/{V2_URL}#compare-trade?scoring=ppr&teams=10", wait_until="networkidle", timeout=90000)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && TradeValueV2.leagueInputs().source === 'link'", timeout=60000)
            self.assertIsNone(page.evaluate(build), "a shared link's league has no state of its own")
            browser.close()


if __name__ == "__main__":
    unittest.main()
