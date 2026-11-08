"""JEG-1572: a trade is not a Natural fit when the best available players already close most of the gap it fills.

From a friend's real-league test (2026-11-08): the page offered Josh Jacobs and Jacoby Brissett for Tyler Shough and
Bryce Young (two QBs) as a Natural fit, when a waiver QB could fill the hole without giving up a good RB.

What we guard (synthetic rows only; never real league data):
- Table-driven cases on hand-made rows (two QB slots, as the friend's workaround setting): DDF.find.waiverAlternative and
  searchPartner equal an independent recomputation here (tradeFit on my roster plus the best available players at the
  positions received). The friend's case with a good waiver QB is moved out of Natural fit and the Why panel names the
  waiver option in plain words; with only a weak waiver QB, or none, it stays a Natural fit.
- Drift: the checks fail when find-engine.js is served with the share threshold moved.
- find.html with the seeded league (synthetic: a snake draft of the frozen player table) at 1440x900 and 390x844: no
  Natural fit card is one the waiver rule demotes, a demoted card shows the waiver note and its Why panel leads with the
  waiver option (no "Natural fit" tag), the partner tag reads "Trade with <team>" on one line (a long team name with a
  comma is cut with an ellipsis and its full name in the title), 44px Why buttons, no overflow, no page errors.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_ddf_why import BANNED, _find_page, _launch, _league

SETUP = r"""(pool) => {
  // ddf, the three analyst charts [cbs, usatoday, fantasypros]; projections and live market = ddf
  const R = (key, name, pos, d, c, fc) => ({player_key: key, name, pos, team: 'X',
    values: {ddf_value: d, ddf_value_charts: d, ddf_value_projections: d, cbs: c[0], usatoday: c[1], fantasypros: c[2], fantasycalc: fc === undefined ? d : fc}});
  // My RBs are deep (Josh Jacobs is the RB3, on the bench behind a WR in FLEX) and my second QB slot is empty.
  const mine = [R('m1', 'Jacoby Brissett', 'QB', 6, [6, 6, 6]),
    R('m2', 'Josh Jacobs', 'RB', 30, [29, 30, 31], 45), R('m3', 'Rex First', 'RB', 40, [39, 40, 41]), R('m4', 'Ray Second', 'RB', 38, [37, 38, 39]),
    R('m5', 'Roy Fourth', 'RB', 22, [21, 22, 23]), R('m6', 'Rod Fifth', 'RB', 18, [17, 18, 19]), R('m7', 'Ron Sixth', 'RB', 12, [11, 12, 13]),
    R('m8', 'Will One', 'WR', 42, [41, 42, 43]), R('m9', 'Walt Two', 'WR', 40, [39, 40, 41]), R('m10', 'Wes Three', 'WR', 36, [35, 36, 37]),
    R('m11', 'Wyatt Four', 'WR', 14, [13, 14, 15]), R('m12', 'Ted End', 'TE', 12, [11, 12, 13])];
  const theirs = [R('t1', 'Quinn Starter', 'QB', 30, [29, 30, 31]), R('t2', 'Quade Second', 'QB', 26, [25, 26, 27]),
    R('t3', 'Tyler Shough', 'QB', 22, [21, 22, 23]), R('t4', 'Bryce Young', 'QB', 20, [19, 20, 21]),
    R('t5', 'Rudy Thin', 'RB', 10, [9, 10, 11]), R('t6', 'Rick Thin', 'RB', 8, [7, 8, 9]),
    R('t7', 'Wade One', 'WR', 32, [31, 32, 33]), R('t8', 'Wynn Two', 'WR', 28, [27, 28, 29]), R('t9', 'Wolf Three', 'WR', 22, [21, 22, 23]),
    R('t10', 'Wim Four', 'WR', 18, [17, 18, 19]), R('t11', 'Tom End', 'TE', 13, [12, 13, 14])];
  const free = {good: [R('w1', 'Gus Waiver', 'QB', 15, [14, 15, 16]), R('w2', 'Gil Waiver', 'QB', 13, [12, 13, 14])],
    weak: [R('w3', 'Lou Waiver', 'QB', 2, [2, 2, 2])], wr: [R('w4', 'Wil Waiver', 'WR', 9, [8, 9, 10])], none: []};
  const by = k => mine.concat(theirs, ...Object.values(free)).find(r => r.player_key === k);
  const expected = {QB: {lo: 2, hi: 3}, RB: {lo: 5, hi: 6}, WR: {lo: 4, hi: 5}, TE: {lo: 1, hi: 2}};
  const shape = {QB: 2, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 6};
  const ctx = Object.assign({}, DDF.find.context(), {shape, expected, weights: {overall: 0.15}, analyst: ['cbs', 'usatoday', 'fantasypros'],
    gate: ['cbs', 'usatoday', 'fantasypros', 'fantasycalc']});
  window.__wv = {mine, theirs, free, by, ctx};
  return true;
}"""

# Independent recomputation (finder module only) + the engine's answers for one trade and one available list.
RUN = r"""([give, receive, poolName]) => {
  const F = window.TradeValueFinder, {mine, theirs, free, by, ctx} = window.__wv;
  const w = rows => F.withChartAverage(rows, ctx.analyst);
  const M = w(mine), T = w(theirs), G = w(give.map(by)), Rv = w(receive.map(by));
  const fitCtx = {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: 'ddf_value', marketKey: 'chart_avg', chartKeys: ctx.analyst, z: F.FIT_Z};
  const fit = F.tradeFit({mine: {roster: M, leaving: G, arriving: Rv}, theirs: {roster: T, leaving: Rv, arriving: G}}, fitCtx);
  // the Waivers tab's own starter gain for each available player on my roster (one add; the drop only touches the bench)
  const pool = free[poolName].map(r => ({row: r, starterDelta: F.lineupValue(mine.concat([r]), ctx.shape, 'ddf_value').starterValue - F.lineupValue(mine, ctx.shape, 'ddf_value').starterValue}));
  const picks = [];
  ['QB', 'RB', 'WR', 'TE'].forEach(p => {
    const n = Rv.filter(r => r.pos === p).length;
    pool.filter(x => x.row.pos === p && x.starterDelta > 0).sort((a, b) => b.starterDelta - a.starterDelta).slice(0, n).forEach(x => picks.push(w([x.row])[0]));
  });
  let want = null;
  if (picks.length) {
    const f2 = F.tradeFit({mine: {roster: M.concat(picks), leaving: G, arriving: Rv}, theirs: {roster: T, leaving: Rv, arriving: G}}, fitCtx);
    const g = fit.us.starterDelta, a = f2.us.starterDelta, covered = g >= 0.05 ? Math.max(0, Math.min(1, (g - a) / g)) : null;
    want = {players: picks.map(r => r.name), covered: covered === null ? null : +covered.toFixed(6), gainAfter: +a.toFixed(6), ok: f2.natural.us.ok,
      demoted: covered !== null && (covered >= 0.5 || !f2.natural.us.ok)};
  }
  const got0 = DDF.find.waiverAlternative({give: G, receive: Rv, fit}, M, T, fitCtx, pool.map(x => ({row: w([x.row])[0], pos: x.row.pos, starterDelta: x.starterDelta})));
  const got = got0 && {players: got0.players.map(p => p.name), covered: got0.covered === null ? null : +got0.covered.toFixed(6), gainAfter: +got0.gainAfter.toFixed(6), ok: got0.ok, demoted: got0.demoted};
  // The full search for this partner, with and without the available players.
  const opts = {your: 'DDF', their: 'Market', sizes: [give.length === receive.length ? give.length : Math.max(give.length, receive.length)].concat(give.length !== receive.length ? [Math.min(give.length, receive.length)] : [])};
  const find = res => res.trades.find(t => t.give.map(r => r.player_key).sort().join() === give.slice().sort().join() && t.receive.map(r => r.player_key).sort().join() === receive.slice().sort().join());
  const withW = find(DDF.find.searchPartner(ctx, mine, theirs, Object.assign({waivers: pool}, opts)));
  const without = find(DDF.find.searchPartner(ctx, mine, theirs, opts));
  const tr = {mine, theirs, give: give.map(by), receive: receive.map(by), waiver: withW ? withW.waiver : null};
  const e = DDFWhy.explain(tr, ctx);
  return {label: fit.label, gain: fit.us.starterDelta, want, got, clsWith: withW ? withW.cls : null, clsWithout: without ? without.cls : null,
    whyNatural: e ? e.natural : null, kinds: e ? e.reasons.map(r => r.kind) : [], texts: e ? e.allReasons.map(r => r.text) : [],
    text: DDFWhy.text(tr, ctx), html: DDFWhy.html(tr, ctx, {})};
}"""

FRIEND = (["m2", "m1"], ["t3", "t4"])
# name: (give, receive, available list, expected class with the list, Why says the waiver option first)
CASES = {
    "friend: RB+QB for two QBs, good waiver QBs": FRIEND + ("good", "neutral", True),
    "friend trade, only a weak waiver QB": FRIEND + ("weak", "natural", False),
    "friend trade, no QB available (a WR only)": FRIEND + ("wr", "natural", False),
    "friend trade, no available players": FRIEND + ("none", "natural", False),
}
WAIVER_RE = re.compile(r"^The best available QBs, Gus Waiver and Gil Waiver, close (\d+)% of the gap this trade fills, without giving up "
                       r"Josh Jacobs and Jacoby Brissett\. With them added, this trade (still adds \+\d+\.\d to your starters|no longer makes your team better)\.$")


def case_errors(page) -> list[str]:
    errors = []
    for name, (give, receive, pool, cls, first) in CASES.items():
        page.evaluate(SETUP)
        r = page.evaluate(RUN, [give, receive, pool])
        if r["label"] != "natural" or r["clsWithout"] != "natural":
            errors.append(f"{name}: the trade must be a Natural fit before the waiver check (label {r['label']}, page class {r['clsWithout']})")
        if r["got"] != r["want"]:
            errors.append(f"{name}: engine {r['got']} vs recomputed {r['want']}")
        if r["clsWith"] != cls:
            errors.append(f"{name}: class {r['clsWith']}, expected {cls}")
        if r["whyNatural"] != (cls == "natural"):
            errors.append(f"{name}: Why natural={r['whyNatural']}")
        has = "waiver" in r["kinds"]
        if first and (r["kinds"][:1] != ["waiver"] or not any(WAIVER_RE.match(t) for t in r["texts"])):
            errors.append(f"{name}: Why does not lead with the waiver option: {r['kinds']} {r['texts'][:2]}")
        if first and "why-tag" in r["html"]:
            errors.append(f"{name}: demoted offer still tagged Natural fit")
        if not first and pool in ("wr", "none") and has:
            errors.append(f"{name}: a waiver line with no QB available: {r['texts']}")
        if pool == "weak" and not (r["want"] and r["want"]["covered"] < 0.5 and not r["want"]["demoted"]):
            errors.append(f"{name}: weak waiver QB should close under half the gap: {r['want']}")
        hits = [b for b in BANNED if re.search(b, r["text"])] + (["Waivers as partner"] if re.search(r"trade with waivers|waivers (would|could) trade", r["text"], re.I) else [])
        if hits:
            errors.append(f"{name}: banned words {hits}")
    return errors


class FindWaiverAlternativeTest(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists():
            raise _render_env.unavailable("dist/find.html is not built")
        self.sync_playwright = sync_playwright

    def _cases(self, overrides=None):
        with serve(DIST, overrides) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = _find_page(browser, base, 1440, 900, _league())
                return case_errors(page), errors
            finally:
                browser.close()

    def test_cases(self):
        found, errors = self._cases()
        self.assertEqual(found, [], "\n".join(found))
        self.assertEqual(errors, [])

    def test_guard_fails_on_drift(self):
        src = (DIST / "find-engine.js").read_text()
        needle = "var WAIVER_SHARE = 0.5;"
        self.assertIn(needle, src)
        found, _ = self._cases({"find-engine.js": src.replace(needle, "var WAIVER_SHARE = 0.99;").encode()})
        self.assertTrue(any("engine" in e or "class" in e for e in found), f"drift not caught: {found[:3]}")

    def test_find_cards(self):
        league = _league()
        long_name = "YoungLove, 1 in a McMillian (a long team name)"
        league["teams"][3]["name"] = long_name
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                for w, h in ((1440, 900), (390, 844)):
                    page, errors = _find_page(browser, base, w, h, league)
                    page.select_option("#partner", label=long_name)
                    page.wait_for_timeout(200)
                    page.select_option("#partner", "all")
                    page.wait_for_timeout(200)
                    cards = page.evaluate(r"""() => [...document.querySelectorAll('[data-offer]')].map(c => {
                      const tag = c.querySelector('[data-partner-tag]'), b = tag.getBoundingClientRect();
                      return {sec: c.closest('#natural-table') ? 'natural' : 'other', partner: c.dataset.partner, tag: tag.textContent, title: tag.title,
                        h: b.height, cut: tag.scrollWidth > tag.clientWidth, demoted: c.dataset.waiverDemoted || '', note: !!c.querySelector('[data-waiver-note]')};
                    })""")
                    self.assertTrue(cards, f"{w}: no offer cards")
                    for c in cards:
                        self.assertEqual(c["tag"], "Trade with " + c["partner"])
                        self.assertEqual(c["title"], "Trading partner: " + c["partner"])
                        self.assertLess(c["h"], 24, f"{w}: partner tag wraps: {c}")
                    self.assertTrue(any(c["partner"] == long_name for c in cards), f"{w}: no card for the long-named team")
                    if w == 390:
                        self.assertTrue(any(c["cut"] for c in cards if c["partner"] == long_name), f"{w}: long team name not cut")
                    self.assertEqual([c for c in cards if c["sec"] == "natural" and c["demoted"] == "1"], [])
                    demoted = [c for c in cards if c["demoted"] == "1"]
                    self.assertTrue(demoted, f"{w}: the seeded league has no offer the waiver rule moves (fixture drifted)")
                    self.assertTrue(all(c["note"] for c in demoted), f"{w}: a demoted card without the waiver note")
                    card = page.locator('[data-offer][data-waiver-demoted="1"]').first
                    note = card.locator("[data-waiver-note]").inner_text()
                    self.assertRegex(note, r"^The best available (QB|RB|WR|TE)s?, .+, closes? \d+% of the gap this trade fills, without giving up .+\.")
                    summary = card.locator("details[data-why] > summary")
                    box = summary.bounding_box()
                    self.assertGreaterEqual(round(box["height"], 1), 44, f"{w}: Why button {box['height']}px")
                    summary.click()
                    body = card.locator(".why-body")
                    body.wait_for(state="visible", timeout=5000)
                    self.assertEqual(body.get_attribute("data-natural"), "0")
                    self.assertEqual(body.locator(".why-tag").count(), 0)
                    self.assertEqual(body.locator(".why-reasons li").first.get_attribute("data-kind"), "waiver")
                    self.assertEqual(body.locator(".why-reasons li").first.inner_text(), note)
                    text = body.inner_text()
                    self.assertEqual([b for b in BANNED if re.search(b, text)], [])
                    overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                    self.assertFalse(overflow, f"{w}: horizontal overflow")
                    self.assertEqual(errors, [])
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
