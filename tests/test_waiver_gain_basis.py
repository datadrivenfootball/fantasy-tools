"""JEG-1648: waiver pickups can be measured against your bench as well as your starters (Max Logan's beta request).

Decision (Jeremy, 2026-11-15): bench players are already discounted per the DDF scoring methodology, so Bench gain is the
Waivers evaluation's own benchDelta (the weighted bench change with the drop it suggests). No new discount, no value math.

What we guard:
- DDF.find.pickupsByBasis on a hand-made full roster (synthetic rows, the real TradeValueWaivers.evaluateAll): one free agent
  beats a bench player but no starter, one beats a starter, one helps nothing, plus a defense. Starter gain lists only the
  starter pickup (today's list), Bench gain only the bench-beating one, Both lists starter first then bench, each entry names
  its basis, the minimum applies to the basis's own number, K/DEF are never listed.
- Default unchanged: the starter list equals the filter and sort waivers.html and find.html used before the choice existed.
- waivers.html and find.html at 390 wide with the seeded league: the choice defaults to Starter gain, switching shows cards
  labelled with their basis, no sideways scroll, no page errors.
- Drift: the checks fail when find-engine.js is served with the bench branch removed.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_ddf_why import _launch
from tests.test_team_engine_parity import seed_script, seeded_league

LEAGUE_READY = "() => window.DDF && DDF.league && DDF.league.current && DDF.league.current() !== null"

SYNTH = r"""() => {
  const R = (key, name, pos, d) => ({player_key: key, name, pos, team: 'X',
    values: {ddf_value: d, ddf_value_charts: d, ddf_value_projections: d, cbs: d, usatoday: d, fantasypros: d, fantasycalc: d}});
  const mine = [R('q1', 'Quin Start', 'QB', 30), R('r1', 'Rex One', 'RB', 40), R('r2', 'Ray Two', 'RB', 38),
    R('w1', 'Will One', 'WR', 42), R('w2', 'Walt Two', 'WR', 40), R('t1', 'Ted One', 'TE', 12), R('w3', 'Wes Flex', 'WR', 36),
    R('b1', 'Ron Bench', 'RB', 18), R('b2', 'Roy Bench', 'RB', 12), R('b3', 'Wyatt Bench', 'WR', 14), R('b4', 'Bo Backup', 'QB', 6),
    R('b5', 'Tim Backup', 'TE', 4), R('b6', 'Will Backup', 'WR', 5), R('b7', 'Rob Backup', 'RB', 3)];
  const free = [R('f1', 'Depth Dan', 'RB', 16), R('f2', 'Quinn Better', 'QB', 45), R('f3', 'Nobody Nate', 'WR', 1)];
  const W = window.TradeValueWaivers, ctx = DDF.find.context();
  const shape = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7};
  const wctx = {shape, weights: ctx.weights, expected: ctx.expected, chartKeys: ctx.analyst, rosterSize: W.rosterSizeOf(shape),
    byes: null, status: W.statusFreshness(null, Date.now()), view: W.viewFor('ddf', null)};
  const out = W.evaluateAll(wctx, mine, free);
  const names = r => r.map(e => e.r.name + ':' + e.basis);
  const legacy = out.results.filter(r => r.starterDelta !== null && Math.round(r.starterDelta * 10) / 10 > 0)
    .sort((a, b) => b.starterDelta - a.starterDelta || (b.totalDelta || 0) - (a.totalDelta || 0) || String(a.name).localeCompare(String(b.name))).map(r => r.name);
  const P = (basis, min) => DDF.find.pickupsByBasis(out.results, basis, min);
  const dan = out.results.find(r => r.name === 'Depth Dan');
  const withDef = out.results.concat([{name: 'Some Defense', pos: 'DEF', starterDelta: null, benchDelta: null, totalDelta: null}]);
  return {starter: names(P('starter', 0).list), bench: names(P('bench', 0).list), both: names(P('both', 0).list),
    benchTotal: P('bench', 0).total, bothMin5: names(P('both', 5).list), bothMin5Total: P('both', 5).total,
    unknown: names(P('nonsense', 0).list), legacy, dan: dan && {s: dan.starterDelta, b: dan.benchDelta, drop: dan.drop && dan.drop.name},
    withDef: names(DDF.find.pickupsByBasis(withDef, 'both', 0).list), bases: DDF.find.BASES};
}"""

SEEDED_DEFAULT = r"""(kind) => {
  const o = kind === 'waivers' ? DDF.waiversPage.last() : null;
  if (!o) return null;
  const legacy = o.results.filter(r => r.starterDelta !== null && Math.round(r.starterDelta * 10) / 10 > 0)
    .sort((a, b) => b.starterDelta - a.starterDelta || (b.totalDelta || 0) - (a.totalDelta || 0) || String(a.name).localeCompare(String(b.name))).map(r => r.name);
  return {legacy, now: DDF.find.pickupsByBasis(o.results, 'starter', 0).list.map(e => e.r.name)};
}"""

CARDS = "() => [...document.querySelectorAll('%s')].map(c => [c.dataset.basis, c.dataset.pickupGain, (c.querySelector('%s') || {}).textContent])"
OVERFLOW = "() => document.documentElement.scrollWidth > innerWidth + 1"


def _league() -> dict:
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:4]
    return lg


def synth_errors(page) -> list[str]:
    errors = []
    r = page.evaluate(SYNTH)
    if r["starter"] != ["Quinn Better:starter"]:
        errors.append(f"Starter gain should list only the starter pickup: {r['starter']}")
    if r["starter"] != [f"{n}:starter" for n in r["legacy"]]:
        errors.append(f"Starter gain differs from the list before the choice existed: {r['starter']} vs {r['legacy']}")
    if r["bench"] != ["Depth Dan:bench"]:
        errors.append(f"Bench gain should list the free agent who beats a bench player and no starter: {r['bench']} ({r['dan']})")
    if r["both"] != ["Quinn Better:starter", "Depth Dan:bench"]:
        errors.append(f"Both should list starter then bench pickups: {r['both']}")
    if not r["dan"] or not (r["dan"]["s"] is not None and round(r["dan"]["s"] * 10) / 10 <= 0 and r["dan"]["b"] > 0 and r["dan"]["drop"]):
        errors.append(f"Depth Dan should beat a bench player (the drop) with no starter gain: {r['dan']}")
    if r["bothMin5"] != ["Quinn Better:starter"] or r["bothMin5Total"] != 2:
        errors.append(f"the minimum applies to each basis's own number: {r['bothMin5']} total {r['bothMin5Total']}")
    if r["unknown"] != r["starter"]:
        errors.append(f"an unknown basis must fall back to Starter gain: {r['unknown']}")
    if r["withDef"] != r["both"]:
        errors.append(f"a K/DEF row with no values must never be listed: {r['withDef']}")
    if r["bases"] != {"starter": "Starter gain", "bench": "Bench gain", "both": "Both"}:
        errors.append(f"basis labels: {r['bases']}")
    return errors


class WaiverGainBasisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        _render_env.ensure_built()
        if not (DIST / "waivers.html").exists():
            raise _render_env.unavailable("dist/waivers.html is not built")
        cls.sync_playwright = staticmethod(sync_playwright)

    def _page(self, browser, base, url, width=390):
        page = browser.new_page(viewport={"width": width, "height": 844})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith(base), lambda r: r.abort())
        page.add_init_script(seed_script(_league()))
        page.goto(f"{base}/{url}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function(LEAGUE_READY, timeout=120000)
        page.wait_for_function("() => window.DDF && DDF.find && DDF.find.pickupsByBasis && window.TradeValueWaivers", timeout=120000)
        return page, errors

    def test_bases_on_a_roster_where_a_free_agent_beats_only_the_bench(self):
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = self._page(browser, base, "waivers.html")
                found = synth_errors(page)
                self.assertEqual(found, [], "\n".join(found))
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_default_list_unchanged_and_page_labels(self):
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = self._page(browser, base, "waivers.html")
                page.wait_for_function("() => DDF.waiversPage.last()", timeout=120000)
                d = page.evaluate(SEEDED_DEFAULT, "waivers")
                self.assertEqual(d["now"], d["legacy"])
                self.assertEqual(page.input_value("#adds-basis"), "starter")
                page.select_option("#adds-min", "0")
                seen = {}
                for v in ("starter", "bench", "both"):
                    page.select_option("#adds-basis", v)
                    cards = page.evaluate(CARDS % ("#adds [data-pickup]", ".wa-basis"))
                    seen[v] = cards
                    self.assertTrue(cards, f"{v}: no cards on the seeded league")
                    for basis, gain, label in cards:
                        self.assertEqual(label, {"starter": "Starter gain", "bench": "Bench gain"}[basis], v)
                        self.assertGreater(float(gain), 0)
                    self.assertFalse(page.evaluate(OVERFLOW), f"{v}: page scrolls sideways at 390")
                self.assertTrue(all(c[0] == "starter" for c in seen["starter"]))
                self.assertTrue(all(c[0] == "bench" for c in seen["bench"]))
                self.assertEqual(seen["both"], seen["starter"] + seen["bench"])
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_find_page_choice_at_phone_width(self):
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = self._page(browser, base, "find.html")
                self.assertEqual(page.input_value("#pickup-basis"), "starter")
                page.select_option("#minimum-gain", "0")
                page.wait_for_selector("#pickup-cards [data-pickup]", timeout=120000)   # no cards is a failure, not a pass
                counts = {}
                for v in ("bench", "both", "starter"):
                    page.select_option("#pickup-basis", v)
                    cards = page.evaluate(CARDS % ("#pickup-cards [data-pickup]", "[data-basis-tag]"))
                    counts[v] = len(cards)
                    if v != "bench":
                        self.assertTrue(cards, f"{v}: find.html rendered no pickup cards on the seeded league")
                    for basis, _gain, label in cards:
                        self.assertEqual(label, {"starter": "Starter gain", "bench": "Bench gain"}[basis], v)
                        if v != "both":
                            self.assertEqual(basis, v)
                    self.assertFalse(page.evaluate(OVERFLOW), f"{v}: find.html scrolls sideways at 390")
                self.assertGreaterEqual(counts["both"], counts["starter"])
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_guard_fails_on_drift(self):
        src = (DIST / "find-engine.js").read_text()
        needle = 'basis === "bench" ? [bench]'
        self.assertIn(needle, src)
        with serve(DIST, {"find-engine.js": src.replace(needle, 'basis === "bench" ? [starter]').encode()}) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, _ = self._page(browser, base, "waivers.html")
                self.assertTrue(any("Bench gain" in e for e in synth_errors(page)), "drift in the bench basis was not caught")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
