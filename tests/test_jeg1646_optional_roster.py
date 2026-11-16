"""JEG-1646: roster sizes are optional on League settings; a standard roster is used and said so.

Max Logan's beta feedback (2026-11-15): people may not want to check each roster size; make it optional or say so.

Pinned here:
  * The standard roster is the engine's own default (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DEF, 7 bench), stated in
    plain words on League settings and marked optional; the page text is filled from the engine, not typed twice.
  * A new user reaches the next step without touching or opening a roster control (continue is enabled and links on).
  * Continuing with the defaults changes no value and stores nothing (no value math change).
  * team.html carries one line, "Standard roster in use", when the roster is the standard one; a league with its own
    sizes (a link here, like an import or a paste) does not show it, and its sizes still fill the settings form.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_jeg1632_kdef_slots import SettingsPage as _Base  # noqa: E402

STANDARD_TEXT = "1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DEF, 7 bench"
STANDARD_ROSTER = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 7, "K": 1, "DST": 1}


class OptionalRoster(_Base):
    def test_default_is_stated_optional_and_continue_needs_no_roster_input(self):
        for width in (1440, 375):
            with self.subTest(width=width):
                page = self.page(width)
                self.assertEqual(page.evaluate("() => DDF.engine.defaultRoster()"), STANDARD_ROSTER)
                text = page.inner_text("#roster-optional")
                self.assertIn("optional", text.lower())
                self.assertIn("change", text.lower())
                page.wait_for_function("() => document.getElementById('std-roster-text').textContent.includes('7 bench')")
                self.assertEqual(page.inner_text("#std-roster-text").strip(), STANDARD_TEXT)
                self.assertEqual(page.evaluate("() => DDF.engine.rosterText(DDF.engine.defaultRoster())"), STANDARD_TEXT)
                self.assertEqual(page.evaluate("() => [...document.querySelectorAll('#editor input[id^=lineup-]')].every(i => i.hasAttribute('required'))"), True,
                                 "every field is still validated if edited")
                cont = page.locator("#finish-setup")
                self.assertIsNone(cont.get_attribute("aria-disabled"), "continue is enabled with nothing touched")
                self.assertEqual(cont.get_attribute("href"), "team.html")
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                self.assertEqual(page.errors, [])

    def test_continuing_with_defaults_changes_no_value_and_stores_nothing(self):
        page = self.page(375)
        snap = "() => JSON.stringify(DDF.engine.players().map(p => [p.key, p.ddf]))"
        before = page.evaluate(snap)
        self.assertGreater(len(page.evaluate("() => DDF.engine.players()")), 100)
        page.evaluate("() => document.getElementById('editor').requestSubmit()")   # the same save continue runs
        self.assertEqual(page.evaluate("() => DDF.engine.settings().roster"), STANDARD_ROSTER)
        self.assertEqual(page.evaluate(snap), before, "default-roster values are unchanged by confirming the defaults")
        self.assertIsNone(page.evaluate("() => localStorage.getItem('ddf.v2.league-settings')"), "defaults are not stored as a choice")
        self.assertTrue(page.evaluate("() => DDF.engine.isStandardRoster()"))
        page.evaluate("() => DDF.engine.apply({roster: {BENCH: 3}})")   # control: a real size change does move values
        self.assertNotEqual(page.evaluate(snap), before)
        self.assertFalse(page.evaluate("() => DDF.engine.isStandardRoster()"))

    def test_results_note_only_for_the_standard_roster(self):
        page = self.page(375, "values.html")
        page.wait_for_function("() => DDF.link && DDF.link.table(1)", timeout=20000)
        mk = """(slots) => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 10, superflex: false, slots},
            teams: [{name: 'Link A', players: ['Josh Allen']}, {name: 'Link B', players: ['Jordan Love']}], me: 0, name: 'Chat League'})"""
        std = page.evaluate(mk, [1, 2, 2, 1, 1, 7])
        own = page.evaluate(mk, [1, 2, 3, 1, 1, 6])
        for token, shown in ((std, True), (own, False)):
            with self.subTest(shown=shown):
                page.goto(f"{self.base}/values.html", wait_until="networkidle", timeout=60000)   # a real load before each link
                page.goto(f"{self.base}/team.html#s={token}", wait_until="networkidle", timeout=60000)
                page.wait_for_function("() => DDF.link.current() && DDF.link.current().name === 'Chat League'", timeout=20000)
                page.wait_for_function("() => document.getElementById('your-team') && !document.getElementById('your-team').hidden", timeout=20000)
                note = page.locator("#std-roster-note")
                self.assertEqual(note.is_visible(), shown)
                if shown:
                    self.assertIn("Standard roster in use", note.inner_text())
                    self.assertIn(STANDARD_TEXT, note.inner_text())
                    self.assertEqual(note.locator("a").get_attribute("href"), "settings.html")
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)

    def test_a_link_league_still_fills_the_sizes(self):
        page = self.page(375)
        token = page.evaluate("""() => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 12,
            superflex: false, slots: [1, 2, 3, 1, 1, 6]}})""")
        page.goto(f"{self.base}/settings.html#s={token}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => document.getElementById('lineup-wr').value === '3'", timeout=20000)
        self.assertEqual(page.input_value("#lineup-bench"), "6")


del _Base  # only the classes defined here are collected below

if __name__ == "__main__":
    unittest.main()
