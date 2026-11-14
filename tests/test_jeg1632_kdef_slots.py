"""JEG-1632: kicker and defense slots in League settings (not valued, but they take roster spots).

Jeremy, 2026-11-13: "League settings needs to allow for inputting defense and kicker, even if we don't score them, as
they take up roster space. We need to factor this in."

Audit (see the JEG-1632 log entry): the JEG-1539 swap dropped the K and DEF steppers the old page had (JEG-565). The
engine still holds K and DST in its roster shape (curve-widget.js, 0-3, default 1 and 1), and the roster-space rules
read them: waivers rosterSizeOf (open roster spots) and isRequiredSpecial (a required kicker or defense is not offered
as a drop). The value engine does not: value-model.js and value_reference.py price QB/RB/WR/TE with bench seats =
teams x Bench, so a K or DEF slot never moves a value (JEG-563 default-roster-001). Whether it should is a decision
left on the ticket.

What is pinned here:
  * Convention twins: roster_convention.py and roster-convention.js give the same bench seats at every K / DEF count.
  * Roster space: a K or DEF slot changes the league's roster spots, the open spots a waiver pickup can fill, and
    which kicker or defense is a drop candidate (v2/waivers.js, used by find.html, waivers.html, team.html).
  * Settings > K and DEF counts (0-3, 44px steppers, "Not evaluated"), counted in "N starters, M bench, T roster
    spots", saved to the engine and ddf.v2.league-settings, at 1440 and 375 with no page overflow.
  * Values are unchanged: every engine row is identical at K / DEF 0, 1 and 3.
  * Link: kdef [k, def] rides in the JSON body only when it is not 1 and 1; a 1 / 1 link and an old link decode as
    before (same 7-byte header, no field), and a link with kdef fills the Settings inputs.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT))

from lib.roster_convention import DEFAULT_SLOTS, POSITIONS, bench_seats  # noqa: E402
from tests import _render_env  # noqa: E402

SKILL = ("QB", "RB", "WR", "TE")


def node(script: str, *args: str) -> object:
    out = subprocess.run(["node", "-e", script, *args], capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    if out.returncode != 0:
        raise AssertionError(out.stderr[-800:])
    return json.loads(out.stdout)


class ConventionTwins(unittest.TestCase):
    """roster_convention.py and roster-convention.js agree on bench seats at every K / DEF slot count."""

    def test_bench_seats_parity_at_every_kdef_count(self):
        cfg = json.loads((ROOT / "config" / "market_bench.json").read_text())
        cases = [(teams, k, d, sf) for teams in (8, 10, 12, 14) for k in range(4) for d in range(4) for sf in (False, True)]
        script = """
const RC = require('./app/trade-value-chart/assets/roster-convention.js').RosterConvention;
const cfg = JSON.parse(process.argv[1]), cases = JSON.parse(process.argv[2]), base = JSON.parse(process.argv[3]);
process.stdout.write(JSON.stringify(cases.map(([teams, k, d, sf]) => {
  const slots = Object.assign({}, base, {K: k, DEF: d});
  return RC.benchSeats(slots, teams, 7, RC.marketBenchRatios(cfg, {superflex: sf, qbSlots: slots.QB}));
})));
"""
        js = node(script, json.dumps(cfg), json.dumps(cases), json.dumps(DEFAULT_SLOTS))
        for (teams, k, d, sf), got in zip(cases, js):
            with self.subTest(teams=teams, K=k, DEF=d, superflex=sf):
                py = bench_seats({**DEFAULT_SLOTS, "K": k, "DEF": d}, teams, 7, superflex=sf)
                self.assertEqual({p: got[p] for p in POSITIONS}, py)
                self.assertEqual(sum(py.values()), teams * 7, "the league's bench seats are teams x Bench")


WAIVERS = """
const W = require('./app/v2/waivers.js');
const shape = (k, d) => ({QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7, K: k, DST: d});
const skill = n => Array.from({length: n}, (_, i) => ({name: 'P' + i, pos: ['QB', 'RB', 'WR', 'TE'][i % 4], key: String(i + 1)}));
const kicker = {name: 'K1', pos: 'K', key: 'x:K:1'}, def1 = {name: 'D1', pos: 'DEF', key: 'x:DEF:1'}, def2 = {name: 'D2', pos: 'DEF', key: 'x:DEF:2'};
// 14 skill players (7 starters + 7 bench) and one defense, no kicker
const team = skill(14).concat([def1]);
const twoDef = skill(13).concat([kicker, def1, def2]);
const size = (k, d) => W.rosterSizeOf(shape(k, d));
process.stdout.write(JSON.stringify({
  size: [size(0, 0), size(1, 1), size(0, 1), size(3, 3)],
  open: [W.openSlots(team, size(0, 1)), W.openSlots(team, size(1, 1))],
  secondDefRequired: [W.isRequiredSpecial(def2, twoDef, shape(1, 1)), W.isRequiredSpecial(def2, twoDef, shape(1, 2))],
  kickerRequired: [W.isRequiredSpecial(kicker, twoDef, shape(0, 1)), W.isRequiredSpecial(kicker, twoDef, shape(1, 1))],
}));
"""


class RosterSpace(unittest.TestCase):
    """A K or DEF slot changes roster spots, open spots for a pickup, and kicker / defense drops (v2/waivers.js)."""

    @classmethod
    def setUpClass(cls):
        cls.got = node(WAIVERS)

    def test_roster_spots_count_k_and_def(self):
        # 7 skill starters + 7 bench, plus each K and DEF slot
        self.assertEqual(self.got["size"], [14, 16, 15, 20])

    def test_open_spot_for_a_pickup(self):
        # no kicker slot: 15 spots, 15 held, so a pickup needs a drop; with a K slot one spot is open (the kicker's)
        self.assertEqual(self.got["open"], [0, 1])

    def test_second_defense_is_a_drop_only_with_one_def_slot(self):
        self.assertEqual(self.got["secondDefRequired"], [False, True])
        self.assertEqual(self.got["kickerRequired"], [False, True])


class SettingsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
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
        context = self.browser.new_context(viewport={"width": width, "height": 900 if width > 760 else 812})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.errors = errors
        page.goto(f"{self.base}/{path}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls()", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.league", timeout=20000)
        page.evaluate("() => DDF.league.ready")
        return page

    def test_inputs_render_save_and_persist(self):
        for width in (1440, 375):
            with self.subTest(width=width):
                page = self.page(width)
                for k, name in (("k", "K"), ("def", "DEF")):
                    inp = page.locator(f"#lineup-{k}")
                    self.assertEqual(inp.input_value(), "1", "default 1 K and 1 DEF")
                    self.assertEqual((inp.get_attribute("min"), inp.get_attribute("max")), ("0", "3"))
                    self.assertEqual(inp.get_attribute("aria-label"), name)
                    self.assertEqual(page.inner_text(f"#elig-{k}").strip(), "Not evaluated")
                    for b in (f"Increase {name}", f"Decrease {name}"):
                        box = page.get_by_role("button", name=b, exact=True).bounding_box()
                        self.assertGreaterEqual(min(box["height"], box["width"]), 43.5, b)
                self.assertEqual(page.inner_text("#st-total").strip(), "9 starters, 7 bench, 16 roster spots")
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                clipped = page.evaluate("() => [...document.querySelectorAll('.st-slots .stepper')].filter(e => e.scrollWidth > e.clientWidth + 1).length")
                self.assertEqual(clipped, 0)
                page.get_by_role("button", name="Decrease K", exact=True).click()
                for _ in range(3):
                    page.get_by_role("button", name="Increase DEF", exact=True).click()
                self.assertEqual((page.input_value("#lineup-k"), page.input_value("#lineup-def")), ("0", "3"), "DEF capped at 3")
                self.assertEqual(page.inner_text("#st-total").strip(), "10 starters, 7 bench, 17 roster spots")
                page.evaluate("() => document.getElementById('editor').requestSubmit()")
                roster = page.evaluate("() => DDF.engine.settings().roster")
                self.assertEqual((roster["K"], roster["DST"], roster["BENCH"]), (0, 3, 7))
                saved = page.evaluate("() => JSON.parse(localStorage.getItem('ddf.v2.league-settings')).roster")
                self.assertEqual((saved["K"], saved["DST"]), (0, 3), "saved with the reader's league settings")
                page.reload(wait_until="networkidle")
                page.wait_for_function("() => window.DDF && DDF.league", timeout=20000)
                page.evaluate("() => DDF.league.ready")
                page.wait_for_function("() => document.getElementById('lineup-def').value === '3'", timeout=20000)
                self.assertEqual(page.input_value("#lineup-k"), "0", "the saved settings fill the form again")
                self.assertEqual(page.errors, [])

    def test_k_and_def_slots_never_move_a_value(self):
        page = self.page(1440)
        got = page.evaluate("""() => {
          const snap = () => JSON.stringify(DDF.engine.players().map(p => [p.key, p.ddf]));
          DDF.engine.apply({roster: {K: 1, DST: 1}});
          const base = snap();
          DDF.engine.apply({roster: {K: 0, DST: 0}});
          const none = snap();
          DDF.engine.apply({roster: {K: 3, DST: 3}});
          const three = snap(), r = DDF.engine.settings().roster;
          return {n: DDF.engine.players().length, same: base === none && base === three, k: r.K, d: r.DST};
        }""")
        self.assertGreater(got["n"], 100)
        self.assertEqual((got["k"], got["d"]), (3, 3))
        self.assertTrue(got["same"], "K and DEF are not valued: every DDF Value is the same at 0, 1 and 3 slots")

    def test_link_round_trip_and_old_links(self):
        page = self.page(1440)
        got = page.evaluate("""async () => {
          const base = {scoring: 'ppr', teams: 12, superflex: false, slots: [1, 2, 2, 1, 1, 7]};
          const st = s => ({v: 1, view: 'team', settings: s, trade: {give: [5], get: [12]}, table: 1});
          const kd = await DDF.link.encodeToken(st({...base, kdef: [0, 2]}), {pack: true});
          const one = await DDF.link.encodeToken(st({...base, kdef: [1, 1]}), {pack: true});
          const old = await DDF.link.encodeToken(st(base), {pack: true});
          const dec = t => DDF.link._internal.decodeToken(t);
          const hdr = t => JSON.stringify(Array.from(DDF.link._internal.b64ToBytes(t.split('+')[0]).slice(0, 7)));
          const [dk, d1, dold] = [await dec(kd), await dec(one), await dec(old)];
          return {dk: dk.settings, d1: d1.settings, dold: dold.settings, sameToken: one === old, sameHeader: hdr(kd) === hdr(old),
                  slots: [DDF.link.kdefSlots(dk.settings), DDF.link.kdefSlots(dold.settings)]};
        }""")
        self.assertEqual(got["dk"].get("kdef"), [0, 2])
        self.assertNotIn("kdef", got["d1"])
        self.assertNotIn("kdef", got["dold"])
        self.assertTrue(got["sameToken"], "a 1 K / 1 DEF league writes exactly the old token")
        self.assertTrue(got["sameHeader"], "kdef rides in the JSON body; the 7-byte header is unchanged")
        self.assertEqual(got["slots"], [{"K": 0, "DST": 2}, {"K": 1, "DST": 1}])

    def test_link_with_kdef_fills_settings_and_engine(self):
        page = self.page(375)
        token = page.evaluate("""() => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 12,
            superflex: false, slots: [1, 2, 2, 1, 1, 6], kdef: [2, 0]}})""")
        page.goto(f"{self.base}/settings.html#s={token}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => document.getElementById('lineup-k').value === '2'", timeout=20000)
        self.assertEqual(page.input_value("#lineup-def"), "0")
        self.assertEqual(page.inner_text("#st-total").strip(), "9 starters, 6 bench, 15 roster spots")
        page.wait_for_function("() => window.DDF && DDF.league", timeout=20000)
        page.evaluate("() => DDF.league.ready")
        roster = page.evaluate("() => DDF.engine.settings().roster")
        self.assertEqual((roster["K"], roster["DST"]), (2, 0), "a link's league applies its K and DEF slots")


if __name__ == "__main__":
    unittest.main()
