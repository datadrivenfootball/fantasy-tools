"""Natural fit 2 on find.html (Jeremy, 2026-11-19): the offer card and its Why panel at 375px and 1440px.

What we guard, on the seeded league (tests.test_team_engine_parity.seeded_league) with every offer listed:
- Every card leads with trade value, then a starting-lineup block for you and for them: starters before, after and the
  change (equal to tradeFit's starterBefore / starterAfter, which find-engine's fit carries), and who moves in or out of a
  starting slot. The blocks sit inside the card (no horizontal overflow at 375px or on the page).
- A Natural card's label carries the public-charts count ("Natural fit · 3/4 public charts"), never under 2; no other
  class shows a count in its label.
- A bench-depth Natural offer is tagged "Bench depth" and its Why says bench depth, not a starter upgrade.
- Jeremy, 2026-11-21: no Natural card shows either side's starters falling; bench depth for them is tagged "Bench depth
  for them"; an offer whose partner's best-lineup starter total falls is not Natural and its Why verdict says so.
- A Natural offer whose gain is under 1% of their starters is tagged "Thin for them" and its Why says so.
- An offer that passes both sides but has only 1 of 4 public charts even or better for them is not Natural, and its Why
  verdict says why.
- The Why panel shows both lineups, "Why you should do this" and "Why they may see it as good", and its verdict is the
  card's own class (one test for the label and the panel).
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_ddf_why import _find_page, _launch, _league

LIST_ALL = r"""() => {
  const fit = document.getElementById('fit'); fit.value = 'all'; fit.dispatchEvent(new Event('change', {bubbles: true}));
  const b = document.querySelector('[data-page-size="200"]'); if (b) b.click();
  document.querySelectorAll('details.section').forEach(d => { d.open = true; });
  return true;
}"""

# Every listed card, read off the page, with the engine fit find-engine gave its selected offer.
READ = r"""() => {
  const shown = n => Math.abs(n) < 0.05 ? '0.0' : (n > 0 ? '+' : '−') + Math.abs(n).toFixed(1);
  const fits = new Map();
  DDF.findPage.visible().forEach(g => { const t = DDF.findPage.selected(g);
    fits.set(g.partner + '|' + t.give.map(r => String(r.player_key)).join(',') + '|' + t.receive.map(r => String(r.player_key)).join(','), t); });
  return [...document.querySelectorAll('[data-offer]')].map(a => {
    const t = fits.get(a.dataset.partner + '|' + a.dataset.give + '|' + a.dataset.receive), f = t && t.fit, n = f && f.natural;
    const side = who => { const el = a.querySelector('[data-lineup="' + who + '"]'); if (!el) return null;
      const r = el.getBoundingClientRect();
      return {before: el.dataset.before, after: el.dataset.after, d: el.querySelector('.lm-d').textContent.trim(), n: el.querySelector('.lm-n').textContent.replace(/\s+/g, ' ').trim(),
        mv: el.querySelector('.lm-mv').textContent.trim(), right: r.right}; };
    const box = a.getBoundingClientRect();
    return {cls: a.dataset.cls, give: a.dataset.give, receive: a.dataset.receive, partner: a.dataset.partner,
      label: a.querySelector('[data-fit-label]').textContent.replace(/\s+/g, ' ').trim(), tags: [...a.querySelectorAll('[data-fit-tag]')].map(x => x.textContent.trim()),
      tv: (a.querySelector('[data-trade-value]') || {}).textContent, you: side('you'), them: side('them'), cardRight: box.right,
      cardOverflow: a.scrollWidth > a.clientWidth + 1,
      fit: f ? {edge: shown(t.edge), agree: t.rivalOkCount, total: t.chartCount, usB: f.us.starterBefore.toFixed(1), usA: f.us.starterAfter.toFixed(1),
        thB: f.them.starterBefore.toFixed(1), thA: f.them.starterAfter.toFixed(1), usD: shown(f.us.starterAfter - f.us.starterBefore), thD: shown(f.them.starterAfter - f.them.starterBefore),
        usIn: f.us.startersIn.map(x => x.name), usOut: f.us.startersOut.map(x => x.name), bench: Boolean(n.benchDepth), benchThem: Boolean(n.benchDepthThem), thDrop: n.them.startersOk === false && n.them.value, thin: Boolean(n.thin),
        bothOk: n.us.ok && n.them.ok, chartsOk: n.charts.ok} : null};
  });
}"""

FIND_CARD = "const card = [...document.querySelectorAll('[data-offer]')].find(a => a.dataset.partner === c.partner && a.dataset.give === c.give && a.dataset.receive === c.receive);"
OPEN_WHY = "(c) => { " + FIND_CARD + " card.querySelector('details[data-why] > summary').click(); return true; }"
WHY = "(c) => { " + FIND_CARD + r"""
  const b = card.querySelector('.why-body'); if (!b) return null;
  const li = sel => [...b.querySelectorAll(sel + ' li')].map(x => x.textContent.trim());
  const box = b.getBoundingClientRect(), cb = card.getBoundingClientRect();
  return {cls: b.dataset.cls, verdict: b.querySelector('[data-verdict]').textContent.trim(), sides: [...b.querySelectorAll('.why-side')].map(x => x.textContent.trim()),
    you: li('[data-why-you]'), them: li('[data-why-them]'), lineups: b.querySelectorAll('.why-lu').length, rows: b.querySelectorAll('.why-lt tbody tr').length,
    tags: [...b.querySelectorAll('[data-tag]')].map(x => x.textContent.trim()), inside: box.right <= cb.right + 1 && box.left >= cb.left - 1};
}"""
HAS_WHY = "(c) => { " + FIND_CARD + " return Boolean(card && card.querySelector('.why-body')); }"


# Neither real league lists an offer whose partner's total rises while their best lineup gets weaker, so this one is built
# by hand (the shape of tests.test_v2_finder_fit check 28) and explained by the page's own DDFWhy: they give their best WR
# (27 on the charts) for two RBs worth 16 each; one takes FLEX, so their starters fall 11 while their total rises.
STARTERS_DROP = r"""() => {
  const R = (key, pos, d, c) => ({player_key: key, name: key, pos, team: 'X',
    values: {ddf_value: d, ddf_value_charts: d, ddf_value_projections: d, cbs: c, usatoday: c, fantasypros: c, fantasycalc: c}});
  const team = (p, qb, rb, wr, te) => [['QB', qb], ['RB', rb], ['WR', wr], ['TE', te]].flatMap(([pos, vs]) => vs.map((v, i) => R(p + pos + i, pos, v, v)));
  const give = [R('Mia Run', 'RB', 2, 16), R('Moe Run', 'RB', 2, 16)], recv = [R('Ty Wide', 'WR', 30, 27)];
  const mine = team('m', [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5]).concat(give);
  const theirs = team('t', [22, 11], [35, 28, 14], [26, 20, 12, 8, 7], [11, 6]).concat(recv);
  const ctx = Object.assign({}, DDF.find.context(), {shape: {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7},
    expected: {QB: {lo: 1, hi: 2}, RB: {lo: 3, hi: 4}, WR: {lo: 4, hi: 5}, TE: {lo: 1, hi: 2}}, weights: {overall: 1},
    analyst: ['cbs', 'usatoday', 'fantasypros'], gate: ['cbs', 'usatoday', 'fantasypros', 'fantasycalc']});
  const e = DDFWhy.explain({mine, theirs, give, receive: recv}, ctx);
  const box = document.createElement('div'); box.style.width = '343px'; box.className = 'why';
  box.innerHTML = DDFWhy.body({mine, theirs, give, receive: recv}, ctx, {}); document.body.appendChild(box);
  const out = {label: e.fit.label, themNet: e.fit.them.net, themStarters: e.fit.them.starterDelta, usOk: e.fit.natural.us.ok,
    verdict: box.querySelector('[data-verdict]').textContent, them: e.why.them, natural: e.natural, overflow: box.scrollWidth > box.clientWidth + 1};
  box.remove();
  return out;
}"""


# Bench depth as your only reason (tests.test_v2_finder_fit check 24): since 2026-11-21 it needs the players added to be
# worth 1% of your starters, and the real leagues may hold none, so it is built by hand too.
BENCH_CASE = r"""() => {
  const R = (key, pos, d, c) => ({player_key: key, name: key, pos, team: 'X',
    values: {ddf_value: d, ddf_value_charts: d, ddf_value_projections: d, cbs: c, usatoday: c, fantasypros: c, fantasycalc: c}});
  const team = (p, qb, rb, wr, te) => [['QB', qb], ['RB', rb], ['WR', wr], ['TE', te]].flatMap(([pos, vs]) => vs.map((v, i) => R(p + pos + i, pos, v, v)));
  const give = [R('Wes Spare', 'WR', 3, 25)], recv = [R('Rex Spare', 'RB', 9, 4)];
  const mine = team('m', [20, 12], [30, 25, 10, 8, 5], [30, 28, 15, 9, 7], [10, 5]).concat(give);
  const theirs = team('t', [22, 11], [35, 28, 14, 12, 9], [26, 20, 9, 8, 7], [11, 6]).concat(recv);
  const ctx = Object.assign({}, DDF.find.context(), {shape: {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7},
    expected: {QB: {lo: 1, hi: 2}, RB: {lo: 4, hi: 5}, WR: {lo: 4, hi: 5}, TE: {lo: 1, hi: 2}}, weights: {overall: 0.15},
    analyst: ['cbs', 'usatoday', 'fantasypros'], gate: ['cbs', 'usatoday', 'fantasypros', 'fantasycalc']});
  const e = DDFWhy.explain({mine, theirs, give, receive: recv}, ctx);
  return {cls: e.verdict.cls, tags: e.verdict.tags, you: e.why.you, label: e.fit.label, reason: e.fit.natural.us.reason};
}"""


class FindNaturalFit2RenderTest(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists():
            raise _render_env.unavailable("dist/find.html is not built")
        self.sync_playwright = sync_playwright

    def _why(self, page, card):
        page.evaluate(OPEN_WHY, card)
        page.wait_for_function(HAS_WHY, arg=card, timeout=10000)
        return page.evaluate(WHY, card)

    def check_cards(self, w, cards):
        judged = [c for c in cards if c["fit"]]
        self.assertGreater(len(judged), 20, f"{w}: too few judged cards")
        for c in judged:
            f, tag = c["fit"], f"{w} {c['partner']} {c['give']}->{c['receive']}"
            # Trade value first, then both lineups before and after, equal to tradeFit's totals.
            self.assertEqual(c["tv"], f["edge"], tag)
            self.assertEqual((c["you"]["before"], c["you"]["after"], c["you"]["d"]), (f["usB"], f["usA"], f["usD"]), tag)
            self.assertEqual((c["them"]["before"], c["them"]["after"], c["them"]["d"]), (f["thB"], f["thA"], f["thD"]), tag)
            self.assertTrue(c["you"]["n"].startswith(f["usB"]) and c["you"]["n"].endswith(f["usA"]), f"{tag}: {c['you']['n']!r}")
            if f["usIn"] or f["usOut"]:
                ins, _, outs = c["you"]["mv"].partition("Out:")
                for name in f["usIn"]:
                    self.assertIn(name, ins, tag)
                for name in f["usOut"]:
                    self.assertIn(name, outs, tag)
            else:
                self.assertEqual(c["you"]["mv"], "No lineup change.", tag)
            # Neat at 375: the blocks sit inside the card.
            self.assertFalse(c["cardOverflow"], f"{tag}: card overflows")
            for s in ("you", "them"):
                self.assertLessEqual(c[s]["right"], c["cardRight"] + 1, f"{tag}: {s} block overflows the card")
            # The label: a Natural card carries the count (2 or more), no other class does.
            if c["cls"] == "natural":
                m = re.match(r"Natural fit · (\d)/(\d) public charts", c["label"])
                self.assertIsNotNone(m, f"{tag}: label {c['label']!r}")
                self.assertEqual((int(m.group(1)), int(m.group(2))), (f["agree"], f["total"]), tag)
                self.assertGreaterEqual(f["agree"], 2, tag)
                self.assertEqual("Bench depth" in c["tags"], f["bench"], tag)
                self.assertEqual("Bench depth for them" in c["tags"], f["benchThem"], tag)
                # Jeremy, 2026-11-21: neither side's best-lineup starter total falls on a Natural card.
                self.assertNotEqual(c["you"]["d"][:1], "\u2212", tag)
                self.assertNotEqual(c["them"]["d"][:1], "\u2212", tag)
                self.assertEqual("Thin for them" in c["tags"], f["thin"], tag)
            else:
                self.assertNotIn("public charts", c["label"], tag)
                self.assertEqual(c["tags"], [], tag)
        return judged

    def check_whys(self, w, page, judged):
        bench = [c for c in judged if c["cls"] == "natural" and c["fit"]["bench"]]
        thin = [c for c in judged if c["cls"] == "natural" and c["fit"]["thin"]]
        one_of_4 = [c for c in judged if c["fit"]["bothOk"] and not c["fit"]["chartsOk"] and c["fit"]["agree"] == 1]
        plain = [c for c in judged if c["cls"] == "natural" and not c["tags"]]
        self.assertTrue(thin and one_of_4 and plain, f"{w}: fixture lacks a case: thin {len(thin)} 1/4 {len(one_of_4)} plain {len(plain)}")
        cases = {"thin": thin[0], "one_of_4": one_of_4[0], "plain": plain[0]}
        if bench:   # the seeded league may hold none since the 1% bench minimum (2026-11-21); BENCH_CASE covers it by hand
            cases["bench"] = bench[0]
        b = page.evaluate(BENCH_CASE)
        self.assertEqual((b["label"], b["cls"], b["reason"]), ("natural", "natural", "bench"), f"{w}: bench case {b}")
        self.assertIn("Bench depth", b["tags"])
        self.assertTrue(any(x.startswith("Bench depth, not a starter upgrade") and "at least 1% of your starters" in x for x in b["you"]), b["you"])
        for name, c in cases.items():
            why = self._why(page, c)
            self.assertIsNotNone(why, f"{w} {name}: no Why body")
            self.assertEqual(why["cls"], c["cls"], f"{w} {name}: panel class vs card")
            self.assertEqual(why["sides"], ["Why you should do this", "Why they may see it as good"])
            self.assertEqual(why["lineups"], 2)
            self.assertGreaterEqual(why["rows"], 14, f"{w} {name}: lineup rows")
            self.assertTrue(any(x.startswith("Your starters: ") for x in why["you"]), why["you"])
            self.assertTrue(any(x.startswith("Their starters: ") for x in why["them"]), why["them"])
            self.assertTrue(any(re.fullmatch(r"\d of \d public trade charts call it even or better for them\.", x) for x in why["them"]), why["them"])
            self.assertTrue(why["inside"], f"{w} {name}: the Why panel overflows the card")
            if name == "bench":
                self.assertIn("Bench depth", why["tags"])
                self.assertTrue(any(x.startswith("Bench depth, not a starter upgrade") for x in why["you"]), why["you"])
                self.assertTrue(any(x.startswith("Your starters: ") and "(0.0 " in x for x in why["you"]), why["you"])
            if name == "thin":
                self.assertIn("Thin for them", why["tags"])
                self.assertTrue(any(x.startswith("Thin for them: the gain is ") for x in why["them"]), why["them"])
            if name == "one_of_4":
                self.assertNotEqual(c["cls"], "natural")
                self.assertIn("Not a natural fit: only 1 of 4 public trade charts call it even or better for them", why["verdict"])
            else:
                self.assertTrue(why["verdict"].startswith("Natural fit ("), why["verdict"])

    def test_cards_and_why_at_375_and_desktop(self):
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                for w, h in ((375, 812), (1440, 900)):
                    with self.subTest(width=w):
                        page, errors = _find_page(browser, base, w, h, _league())
                        page.evaluate(LIST_ALL)
                        page.wait_for_timeout(300)
                        judged = self.check_cards(w, page.evaluate(READ))
                        self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"), f"{w}: page overflow")
                        self.check_whys(w, page, judged)
                        drop = page.evaluate(STARTERS_DROP)
                        self.assertTrue(drop["usOk"] and drop["themNet"] > 0.05 and drop["themStarters"] < -0.05, f"{w}: setup {drop}")
                        self.assertNotEqual(drop["label"], "natural")
                        self.assertFalse(drop["natural"])
                        self.assertIn("their starters drop", drop["verdict"])
                        self.assertTrue(any(x.startswith("Their best lineup gets weaker") for x in drop["them"]), drop["them"])
                        self.assertFalse(drop["overflow"], f"{w}: the Why body overflows 343px")
                        self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"), f"{w}: page overflow with Why open")
                        self.assertEqual(errors, [])
                        page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
