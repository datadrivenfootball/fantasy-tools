"""JEG-1393 round 7 wording fixes (lane B). Text only; no number is computed differently.

- R7-OP-01: the caveats note says what each page does with a chart that does not list a player: DDF Value uses an
  estimate inside the rosterable depth and 0 past it; Team / Trading Partners count the Analyst charts and Live market
  at 0 (ddf-league.js chartRows); Trade & Waiver Recommendations reads the rows as they are, so the estimate counts.
- R7-OP-03: Learn defines "League allocation" and lists the allocations (counts and weights) on Build-up and Trace.
- R7-OP-04: the Buy / Sell (i) names both estimate paths.
- R7-CX-01: at 2 QB without superflex the QB weight is the projections-only mean, recomputed here from the page's own
  inputs; "the engine then rescales" is gone.
- R7-CX-03: with a FantasyCalc-only basis, Values' methodology and Buy / Sell notes and Build a Trade's subtitle name it.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve, chromium_executable

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FC_BASIS = {"v": 2, "basis": {"mode": "single", "source": "fantasycalc"}, "values": {}, "names": {}}
SNAP_READY = """() => { const s = window.DDFNumbers && DDFNumbers.snapshot();
  return !!s && document.getElementById('nx-loading').hidden && !!document.querySelector('#bu-worked-pick'); }"""


def setUpModule():
    _render_env.ensure_built()


class StaticWording(unittest.TestCase):
    def test_caveats_modes(self):
        src = (DIST / "caveats.js").read_text(encoding="utf-8")
        self.assertNotIn("Where a chart does not list a player, we estimate one.", src)
        self.assertIn("leave that estimate out and count that chart at 0", src)
        self.assertIn("use that estimate too", src)
        self.assertIn("from the other charts or from the chart’s own curve", src)
        self.assertIn('data-ddf-charts="estimate"', (DIST / "find.html").read_text(encoding="utf-8"))
        for page in ("team.html", "partners.html"):
            self.assertNotIn('data-ddf-charts="estimate"', (DIST / page).read_text(encoding="utf-8"), page)

    def test_glossary_league_allocation(self):
        html = (DIST / "learn.html").read_text(encoding="utf-8")
        self.assertIn('id="g-league-allocation"', html)
        self.assertNotIn("the league has a set number of starter", html)
        self.assertIn('href="#numbers/glossary/league-allocation">league allocations</a>', html)

    def test_buy_sell_info_names_both_paths(self):
        html = (DIST / "values.html").read_text(encoding="utf-8")
        self.assertIn("fills in for that chart (from the other charts or from the chart’s own curve)", html)
        self.assertNotIn("fills in for that chart from the other charts:", html)
        self.assertEqual(html.count('class="basis-now"'), 3)

    def test_learn_no_unexplained_rescale(self):
        self.assertNotIn("the engine then rescales", (DIST / "learn" / "numbers" / "numbers.js").read_text(encoding="utf-8"))


class RenderedWording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            if _render_env.required():
                raise
            raise unittest.SkipTest("playwright not installed")
        cls.sync_playwright = staticmethod(sync_playwright)

    def _ctx(self, p, stored=None, width=1280):
        browser = p.chromium.launch(executable_path=chromium_executable(p), args=_render_env.HERMETIC_ARGS)
        ctx = browser.new_context(viewport={"width": width, "height": 900})
        if stored:
            ctx.add_init_script("localStorage.setItem('ddf-v2-value-overrides', %s)" % json.dumps(json.dumps(stored)))
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # The hermetic browser blocks external hosts (fonts), which logs "Failed to load resource"; anything else counts.
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        return browser, page, errors

    def test_caveats_per_page(self):
        with serve() as base, self.sync_playwright() as p:
            browser, page, errors = self._ctx(p)
            got = {}
            for name in ("team.html", "partners.html", "find.html"):
                page.goto(base + "/" + name)
                page.wait_for_selector(".ddf-caveats li", state="attached", timeout=30000)
                got[name] = page.evaluate("() => [...document.querySelectorAll('.ddf-caveats li')].map(l => l.textContent).find(t => /^Estimated chart values/.test(t)) || ''")
            browser.close()
        for name in ("team.html", "partners.html"):
            self.assertIn("count that chart at 0", got[name], name)
        self.assertIn("use that estimate too", got["find.html"])
        for t in got.values():
            self.assertIn("past that depth the chart counts 0", t)

    def test_two_qb_weight_and_allocations(self):
        q = "?scoring=ppr&teams=12&roster=QB2.RB2.WR2.TE1.FLEX1.SF0.BN7"
        with serve() as base, self.sync_playwright() as p:
            browser, page, errors = self._ctx(p, width=390)
            page.goto(base + "/learn.html#numbers/build-up/cbs" + q)
            page.wait_for_function(SNAP_READY, timeout=90000)
            key = page.evaluate("() => { const o = [...document.querySelectorAll('#bu-worked-pick option')].find(o => /Josh Allen/.test(o.textContent)); return o && o.value; }")
            self.assertTrue(key, "Josh Allen missing from the CBS build-up")
            page.select_option("#bu-worked-pick", key)
            page.wait_for_timeout(400)
            rows = page.evaluate("() => [...document.querySelectorAll('#bu-worked tr')].map(t => t.innerText)")
            eng = page.evaluate("""() => { const vp = DDFNumbers.snapshot().inspection.valuePipeline;
              // JEG-1569: on the charts-only split (the default) the 2-QB QB weight is the included charts' mean;
              // the JEG-1366 projections rule is the old "all" split's.
              const fam = vp.ddfSplit === 'charts' ? 'chart' : 'projection';
              const proj = vp.included.filter(k => vp.sources[k].family === fam && !(vp.sources[k].positions.QB && vp.sources[k].positions.QB.method === 'no_players'));
              return {W: vp.ddfWeights['QB|starter'], shares: proj.map(k => vp.sources[k].weights['QB|starter']),
                mix: (vp.allocationMix || []).map(m => m.weight)}; }""")
            overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            browser.close()
        self.assertEqual(errors, [])
        self.assertLessEqual(overflow, 0)
        starter = next(r for r in rows if r.startswith("Starter rate"))
        self.assertNotIn("rescales", starter)
        # JEG-1569 decision 4 (2026-11-07): the 2-QB rule uses the charts only, so no projections clause.
        self.assertNotIn("come from the included projections only", starter)
        self.assertIn("included trade charts’ own QB starter shares", starter)
        mean = sum(eng["shares"]) / len(eng["shares"])
        self.assertAlmostEqual(mean, eng["W"], places=6)
        m = re.search(r"\) ÷ %d = ([\d.]+)%%" % len(eng["shares"]), starter)
        self.assertTrue(m, starter)
        self.assertAlmostEqual(float(m.group(1)), round(mean * 100, 2), places=6)
        alloc = next(r for r in rows if r.startswith("QB league allocations"))
        pcts = [float(x) for x in re.findall(r"rostered in ([\d.]+)%", alloc)]
        self.assertAlmostEqual(sum(pcts), 100.0, delta=0.15)
        self.assertIn(f"the {len(eng['mix'])} whole-seat league allocations", alloc)

    def test_basis_named(self):
        with serve() as base, self.sync_playwright() as p:
            browser, page, errors = self._ctx(p, stored=FC_BASIS)
            page.goto(base + "/values.html")
            page.wait_for_function("() => document.body.classList.contains('values-live')", timeout=90000)
            notes = page.evaluate("() => [...document.querySelectorAll('.basis-now')].map(e => e.textContent)")
            page.goto(base + "/build.html?give=Jahmyr+Gibbs&get=Josh+Allen")
            page.wait_for_selector(".tc-sub", timeout=90000)
            sub = page.inner_text(".tc-sub")
            browser.close()
        self.assertEqual(errors, [])
        self.assertEqual(len(notes), 3)
        for n in notes:
            self.assertIn("Your current basis is FantasyCalc only", n)
        self.assertIn("By default, DDF Value is the average of the four charts’ adjusted values", sub)
        self.assertIn("Your current basis is FantasyCalc only, so the DDF Value shown here is FantasyCalc’s adjusted value.", sub)


if __name__ == "__main__":
    unittest.main()
