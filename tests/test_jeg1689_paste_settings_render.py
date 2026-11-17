"""JEG-1689: a pasted league sets the league settings it shows, and League settings says which ones (built dist/, Chromium).

Jeremy, 2026-11-16: "Pasting leagues should allow for getting to at least the total number of rostered players. It may
allow for inferring the roster construction as well. Update so what is set to default takes advantage of the paste."
Addition the same day: the settings page says the values were read from the paste and need checking, each one carries a
visible marker, and confirming or changing a value clears its marker and is remembered.

Pinned here, on the real connect.html -> settings.html flow with tests/fixtures/paste_defaults:
  * ESPN 10-team paste: the engine runs 10 teams and 6 bench; League settings shows them with "From your paste" on every
    read value and the notice in place of "Roster sizes are optional".
  * Changing a value clears its marker and records it; reading the same paste again does not reset it; confirming the
    page clears every marker, and a reload shows them confirmed.
  * A cut-off paste changes nothing and says so; no paste: no notice, no markers.
  * 1440 and 390 wide: no page overflow. The pages have one (light) theme; a dark color scheme renders the same page.
Inference rules and copy for every provider are in tests/test_paste_settings.js.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _render_env  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "paste_defaults"
FIELDS = ["teams", "QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST", "BENCH"]


class PasteSettingsRender(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def context(self, width, scheme="light"):
        ctx = self.browser.new_context(viewport={"width": width, "height": 900 if width > 760 else 844}, color_scheme=scheme)
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
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

    def paste(self, page, fixture):
        self.go(page, "connect.html")
        page.fill("#rosters", (FIX / fixture).read_text(encoding="utf-8"))
        page.evaluate("() => DDF.connectEntry.check(false, false)")
        page.wait_for_function("() => { const p = DDF.state.get('pasted', null); return p && p.pasteSettings; }", timeout=20000)

    def engine(self, page):
        return page.evaluate("() => { const s = DDF.engine.settings(); return Object.assign({teams: s.teams}, s.roster); }")

    def markers(self, page):
        return page.evaluate(f"() => {FIELDS!r}.filter(f => {{ const m = document.getElementById('from-' + f); return m && !m.hidden && m.offsetParent !== null; }})")

    def notice(self, page):
        return page.evaluate("() => { const b = document.getElementById('paste-notice'); return b.hidden ? null : [...b.querySelectorAll('p')].map(p => p.textContent); }")

    def test_espn_paste_sets_marks_and_remembers(self):
        page = self.context(1440)
        self.paste(page, "espn-10team.txt")
        got = self.engine(page)
        self.assertEqual({k: got[k] for k in ("teams", "QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST", "BENCH")},
                         {"teams": 10, "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "K": 1, "DST": 1, "BENCH": 6})
        self.go(page, "settings.html")
        self.assertEqual(page.input_value("#teams"), "10")
        self.assertEqual(page.input_value("#lineup-bench"), "6")
        self.assertEqual(self.markers(page), FIELDS, "every read value is marked")
        self.assertEqual(page.inner_text("#from-QB").strip(), "From your paste")
        self.assertIn("from-QB", page.get_attribute("#lineup-qb", "aria-describedby"))
        lines = self.notice(page)
        self.assertEqual(lines[0], "We read 10 teams and 159 players from your paste, up to 16 on a roster.")
        self.assertTrue(lines[-1].startswith("Please check each one marked"))
        self.assertTrue(page.locator("#roster-optional").is_hidden(), "the standard-roster note gives way to the paste notice")
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)

        # a change clears that marker; confirming the page clears every marker and saves
        page.get_by_role("button", name="Decrease BENCH", exact=True).click()
        self.assertNotIn("BENCH", self.markers(page))
        self.assertIn("QB", self.markers(page))
        page.evaluate("() => document.getElementById('editor').requestSubmit()")
        self.assertEqual(self.markers(page), [])
        confirmed = page.evaluate("() => DDF.state.get('pasted').confirmed")
        self.assertEqual(confirmed["BENCH"], 5)
        self.assertEqual(confirmed["teams"], 10)
        self.assertEqual(self.engine(page)["BENCH"], 5)

        # the same paste read again keeps the reader's bench and shows no markers
        self.paste(page, "espn-10team.txt")
        self.assertEqual(page.evaluate("() => DDF.state.get('pasted').confirmed"), confirmed)
        self.assertEqual(self.engine(page)["BENCH"], 5)
        self.go(page, "settings.html")
        self.assertEqual(page.input_value("#lineup-bench"), "5")
        self.assertEqual(self.markers(page), [])
        self.assertEqual(self.notice(page)[-1], "You've checked these. You can still change any of them below.")
        self.assertEqual(self.engine(page)["teams"], 10)

        # another league is read fresh
        self.paste(page, "sleeper-14team.txt")
        self.assertEqual(self.engine(page)["teams"], 14)
        self.assertEqual(self.engine(page)["BENCH"], 5)
        self.go(page, "settings.html")
        self.assertEqual(self.markers(page), FIELDS)
        self.assertEqual(page.errors, [])

    def test_phone_and_dark_scheme(self):
        for width, scheme in ((390, "light"), (390, "dark"), (1440, "dark")):
            with self.subTest(width=width, scheme=scheme):
                page = self.context(width, scheme)
                self.paste(page, "yahoo-12team-superflex.txt")
                self.go(page, "settings.html")
                self.assertEqual(page.input_value("#lineup-sf"), "1")
                self.assertEqual(len(self.markers(page)), len(FIELDS))
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                bg = page.evaluate("getComputedStyle(document.getElementById('paste-notice')).backgroundColor")
                self.assertEqual(bg, "rgb(255, 248, 230)")

    def test_cut_off_paste_changes_nothing_and_says_so(self):
        page = self.context(1440)
        self.go(page, "settings.html")
        before = self.engine(page)
        self.paste(page, "espn-10team-partial.txt")
        self.assertEqual(self.engine(page), before)
        self.go(page, "settings.html")
        self.assertEqual(self.markers(page), [])
        self.assertTrue(self.notice(page)[0].startswith("Your paste looks cut off: Bench Mob shows only 4 players"))
        self.assertTrue(page.locator("#roster-optional").is_visible())

    def test_no_paste_no_notice(self):
        page = self.context(1440)
        self.go(page, "settings.html")
        self.assertIsNone(self.notice(page))
        self.assertEqual(self.markers(page), [])
        self.assertTrue(page.locator("#roster-optional").is_visible())


if __name__ == "__main__":
    unittest.main()
