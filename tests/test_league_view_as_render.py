"""JEG-1696: a kept league stays fully editable; "Viewing as" any team, with one tap back to your own.

Jeremy, 2026-11-17: "Enable me changing all settings when I go back to see my league after it is cached, for example I
may want to pretend I'm another team and see their options. I should be able to back up in the league setup easily and
be able to see the selections there and swap them at all times."

1. A returning visitor (saved league in localStorage, no tab session) sees the league on setup.html with their team
   picked, can move on from connect.html, and every entry step is a link both ways.
2. Completed entry steps are readable on the dark header (not dark green on dark green).
3. The header league menu and the workspace step trail carry a "Viewing as" picker; switching writes `me` (pasted and
   saved leagues), keeps `own`, drops the other team's waiver moves, and every page reads the new team.
4. Viewing as another team shows a banner with one tap back; setup.html still picks the reader's own team.
5. Phone width (375): no horizontal overflow, 44px picker targets.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._dist_server import serve
from tests.test_bookmark_freshness import seed_script

ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.viewAs"
LEAGUE_READY = "() => window.DDF && DDF.league && DDF.league.current && DDF.league.current()"
SAVED = {"v": 1, "activeId": "L1", "workspaces": [{"id": "L1", "name": "USO Season XVIII", "settings": None, "myTeamId": "t2", "teams": [
    {"id": "t1", "name": "Fourth Down Club", "entries": [{"key": "869", "name": "Josh Allen", "pos": "QB"}]},
    {"id": "t2", "name": "Hail Marys", "entries": [{"key": "2227", "name": "Jahmyr Gibbs", "pos": "RB"}]},
    {"id": "t3", "name": "Kingdom of Caleb", "entries": [{"key": "1370", "name": "Puka Nacua", "pos": "WR"}]}]}]}
SAVED_SEED = ("(() => { if (sessionStorage.getItem('ddf:seeded')) return; localStorage.setItem('ddf.v2.workspaces', "
              + json.dumps(json.dumps(SAVED)) + "); sessionStorage.setItem('ddf:seeded', '1'); })()")


def setUpModule():
    _render_env.ensure_built()


class ViewAsSourceTest(unittest.TestCase):

    def test_no_new_storage_key_and_no_ticket_ids_in_copy(self):
        from tests.test_edit_league import source_keys, NEXT
        site = (NEXT / "site.js").read_text(encoding="utf-8")
        for key in source_keys():
            self.assertIn(key, site, f"{key} must be listed in DDF.startFresh.KEYS")
        self.assertIn('<label class="ddf-cm-va" hidden><span>Viewing as</span></label>', site)
        for needle in ("'Viewing as ' + r.names[r.me] + '.'", "'Back to ' + r.names[r.own]", "'✓ League settings'"):
            self.assertIn(needle, site)


class ViewAsRenderTest(unittest.TestCase):

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

    def page(self, seed, width=375):
        context = self.browser.new_context(viewport={"width": width, "height": 812})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        page.add_init_script(seed)
        return page

    def open(self, page, path, league=True):
        page.goto(f"{self.base}/{path}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.viewAs", timeout=60000)
        if league:
            page.wait_for_function(LEAGUE_READY, timeout=60000)
            page.wait_for_timeout(150)

    def overflow(self, page):
        return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")

    def trail(self, page):
        return page.eval_on_selector_all("ol.entry-steps > li", "els => els.map(e => [!!e.querySelector('a'), e.textContent.trim()])")

    def test_returning_visitor_sees_and_changes_the_saved_league(self):
        page = self.page(SAVED_SEED)
        self.open(page, "setup.html", league=False)
        self.assertEqual(page.eval_on_selector("input[name=team]:checked", "e => e.value"), "Hail Marys")
        self.assertTrue(page.is_hidden("#setup-empty"))
        self.assertEqual(self.trail(page), [[True, "✓ 1. League rosters"], [False, "2. Your team"], [True, "✓ 3. League settings"]])
        # completed steps read on the dark header
        color = page.eval_on_selector("ol.entry-steps .is-complete a", "a => getComputedStyle(a).color")
        self.assertEqual(color, "rgb(247, 248, 245)")
        page.check("input[name=team][value='Kingdom of Caleb']", force=True)
        saved = json.loads(page.evaluate("localStorage.getItem('ddf.v2.workspaces')"))["workspaces"][0]
        self.assertEqual((saved["myTeamId"], saved["ownTeamId"]), ("t3", "t3"))
        self.assertEqual(self.overflow(page), 0)
        self.open(page, "connect.html", league=False)
        self.assertEqual(self.trail(page), [[False, "1. League rosters"], [True, "✓ 2. Your team"], [True, "✓ 3. League settings"]])
        self.assertIsNone(page.get_attribute("#connect-next", "aria-disabled"), "a kept league moves on from step 1")
        self.assertEqual(page.errors, [])

    def test_switch_team_from_the_trail_and_back_from_the_banner(self):
        page = self.page(seed_script(1))
        page.add_init_script("if (!sessionStorage.getItem('ddf:seeded-moves')) { sessionStorage.setItem('ddf:moves', JSON.stringify([{add: '1370', drop: null, at: 1}])); sessionStorage.setItem('ddf:seeded-moves', '1'); }")
        self.open(page, "find.html")
        self.assertIsNone(page.query_selector("#ddf-viewas"))
        sel = "nav.ws-steps .ws-viewas select"
        self.assertEqual(page.eval_on_selector(sel, "s => s.options[s.selectedIndex].text"), "Hail Marys (yours)")
        self.assertEqual(page.eval_on_selector("nav.ws-steps .ws-setup", "a => a.getAttribute('href')"), "settings.html")
        with page.expect_navigation():
            page.select_option(sel, "2")
        page.wait_for_function(LEAGUE_READY, timeout=60000)
        page.wait_for_timeout(150)
        pasted = json.loads(page.evaluate("sessionStorage.getItem('ddf:pasted')"))
        self.assertEqual((pasted["me"], pasted["own"]), (2, 1))
        self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:moves')"), "the other team's waiver moves are dropped")
        self.assertEqual(page.evaluate("DDF.league.myTeam().name"), "Kingdom of Caleb")
        self.assertEqual(page.text_content("#ddf-viewas strong"), "Viewing as Kingdom of Caleb.")
        self.assertEqual(page.text_content("#ddf-viewas button"), "Back to Hail Marys")
        self.assertTrue(page.eval_on_selector(".ddf-chipwrap", "w => w.classList.contains('is-viewas')"))
        self.assertGreaterEqual(page.eval_on_selector("#ddf-viewas button", "b => b.getBoundingClientRect().height"), 44)
        self.assertEqual(self.overflow(page), 0)
        # every workspace page reads the team in view
        for path in ("team.html", "waivers.html", "build.html", "values.html"):
            self.open(page, path)
            self.assertEqual(page.evaluate("DDF.league.myTeam().name"), "Kingdom of Caleb", path)
            self.assertEqual(self.overflow(page), 0, path)
        self.assertEqual(page.evaluate("DDF.viewAs.read().me"), 2)
        self.open(page, "find.html")
        with page.expect_navigation():
            page.click("#ddf-viewas button")
        page.wait_for_function(LEAGUE_READY, timeout=60000)
        page.wait_for_timeout(150)
        self.assertEqual(page.evaluate("DDF.league.myTeam().name"), "Hail Marys")
        self.assertIsNone(page.query_selector("#ddf-viewas"))
        self.assertEqual(page.errors, [])

    def test_switch_from_the_header_menu_on_a_saved_league(self):
        page = self.page(SAVED_SEED)
        self.open(page, "team.html")
        page.click("header .ddf-chip")
        picker = page.query_selector(".ddf-chipmenu .ddf-cm-team")
        self.assertTrue(picker.is_visible())
        self.assertGreaterEqual(picker.bounding_box()["height"], 44)
        links = page.eval_on_selector_all(".ddf-chipmenu a", "as => as.map(a => a.getAttribute('href'))")
        self.assertEqual(links, ["connect.html?edit=1", "settings.html"])
        page.click(".ddf-chipmenu label")   # the picker keeps the menu open
        self.assertTrue(page.eval_on_selector(".ddf-chipwrap", "w => w.classList.contains('open')"))
        with page.expect_navigation():
            page.select_option(".ddf-chipmenu .ddf-cm-team", "0")
        page.wait_for_function(LEAGUE_READY, timeout=60000)
        saved = json.loads(page.evaluate("localStorage.getItem('ddf.v2.workspaces')"))["workspaces"][0]
        self.assertEqual((saved["myTeamId"], saved["ownTeamId"]), ("t1", "t2"))
        self.assertEqual(page.evaluate("DDF.league.myTeam().name"), "Fourth Down Club")
        page.wait_for_selector("#ddf-viewas")
        # setup.html still asks which team is yours, and shows it
        self.open(page, "setup.html", league=False)
        self.assertEqual(page.eval_on_selector("input[name=team]:checked", "e => e.value"), "Hail Marys")
        self.assertEqual(page.errors, [])


if __name__ == "__main__":
    unittest.main()
