"""JEG-1571: a flex slot that can start a QB (superflex / QWRT / OP), counted 0, 1 or 2 per team.

A friend's real league starts QB, 2 RB, 2 WR, TE, FLEX and a QWRT (QB/WR/RB/TE) flex with 12 bench spots. Settings
offered only a Superflex yes/no, so he entered 2 QB slots, then 2 FLEX. The engine already models SUPERFLEX as a slot
count (value-model.js vpAllocate: teams x SUPERFLEX QB-eligible seats after the dedicated slots, before FLEX), but
curve-widget.js and get-values clamped it to 0-1, the link carried one bit and Settings had no count.

What is pinned here:
  * Parity: the engine (value-model.js through the edge function's own mapping, tests/_edge_pipeline_runner.cjs)
    equals the Python reference (pipelines/value_reference.py) at 3 scorings x 4 team counts x 0/1/2 QB flex slots.
  * A 2-slot league is priced as 2 slots (not clamped to 1), and QB value rises with each QB flex slot.
  * The friend's lineup: QB values rise against the 1-QB league and against his 2-FLEX workaround.
  * Settings > Position counts: FLEX (RB, WR or TE) and SUPERFLEX (QB, RB, WR or TE) are separate boxes in the
    position grid (Jeremy, 2026-11-08: "Show it as two different positions"), SUPERFLEX 0-2, 44px steppers,
    "N starters, M bench" counts it, it reaches the engine, and a link round-trips 2 while old links decode unchanged.
  * Pasted rosters: QB flex slot labels (Q/W/R/T, OP, SUPERFLEX...) give the count (league-paste.js qbFlexSlots).
Existing settings are byte-identical: see the JEG-1571 log entry (36 settings, edge runner, diff -r before/after).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT))

import value_reference as ref  # noqa: E402
from tests import _render_env  # noqa: E402

RUNNER = ["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tests" / "_edge_pipeline_runner.cjs")]
TOL = 0.06  # value_check's tolerance (tests/test_jeg1365_two_qb_superflex_values.py)
FRIEND = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 1, "BENCH": 12}
WORKAROUND = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "SUPERFLEX": 0, "BENCH": 12}
TWO_QB = {"QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 12}
BANNED = [r"\bDDF\b", r"player pool", r"(?<!Live )\bMarket\b", r"\bdemo\b", r"\bsample\b", r"\bmock", r"illustrative",
          r"\bchoose\b", r"\bset up\b", r"wireframe"]


def data_today() -> str:
    from tests.test_week_history import _fixture_today
    return _fixture_today()


def setUpModule():
    _render_env.ensure_built()


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = {**os.environ, "TRADE_VALUE_TODAY": data_today()}
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))
        cls.pos = {int(k): p["pos"] for k, p in cls.inp.players.items()}
        cls.cache = {}

    def edge(self, scoring, teams, roster):
        key = (scoring, teams, json.dumps(roster, sort_keys=True))
        if key not in self.cache:
            league = {"scoring": scoring, "teams": teams, "roster": roster}
            out = subprocess.run(RUNNER + ["--league", json.dumps(league), "--dist", str(ROOT / "dist")],
                                 capture_output=True, text=True, timeout=120, env=self.env)
            self.assertEqual(out.returncode, 0, out.stderr[-800:])
            self.cache[key] = {int(k): v for k, v in json.loads(out.stdout).items()}
        return self.cache[key]

    def total(self, values, pos):
        return sum(v for k, v in values.items() if self.pos.get(k) == pos and isinstance(v, (int, float)))

    def test_engine_equals_reference_at_0_1_2_qb_flex_slots(self):
        for scoring in ("ppr", "half_ppr", "standard"):
            for teams in (8, 10, 12, 14):
                for sf in (0, 1, 2):
                    with self.subTest(scoring=scoring, teams=teams, superflex=sf):
                        edge = self.edge(scoring, teams, {"SUPERFLEX": sf})
                        rows = ref.Setting(self.inp, scoring, teams, superflex=sf).rows("adj")
                        want = {int(k): v["ddf_value"] for k, v in rows.items() if isinstance(v.get("ddf_value"), (int, float))}
                        self.assertGreater(len(edge), 50)
                        bad = [k for k in set(edge) | set(want) if abs(edge.get(k, 0) - want.get(k, 0)) > TOL]
                        self.assertEqual(bad[:10], [], f"{len(bad)} players differ")

    def test_two_slots_are_not_clamped_to_one(self):
        one, two = self.edge("ppr", 12, {"SUPERFLEX": 1}), self.edge("ppr", 12, {"SUPERFLEX": 2})
        self.assertNotEqual(one, two)

    def test_qb_value_rises_with_each_qb_flex_slot(self):
        for scoring in ("ppr", "half_ppr", "standard"):
            with self.subTest(scoring=scoring):
                qb = [self.total(self.edge(scoring, 12, {"SUPERFLEX": n}), "QB") for n in (0, 1, 2)]
                share = [qb[n] / sum(self.edge(scoring, 12, {"SUPERFLEX": n}).values()) for n in (0, 1, 2)]
                self.assertLess(qb[0], qb[1])
                self.assertLess(qb[1], qb[2])
                self.assertLess(share[0], share[1])
                self.assertLess(share[1], share[2])

    def test_friend_league_qwrt(self):
        friend = self.edge("ppr", 12, FRIEND)
        flex2 = self.edge("ppr", 12, WORKAROUND)
        one_qb = self.edge("ppr", 12, {**FRIEND, "SUPERFLEX": 0})
        # QBs are worth more with the QWRT slot than in his 2-FLEX workaround or a 1-QB league
        self.assertGreater(self.total(friend, "QB"), 1.5 * self.total(flex2, "QB"))
        self.assertGreater(self.total(friend, "QB"), 1.5 * self.total(one_qb, "QB"))
        # the 2-FLEX workaround prices RB/WR/TE higher than the real league, since its extra slot never holds a QB
        for pos in ("RB", "WR", "TE"):
            with self.subTest(pos=pos):
                self.assertLess(self.total(friend, pos), self.total(flex2, pos))


class Paste(unittest.TestCase):
    def test_qb_flex_labels_give_the_count(self):
        script = """
global.window = globalThis;
const LP = require(process.argv[1]);
const block = (labels) => labels.join('\\n');
const out = {
  yahoo12: LP.qbFlexSlots(Array.from({length: 12}, () => block(['QB', 'Josh Allen', 'W/R/T', 'Q/W/R/T', 'Joe Burrow', 'BN'])).join('\\n'), 12),
  two: LP.qbFlexSlots(Array.from({length: 10}, () => block(['OP', 'A', 'SUPERFLEX', 'B'])).join('\\n'), 10),
  md: LP.qbFlexSlots('| Q/W/R/T | Josh Allen | QB |\\n| QWRT | Joe Burrow |', 2),
  none: LP.qbFlexSlots('QB\\nJosh Allen\\nW/R/T\\nBN', 1),
  sfTeam: LP.qbFlexSlots('SF\\nBrock Purdy', 1),
  stray: LP.qbFlexSlots('OP\\n' + Array.from({length: 12}, () => 'QB\\nA\\nBN').join('\\n'), 12),
};
process.stdout.write(JSON.stringify(out));
"""
        out = subprocess.run(["node", "-e", script, str(ROOT / "app" / "next" / "league-paste.js")],
                             capture_output=True, text=True, timeout=30, cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        self.assertEqual(json.loads(out.stdout), {"yahoo12": 1, "two": 2, "md": 1, "none": None, "sfTeam": None, "stray": None})


class SettingsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def page(self, width, path="settings.html"):
        context = self.browser.new_context(viewport={"width": width, "height": 900 if width > 760 else 844})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # off-host requests are aborted above (fonts), so their "Failed to load resource" lines are not page errors
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.errors = errors
        page.goto(f"{self.base}/{path}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls()", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.league", timeout=20000)
        page.evaluate("() => DDF.league.ready")
        return page

    def test_control_render_and_engine(self):
        import re
        for width in (1440, 820, 390):
            with self.subTest(width=width):
                page = self.page(width)
                clipped = page.evaluate("() => [...document.querySelectorAll('.st-slots .stepper')].filter(e => e.scrollWidth > e.clientWidth + 1).length")
                self.assertEqual(clipped, 0, "no stepper is clipped (the + button and the number stay visible)")
                cut = page.evaluate("""() => [...document.querySelectorAll('.st-slots .stepper input')].filter(i => {
                  const old = i.value; i.value = '20'; const bad = i.scrollWidth > i.clientWidth; i.value = old; return bad; }).map(i => i.id)""")
                self.assertEqual(cut, [], "a two-digit count (bench 12, 20) shows in full")
                grid = page.locator(".st-slots > label")
                self.assertEqual([t.split("\n")[0].strip() for t in grid.all_inner_texts()],
                                 ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "Bench", "K", "DEF"],
                                 "two positions in one grid; K and DEF in their own row (JEG-1632)")
                self.assertEqual(page.inner_text("#elig-flex").strip(), "RB, WR or TE")
                self.assertTrue(page.inner_text("#elig-sf").strip().startswith("QB, RB, WR or TE"))
                inp = page.locator("#lineup-sf")
                self.assertEqual(inp.get_attribute("aria-label"), "SUPERFLEX")
                self.assertEqual(inp.get_attribute("aria-describedby"), "elig-sf")
                self.assertEqual(page.locator("#lineup-flex").get_attribute("aria-describedby"), "elig-flex")
                tops = page.evaluate("() => ['qb','flex','sf','bench'].map(k => Math.round(document.getElementById('lineup-' + k).getBoundingClientRect().top))")
                if width > 1100:
                    self.assertEqual(len(set(tops)), 1, f"steppers line up across the row: {tops}")
                boxes = page.evaluate("() => [...document.querySelectorAll('.st-slots .stepper')].map(e => { const r = e.getBoundingClientRect(); return [r.left, r.right, r.top]; })")
                for a, b in zip(boxes, boxes[1:]):
                    if abs(a[2] - b[2]) < 1:
                        self.assertGreaterEqual(b[0] - a[1], 8, f"steppers in a row keep a gap: {a} {b}")
                self.assertEqual((inp.get_attribute("min"), inp.get_attribute("max")), ("0", "2"))
                for name in ("Increase SUPERFLEX", "Decrease SUPERFLEX", "Increase QB", "Increase FLEX"):
                    box = page.get_by_role("button", name=name, exact=True).bounding_box()
                    self.assertGreaterEqual(box["height"], 43.5, name)
                    self.assertGreaterEqual(box["width"], 43.5, name)
                self.assertEqual(page.locator("#superflex").count(), 0, "the yes/no select is replaced by the count")
                self.assertEqual(page.evaluate("() => document.querySelector('details.sf-info').parentElement.id"), "sf-help",
                                 "the SUPERFLEX (i) sits beside the 2-QB note")
                self.assertEqual(page.evaluate("() => [...document.querySelectorAll('#editor p')].filter(p => !p.textContent.trim()).length"), 0)
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                # the friend's league: QB 1, RB 2, WR 2, TE 1, FLEX 1, QWRT 1, bench 12
                for k, v in (("qb", 1), ("rb", 2), ("wr", 2), ("te", 1), ("flex", 1), ("bench", 12)):
                    page.fill(f"#lineup-{k}", str(v))
                    page.dispatch_event(f"#lineup-{k}", "input")
                page.get_by_role("button", name="Increase SUPERFLEX", exact=True).click()
                self.assertEqual(page.input_value("#lineup-sf"), "1")
                # JEG-1632: the starter count includes the 1 K and 1 DEF slots
                self.assertEqual(page.inner_text("#st-total").strip(), "10 starters, 12 bench, 22 roster spots")
                page.get_by_role("button", name="Increase SUPERFLEX", exact=True).click()
                page.get_by_role("button", name="Increase SUPERFLEX", exact=True).click()
                self.assertEqual(page.input_value("#lineup-sf"), "2", "capped at 2")
                self.assertEqual(page.inner_text("#st-total").strip(), "11 starters, 12 bench, 23 roster spots")
                page.evaluate("() => document.getElementById('editor').requestSubmit()")
                roster = page.evaluate("() => DDF.engine.settings().roster")
                self.assertEqual({k: roster[k] for k in FRIEND}, {**FRIEND, "SUPERFLEX": 2})
                self.assertEqual(page.evaluate("() => DDF.league.current() ? DDF.league.current().settings.superflexSlots : DDF.engine.settings().roster.SUPERFLEX"), 2)
                text = page.inner_text("main")
                for pat in BANNED:
                    self.assertIsNone(re.search(pat, text, re.I), pat)
                self.assertEqual(page.errors, [])

    def test_engine_counts_on_the_page(self):
        page = self.page(1440)
        got = page.evaluate("""() => {
          const qbTotal = () => DDF.engine.players().filter(p => p.pos === 'QB' && typeof p.ddf === 'number').reduce((a, p) => a + p.ddf, 0);
          const snap = () => JSON.stringify(DDF.engine.players().map(p => [p.key, p.ddf]));
          DDF.engine.apply({scoring: 'ppr', teams: 12, superflex: true});
          const bool1 = snap(), q1 = qbTotal();
          DDF.engine.apply({superflexSlots: 1});
          const count1 = snap();
          DDF.engine.apply({superflexSlots: 2});
          const q2 = qbTotal(), sf2 = DDF.engine.settings().roster.SUPERFLEX;
          DDF.engine.apply({superflex: false});
          const q0 = qbTotal();
          return {same: bool1 === count1, q0, q1, q2, sf2};
        }""")
        self.assertTrue(got["same"], "superflexSlots 1 prices exactly as superflex: true")
        self.assertEqual(got["sf2"], 2)
        self.assertLess(got["q0"], got["q1"])
        self.assertLess(got["q1"], got["q2"])

    def test_link_round_trip_and_old_links(self):
        page = self.page(1440)
        got = page.evaluate("""async () => {
          const base = {scoring: 'ppr', teams: 12, superflex: true, slots: [1, 2, 2, 1, 1, 12]};
          const st = s => ({v: 1, view: 'team', settings: s, trade: {give: [5], get: [12]}, table: 1});
          const two = await DDF.link.encodeToken(st({...base, superflexSlots: 2}), {pack: true});
          const one = await DDF.link.encodeToken(st(base), {pack: true});
          const d2 = await DDF.link._internal.decodeToken(two), d1 = await DDF.link._internal.decodeToken(one);
          const hdr = t => Array.from(DDF.link._internal.b64ToBytes(t.split('+')[0]).slice(0, 7));
          return {d2: d2.settings, d1: d1.settings, sameHeader: JSON.stringify(hdr(two)) === JSON.stringify(hdr(one)),
                  label2: DDF.link.settingsLabel(d2.settings), label1: DDF.link.settingsLabel(d1.settings),
                  count: [DDF.link.superflexSlots(d2.settings), DDF.link.superflexSlots(d1.settings), DDF.link.superflexSlots({...base, superflex: false})]};
        }""")
        self.assertEqual(got["d2"].get("superflexSlots"), 2)
        self.assertNotIn("superflexSlots", got["d1"], "a one-slot link decodes exactly as before")
        self.assertTrue(got["sameHeader"], "the 7-byte header is the same; 2 slots ride in the JSON body")
        self.assertEqual(got["label1"], "PPR · 12 teams · Superflex")
        self.assertEqual(got["label2"], "PPR · 12 teams · 2 superflex")
        self.assertEqual(got["count"], [2, 1, 0])

    def test_link_with_two_slots_fills_settings(self):
        page = self.page(1440)
        token = page.evaluate("""() => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 12, superflex: true,
            superflexSlots: 2, slots: [1, 2, 2, 1, 1, 12]}})""")
        page.goto(f"{self.base}/settings.html#s={token}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => document.getElementById('lineup-sf').value === '2'", timeout=20000)
        self.assertEqual(page.inner_text("#st-total").strip(), "11 starters, 12 bench, 23 roster spots")


if __name__ == "__main__":
    unittest.main()
