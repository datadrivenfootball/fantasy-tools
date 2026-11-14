"""JEG-1633: "Evaluate pickup" on Waivers and on Trade & Waiver Recommendations opens Build a Trade with the league and
the pickup carried across.

Jeremy's report (2026-11-13, live site, phone): with a loaded league, tapping "Evaluate pickup" on a Best add card opened
Build a Trade in Add from waivers + My league showing "No rosters entered yet" and the "Add your roster" lock card.

Two causes, both guarded here (synthetic league: a snake draft of the frozen player table, my team missing three
players so the best adds are real):
- Confirming League settings on a pasted league stores a link state with settings and no teams (site.js
  confirmSettings, ddf:link source 'manual'). build-trade.js readLeague took that teamless state as the league, while
  ddf-league.js (Waivers, Recommendations) skips it. Variant "settings" seeds that state.
- Build a Trade's available players came only from its own list, a chat link's list or the old v2 list, never the list
  Waivers and Recommendations judge pickups on (the names entered on Waivers, else the league's available players), so
  the add was dropped and the empty state showed. Variants "plain" and "entered".

Each path clicks the first card's "Evaluate pickup" at 1440x900 and 375x812 and checks Build a Trade: the waiver board
is shown (no lock card, no empty state), the card's add is the picked add, the card's drop (or a direct link's drop) is
the chosen drop, the claim note names both, Back returns to the page, and no page errors.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_ddf_why import _launch
from tests.test_team_engine_parity import ROOT, seed_script, seeded_league

LEAGUE_READY = "() => window.DDF && DDF.league && DDF.league.current && DDF.league.current() !== null"
# League settings confirmed on settings.html with no chat link: the state site.js confirmSettings writes.
SETTINGS_STATE = ("(function(){ try { if (sessionStorage.getItem('t-set')) return; sessionStorage.setItem('t-set','1');"
                  " sessionStorage.setItem('ddf:league', JSON.stringify({v:1, settings:{scoring:'standard', teams:12, superflex:false, slots:[1,2,3,1,1,6]}}));"
                  " sessionStorage.setItem('ddf:link', JSON.stringify({source:'manual', at:Date.now()})); } catch(_){} })()")
BUILD_READY = ("() => document.body.classList.contains('kind-waivers') && (document.querySelector('#wv-roster input') !== null"
               " || [...document.querySelectorAll('.lock-card[data-kind=\"waivers\"]')].some(el => el.offsetParent))")
READ_BUILD = r"""() => {
  const q = id => document.getElementById(id), shown = el => !!(el && !el.hidden && el.offsetParent);
  const picked = document.querySelector('#wv-adds [aria-pressed="true"]');
  const drop = document.querySelector('#wv-roster input:checked');
  const lock = [...document.querySelectorAll('.lock-card[data-kind="waivers"]')].some(shown);
  return {board: shown(q('waivers-ui')), lock, empty: shown(q('wv-empty')), count: q('wv-count').textContent,
    picked: picked ? picked.dataset.pick : null, drop: drop ? drop.value : null, claim: q('claim').value,
    note: q('roster-note').textContent, overflow: document.documentElement.scrollWidth > innerWidth + 1};
}"""


def _league() -> dict:
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:4]
    return lg


def _free_names(league: dict, n: int) -> list[dict]:
    rostered = {p["name"] for t in league["teams"] for p in t["players"]}
    rows = [r.split("|") for r in json.loads((ROOT / "app/next/players-table-1.json").read_text())]
    return [{"n": r[0], "pos": r[1]} for r in rows if len(r) > 3 and r[1] in ("QB", "RB", "WR", "TE") and r[0] not in rostered][:n]


class BuildWaiverHandoffTest(unittest.TestCase):
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

    def _open(self, browser, base, url, variant, size):
        league = _league()
        page = browser.new_page(viewport=size)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith(base), lambda r: r.abort())
        page.add_init_script(seed_script(league))
        if variant == "settings":
            page.add_init_script(SETTINGS_STATE)
        if variant == "entered":
            names = json.dumps(json.dumps({"source": "list", "players": _free_names(league, 12)}))
            page.add_init_script(f"(function(){{ try {{ if (!sessionStorage.getItem('ddf:available')) sessionStorage.setItem('ddf:available', {names}); }} catch(_){{}} }})()")
        page.goto(f"{base}/{url}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function(LEAGUE_READY, timeout=120000)
        return page, errors

    def _check_build(self, page, label, add, drop):
        page.wait_for_function(BUILD_READY, timeout=60000)
        page.wait_for_timeout(500)
        got = page.evaluate(READ_BUILD)
        self.assertTrue(got["board"], f"{label}: waiver board hidden: {got}")
        self.assertFalse(got["lock"], f"{label}: lock card shown ('Add your roster...'): {got}")
        self.assertFalse(got["empty"], f"{label}: 'No available players yet' shown: {got}")
        self.assertNotIn("No rosters entered yet", got["note"], label)
        self.assertEqual(got["picked"], add, f"{label}: picked add {got}")
        if drop:
            self.assertEqual(got["drop"], drop, f"{label}: chosen drop {got}")
        self.assertFalse(got["overflow"], f"{label}: page scrolls sideways")
        return got

    def _card_flow(self, browser, base, source, variant, size):
        page, errors = self._open(browser, base, source, variant, size)
        try:
            cards = "#adds [data-pickup]" if source == "waivers.html" else "#pickup-cards [data-pickup]"
            page.wait_for_selector(cards + " a.button", timeout=120000)
            card = page.eval_on_selector(cards, "c => ({add: c.dataset.add, drop: c.dataset.drop})")
            label = f"{source} {variant} {size['width']}px"
            page.click(cards + " a.button")
            got = self._check_build(page, label, card["add"], card["drop"] or None)
            if variant == "entered":
                self.assertIn("entered", got["count"], label)
            else:
                self.assertIn("in your league", got["count"], label)
            page.go_back()
            page.wait_for_function(LEAGUE_READY, timeout=60000)
            self.assertTrue(page.url.endswith("/" + source), f"{label}: Back went to {page.url}")
            self.assertEqual(errors, [], label)
        finally:
            page.close()

    def test_evaluate_pickup_from_waivers_and_recommendations(self):
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                desktop, phone = {"width": 1440, "height": 900}, {"width": 375, "height": 812}
                for source, variant, size in [("waivers.html", "settings", phone), ("waivers.html", "plain", desktop),
                                              ("waivers.html", "entered", phone), ("find.html", "settings", desktop)]:
                    with self.subTest(source=source, variant=variant, width=size["width"]):
                        self._card_flow(browser, base, source, variant, size)
            finally:
                browser.close()

    def test_direct_link_carries_the_drop(self):
        # Jeremy's card named a drop (add Kyle Monangai, drop Darren Waller): the link's drop is the chosen one.
        league = _league()
        mine = [p["name"] for p in league["teams"][league["me"]]["players"] if p["pos"] in ("QB", "RB", "WR", "TE")]
        add = _free_names(league, 1)[0]["n"]
        from urllib.parse import quote
        url = f"build.html?mode=league&waivers=1&drop={quote(mine[-1])}&add={quote(add)}"
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = self._open(browser, base, url, "settings", {"width": 375, "height": 812})
                page.wait_for_function(BUILD_READY, timeout=60000)
                keys = page.evaluate("([d, a]) => { const C = window.TradeValueCurveControls, rows = C.getAllRows();"
                                     " const k = n => { const r = rows.find(r => r.name === n); return r ? String(r.player_key) : null; }; return [k(d), k(a)]; }",
                                     [mine[-1], add])
                got = self._check_build(page, "direct link", keys[1], keys[0])
                self.assertIn(add, got["claim"])
                self.assertIn(mine[-1], got["claim"])
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
