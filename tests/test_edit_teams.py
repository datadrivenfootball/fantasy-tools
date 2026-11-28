"""JEG-1740: Edit teams (teams.html), change rosters by hand after setup, and paste again keeping settings and your team.

Jeremy, 2026-11-28: a screen for editing teams after everything is loaded, that recommends redoing the paste after time
has passed (a link that starts the paste over but keeps the league settings and your team), and still lets you modify
teams easily.

1. Links: the league chip menu, the More menu, Team assessment and the site map open teams.html; the roster-age banner
   offers it next to the paste link, and every "paste again" link opens connect.html?edit=1&again=1.
2. The roster-age card: quiet when the rosters are a day old, a primary "Paste rosters again" from 2 days; the page banner
   stays off here (the card replaces it).
3. A pasted league: rename (a duplicate name is refused), remove, add, move a player from another team, undo; each change
   is in ddf:pasted at once, your team stays yours, and Team assessment reads the change. A paste line we could not match
   is found and added, or removed.
4. A saved league (localStorage only) and a chat link league are edited where they live.
5. Paste again (connect.html?edit=1&again=1): the new paste keeps the league's settings (nothing the paste infers
   changes them), its name and your team.
6. Phone width: no sideways scroll, 44px targets.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve
from tests.test_bookmark_freshness import seed_script

ROOT = Path(__file__).resolve().parents[1]
NEXT = ROOT / "app" / "next"
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.teamsEntry !== undefined"
PASTED = "JSON.parse(sessionStorage.getItem('ddf:pasted'))"


def setUpModule():
    _render_env.ensure_built()


class EditTeamsSourceTest(unittest.TestCase):

    def test_links_reach_edit_teams(self):
        site = (NEXT / "site.js").read_text(encoding="utf-8")
        self.assertIn('<a href="connect.html?edit=1">Edit league</a><a href="teams.html">Edit teams</a>', site)
        self.assertIn("['teams.html','Edit teams']", site)
        self.assertIn('href="connect.html?edit=1&amp;again=1"', site)
        team = (NEXT / "team.html").read_text(encoding="utf-8")
        self.assertIn('<a href="teams.html">Edit teams</a>: fix a roster by hand', team)
        for page in ("team", "find", "build", "values", "explore", "partners", "waivers"):
            self.assertIn('<a href="settings.html">League settings</a><a href="teams.html">Edit teams</a>',
                          (NEXT / f"{page}.html").read_text(encoding="utf-8"), page)
        build = (ROOT / "pipelines" / "build_root_pages.py").read_text(encoding="utf-8")
        self.assertIn('"teams.html"', build)
        self.assertIn('"teams-entry.js"', build)


class EditTeamsRenderTest(unittest.TestCase):

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

    def page(self, width=1440, seed=None):
        context = self.browser.new_context(viewport={"width": width, "height": 900})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        if seed:
            page.add_init_script(seed)
        return page

    def open(self, page, path, ready=ENGINE_READY):
        page.goto(f"{self.base}/{path}", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ready, timeout=60000)

    def label_of(self, page, name):
        """The add box's option text for a player on the engine's list."""
        return page.evaluate("""n => { const o = Array.from(document.querySelectorAll('#tm-options option')).map(x => x.value)
            .filter(v => v.startsWith(n + ' (')); return o.length === 1 ? o[0] : null; }""", name)

    def free_player(self, page):
        """A priced player on no team in the league, as the add box lists it."""
        return page.evaluate("""() => {
            const on = new Set(JSON.parse(sessionStorage.getItem('ddf:pasted')).teams.flatMap(t => t.players.map(p => p.key)));
            const r = DDF.engine.controls().getAllRows().filter(x => x && x.name && x.pos === 'RB' && !on.has(String(x.player_key)));
            const names = r.map(x => x.name), one = r.find(x => names.filter(n => n === x.name).length === 1);
            return {name: one.name, key: String(one.player_key), label: one.name + ' (' + one.pos + (one.team ? ', ' + one.team : '') + ')'};
        }""")

    def test_roster_age_card_and_links(self):
        for days, band, primary in ((0, "fresh", False), (5, "prompt", True), (9, "stale", True)):
            with self.subTest(days=days):
                page = self.page(seed=seed_script(days))
                self.open(page, "teams.html")
                self.assertEqual(page.get_attribute("#tm-fresh", "data-band"), band)
                self.assertIn("today" if days == 0 else f"{days} days ago", page.text_content("#tm-fresh-title"))
                self.assertEqual(page.get_attribute("#tm-again", "href"), "connect.html?edit=1&again=1")
                self.assertEqual("primary" in (page.get_attribute("#tm-again", "class") or ""), primary)
                self.assertIn("league settings, league name and your team stay", page.text_content("#tm-keep"))
                self.assertEqual(page.locator("#ddf-fresh").count(), 0, "the page card replaces the banner")
                self.assertEqual(page.errors, [])
        page = self.page(seed=seed_script(5))
        self.open(page, "team.html", "() => !!document.querySelector('#ddf-fresh')")
        self.assertEqual(page.get_attribute("#ddf-fresh .ddf-fresh-go", "href"), "connect.html?edit=1&again=1")
        self.assertEqual(page.get_attribute("#ddf-fresh .ddf-fresh-edit", "href"), "teams.html")
        page.click("header .ddf-chip")
        page.click(".ddf-chipmenu a[href='teams.html']")
        page.wait_for_url("**/teams.html", timeout=20000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.assertEqual(page.get_attribute("#tm-teams [aria-pressed=true]", "data-team"), "1", "opens on your team")

    def test_pasted_league_rename_remove_add_move_undo(self):
        page = self.page(seed=seed_script(5))
        self.open(page, "teams.html")
        self.assertIn("Your team", page.text_content("#tm-editor-title"))
        self.assertIn("Hail Marys", page.text_content("#tm-editor-title"))
        # rename, and a duplicate is refused
        page.fill("#tm-name", "Kingdom of Caleb")
        page.click("#tm-rename")
        self.assertIn("already has that name", page.text_content("#tm-status"))
        page.fill("#tm-name", "Hail Yes")
        page.press("#tm-name", "Enter")
        rec = page.evaluate(PASTED)
        self.assertEqual(rec["teams"][1]["name"], "Hail Yes")
        self.assertEqual(rec["me"], 1)
        # move Puka Nacua from Kingdom of Caleb
        page.fill("#tm-find", self.label_of(page, "Puka Nacua"))
        page.click("#tm-add")
        self.assertIn("is on Kingdom of Caleb", page.text_content("#tm-status"))
        page.click("#tm-move")
        rec = page.evaluate(PASTED)
        self.assertEqual([p["key"] for p in rec["teams"][1]["players"]], ["2227", "1370"])
        self.assertEqual(rec["teams"][2]["players"], [])
        # add a player on no team
        free = self.free_player(page)
        page.fill("#tm-find", free["label"])
        page.press("#tm-find", "Enter")
        rec = page.evaluate(PASTED)
        self.assertEqual(rec["teams"][1]["players"][-1]["key"], free["key"])
        self.assertEqual(rec["teams"][1]["players"][-1]["line"], free["name"])
        # remove Jahmyr Gibbs, then undo it
        page.click("#tm-rows button[data-remove]:has(.sr-only:text-is(' Jahmyr Gibbs'))")
        self.assertNotIn("2227", [p["key"] for p in page.evaluate(PASTED)["teams"][1]["players"]])
        page.click("#tm-undo")
        self.assertIn("2227", [p["key"] for p in page.evaluate(PASTED)["teams"][1]["players"]])
        self.assertEqual(page.evaluate(PASTED)["enteredAt"], rec["enteredAt"], "hand edits keep the roster date")
        # every page reads the change
        self.open(page, "team.html", "() => window.DDF && DDF.league && DDF.league.current && DDF.league.current()")
        lg = page.evaluate("(() => { const c = DDF.league.current(); return {me: c.me, names: c.teams.map(t => t.name), mine: c.teams[c.me].players.map(p => p.key)}; })()")
        self.assertEqual(lg["names"], ["Fourth Down Club", "Hail Yes", "Kingdom of Caleb"])
        self.assertEqual(lg["me"], 1)
        self.assertEqual(sorted(lg["mine"]), sorted(["2227", "1370", free["key"]]))
        self.assertEqual(page.errors, [])

    def test_unmatched_line_find_and_remove(self):
        seed = seed_script(1).replace('"players": [{"name": "Josh Allen"',
                                      '"unmatched": [{"line": "Puka Nacua WR LA", "reason": "nomatch"}, {"line": "Bench Note", "reason": "nomatch"}], "players": [{"name": "Josh Allen"', 1)
        seed = seed.replace('"team": "BUF", "id": null}], "unmatched": []}', '"team": "BUF", "id": null}]}', 1)
        seed = seed.replace('{"name": "Kingdom of Caleb", "players": [{"name": "Puka Nacua", "key": "1370", "pos": "WR", "team": "LA", "id": 3}]', '{"name": "Kingdom of Caleb", "players": []', 1)
        page = self.page(seed=seed)
        self.open(page, "teams.html?team=0")
        self.assertFalse(page.locator("#tm-unmatched").is_hidden())
        page.click("#tm-unmatched-list button[data-find='0']")
        self.assertEqual(page.input_value("#tm-find"), "Puka Nacua")
        page.fill("#tm-find", self.label_of(page, "Puka Nacua"))
        page.click("#tm-add")
        rec = page.evaluate(PASTED)
        self.assertEqual([p["key"] for p in rec["teams"][0]["players"]], ["869", "1370"])
        self.assertEqual([u["line"] for u in rec["teams"][0]["unmatched"]], ["Bench Note"])
        page.click("#tm-unmatched-list button[data-dismiss='0']")
        self.assertEqual(page.evaluate(PASTED)["teams"][0]["unmatched"], [])
        self.assertTrue(page.locator("#tm-unmatched").is_hidden())
        self.assertEqual(page.errors, [])

    def test_saved_and_link_leagues_are_edited_where_they_live(self):
        ws = {"v": 1, "activeId": "lg1", "workspaces": [{"id": "lg1", "name": "Saved League", "myTeamId": "t2", "settings": None,
              "teams": [{"id": "t1", "name": "Alpha", "entries": [{"key": "869", "name": "Josh Allen", "pos": "QB", "team": "BUF"}]},
                        {"id": "t2", "name": "Bravo", "entries": [{"key": "2227", "name": "Jahmyr Gibbs", "pos": "RB", "team": "DET"}]}]}]}
        page = self.page(seed="localStorage.setItem('ddf.v2.workspaces', " + json.dumps(json.dumps(ws)) + ")")
        self.open(page, "teams.html")
        self.assertIn("Bravo", page.text_content("#tm-editor-title"))
        page.fill("#tm-name", "Bravo Two")
        page.click("#tm-rename")
        page.click("#tm-rows button[data-remove]")
        saved = page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces')).workspaces[0]")
        self.assertEqual(saved["teams"][1]["name"], "Bravo Two")
        self.assertEqual(saved["teams"][1]["id"], "t2")
        self.assertEqual(saved["teams"][1]["entries"], [])
        self.assertEqual(saved["myTeamId"], "t2")

        state = {"v": 1, "settings": {"scoring": "ppr", "teams": 12, "superflex": False, "slots": [1, 2, 2, 1, 1, 7]}, "me": 0,
                 "teams": [{"name": "Chat One", "players": ["Josh Allen"]}, {"name": "Chat Two", "players": ["Jahmyr Gibbs"]}]}
        seed = ("(() => { if (sessionStorage.getItem('ddf:seeded')) return; sessionStorage.setItem('ddf:league', " + json.dumps(json.dumps(state))
                + "); sessionStorage.setItem('ddf:link', JSON.stringify({source: 'chat', at: 1})); sessionStorage.setItem('ddf:seeded', '1'); })()")
        page = self.page(seed=seed)
        self.open(page, "teams.html")
        page.fill("#tm-find", self.label_of(page, "Puka Nacua"))
        page.click("#tm-add")
        page.fill("#tm-name", "Chat Uno")
        page.click("#tm-rename")
        link = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:league'))")
        self.assertEqual(link["teams"][0]["name"], "Chat Uno")
        self.assertEqual(link["teams"][0]["players"][0], "Josh Allen")
        self.assertEqual(len(link["teams"][0]["players"]), 2)
        self.assertEqual(link["me"], 0)
        self.assertEqual(link["settings"]["teams"], 12)
        self.assertEqual(page.errors, [])

    def test_paste_again_keeps_settings_name_and_team(self):
        page = self.page(width=390, seed=seed_script(8))
        self.open(page, "teams.html")
        page.evaluate("DDF.engine.apply({teams: 13, roster: {BENCH: 4}})")
        before = page.evaluate("DDF.engine.settings()")
        page.click("#tm-again")
        page.wait_for_url("**/connect.html?edit=1&again=1", timeout=20000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls()", timeout=60000)
        self.assertIn("Your league settings and your team stay as they are", page.text_content("#entry-top-text"))
        self.assertEqual(page.text_content("#entry-keep"), "Keep my current rosters")
        page.fill("#rosters", (FIXTURES / "01-yahoo-iphone.txt").read_text(encoding="utf-8"))   # has "Hail Marys"
        page.click("#recognize-button")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertEqual(page.locator("#team-pick-list .team-pick-option.selected strong").all_text_contents(), ["Hail Marys"])
        self.assertEqual(page.evaluate("DDF.engine.settings()"), before, "the paste's inferred settings do not apply")
        page.click(".ddf-actionbar__next")
        page.wait_for_url("**/settings.html", timeout=20000)
        kept = page.evaluate(PASTED)
        self.assertEqual(kept["name"], "USO Season XVIII")
        self.assertEqual(kept["teams"][kept["me"]]["name"], "Hail Marys")
        self.assertTrue(kept.get("pasteSettings"), "the fixture paste infers settings")
        self.assertEqual(page.evaluate("(() => { const r = " + PASTED + "; return DDF.leaguePaste.pendingFields(r.pasteSettings, r.confirmed); })()"), [],
                         "nothing the paste read waits to replace a setting")
        self.assertEqual(page.evaluate("DDF.engine.settings()"), before)
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)

    def test_phone_width(self):
        page = self.page(width=390, seed=seed_script(5))
        self.open(page, "teams.html")
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
        small = page.evaluate("""() => Array.from(document.querySelectorAll('main button, main a.button, main input'))
            .filter(e => e.offsetParent && e.getBoundingClientRect().height < 44).map(e => e.id || e.textContent.trim())""")
        self.assertEqual(small, [])
        self.assertEqual(page.errors, [])


if __name__ == "__main__":
    unittest.main()
