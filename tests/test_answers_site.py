"""JEG-1543: the answers version (/answers/) shows no source name or third-party number and the same DDF Value.

1. The privacy checker (pipelines/answers_privacy.py) catches what it must: banned names, long decimals, a table with a
   source key or field, a table column that is a source's column, a file outside the allowlist (broken variants).
2. The built tree (dist/answers) passes the checker in full (every table fingerprinted), and has every grid cell.
3. Parity: grid tables equal get-values' own pipeline (tests/_edge_pipeline_runner.cjs) at 1 dp on sample cells,
   including 2 QB-eligible flex slots and the bench and lineup extremes.
4. Overrides: the answers engine's override rule equals ValueModel.applyDdfOverride on the same cases.
5. In the browser, every answers page in every state at 1280, 390 and 320:
   - every request stays under /answers/ (no source file, no engine, no root page, nothing off the host);
   - every response body and the whole DOM (hidden parts, templates and scripts included) pass the text checks;
   - no engine globals or data islands; no horizontal overflow;
   - DDF Value on the answers page equals the full site's DDF Value for the same saved settings;
   - the saved league and overrides are never written.
   Broken variants (an answers page that fetches the source file, loads the engine, or carries a source name in a
   hidden template) must each fail the same audit.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ANSWERS = DIST / "answers"
sys.path.insert(0, str(ROOT / "pipelines"))
import answers_privacy as ap  # noqa: E402

NODE = ["node", "--experimental-strip-types", "--no-warnings"]
RUNNER = ROOT / "tests" / "_edge_pipeline_runner.cjs"
PARITY_CELLS = ["ppr-12-sf0-q1w2f1-b7", "half_ppr-10-sf2-q2w3f2-b5", "standard-14-sf1-q1w3f1-b10",
                "ppr-8-sf0-q2w2f2-b6", "half_ppr-12-sf1-q1w2f1-b6"]
LEAGUE_KEY = "ddf.v2.league-settings"
OV_KEY = "ddf-v2-value-overrides"
ON_GRID = {"v": 1, "scoring": "half_ppr", "teams": 10, "roster": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1,
           "SUPERFLEX": 1, "BENCH": 6, "K": 0, "DST": 0}}
OFF_GRID = {"v": 1, "scoring": "ppr", "teams": 12, "roster": {"QB": 1, "RB": 3, "WR": 2, "TE": 1, "FLEX": 1,
            "SUPERFLEX": 0, "BENCH": 7}}
STATES = {"no-league": {}, "on-grid": {LEAGUE_KEY: ON_GRID}, "off-grid": {LEAGUE_KEY: OFF_GRID},
          "overrides": {LEAGUE_KEY: ON_GRID, OV_KEY: {"v": 2, "basis": {"mode": "single", "source": "x"},
                        "values": {"2227": 10, "3247": {"type": "adjustment", "delta": 5}}, "names": {}}}}
PAGES = ["index.html", "values.html"]
WIDTHS = [1280, 390, 320]


def cell_league(cell: str) -> dict:
    m = re.match(r"^(standard|half_ppr|ppr)-(\d+)-sf(\d)-q(\d)w(\d)f(\d)-b(\d+)$", cell)
    s, t, sf, q, w, f, b = m.groups()
    return {"scoring": s, "teams": int(t), "roster": {"QB": int(q), "RB": 2, "WR": int(w), "TE": 1, "FLEX": int(f),
            "SUPERFLEX": int(sf), "BENCH": int(b)}}


def need_tree():
    if not (ANSWERS / "data" / "grid.json").exists():
        raise _render_env.unavailable("dist/answers is not built (run make sync)")


def need_node():
    if shutil.which("node") is None or subprocess.run([*NODE, "-e", "1"], capture_output=True).returncode:
        raise _render_env.unavailable("node with --experimental-strip-types is not available")


class CheckerTest(unittest.TestCase):
    """Broken variants: each must be caught."""

    def test_banned_text(self):
        for bad in ["FantasyPros says", "per CBS Sports", "USA Today", "fantasycalc", "Razzball", "ESPN projections",
                    "Analyst charts", "Live market", "trade chart", "players-data", "chart_indexed"]:
            self.assertTrue(ap.text_findings("x", f"<p>{bad}</p>"), bad)
        self.assertEqual([], ap.text_findings("x", "<p>DDF Value 37.4 for Josh Allen, Week 9</p>"))

    def test_long_decimals(self):
        self.assertTrue(ap.text_findings("x", '{"f":1.2493025}'))
        self.assertEqual([], ap.text_findings("x", '{"v":37.4,"t":"2026-11-04T04:04:04+00:00"}'))

    def test_table_schema(self):
        good = {"v": 1, "cell": "ppr-12-sf0-q1w2f1-b7", "build": "t", "as_of": None, "week": 9,
                "fields": ap.ROW_FIELDS, "rows": [[1, 30.1, 2.0, 0]]}
        self.assertEqual([], ap.table_findings("t", good))
        self.assertTrue(ap.table_findings("t", {**good, "cbs": {}}))
        self.assertTrue(ap.table_findings("t", {**good, "fields": ap.ROW_FIELDS + ["fp"]}))
        self.assertTrue(ap.table_findings("t", {**good, "rows": [[1, 30.1, 2.0, 0, 28.0]]}))

    def test_fingerprint(self):
        col = {k: float(k % 50) + 0.5 for k in range(100)}
        leaked = {"rows": [[k, v, 1.0, 0] for k, v in col.items()]}
        own = {"rows": [[k, v + 1.3, 1.0, 0] for k, v in col.items()]}
        self.assertTrue(ap.fingerprint_findings("t", leaked, {"src.combo.native": col}))
        self.assertEqual([], ap.fingerprint_findings("t", own, {"src.combo.native": col}))

    def test_file_allowlist(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data").mkdir()
            (root / "index.html").write_text("<p>ok</p>")
            (root / "comparison.json").write_text("{}")
            self.assertTrue(any("not an answers file" in f for f in ap.check_tree(root)))


class BuiltTreeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        need_tree()

    def test_tree_passes_in_full(self):
        bundle = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
        self.assertGreater(len(ap.source_columns(bundle)), 20)   # the fingerprints have something to compare
        self.assertEqual([], ap.check_tree(ANSWERS, bundle, fingerprint_every=1))

    def test_every_grid_cell(self):
        grid = json.loads((ANSWERS / "data" / "grid.json").read_text())["grid"]
        n = 1
        for v in grid.values():
            n *= len(v)
        self.assertEqual(1728, n)
        self.assertEqual(n, len(list((ANSWERS / "data").glob("*-sf*-q*.json"))))
        players = {r[0] for r in json.loads((ANSWERS / "data" / "players.json").read_text())["rows"]}
        for cell in PARITY_CELLS:
            rows = json.loads((ANSWERS / "data" / f"{cell}.json").read_text())["rows"]
            self.assertTrue(rows and all(r[0] in players and r[1] > 0 for r in rows), cell)

    def test_pages_are_noindex_on_their_own(self):
        # The sync adds noindex to every page; the answers pages also carry it in their source (linked from nowhere).
        for name in ("index.html", "values.html"):
            self.assertIn('<meta name="robots" content="noindex, nofollow">', (ROOT / "app" / "answers" / name).read_text())

    def test_pages_carry_no_engine(self):
        for name in ap.PAGE_FILES:
            text = (ANSWERS / name).read_text(encoding="utf-8")
            # A quoted reference (src, href, fetch) to the engine, a parent folder or the site's assets.
            ref = re.search(r"[\"'][^\"'\s]*(?:value-model|curve-widget|product-data|ddf-engine)\.js|[\"']\.\./|[\"'][^\"'\s]*assets/", text)
            self.assertIsNone(ref, f"{name} references {ref.group(0) if ref else ''}")


class ParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        need_tree()
        need_node()

    def test_tables_equal_get_values_pipeline(self):
        from tests.test_week_history import _fixture_today
        import os
        env = {**os.environ, "TRADE_VALUE_TODAY": _fixture_today()}
        for cell in PARITY_CELLS:
            with self.subTest(cell=cell):
                out = subprocess.run([*NODE, str(RUNNER), "--dist", str(DIST), "--league", json.dumps(cell_league(cell))],
                                     capture_output=True, text=True, timeout=120, env=env, check=True).stdout
                want = {int(k): round(v, 1) for k, v in json.loads(out).items() if round(v, 1) > 0}
                got = {r[0]: r[1] for r in json.loads((ANSWERS / "data" / f"{cell}.json").read_text())["rows"]}
                self.assertEqual(want, got)

    def test_override_rule_equals_value_model(self):
        script = r"""
const vm = require("vm"), fs = require("fs");
const VM = require(process.argv[1] + "/dist/assets/value-model.js");
const ctx = {window: {addEventListener() {}}, localStorage: {getItem() { return null; }}, console,
  fetch: () => new Promise(() => {}), Map, Promise, Math, Number, JSON, Object, String, isFinite};
ctx.window.window = ctx.window;
vm.createContext(ctx);
vm.runInContext("var window = this.window; var localStorage = this.localStorage; var fetch = this.fetch;" +
  fs.readFileSync(process.argv[1] + "/app/answers/answers-engine.js", "utf8"), ctx);
const A = ctx.window.DDF.answers._override;
const cases = [5, "12.5", -1, 150, "", null, "x", {value: 40}, {value: -2}, {type: "adjustment", delta: 5},
  {type: "adjustment", delta: "-7.5"}, {type: "adjustment", delta: 300}, {type: "adjustment", delta: ""}, {type: "other"}];
const bases = [0, 12.3, 98.7, null];
const out = [];
for (const c of cases) for (const b of bases) {
  const entry = VM.applyDdfOverride({value: b}, c);
  const spec = A.normalize(c);
  out.push([JSON.stringify(c), b, entry.overridden ? entry.value : b, spec ? A.apply(b, spec) : b]);
}
process.stdout.write(JSON.stringify(out));
"""
        out = subprocess.run(["node", "-e", script, str(ROOT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, out.returncode, out.stderr)
        for case, base, want, got in json.loads(out.stdout):
            self.assertEqual(want, got, f"override {case} on {base}")


# Records every write to web storage, so a write by an answers page is caught.
WRITE_SPY = """(() => { window.__writes = []; const set = Storage.prototype.setItem, rm = Storage.prototype.removeItem;
  Storage.prototype.setItem = function (k) { window.__writes.push(String(k)); return set.apply(this, arguments); };
  Storage.prototype.removeItem = function (k) { window.__writes.push('-' + k); return rm.apply(this, arguments); }; })();"""
DOM_DUMP = """() => { const parts = [document.documentElement.outerHTML, document.body.innerText];
  document.querySelectorAll('template').forEach(t => parts.push(t.innerHTML));
  return parts.join('\\n'); }"""
GLOBALS = """() => ({engine: Boolean(window.TradeValueCurveControls), model: Boolean(window.ValueModel),
  island: Boolean(document.getElementById('players-data') || document.getElementById('methodology-data')),
  ddfEngine: Boolean(window.DDF && window.DDF.engine)})"""
OVERFLOW = "() => document.documentElement.scrollWidth - window.innerWidth"


class RenderedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        need_tree()
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._srv = serve()
        cls.base = cls._srv.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                                 executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._srv.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._srv.__exit__(None, None, None)

    def audit(self, base: str, page_name: str, store: dict, width: int = 1280, height: int = 900):
        """(findings, page facts) for one answers page in one state."""
        context = self.browser.new_context(viewport={"width": width, "height": height})
        seed = "".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in store.items())
        context.add_init_script(f"(() => {{ try {{ if (!sessionStorage.getItem('seeded')) {{ {seed} "
                                f"sessionStorage.setItem('seeded', '1'); }} }} catch (e) {{}} }})();" + WRITE_SPY)
        findings, responses = [], []
        context.on("request", lambda r: findings.extend(self.url_findings(base, r.url)))
        context.on("response", lambda r: responses.append(r))
        page = context.new_page()
        try:
            page.goto(f"{base}/answers/{page_name}", wait_until="load", timeout=60000)
            page.wait_for_function("() => window.DDF && DDF.answers", timeout=20000)
            page.evaluate("() => DDF.answers.ready")
            page.wait_for_timeout(150)
            for r in responses:
                try:
                    body = r.text()
                except Exception:
                    continue
                findings += ap.text_findings(r.url.replace(base, ""), body)
            findings += ap.text_findings(f"{page_name} DOM", page.evaluate(DOM_DUMP))
            g = page.evaluate(GLOBALS)
            findings += [f"{page_name}: global {k} present" for k, v in g.items() if v]
            facts = {"overflow": page.evaluate(OVERFLOW), "writes": page.evaluate("() => window.__writes"),
                     "players": page.evaluate("() => DDF.answers.players().slice(0, 40).map(p => [p.key, p.ddf])"),
                     "cell": page.evaluate("() => DDF.answers.cell()"),
                     "notice": page.evaluate("() => { const n = document.getElementById('n-offgrid'); return n && !n.hidden ? n.textContent : ''; }"),
                     "rows": page.evaluate("() => document.querySelectorAll('#rows tr').length"),
                     "ov": page.evaluate("() => document.querySelectorAll('#rows .tag.yours').length")}
        finally:
            context.close()
        return findings, facts

    @staticmethod
    def url_findings(base: str, url: str) -> list[str]:
        if url.startswith("data:"):
            return []
        if not url.startswith(base + "/answers/"):
            return [f"request outside /answers/: {url}"]
        return []

    def test_pages_states_widths(self):
        for name in PAGES:
            for state, store in STATES.items():
                for width in WIDTHS:
                    with self.subTest(page=name, state=state, width=width):
                        findings, facts = self.audit(self.base, name, store, width)
                        self.assertEqual([], findings)
                        self.assertLessEqual(facts["overflow"], 0)
                        self.assertEqual([], facts["writes"])
                        if name == "values.html":
                            if state == "off-grid":
                                self.assertIsNone(facts["cell"])
                                self.assertIn("RB slots", facts["notice"])
                                self.assertEqual(0, facts["rows"])
                            else:
                                self.assertGreater(facts["rows"], 50)
                            if state == "overrides":
                                ov = dict(facts["players"])
                                self.assertNotIn("2227", ov)   # 10.0 is below the first 40
                                self.assertTrue(facts["ov"])

    def test_same_ddf_value_as_full_site(self):
        for settings in (ON_GRID, {**ON_GRID, "scoring": "ppr", "teams": 12,
                                   "roster": {**ON_GRID["roster"], "SUPERFLEX": 2, "WR": 2, "BENCH": 7}}):
            with self.subTest(settings=settings["scoring"] + str(settings["roster"]["SUPERFLEX"])):
                _, facts = self.audit(self.base, "values.html", {LEAGUE_KEY: settings})
                full = self.full_site_values(settings)
                self.assertTrue(facts["players"])
                for key, ddf in facts["players"]:
                    self.assertAlmostEqual(full[key], ddf, delta=0.051, msg=f"player {key}")

    def full_site_values(self, settings: dict) -> dict:
        context = self.browser.new_context()
        context.add_init_script(f"localStorage.setItem({json.dumps(LEAGUE_KEY)}, {json.dumps(json.dumps(settings))});"
                                + _render_env.pin_data_week_script())
        page = context.new_page()
        try:
            page.goto(f"{self.base}/values.html", wait_until="load", timeout=90000)
            page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.ready", timeout=60000)
            page.evaluate("() => DDF.engine.ready")
            return dict(page.evaluate("() => DDF.engine.players().filter(p => p.ddf !== null).map(p => [p.key, p.ddf])"))
        finally:
            context.close()

    def test_broken_variants_fail(self):
        values = (ANSWERS / "values.html").read_text(encoding="utf-8")
        engine = (ANSWERS / "answers-engine.js").read_text(encoding="utf-8")
        variants = {
            "fetches the source file": {"answers/answers-engine.js":
                (engine + "\nfetch('../assets/comparison-sources-data.json');").encode()},
            "loads the engine": {"answers/values.html":
                values.replace("</body>", '<script src="../assets/value-model.js"></script></body>').encode()},
            "source name in a hidden template": {"answers/values.html":
                values.replace("</main>", "<template><p>FantasyPros</p></template></main>").encode()},
        }
        for label, overrides in variants.items():
            with self.subTest(variant=label):
                with serve(overrides=overrides) as base:
                    findings, _ = self.audit(base, "values.html", STATES["on-grid"])
                self.assertTrue(findings, label)


if __name__ == "__main__":
    unittest.main()
