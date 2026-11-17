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


def sleeper_fixture():
    d = json.loads((FIX / "sleeper-live" / "full.json").read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    ids = list(json.loads((ROOT / "dist" / "sleeper-players.json").read_text(encoding="utf-8"))["p"].keys())[:60]
    for i, r in enumerate(d["rosters"]):
        r["players"] = ids[i * 4:i * 4 + 4]
    d["league"]["settings"]["playoff_week_start"] = START
    d["matchups"] = {k: v for k, v in d["matchups"].items() if int(k) <= START - 1}
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

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def sleeper_api(self, route):
        fx = self.fx
        lid = fx["league"]["league_id"]
        path = route.request.url.split("/v1/", 1)[1].split("?")[0]
        table = {f"league/{lid}": fx["league"], f"league/{lid}/users": fx["users"], f"league/{lid}/rosters": fx["rosters"], "state/nfl": fx["state"]}
        for wk, rows in fx["matchups"].items():
            table[f"league/{lid}/matchups/{wk}"] = rows
        if path in table:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(table[path]))
        else:
            route.fulfill(status=404, content_type="application/json", body="null")

    def page(self):
        ctx = self.browser.new_context(viewport={"width": 1000, "height": 900})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.route("https://api.sleeper.app/v1/**", self.sleeper_api)
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
        page.fill("#league-ref", self.fx["league"]["league_id"])
        page.click("#get-link")
        page.wait_for_function("() => { const p = DDF.state.get('pasted', null); return p && p.source === 'sleeper'; }", timeout=30000)

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
        self.assertIn("Source: sleeper:", note)
        self.assertRegex(note, r"as of 2026-\d\d-\d\d\.")
        self.assertEqual(self.weeks(page), rec["weeksFilled"], "the weeks survive a reload")

        # a week changed elsewhere is the reader's: the line goes away rather than claim the league
        page.evaluate("() => DDF.engine.apply({weeks: {regularEnd: 12, playoffLo: 13, playoffHi: 16}})")
        self.go(page, "settings.html")
        self.assertTrue(page.locator("#weeks-note").is_hidden())
        self.assertEqual(page.errors, [])

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


if __name__ == "__main__":
    unittest.main()
