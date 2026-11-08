"""JEG-1536: Learn > How we get our numbers shows the engine's own numbers.

The Learn page (dist/learn.html, built by pipelines/build_root_pages.py with the live engine
injected) renders the Value pie, Health check, Source build-up and Trace from the engine that runs
hidden on the page. This test reads the engine directly (TradeValueCurveControls.getAllRows /
getInspection / getPublishedMath, never the page's own model) and requires every number the page
shows to equal it, at 3 scorings x 10/12 teams x superflex on/off (plan step 2 parity gate):

  * every player in the picker: his DDF Value (the 4-chart mean, ddfByVersion.blended) and no
    player the engine does not price, none missing;
  * Trace for the top three players: DDF Value, and per chart published / index factor / indexed /
    adjusted;
  * Value pie: the donut total and each chart's adjusted value;
  * Source build-up (CBS Sports and FantasyCalc, first page): published, indexed, adjusted and
    DDF Value per row, in the chart's own order;
  * Health check: each source's adjusted total;
  * the settings the page says it shows are the engine's.

Discrimination (test_guard_catches_a_wrong_number): the same comparison must fail when the page's
reader is served with DDF Value nudged by 0.2.

Also here: the Manifesto renders word for word from docs/manifesto-mirror.md (the Doc mirror the
live tab is held to, MF-01), one visible h1 per view, the methodology draft and the week-9
snapshot files are not published (decisions D6 and D8, 2026-11-06).
"""
from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve, chromium_executable

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MIRROR = ROOT / "docs" / "manifesto-mirror.md"
CHARTS = ("cbs", "usatoday", "fantasypros", "fantasycalc")
COMBOS = [(scoring, teams, sf) for scoring in ("standard", "half_ppr", "ppr") for teams in (10, 12) for sf in (0, 1)]
ROSTER = "QB1.RB2.WR2.TE1.FLEX1.SF{sf}.BN7"
SNAP_READY = """(want) => { const s = window.DDFNumbers && DDFNumbers.snapshot();
  return !!s && s.settings.scoring === want.scoring && s.settings.teams === want.teams && s.settings.superflex === want.sf
    && document.getElementById('nx-loading').hidden; }"""


def setUpModule():
    _render_env.ensure_built()


def f1(v):
    if v is None:
        return "—"
    text = f"{v:.1f}"
    if text in ("-0.0",):
        text = "0.0"
    return text.replace("-", "−")


def fpub(src, v):
    if v is None:
        return "—"
    return f"{round(v):,}" if src == "fantasycalc" else f1(v)


def ffactor(v):
    """The page's String(Number(v.toPrecision(6)))."""
    if v is None:
        return "—"
    text = str(float(f"{v:.6g}"))
    return text[:-2] if text.endswith(".0") else text


# The engine, read straight from TradeValueCurveControls (not from the page's model).
ENGINE = """() => {
  const C = window.TradeValueCurveControls, ins = C.getInspection(), st = C.getState(), shape = C.getRosterShape();
  const rows = {};
  C.getAllRows().forEach(r => {
    const b = r.ddfByVersion && r.ddfByVersion.blended;
    if (!b || typeof b.value !== 'number' || !isFinite(b.value)) return;
    const k = String(r.player_key), ir = ins.rows[k] || {};
    const src = {};
    ['cbs','usatoday','fantasypros','fantasycalc'].forEach(s => {
      const p = ins.players[s] && ins.players[s][k];
      const num = v => (typeof v === 'number' && isFinite(v) ? v : null);
      src[s] = {published: p ? num(p.native) : null, indexed: num(ir.indexed && ir.indexed[s]), adjusted: num(ir.adjusted && ir.adjusted[s])};
    });
    rows[k] = {name: r.name, ddf: b.value, src};
  });
  const factor = {};
  const anyKey = Object.keys(rows)[0];
  ['cbs','usatoday','fantasypros','fantasycalc'].forEach(s => {
    const pm = C.getPublishedMath(Number(anyKey), s); factor[s] = pm ? pm.factor : null; });
  const order = {};
  ['cbs','fantasycalc'].forEach(s => {
    const ps = ins.players[s] || {};
    order[s] = Object.keys(ps).sort((a, b) => (ps[b].native - ps[a].native) || (Number(a) - Number(b)))
      .map(k => ({k, published: ps[k].native, indexed: ins.rows[k] && ins.rows[k].indexed ? ins.rows[k].indexed[s] : null,
        adjusted: ins.rows[k] && ins.rows[k].adjusted ? ins.rows[k].adjusted[s] : null}));
  });
  const totals = {};
  Object.keys(ins.players).forEach(s => {
    if (!ins.valuePipeline.sources[s]) return;
    /* JEG-1393 (R1-CX-03): the total is every priced player's adjusted value; the waiver-role remainder is its own column. */
    const ps = Object.values(ins.players[s]).filter(p => ['QB','RB','WR','TE'].includes(p.pos));
    totals[s] = {all: ps.reduce((t, p) => t + (p.adjusted || 0), 0),
      waiver: ps.reduce((t, p) => t + (p.role !== 'starter' && p.role !== 'bench' ? (p.adjusted || 0) : 0), 0)};
  });
  return {scoring: st.scoring, teams: st.teams, sf: shape.SUPERFLEX || 0, rows, factor, order, totals};
}"""

PAGE_PICKER = """() => [...document.querySelectorAll('#nx-players option')].map(o => ({k: o.dataset.key, name: o.value, label: o.label || o.textContent}))"""
PAGE_TRACE = """() => ({big: document.getElementById('tr-big').textContent.trim(),
  rows: Object.fromEntries([...document.querySelectorAll('#tr-pub tbody tr')].map(tr => [tr.dataset.src, [...tr.querySelectorAll('td')].map(td => td.textContent.trim())]))})"""
PAGE_PIE = """() => ({big: document.querySelector('#pie-chart .nx-donut-val').textContent.trim(),
  rows: Object.fromEntries([...document.querySelectorAll('#pie-table tbody tr')].map(tr => [tr.dataset.src, [...tr.querySelectorAll('td')].map(td => td.textContent.trim())])),
  totals: Object.fromEntries([...document.querySelectorAll('#hc-body table.nx-hc')[0].querySelectorAll('tbody tr')].map(tr => [tr.dataset.src, [...tr.querySelectorAll('td')].map(td => td.textContent.trim())]))})"""
# JEG-1393 (R1-CX-04/07/08): the chart's worked example and index-factor totals, read straight from the engine.
ENGINE_WORKED = """(a) => { const C = window.TradeValueCurveControls, ins = C.getInspection(), p = ins.players[a.s][a.k];
  const src = ins.valuePipeline.sources[a.s], pm = C.getPublishedMath(Number(a.k), a.s);
  return {adjusted: p.adjusted, parts: [p.starterSlice, src.rates[p.pos + '|starter'], p.benchSlice, src.rates[p.pos + '|bench']],
    vorpDisplay: p.vorpDisplay, rates: [src.rates[p.pos + '|starter'], src.rates[p.pos + '|bench']], native: p.native,
    anchor: pm.anchorTotal, chart: pm.chartTotal, factor: pm.factor,
    sigmaRel: ins.valuePipeline.chartSigma[p.pos].sigma_rel, pos: p.pos, startWorthy: p.startWorthy,
    starterLine: src.positions[p.pos].starterLine, pie: ins.valuePipeline.pie, surplus: src.surplusTotal, vorpFactor: src.vorpFactor,
    allocations: (ins.valuePipeline.allocationMix || []).length || 1}; }"""
PAGE_WORKED = """() => ({eq: [...document.querySelectorAll('#bu-worked tbody tr')].pop().querySelector('td').textContent.trim(),
  explain: document.getElementById('bu-explain').textContent,
  rows: Object.fromEntries([...document.querySelectorAll('#bu-worked tbody tr')].map(tr => [tr.querySelector('th').firstChild.textContent.trim(),
    {value: tr.querySelector('td').textContent.trim(), how: (tr.querySelector('.nx-how') || {}).textContent || ''}]))})"""
# JEG-1393 R5-OP-02 / R5-OP-05: the raw engine inputs behind CBS Sports's RB worked row, for the top RB by DDF Value.
ENGINE_R5 = """() => { const C = window.TradeValueCurveControls, ins = C.getInspection(), vp = ins.valuePipeline, src = vp.sources.cbs;
  const top = C.getAllRows().filter(r => r.pos === 'RB' && r.ddfByVersion && r.ddfByVersion.blended && isFinite(r.ddfByVersion.blended.value)
    && ins.players.cbs[String(r.player_key)]).sort((a, b) => b.ddfByVersion.blended.value - a.ddfByVersion.blended.value)[0];
  const P = src.positions.RB, mix = (vp.allocationMix && vp.allocationMix.length) ? vp.allocationMix : [{weight: 1, allocation: vp.allocation}];
  const weights = {}, method = {};
  Object.keys(vp.sources).forEach(s => { weights[s] = vp.sources[s].weights; method[s] = vp.sources[s].positions.RB.method; });
  const paths = [];
  ['QB','RB','WR','TE'].forEach(q => Object.values(src.positions[q].estimates || {}).forEach(e => paths.push(e.path)));
  return {key: String(top.player_key), bye: vp.lineup.bye, m: P.lineup.m, avail: P.avail, conf: vp.lineup.projection_confidence,
    sigmaRel: P.lineup.sigmaRel, cs: vp.chartSigma.RB, W: vp.ddfWeights, included: vp.included, weights, method,
    work: Object.values(ins.players.cbs).filter(p => p.pos === 'RB').map(p => [p.rank, p.native]),
    mix: mix.map(m => [m.weight, m.allocation.RB.starters]), waiver: P.waiver, starterLine: P.starterLine, paths}; }"""
PAGE_BUILDUP = """() => [...document.querySelectorAll('#bu-table tbody tr')].map(tr => ({k: tr.dataset.key, cells: [...tr.querySelectorAll('td')].map(td => td.textContent.trim())}))"""


def go(page, hash_):
    page.evaluate("h => { location.hash = h; }", hash_)
    page.wait_for_timeout(120)


def compare(page, combo) -> list[str]:
    """Every mismatch between the Learn page and the engine at one setting."""
    scoring, teams, sf = combo
    q = f"?scoring={scoring}&teams={teams}&roster={ROSTER.format(sf=sf)}"
    errors: list[str] = []
    tag = f"{scoring}/{teams}/sf{sf}"
    go(page, "#numbers/pie" + q)
    page.wait_for_function(SNAP_READY, arg={"scoring": scoring, "teams": teams, "sf": bool(sf)}, timeout=60000)
    eng = page.evaluate(ENGINE)
    if (eng["scoring"], eng["teams"], eng["sf"]) != (scoring, teams, sf):
        return [f"{tag}: engine is at {eng['scoring']}/{eng['teams']}/sf{eng['sf']}"]
    rows = eng["rows"]

    picker = page.evaluate(PAGE_PICKER)
    seen = set()
    for opt in picker:
        row = rows.get(opt["k"])
        if row is None:
            errors.append(f"{tag}: picker lists {opt['name']} ({opt['k']}), the engine has no DDF Value for him")
            continue
        seen.add(opt["k"])
        want = f1(row["ddf"])
        if not opt["label"].endswith("· " + want):
            errors.append(f"{tag}: {row['name']} DDF Value on the page {opt['label']!r}, engine {want}")
    if set(rows) - seen:
        errors.append(f"{tag}: {len(set(rows) - seen)} priced players missing from the page")

    top = sorted(rows, key=lambda k: (-rows[k]["ddf"], int(k)))[:3]
    for k in top:
        go(page, f"#numbers/trace/{k}{q}")
        tr = page.evaluate(PAGE_TRACE)
        if tr["big"] != f1(rows[k]["ddf"]):
            errors.append(f"{tag}: trace {rows[k]['name']} shows {tr['big']}, engine {f1(rows[k]['ddf'])}")
        for s in CHARTS:
            e = rows[k]["src"][s]
            want = [fpub(s, e and e["published"]), ffactor(eng["factor"][s]), f1(e and e["indexed"]), f1(e and e["adjusted"])]
            if tr["rows"].get(s) != want:
                errors.append(f"{tag}: trace {rows[k]['name']} {s} page {tr['rows'].get(s)}, engine {want}")
    k = top[0]
    go(page, f"#numbers/pie/{k}{q}")
    pie = page.evaluate(PAGE_PIE)
    if pie["big"] != f1(rows[k]["ddf"]):
        errors.append(f"{tag}: pie total {pie['big']}, engine {f1(rows[k]['ddf'])}")
    for s in CHARTS:
        e = rows[k]["src"][s]
        got = (pie["rows"].get(s) or [None])[0]
        if got != f1(e and e["adjusted"]):
            errors.append(f"{tag}: pie {s} adjusted {got}, engine {f1(e and e['adjusted'])}")
    for s, total in eng["totals"].items():
        cells = pie["totals"].get(s)
        if not cells or cells[3] != f1(total["all"]):
            errors.append(f"{tag}: health check {s} total {cells and cells[3]}, engine {f1(total['all'])}")
        if not cells or cells[2] != f1(total["waiver"]):
            errors.append(f"{tag}: health check {s} waiver-role remainder {cells and cells[2]}, engine {f1(total['waiver'])}")

    for s in ("cbs", "fantasycalc"):
        go(page, f"#numbers/build-up/{s}{q}")
        got = page.evaluate(PAGE_BUILDUP)
        want_rows = eng["order"][s][:len(got)]
        if not got:
            errors.append(f"{tag}: build-up {s} shows no rows")
        for i, (g, w) in enumerate(zip(got, want_rows)):
            if g["k"] != w["k"]:
                errors.append(f"{tag}: build-up {s} row {i + 1} is {g['k']}, engine order {w['k']}")
                break
            # cells: rank, pos, role, published, indexed, adjusted, others, ddf
            ddf = rows.get(w["k"])
            want = [fpub(s, w["published"]), f1(w["indexed"]), f1(w["adjusted"])]
            if g["cells"][3:6] != want:
                errors.append(f"{tag}: build-up {s} {w['k']} page {g['cells'][3:6]}, engine {want}")
            if g["cells"][7] != (f1(ddf["ddf"]) if ddf else "—"):
                errors.append(f"{tag}: build-up {s} {w['k']} DDF {g['cells'][7]}, engine {ddf and f1(ddf['ddf'])}")
        if got:
            ew = page.evaluate(ENGINE_WORKED, {"s": s, "k": got[0]["k"]})
            pw = page.evaluate(PAGE_WORKED)
            # The printed operands reproduce the printed result (R1-CX-08): a x b + c x d ~ X -> f1.
            m = re.match(r"([\d.]+) × ([\d.]+) \+ ([\d.]+) × ([\d.]+) ≈ ([\d.]+) → ([\d.]+)$", pw["eq"])
            if not m:
                errors.append(f"{tag}: build-up {s} worked equation {pw['eq']!r} not in a x b + c x d form")
            else:
                a, b, c, d, approx, shown = (float(x) for x in m.groups())
                if abs(a * b + c * d - ew["adjusted"]) > 0.005 or shown != round(ew["adjusted"], 1) or abs(approx - ew["adjusted"]) > 0.0006:
                    errors.append(f"{tag}: build-up {s} worked {pw['eq']!r}, engine adjusted {ew['adjusted']}")
            # R2-OP-05: the pie-scaled Value above waivers is the engine's display VORP; the chart-unit row is named apart.
            vaw = pw["rows"].get("Value above waivers (on the value pie)")
            if not vaw or vaw["value"] != f1(ew["vorpDisplay"]) or not any(k.startswith("Above the waiver line (") for k in pw["rows"]):
                errors.append(f"{tag}: build-up {s} value-above-waivers rows {vaw!r}, engine {ew['vorpDisplay']}")
            # R2-OP-03: each rate's budget ÷ group total sits beside it and lands near the averaged rate (the engine averages
            # each allocation's rate; the page divides the averaged budget by the averaged total: 1.5% apart at half PPR/10/SF).
            for name, rate in (("Starter rate", ew["rates"][0]), ("Fill-in rate", ew["rates"][1])):
                how = (pw["rows"].get(name) or {}).get("how", "")
                mm = re.search(r"≈ ([\d.]+)(?:\. |$)", how)
                if rate and (not mm or abs(float(mm.group(1)) - rate) > 0.05 * rate):
                    errors.append(f"{tag}: build-up {s} {name} formula {how!r}, engine rate {rate}")
                # R4-OP-03: the rate says why its formula is close to, not equal to, the averaged rate.
                if ew["allocations"] > 1 and f"Averaged rate = Σ allocation weight × that allocation’s rate, over the {ew['allocations']} league allocations" not in how:
                    errors.append(f"{tag}: build-up {s} {name} lacks the averaged-rate sentence: {how[-200:]!r}")
            errors += worked_spread_errors(tag, s, pw, ew)
            # R2-OP-04: the Adjusted step starts from the published value, not the indexed one.
            if f"{fpub(s, ew['native'])} → " not in pw["explain"]:
                errors.append(f"{tag}: build-up {s} Adjusted step does not start from published {fpub(s, ew['native'])}")
            # The factor's two totals sit beside it and divide to it (R1-CX-04).
            if f"({ew['anchor']:.2f})" not in pw["explain"] or ffactor(ew["factor"]) not in pw["explain"]:
                errors.append(f"{tag}: build-up {s} factor text lacks DDF total {ew['anchor']:.2f} or factor {ffactor(ew['factor'])}")
            elif abs(float(f"{ew['anchor']:.2f}") / ew["chart"] - float(ffactor(ew["factor"]))) > 5e-6 * ew["factor"] + 1e-9:
                errors.append(f"{tag}: build-up {s} shown totals do not divide to the shown factor")
    return errors


def worked_spread_errors(tag, s, pw, ew) -> list[str]:
    """R4-OP-04 / R4-OP-09: the spread σ row and the chance substitution recompute from the engine's chart spread rate,
    and the value-pie factor's division is shown and is not the Indexed factor."""
    out = []
    num = r"([\d,]+(?:\.\d+)?)"
    sig = pw["rows"].get("Spread σ") or {}
    m = re.search(num + r" × " + num + r" = " + num, sig.get("how", ""))
    sigma = ew["sigmaRel"] * ew["native"]
    if not m:
        out.append(f"{tag}: build-up {s} has no spread row with its numbers: {sig!r}")
    else:
        rate, native, shown_sigma = (float(x.replace(",", "")) for x in m.groups())
        if rate != round(ew["sigmaRel"], 4) or abs(native - ew["native"]) > 0.006 + 0.5 * (s == "fantasycalc") \
                or abs(shown_sigma - sigma) > 0.006 + 0.5 * (s == "fantasycalc"):
            out.append(f"{tag}: build-up {s} spread {m.group(0)!r}, engine {ew['sigmaRel']} × {ew['native']} = {sigma}")
    chance = (pw["rows"].get("Chance above the starter line") or {}).get("how", "")
    m = re.search(r"1 − Φ\(\(" + num + r" − " + num + r"\) ÷ " + num + r"\) = 1 − Φ\(([−\d.]+)\) ≈ ([\d.]+)%", chance)
    if "standard normal cumulative probability" not in chance or not m:
        out.append(f"{tag}: build-up {s} chance row lacks Φ's definition or its substitution: {chance!r}")
    else:
        line, nat, sg, z, pct = m.groups()
        z_want = (ew["starterLine"] - ew["native"]) / sigma
        if abs(float(z.replace("−", "-")) - z_want) > 0.0015 or pct != f"{ew['startWorthy'] * 100:.1f}":
            out.append(f"{tag}: build-up {s} chance z {z} (engine {z_want:.4f}), {pct}% (engine {ew['startWorthy']})")
        # 1 − Φ(z) is the engine's chance up to the averaging of the lines over the allocations.
        if abs(0.5 * math.erfc(z_want / math.sqrt(2)) - ew["startWorthy"]) > 0.01:
            out.append(f"{tag}: build-up {s} 1 − Φ(z) = {0.5 * math.erfc(z_want / math.sqrt(2)):.4f} far from {ew['startWorthy']}")
    vaw = (pw["rows"].get("Value above waivers (on the value pie)") or {}).get("how", "")
    ratio = ew["pie"] / ew["surplus"]
    m = re.search(r"over its work list \(" + num + r" ÷ " + num + r" ≈ ([\d.]+)\)", vaw)
    if "It is not the Indexed factor" not in vaw or not m or float(m.group(1).replace(",", "")) != ew["pie"] \
            or abs(float(m.group(2).replace(",", "")) - ew["surplus"]) > 0.051 + 0.5 * (s == "fantasycalc") or m.group(3) != ffactor(ratio):
        out.append(f"{tag}: build-up {s} value-pie factor not defined with its division ({ew['pie']} ÷ {ew['surplus']} = {ratio}): {vaw!r}")
    return out


def manifesto_words(mirror: str) -> list[str]:
    """Same rule as tests/test_v2_contract_render.py MF-01: the mirror body without Markdown marks."""
    body = mirror.split("-->", 1)[1] if mirror.startswith("<!--") else mirror
    body = re.sub(r"^\s*- ", " ", body, flags=re.M)
    return body.replace("*", "").replace("#", " ").split()


class LearnEngineParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            if _render_env.required():
                raise
            raise unittest.SkipTest("playwright not installed")
        if not (DIST / "learn.html").exists():
            if _render_env.required():
                raise AssertionError("dist/learn.html is not built")
            raise unittest.SkipTest("dist/learn.html is not built")
        cls.sync_playwright = staticmethod(sync_playwright)

    def _page(self, p, base, viewport=(1440, 900)):
        browser = p.chromium.launch(executable_path=chromium_executable(p), args=_render_env.HERMETIC_ARGS)
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(base + "/learn.html#numbers/pie")
        page.wait_for_function("() => window.DDFNumbers && DDFNumbers.snapshot()", timeout=90000)
        return browser, page, errors

    def test_numbers_match_engine(self):
        with serve() as base, self.sync_playwright() as p:
            browser, page, console = self._page(p, base)
            errors = []
            for combo in COMBOS:
                errors += compare(page, combo)
            browser.close()
        self.assertEqual(errors, [], "\n".join(errors[:40]))
        self.assertEqual([e for e in console if "Failed to load resource" not in e], [])

    def test_guard_catches_a_wrong_number(self):
        reader = (DIST / "learn" / "numbers" / "learn-engine.js").read_text(encoding="utf-8")
        anchor = "if (ddf === null) return;"
        self.assertIn(anchor, reader, "the nudge anchor moved; update the guard")
        nudged = reader.replace(anchor, anchor + " ddf += 0.2;", 1)
        with serve(overrides={"learn/numbers/learn-engine.js": nudged.encode()}) as base, self.sync_playwright() as p:
            browser, page, _ = self._page(p, base)
            errors = compare(page, ("ppr", 12, 0))
            browser.close()
        self.assertTrue(any("DDF Value" in e or "trace" in e for e in errors), errors[:5])

    def test_round4_notes(self):
        """R4-OP-03 (superflex: the trace says the ≈ rate is not the averaged rate and why), R4-OP-06 (a held source's
        note in plain words, projections left out of DDF Value · projections) and R4-OP-01 (glossary Bench weight is
        not the bench share of the pie)."""
        q = "?scoring=ppr&teams=12&roster=" + ROSTER.format(sf=1)
        with serve() as base, self.sync_playwright() as p:
            browser, page, console = self._page(p, base, viewport=(390, 844))
            go(page, "#numbers/pie" + q)
            page.wait_for_function(SNAP_READY, arg={"scoring": "ppr", "teams": 12, "sf": True}, timeout=60000)
            snap = page.evaluate("""() => { const s = DDFNumbers.snapshot(), a = s.players.find(p => p.name === 'Josh Allen');
              return {key: a && a.player_key, mix: (s.inspection.valuePipeline.allocationMix || []).length,
                held: (s.inspection.excluded || []).filter(e => /^held: fidelity: scrape_validity$/.test(e.reason)).map(e => e.key)}; }""")
            self.assertTrue(snap["key"], "Josh Allen is not priced at this setting; pick another example")
            go(page, f"#numbers/trace/{snap['key']}{q}")
            trace = page.text_content("#tr-adj-body")
            notes = {}
            for src in snap["held"]:
                go(page, f"#numbers/build-up/{src}{q}")
                notes[src] = page.text_content("#bu-meta")
            gloss = page.text_content("#g-bench-weight")
            overflow = page.evaluate("() => document.documentElement.scrollWidth > innerWidth + 1")
            browser.close()
        self.assertGreater(snap["mix"], 1, "superflex should average several allocations; the check proves nothing")
        self.assertIn(f"the engine’s rate, the weight-average of each of the {snap['mix']} league allocations’ own rate", trace)
        self.assertNotIn("averaged over the allocations:", trace)
        for src, note in notes.items():
            self.assertNotIn("held: fidelity", note, src)
            self.assertIn("Held this week (its latest scrape failed validation): left out of DDF Value · projections, but still "
                          "counted in the league allocation and the DDF weights.", note, src)
        self.assertIn("It is not the bench share of the pie shown on Full value logic", gloss)
        self.assertFalse(overflow, "horizontal overflow at 390 px")
        self.assertEqual([e for e in console if "Failed to load resource" not in e], [])

    def test_round5_derivations_and_status(self):
        """R5-OP-02: the worked rows derive availability, the starter line, the chart spread rate and the DDF weights at the
        reader's setting, recomputed here from the engine's raw inspection (never the page model), at two settings.
        R5-OP-05: the build-up's filled-in count says how each estimate was made. R5-OP-08: the status line follows a
        settings change."""
        settings = [("ppr", 12, 0), ("half_ppr", 10, 1)]
        got, errors = {}, []
        with serve() as base, self.sync_playwright() as p:
            browser, page, console = self._page(p, base, viewport=(390, 844))
            for scoring, teams, sf in settings:
                q = f"?scoring={scoring}&teams={teams}&roster=" + ROSTER.format(sf=sf)
                go(page, "#numbers/pie" + q)
                page.wait_for_function(SNAP_READY, arg={"scoring": scoring, "teams": teams, "sf": bool(sf)}, timeout=60000)
                eng = page.evaluate(ENGINE_R5)
                go(page, f"#numbers/build-up/cbs/RB{q}")
                page.wait_for_selector("#bu-worked-pick", timeout=20000)
                page.select_option("#bu-worked-pick", eng["key"])
                page.wait_for_timeout(150)
                worked = page.evaluate(PAGE_WORKED)["rows"]
                go(page, f"#numbers/build-up/cbs{q}")
                page.wait_for_timeout(150)
                meta = page.text_content("#bu-meta")
                go(page, f"#numbers/trace/{eng['key']}{q}")
                page.wait_for_timeout(150)
                trace = page.text_content("#tr-adj-body")
                got[(scoring, teams, sf)] = (eng, worked, meta, trace)
            # R5-OP-08: on the Trace at the second setting, switch to 12 teams with the page's own control.
            before = page.text_content("#nx-live")
            page.select_option("#set-teams", "12")
            page.wait_for_function(SNAP_READY, arg={"scoring": "half_ppr", "teams": 12, "sf": True}, timeout=60000)
            page.wait_for_timeout(300)
            after = page.text_content("#nx-live")
            new_ddf = page.evaluate("""(k) => { const r = TradeValueCurveControls.getAllRows().find(r => String(r.player_key) === k);
              return r.ddfByVersion.blended.value; }""", got[settings[1]][0]["key"])
            browser.close()
        for combo, (eng, worked, meta, trace) in got.items():
            tag = "/".join(map(str, combo))
            # Availability = (1 − bye share) × (1 − missed-game rate).
            a = (1 - eng["bye"]) * (1 - eng["m"])
            want = f"(1 − bye share {eng['bye'] * 100:.2f}%) × (1 − RB missed-game rate {eng['m'] * 100:.2f}%) = {1 - eng['bye']:.4f} × {1 - eng['m']:.4f} = {a * 100:.1f}%"
            if want not in worked["Availability"]["how"] or abs(a - eng["avail"]) > 1e-9:
                errors.append(f"{tag}: availability {worked['Availability']['how']!r}, want {want!r} (engine {eng['avail']})")
            # DDF weight = mean of the included sources' own shares for the group.
            for group, row in (("RB|starter", "Starter rate"), ("RB|bench", "Fill-in rate")):
                shares = [eng["weights"][s][group] for s in eng["included"] if eng["weights"].get(s) and eng["method"][s] != "no_players"]
                mean = sum(shares) / len(shares)
                role = "starter" if group.endswith("starter") else "fill-in"
                want = f"DDF weight {eng['W'][group] * 100:.2f}% = the mean of the {len(shares)} included sources’ own RB {role} shares (held sources too)"
                if abs(mean - eng["W"][group]) > 5e-6 or want not in worked[row]["how"] or f"÷ {len(shares)} = {mean * 100:.2f}%" not in worked[row]["how"]:
                    errors.append(f"{tag}: {group} weight {worked[row]['how'][:300]!r}, want {want!r} mean {mean}")
                if want not in trace:
                    errors.append(f"{tag}: trace lacks the {group} weight derivation")
            # Starter line = midpoint of the last starter and first non-starter at each allocation's count, weighted.
            work = [v for _, v in sorted((r, v) for r, v in eng["work"])]
            shares = {}
            for wt, s in eng["mix"]:
                shares[s] = shares.get(s, 0) + wt
            tot = sum(shares.values())
            line = sum(w / tot * max((work[s - 1] + work[s]) / 2 if len(work) > s else work[s - 1], eng["waiver"]) for s, w in shares.items())
            want = f"weighted by those shares, {line:.2f}" if len(shares) > 1 else f"= {line:.2f} ({next(iter(shares))} RB starters)"
            if abs(line - eng["starterLine"]) > 1e-6 or want not in worked["RB starter line"]["how"]:
                errors.append(f"{tag}: starter line {worked['RB starter line']['how']!r}, want {want!r} (engine {eng['starterLine']})")
            # Chart spread rate and its rank band.
            cs = eng["cs"]
            first = cs["starters"] // 2 + 1
            want = f"RB chart spread rate {cs['sigma_rel']:.4f} = the median chart disagreement at RB ranks {first}–{first + cs['band'] - 1} ({cs['band']} players"
            if want not in worked["Spread σ"]["how"] or abs(cs["sigma_rel"] * eng["conf"] - eng["sigmaRel"]) > 1e-9:
                errors.append(f"{tag}: spread {worked['Spread σ']['how']!r}, want {want!r}")
            # R5-OP-05: how CBS Sports's estimates were made.
            peers, curve = eng["paths"].count("peers"), eng["paths"].count("curve")
            want = ("filled in from the other charts," if not curve else
                    f"filled in ({peers} from the other charts, {curve} from the chart’s own values against projected points")
            if f"{peers + curve} {want}" not in meta:
                errors.append(f"{tag}: build-up meta {meta[:200]!r}, want {want!r}")
        self.assertEqual(errors, [], "\n".join(errors))
        self.assertNotEqual(f1(new_ddf), before.split("DDF Value ")[-1].rstrip("."), "the setting change did not move his value; the check proves nothing")
        self.assertIn(f"DDF Value {f1(new_ddf)}.", after, f"status kept the old setting: {after!r}")
        self.assertEqual([e for e in console if "Failed to load resource" not in e], [])

    def test_round6_waiver_line_and_notes(self):
        """R6-OP-01: the waiver line row and the Trace derive the line from each league allocation's own run, recomputed
        here from TradeValueCurveHarness.runPipelineWith (never the page model): the player at the first seat past the
        heaviest allocation's rostered count, and the weight-average of every allocation's line equals the engine's.
        R6-OP-02: the spread band's end is the D'Hondt N′, not the league's rostered count. R6-OP-03: the intro.
        R6-OP-07: superflex Josh Allen on USA Today states the engine's restatement when the subtraction differs."""
        cases = [(("ppr", 12, 0), "cbs", None), (("half_ppr", 10, 1), "usatoday", "Josh Allen")]
        engine_js = """(a) => { const H = TradeValueCurveHarness, ins = TradeValueCurveControls.getInspection(), vp = ins.valuePipeline;
          const s = DDFNumbers.snapshot(); let key = null, pos = 'RB';
          if (a.name) { const p = s.players.find(p => p.name === a.name); key = String(p.player_key); pos = p.pos; }
          else key = String(s.players.filter(p => p.pos === 'RB' && ins.players[a.s][String(p.player_key)]).sort((x, y) => y.ddf - x.ddf)[0].player_key);
          const mix = vp.allocationMix && vp.allocationMix.length > 1 ? vp.allocationMix : [{weight: 1, allocation: (vp.allocationMix && vp.allocationMix[0] || {}).allocation || vp.allocation}];
          const reads = mix.map(m => { const r = mix.length > 1 ? H.runPipelineWith({seatAllocation: m.allocation}) : {sources: {[a.s]: {players: ins.players[a.s], positions: vp.sources[a.s].positions}}};
            const src = r.sources[a.s], P = src.positions[pos];
            const work = Object.entries(src.players).filter(([k, q]) => q.pos === pos && isFinite(q.rank)).sort((x, y) => x[1].rank - y[1].rank);
            const W = m.allocation[pos].rostered, at = work[W];
            return {weight: m.weight, W, waiver: P.waiver, key: at && at[0], native: at && at[1].native, est: !!(at && at[1].estimated)}; });
          const p = ins.players[a.s][key], P = vp.sources[a.s].positions[pos], o = vp.sources[a.s];
          const nm = k => (s.players.find(q => String(q.player_key) === k) || {}).name || null;
          return {key, pos, reads, names: reads.map(r => nm(r.key)), waiver: P.waiver, rostered: P.rostered, cs: vp.chartSigma[pos],
            native: p.native, vorp: p.vorp, vorpDisplay: p.vorpDisplay, factor: o.vorpFactor, n: mix.length}; }"""
        got = {}
        with serve() as base, self.sync_playwright() as p:
            browser, page, console = self._page(p, base, viewport=(390, 844))
            for (scoring, teams, sf), src, name in cases:
                q = f"?scoring={scoring}&teams={teams}&roster=" + ROSTER.format(sf=sf)
                go(page, "#numbers/pie" + q)
                page.wait_for_function(SNAP_READY, arg={"scoring": scoring, "teams": teams, "sf": bool(sf)}, timeout=60000)
                eng = page.evaluate(engine_js, {"s": src, "name": name})
                intro = page.text_content("#nx-method")
                go(page, f"#numbers/build-up/{src}/{eng['pos']}{q}")
                page.wait_for_selector("#bu-worked-pick", timeout=20000)
                page.select_option("#bu-worked-pick", eng["key"])
                page.wait_for_timeout(150)
                worked = page.evaluate(PAGE_WORKED)["rows"]
                go(page, f"#numbers/trace/{eng['key']}{q}")
                page.wait_for_timeout(200)
                trace = page.text_content("#tr-adj-body")
                overflow = page.evaluate("() => document.documentElement.scrollWidth > innerWidth + 1")
                got[src] = (eng, intro, worked, trace, overflow)
            browser.close()
        u = lambda v, s: f"{round(v):,}" if s == "fantasycalc" else f"{v:.2f}"
        for src, (eng, intro, worked, trace, overflow) in got.items():
            pos, reads = eng["pos"], eng["reads"]
            tot = sum(r["weight"] for r in reads)
            line = sum(r["weight"] * r["waiver"] for r in reads) / tot
            self.assertAlmostEqual(line, eng["waiver"], places=9, msg=f"{src}: the allocations' lines do not average to the engine's")
            for r in reads:  # a chart's line is the one player at the first seat past the rostered count
                self.assertAlmostEqual(r["native"], r["waiver"], places=9, msg=f"{src}: allocation line is not work[W]")
            h = max(range(len(reads)), key=lambda i: reads[i]["weight"])
            hr = reads[h]
            want = f"{pos}{hr['W'] + 1} {eng['names'][h] + ' ' if eng['names'][h] else ''}{'(est.) ' if hr['est'] else ''}{u(hr['native'], src)}"
            how = worked[f"{pos} waiver line"]["how"]
            self.assertIn(want, how, src)
            self.assertIn(want, trace, src)
            if eng["n"] > 1:
                ns = [r["W"] for r in reads]
                self.assertIn(f"weighted over the {eng['n']} league allocations ({min(ns)} to {max(ns)} rostered, read at {pos}{min(ns) + 1} to {pos}{max(ns) + 1}", how, src)
                self.assertIn(f") = {u(line, src)}", how, src)
            self.assertNotIn("the engine’s line is", how, src)
            # R6-OP-02: N′ = the starters plus the D'Hondt bench seats.
            cs = eng["cs"]
            want = f"to {cs['rostered']} (the {cs['starters']} seats plus {pos}’s {cs['rostered'] - cs['starters']} bench seats from a fixed D’Hondt split"
            self.assertIn(want, worked["Spread σ"]["how"], src)
            if cs["rostered"] != eng["rostered"]:
                self.assertIn(f"not the league’s {eng['rostered']} rostered", worked["Spread σ"]["how"], src)
            self.assertIn("his expected share of it in a lineup, after byes and injuries, so together less than the whole", intro)
            self.assertNotIn("split into a start-worthy part", intro)
            # R6-OP-07: the restatement, with both numbers, only when the subtraction differs.
            sub = eng["native"] - eng["waiver"]
            if u(sub, src) != u(eng["vorp"], src):
                want = (f"here the engine’s figure is value above waivers on the value pie {eng['vorpDisplay']:.3f} ÷ the averaged value-pie factor "
                        f"{ffactor(eng['factor'])} = {u(eng['vorp'], src)}; it differs from {u(eng['native'], src)} − {u(eng['waiver'], src)} = {u(sub, src)}")
                self.assertIn(want, worked[f"Above the waiver line ({'FantasyCalc' if src == 'fantasycalc' else {'cbs': 'CBS Sports', 'usatoday': 'USA Today'}[src]} units)"]["how"], src)
                self.assertIn(want, trace, src)
                self.assertAlmostEqual(eng["vorpDisplay"] / eng["factor"], eng["vorp"], places=9)
            else:
                self.assertIn(f"{u(eng['native'], src)} − {u(eng['waiver'], src)} = {u(sub, src)}", worked[[k for k in worked if k.startswith("Above the waiver line")][0]]["how"], src)
            self.assertFalse(overflow, f"{src}: horizontal overflow at 390 px")
        self.assertNotEqual(u(got["usatoday"][0]["native"] - got["usatoday"][0]["waiver"], "usatoday"), u(got["usatoday"][0]["vorp"], "usatoday"),
                            "Josh Allen's subtraction matches at this setting; the R6-OP-07 check proves nothing")
        self.assertEqual([e for e in console if "Failed to load resource" not in e], [])

    def test_round6_bench_weight_scope(self):
        """R6-CX-01: the glossary scopes Bench weight to the comparisons that use it and says Team's totals count in full."""
        html = (DIST / "learn.html").read_text(encoding="utf-8")
        self.assertIn("Team’s “Your roster” and ROSTER DDF totals do not use it: they count every player’s DDF Value in full.", html)
        self.assertIn("Team’s best move, the trade fit (Build a Trade’s Why", html)
        self.assertNotIn("when Team, Build a Trade and Buy / Sell’s natural fit add up a roster", html)

    def test_round5_glossary(self):
        """R5-OP-02 / R5-OP-03 / R5-OP-05: the new terms and the parts as value amounts."""
        html = (DIST / "learn.html").read_text(encoding="utf-8")
        for term in ("g-starter-line", "g-availability", "g-ddf-weights"):
            self.assertIn(f'id="{term}"', html)
        self.assertIn("(1 − bye share) × (1 − the position’s missed-game rate)", html)
        self.assertEqual(html.count("× his value above the waiver line × his chance of clearing"), 2)
        self.assertNotIn("start-worthy part (his chance of clearing", html)
        self.assertNotIn("filled in from the other charts is left out", html)
        self.assertEqual(html.count("from the other charts or, when none is usable, from the chart’s own values against projected points"), 2)

    def test_overrides_and_basis_not_applied(self):
        """Learn explains the model's own DDF Value: a stored override and a one-chart basis must not change it."""
        q = "?scoring=ppr&teams=12&roster=" + ROSTER.format(sf=0)
        with serve() as base, self.sync_playwright() as p:
            browser, page, _ = self._page(p, base)
            go(page, "#numbers/pie" + q)
            page.wait_for_function(SNAP_READY, arg={"scoring": "ppr", "teams": 12, "sf": False}, timeout=60000)
            top = page.evaluate(ENGINE)
            key = sorted(top["rows"], key=lambda k: (-top["rows"][k]["ddf"], int(k)))[0]
            go(page, f"#numbers/trace/{key}{q}")
            clean = page.evaluate(PAGE_TRACE)
            browser.close()
            stored = {"v": 2, "basis": {"mode": "single", "source": "fantasycalc"}, "values": {key: 5}, "names": {}}
            browser = p.chromium.launch(executable_path=chromium_executable(p), args=_render_env.HERMETIC_ARGS)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script("localStorage.setItem('ddf-v2-value-overrides', %s)" % repr(__import__("json").dumps(stored)))
            page = ctx.new_page()
            page.goto(base + f"/learn.html#numbers/trace/{key}{q}")
            page.wait_for_function(SNAP_READY, arg={"scoring": "ppr", "teams": 12, "sf": False}, timeout=90000)
            page.wait_for_timeout(300)
            got = page.evaluate(PAGE_TRACE)
            note = page.inner_text("#nx-settings")
            ov = page.inner_text("#tr-ov")
            applied = page.evaluate("() => TradeValueCurveControls.getValueOverrides()")
            browser.close()
        self.assertTrue(applied, "the stored override did not reach the engine; the test proves nothing")
        self.assertEqual(got, clean, "an override or basis changed the numbers Learn explains")
        self.assertIn("override is not applied", note)
        self.assertIn("value basis (FantasyCalc only) is not applied", note)
        self.assertIn("5.0", ov)

    def test_manifesto_verbatim_and_one_h1(self):
        want = manifesto_words(MIRROR.read_text(encoding="utf-8"))
        with serve() as base, self.sync_playwright() as p:
            for viewport in ((1440, 900), (390, 844)):
                browser, page, console = self._page(p, base, viewport)
                go(page, "#manifesto")
                page.wait_for_selector("#post-body h1", timeout=20000)
                got = page.evaluate("""() => { const b = document.getElementById('post-body').cloneNode(true);
                  b.querySelectorAll('#post-actions').forEach(n => n.remove()); document.body.appendChild(b);
                  const t = b.innerText; b.remove(); return t; }""").split()
                self.assertEqual(got, want, "Manifesto differs from docs/manifesto-mirror.md")
                for h in ("#", "#manifesto", "#numbers/pie", "#numbers/build-up", "#numbers/trace", "#numbers/glossary", "#numbers/logic"):
                    go(page, h)
                    page.wait_for_timeout(300)
                    n = page.evaluate("() => [...document.querySelectorAll('h1')].filter(h => h.getClientRects().length).length")
                    self.assertEqual(n, 1, f"{h} at {viewport[0]}: {n} visible h1")
                browser.close()

    def test_old_routes_redirect(self):
        """The live #writing/* and #values-auditing/* links (and their legacy forms) land on the right Learn view.
        JEG-1539: legacy-routes.js (on the front door and /v2/ stub) handles redirects unconditionally;
        no navigator.webdriver masking needed."""
        cases = [
            ("#writing/manifesto", "learn.html#manifesto"),
            ("#manifesto", "learn.html#manifesto"),
            ("#writing/how-values", "learn.html#numbers/logic"),
            ("#how-values", "learn.html#numbers/logic"),
            ("#writing/research", "learn.html"),
            ("#research/some-post", "learn.html"),
            ("#writing", "learn.html"),
            ("#values-auditing/health-check", "learn.html#numbers/pie"),
            ("#values-auditing/value-pie", "learn.html#numbers/pie"),
            ("#values-auditing/single-source", "learn.html#numbers/build-up"),
            ("#values-auditing", "learn.html#numbers/pie"),
        ]
        with serve() as base, self.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chromium_executable(p), args=_render_env.HERMETIC_ARGS)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            failures = []
            for prefix in ("/", "/v2/"):
                for old, want in cases:
                    page.goto(base + prefix + old)
                    try:
                        page.wait_for_url(re.compile(re.escape(base + "/" + want.split("#")[0]) + r"(#.*)?$"), timeout=30000)
                    except Exception:
                        failures.append(f"{prefix}{old} stayed at {page.url}")
                        continue
                    got = page.url[len(base) + 1:]
                    if not (got == want or got.startswith(want + "?") or got.startswith(want + "/")):
                        failures.append(f"{prefix}{old} -> {got}, want {want}")
            # The classic values explainer URL ends on the Learn tab that frames it.
            page.goto(base + "/value-logic/")
            try:
                page.wait_for_url(re.compile(r".*/learn\.html#numbers/logic.*"), timeout=30000)
                page.wait_for_function("() => { const f = document.getElementById('logic-frame'); return f && f.offsetHeight > 700; }", timeout=30000)
            except Exception:
                failures.append(f"value-logic/ ended at {page.url} without the framed explainer")
            # Reader-facing check: the manifesto view renders after the redirect.
            page.goto(base + "/#writing/manifesto")
            page.wait_for_selector("#post-body h1", timeout=30000)
            browser.close()
        self.assertEqual(failures, [], "\n".join(failures))

    def test_no_snapshots_or_drafts_published(self):
        self.assertFalse((DIST / "learn" / "data").exists(), "week snapshot files are published (D8)")
        posts = (DIST / "learn" / "posts.json").read_text(encoding="utf-8")
        self.assertNotIn('"draft"', posts, "a draft post is listed (D6)")
        self.assertFalse((DIST / "learn" / "posts" / "methodology.md").exists())
        page = (DIST / "learn.html").read_text(encoding="utf-8")
        start = page.index('<main id="learn-main">')
        main = page[start:page.index("</main>", start)]
        for stale in ("week 9", "week9", "Week 9", "84.3", "2,688", "Jahmyr Gibbs"):
            self.assertNotIn(stale, main, f"hard-coded snapshot text in learn.html: {stale!r}")


if __name__ == "__main__":
    unittest.main()
