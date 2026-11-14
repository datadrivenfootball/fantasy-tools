"""JEG-1635: Build a Trade > Add from waivers > Any players works with no league.

Jeremy (2026-11-13, phone): with no league loaded the screen showed only "Adding from waivers uses your roster and the
available players in your league" and "Switch to My league". It now takes your roster and the available players by
paste or typing, and evaluates with the current league settings. My league mode is unchanged.

Guarded here (synthetic players from the frozen player table, never real league data):
- No league, 375x812 and 1440x900: the waiver board shows (no lock card), the roster entry is open, entering a roster
  and available players lists ranked adds, picking one shows the charts and the claim note, Confirm roster move swaps
  the two players (and Undo restores them), the roster is kept for the tab, no sideways scroll, no page errors.
- Agreement with My league (JEG-1633): the same roster, drop and add give the same gain in Any players (typed roster)
  as in My league (pasted league), and a pickup link (?waivers=1&drop=&add=) opened with no league lands prefilled.
"""
from __future__ import annotations

import json
import unittest
from urllib.parse import quote

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_ddf_why import _launch
from tests.test_team_engine_parity import ROOT, seed_script, seeded_league

PHONE, DESKTOP = {"width": 375, "height": 812}, {"width": 1440, "height": 900}
BOARD_READY = ("() => document.body.classList.contains('kind-waivers') && window.DDFBuild"
               " && !document.getElementById('waivers-ui').hidden")
READ = r"""() => {
  const q = id => document.getElementById(id), shown = el => !!(el && !el.hidden && el.offsetParent);
  const picked = document.querySelector('#wv-adds [aria-pressed="true"]'), drop = document.querySelector('#wv-roster input:checked');
  return {board: shown(q('waivers-ui')), lock: [...document.querySelectorAll('.lock-card[data-kind="waivers"]')].some(shown),
    entryOpen: q('wv-roster-entry').open, entryShown: shown(q('wv-roster-entry')), mode: DDFBuild.state().mode,
    roster: [...document.querySelectorAll('#wv-roster input')].map(i => i.value), drop: drop ? drop.value : null,
    adds: [...document.querySelectorAll('#wv-adds [data-pick]')].map(b => b.dataset.pick), picked: picked ? picked.dataset.pick : null,
    gain: picked ? +picked.closest('li').querySelector('[data-gain]').dataset.gain * (picked.closest('li').querySelector('.wv-gain').textContent.trim().startsWith('−') ? -1 : 1) : null,
    result: shown(q('result')), claim: q('claim').value, lede: q('lede').textContent,
    stored: JSON.parse(sessionStorage.getItem('ddf:anyroster') || 'null'), overflow: document.documentElement.scrollWidth > innerWidth + 1};
}"""
KEYS = "(names) => { const rows = TradeValueCurveControls.getAllRows(); return names.map(n => { const r = rows.find(r => r.name === n); return r ? String(r.player_key) : null; }); }"


def _table():
    return [r.split("|") for r in json.loads((ROOT / "app/next/players-table-1.json").read_text())]


def _roster_and_free():
    """My roster: the seeded league's team minus its top three; available: the best players on no seeded roster."""
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:4]
    mine = [p["name"] for p in lg["teams"][lg["me"]]["players"] if p["pos"] in ("QB", "RB", "WR", "TE")]
    rostered = {p["name"] for t in lg["teams"] for p in t["players"]}
    free = [r[0] for r in _table() if len(r) > 3 and r[1] in ("QB", "RB", "WR", "TE") and r[0] not in rostered][:10]
    return lg, mine, free


class BuildAnyWaiversTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        _render_env.ensure_built()
        if not (DIST / "build.html").exists():
            raise _render_env.unavailable("dist/build.html is not built")
        cls.sync_playwright = staticmethod(sync_playwright)

    def _page(self, browser, base, url, size, league=None):
        page = browser.new_page(viewport=size)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith(base), lambda r: r.abort())
        page.add_init_script(seed_script(league))
        page.goto(f"{base}/{url}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function(BOARD_READY, timeout=120000)
        page.wait_for_timeout(300)
        return page, errors

    def _enter(self, page, mine, free):
        page.fill("#wv-roster-paste", "\n".join(mine))
        page.click("#wv-roster-add")
        page.click("#wv-open-entry")
        page.fill("#wv-paste", "\n".join(free))
        page.click("#wv-paste-add")
        page.wait_for_timeout(300)

    def test_no_league_entry_flow(self):
        _, mine, free = _roster_and_free()
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                for size in (PHONE, DESKTOP):
                    label = f"{size['width']}px"
                    with self.subTest(width=size["width"]):
                        page, errors = self._page(browser, base, "build.html?waivers=1", size)
                        got = page.evaluate(READ)
                        self.assertEqual(got["mode"], "any", label)
                        self.assertTrue(got["board"] and not got["lock"], f"{label}: board hidden or lock card shown: {got}")
                        self.assertTrue(got["entryShown"] and got["entryOpen"], f"{label}: roster entry not open: {got}")
                        self.assertEqual(got["roster"], [], label)
                        self._enter(page, mine, free)
                        keys_mine, keys_free = page.evaluate(KEYS, mine), page.evaluate(KEYS, free)
                        got = page.evaluate(READ)
                        self.assertEqual(sorted(got["roster"]), sorted(keys_mine), f"{label}: roster")
                        self.assertEqual(got["stored"]["keys"], keys_mine, f"{label}: stored roster")
                        self.assertFalse(got["entryOpen"], f"{label}: entry stays open after a roster is entered")
                        self.assertIn(got["drop"], keys_mine, label)
                        self.assertTrue(set(got["adds"]) <= set(keys_free) and got["adds"], f"{label}: adds {got['adds']}")
                        first = got["adds"][0]
                        page.click(f'#wv-adds [data-pick="{first}"]')
                        got = page.evaluate(READ)
                        self.assertEqual(got["picked"], first, label)
                        self.assertTrue(got["result"], f"{label}: result hidden")
                        add_name, drop_name = free[keys_free.index(first)], mine[keys_mine.index(got["drop"])]
                        self.assertIn(add_name, got["claim"]); self.assertIn(drop_name, got["claim"])
                        drop = got["drop"]
                        page.click("#wv-confirm")
                        got = page.evaluate(READ)
                        self.assertIn(first, got["roster"], label); self.assertNotIn(drop, got["roster"], label)
                        self.assertIn(first, got["stored"]["keys"], label)
                        page.click("#wv-undo")
                        got = page.evaluate(READ)
                        self.assertIn(drop, got["roster"], label); self.assertNotIn(first, got["roster"], label)
                        page.reload(wait_until="domcontentloaded")
                        page.wait_for_function(BOARD_READY, timeout=120000)
                        self.assertEqual(sorted(page.evaluate(READ)["roster"]), sorted(keys_mine), f"{label}: roster not kept on reload")
                        self.assertFalse(page.evaluate(READ)["overflow"], f"{label}: page scrolls sideways")
                        self.assertEqual(errors, [], label)
                        page.close()
            finally:
                browser.close()

    def test_any_players_agrees_with_my_league(self):
        lg, mine, free = _roster_and_free()
        drop, add = mine[-1], free[0]
        link = f"build.html?waivers=1&drop={quote(drop)}&add={quote(add)}"
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = self._page(browser, base, link + "&mode=league", PHONE, lg)
                league = page.evaluate(READ)
                self.assertEqual(league["mode"], "league")
                page.close()
                # No league: the pickup link lands prefilled in Any players; then type the same roster.
                page, errors2 = self._page(browser, base, link, PHONE)
                keys = page.evaluate(KEYS, [drop, add])
                got = page.evaluate(READ)
                self.assertEqual(got["mode"], "any")
                self.assertEqual((got["drop"], got["picked"]), tuple(keys), f"pickup link not prefilled: {got}")
                self.assertFalse(got["entryOpen"])   # the prefilled drop is a roster
                page.click("#wv-roster-summary")
                page.fill("#wv-roster-paste", "\n".join(mine))
                page.click("#wv-roster-add")
                if page.evaluate(READ)["drop"] != keys[0]:
                    page.click(f'#wv-roster input[value="{keys[0]}"]')
                if page.evaluate(READ)["picked"] != keys[1]:
                    page.click(f'#wv-adds [data-pick="{keys[1]}"]')
                got = page.evaluate(READ)
                self.assertEqual((league["drop"], league["picked"]), tuple(keys))
                self.assertIsNotNone(league["gain"])
                self.assertEqual(got["gain"], league["gain"], f"Any players gain {got['gain']} vs My league {league['gain']}")
                self.assertEqual(errors + errors2, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
