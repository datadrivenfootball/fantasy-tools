"""JEG-1568: "Edit league" opens the start of the entry flow; "Start fresh" clears the league from this browser.

1. Every "Edit league" link (header menu, page strips, chat strip) goes to connect.html?edit=1.
2. Editing keeps the current league in use until a replacement is read: typing in the box, emptying it or leaving the
   page loses nothing; "Replacing: <name>" shows.
3. A replacement paste without a league name gets the current name as the suggestion, and the team you had is
   preselected when the new paste has a team of that name.
4. Start fresh clears every key in DDF.startFresh.KEYS (session, prefixes, local), keeps value overrides unless the
   checkbox is on, keeps the player table; the source scan fails when a new storage key is not in those lists.
5. A wiped #s= link is not imported again: the address loses it, and the same link reopened in the session is ignored.
6. The confirm is in the page: role=dialog, labelled, focus on "Keep my league", Esc returns focus, Tab stays inside,
   44px targets, no overflow at 390 and 1440.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve
from tests.test_bookmark_freshness import seed_script

ROOT = Path(__file__).resolve().parents[1]
NEXT = ROOT / "app" / "next"
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.startFresh"
# Event names that share the ddf: prefix but are not storage keys.
EVENTS_ONLY = {"ddf:values-change"}


def source_keys() -> set[str]:
    """Storage keys the redesign pages use, read from the source."""
    keys = set()
    for f in list(NEXT.glob("*.js")) + list(NEXT.glob("*.html")):
        text = f.read_text(encoding="utf-8")
        keys |= set(re.findall(r"""['"](ddf:[a-zA-Z][\w-]*:?|ddf\.v2\.[\w-]+|ddf-v2-[\w-]+|ddf-recommendation)['"]""", text))
        keys |= {"ddf:" + k for k in re.findall(r"""DDF\.state\.(?:get|set|remove)\(\s*['"]([\w:-]+)['"]""", text)}
        keys |= {"ddf:" + k for k in re.findall(r"""(?:getList|setList)\(\s*['"](\w+)['"]""", text)}
    return {k for k in keys if k not in EVENTS_ONLY}


def setUpModule():
    _render_env.ensure_built()


class EditLeagueSourceTest(unittest.TestCase):

    def test_every_edit_league_link_opens_the_start(self):
        for page in ("find", "build", "waivers", "explore", "team", "partners"):
            text = (NEXT / f"{page}.html").read_text(encoding="utf-8")
            self.assertIn('<a href="connect.html?edit=1">Edit league</a>', text, page)
            self.assertNotIn('<a href="settings.html">Edit league</a>', text, page)
        site = (NEXT / "site.js").read_text(encoding="utf-8")
        self.assertEqual(site.count('href="connect.html?edit=1">Edit league</a>'), 2)   # header menu + chat strip


class EditLeagueRenderTest(unittest.TestCase):

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

    def open(self, page, path):
        page.goto(f"{self.base}/{path}", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)

    def test_menu_edit_league_and_abandoned_edit_keeps_the_league(self):
        page = self.page(seed=seed_script(2))
        self.open(page, "team.html")
        page.click("header .ddf-chip")
        self.assertEqual(page.get_attribute(".ddf-chipmenu a", "href"), "connect.html?edit=1")
        before = page.evaluate("sessionStorage.getItem('ddf:pasted')")
        page.click(".ddf-chipmenu a")
        page.wait_for_url("**/connect.html?edit=1", timeout=20000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        self.assertTrue(page.text_content("#entry-top-text").startswith("Replacing: USO Season XVIII."))
        self.assertEqual(page.text_content("#replacing-line"), "Replacing: USO Season XVIII")
        page.fill("#rosters", "some text that is not a league")
        page.click("#recognize-button")
        page.wait_for_timeout(500)
        page.fill("#rosters", "")
        page.click("#manual-toggle")
        page.fill("#manual-names", "One")
        page.fill("#manual-names", "")
        page.dispatch_event("#manual-names", "input")
        self.assertEqual(page.evaluate("sessionStorage.getItem('ddf:pasted')"), before, "nothing replaced the league")
        self.open(page, "team.html")
        self.assertEqual(page.text_content("header .ddf-chip .ddf-chip-t"), "USO Season XVIII")
        self.assertEqual(page.errors, [])

    def test_replacement_prefills_name_and_team(self):
        page = self.page(width=390, seed=seed_script(2))
        self.open(page, "connect.html?edit=1")
        page.fill("#rosters", (FIXTURES / "01-yahoo-iphone.txt").read_text(encoding="utf-8"))   # no league name; has "Hail Marys"
        page.click("#recognize-button")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.click("#connect-next")
        page.wait_for_url("**/setup.html", timeout=20000)
        self.assertEqual(page.input_value("#league-name"), "USO Season XVIII")
        self.assertIn("current league", page.text_content("#league-name-note"))
        self.assertEqual(page.eval_on_selector("input[name=team]:checked", "e => e.value"), "Hail Marys")
        self.assertIsNone(page.get_attribute("#continue-btn", "aria-disabled"))
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)

    def test_start_fresh_clears_every_listed_key(self):
        for clear_overrides in (False, True):
            with self.subTest(overrides=clear_overrides):
                page = self.page(seed=seed_script(2))
                self.open(page, "team.html")
                keys = page.evaluate("DDF.startFresh.KEYS")
                listed = set(keys["session"] + keys["local"] + keys["overridesSession"] + keys["overridesLocal"] + keys["keep"])
                missing = sorted(k for k in source_keys()
                                 if k not in listed and not any(k.startswith(p) for p in keys["sessionPrefixes"] + keys["keepPrefixes"]))
                self.assertEqual(missing, [], "a storage key is not in DDF.startFresh.KEYS (wipe or keep it on purpose)")
                page.evaluate("""k => {
                    k.session.concat(['ddf:freshdismiss:note'], k.overridesSession).forEach(x => { if (!sessionStorage.getItem(x)) sessionStorage.setItem(x, '{}'); });
                    sessionStorage.setItem('ddf:wipedlink', '"x"');
                    k.local.concat(k.overridesLocal).forEach(x => localStorage.setItem(x, '{"v":1}'));
                }""", keys)
                page.click("header .ddf-chip")
                page.click(".ddf-cm-fresh")
                page.wait_for_selector(".ddf-fresh-panel", state="visible")
                if clear_overrides:
                    page.check("#ddf-sf-ov")
                page.click(".ddf-sf-go")
                page.wait_for_url("**/connect.html", timeout=20000)
                page.wait_for_load_state("networkidle")
                left_s = page.evaluate("Object.keys(sessionStorage)")
                left_l = page.evaluate("Object.keys(localStorage)")
                for k in keys["session"] + ["ddf:freshdismiss:note"]:
                    if k == "ddf:bmovbase":
                        continue   # the new page writes its baseline again (a count, no league data)
                    self.assertNotIn(k, left_s, k)
                for k in keys["local"]:
                    self.assertNotIn(k, left_l, k)
                vals = page.evaluate("k => Object.fromEntries(k.map(x => [x, sessionStorage.getItem(x)]))", keys["overridesSession"])
                for k in keys["overridesSession"]:
                    if clear_overrides:
                        self.assertIn(vals[k], (None, "{}"), k)   # the new page may write an empty store
                    else:
                        self.assertIsNotNone(vals[k], k)
                for k in keys["overridesLocal"]:
                    (self.assertNotIn if clear_overrides else self.assertIn)(k, left_l, k)
                self.assertIn("ddf:wipedlink", left_s)
                self.assertTrue(page.is_hidden("#entry-top"))
                self.assertIn("Add your league", page.title())
                self.assertEqual(page.errors, [])

    def test_wiped_link_is_not_imported_again(self):
        page = self.page()
        self.open(page, "values.html")
        page.wait_for_function("() => DDF.link && DDF.link.table(1)", timeout=20000)
        token = page.evaluate("""() => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 10, superflex: false,
            slots: [1, 2, 2, 1, 1, 6]}, teams: [{name: 'Link A', players: ['Josh Allen']}, {name: 'Link B', players: ['Jordan Love']}], me: 0, name: 'Chat League'})""")
        self.open(page, f"team.html#s={token}")
        page.wait_for_function("() => DDF.link.current() && DDF.link.current().name === 'Chat League'", timeout=20000)
        page.evaluate("DDF.startFresh.open()")
        page.click(".ddf-sf-go")
        page.wait_for_url("**/connect.html", timeout=20000)
        page.go_back(wait_until="networkidle")
        self.assertNotIn("#s=", page.url)
        self.open(page, f"team.html#s={token}")
        page.wait_for_timeout(1000)
        self.assertIsNone(page.evaluate("DDF.link.current()"))
        self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:league')"))

    def test_dialog_keyboard_labels_and_targets(self):
        for width in (390, 1440):
            with self.subTest(width=width):
                page = self.page(width=width, seed=seed_script(2))
                self.open(page, "team.html")
                page.click("header .ddf-chip")
                self.assertGreaterEqual(page.evaluate("document.querySelector('.ddf-cm-fresh').getBoundingClientRect().height"), 43.5)
                page.click(".ddf-cm-fresh")
                panel = page.locator(".ddf-fresh-panel")
                self.assertEqual(panel.get_attribute("role"), "dialog")
                self.assertEqual(panel.get_attribute("aria-modal"), "true")
                self.assertEqual(page.text_content("#" + panel.get_attribute("aria-labelledby")), "Start fresh?")
                self.assertIn("league name and settings", page.text_content("#" + panel.get_attribute("aria-describedby")))
                self.assertEqual(page.evaluate("document.activeElement.textContent"), "Keep my league")
                for sel in (".ddf-sf-go", ".ddf-sf-keep", ".ddf-sf-check"):
                    self.assertGreaterEqual(page.evaluate(f"document.querySelector('{sel}').getBoundingClientRect().height"), 43.5, sel)
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                for _ in range(4):
                    page.keyboard.press("Tab")
                self.assertTrue(page.evaluate("document.querySelector('.ddf-fresh-panel').contains(document.activeElement)"), "focus stays in the dialog")
                page.keyboard.press("Escape")
                self.assertTrue(page.is_hidden(".ddf-fresh-panel"))
                self.assertEqual(page.evaluate("document.activeElement.className"), "ddf-chip")
                self.assertIsNotNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"), "Keep my league / Esc clears nothing")


if __name__ == "__main__":
    unittest.main()
