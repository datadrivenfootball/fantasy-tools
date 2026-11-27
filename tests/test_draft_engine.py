"""Draft tool price engine (JEG-1667, Phase 0): app/draft/draft-engine.js.

The worked example (tests/fixtures/draft_worked_example.json, derived by hand
in docs/draft-tool/engine.md) must match to the dollar: inflation, max bid per
team, walk-away price and push floor. Further checks: prices split the whole
budget, scoring and Vegas conversion, rank-to-dollar mapping, and a full
league run through the existing value build (ValueModel.runValuePipeline in
expected-starts mode, the live page's DDF bench share).

Discrimination: test_guard_* mutate the engine (max bid without the $1-per-
slot reserve, push floor without the rival cap, inflation over every
available player) and require the worked example to fail.

Skips when node is missing, unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "app" / "draft" / "draft-engine.js"
DRIVER = ROOT / "tests" / "draft_engine_driver.js"
FIXTURE = ROOT / "tests" / "fixtures" / "draft_worked_example.json"
LINEUP = ROOT / "config" / "lineup_parameters.json"
TOL = 1e-9


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def run(mode, file=FIXTURE, variant=None, driver=DRIVER):
    cmd = [_node(), str(driver), mode, str(file)] + ([variant] if variant else [])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT)
    return json.loads(out.stdout)


def fixture():
    return json.loads(FIXTURE.read_text())


def worked_mismatches(board, expected, rows_only=None):
    """Every expected leaf vs the board; returns a list of mismatch strings."""
    bad = []
    rows = {r["key"]: r for r in board["rows"]}
    exp_rows = expected if rows_only else expected["rows"]
    for key, fields in exp_rows.items():
        for f, want in fields.items():
            got = rows[key][f]
            if want is None or got is None:
                if want is not got:
                    bad.append(f"{key}.{f}: want {want} got {got}")
            elif abs(got - want) > TOL:
                bad.append(f"{key}.{f}: want {want} got {got}")
    if rows_only:
        return bad
    inf = board["inflation"]
    for f in ("moneyLeft", "openSlots", "surplusLeft"):
        if inf["ours"][f] != expected[f]:
            bad.append(f"{f}: want {expected[f]} got {inf['ours'][f]}")
    for side in ("ours", "market"):
        for f, want in expected[side].items():
            if abs(inf[side][f] - want) > TOL:
                bad.append(f"{side}.{f}: want {want} got {inf[side][f]}")
    for team, want in expected["maxBids"].items():
        if board["maxBids"][team] != want:
            bad.append(f"maxBid {team}: want {want} got {board['maxBids'][team]}")
    return bad


class WorkedExample(unittest.TestCase):
    def test_board_matches_hand_check_to_the_dollar(self):
        board = run("worked")
        self.assertEqual(worked_mismatches(board, fixture()["auction"]["expected"]), [])

    def test_rival_cap_variant(self):
        a = fixture()["auction"]
        board = run("worked", variant="variant_rival_cap")
        self.assertEqual(worked_mismatches(board, a["variant_rival_cap"]["expected_rows"], rows_only=True), [])

    def test_pricing_splits_the_whole_budget(self):
        p = fixture()["pricing"]
        out = run("pricing")
        self.assertEqual(set(out["prices"]), set(p["expected_prices"]))
        for k, want in p["expected_prices"].items():
            self.assertAlmostEqual(out["prices"][k], want, places=9)
        shape = out["shape"]
        pool = shape["teams"] * shape["valuedSlotsPerTeam"]
        empty = pool - len(out["prices"])
        self.assertEqual(empty, p["expected_empty_pool_slots"])
        total = sum(out["prices"].values()) + empty * shape["minBid"]
        self.assertAlmostEqual(total, shape["teams"] * shape["budget"], places=9)


class GuardsCatchMutations(unittest.TestCase):
    """Each mutation is a plausible mistake; the worked example must fail."""

    def _mutated(self, old, new, variant=None):
        src = ENGINE.read_text()
        self.assertIn(old, src, "mutation anchor missing; update the guard")
        tmp = Path(tempfile.mkdtemp())
        (tmp / "app" / "draft").mkdir(parents=True)
        (tmp / "app" / "trade-value-chart" / "assets").mkdir(parents=True)
        (tmp / "tests").mkdir()
        (tmp / "app" / "draft" / "draft-engine.js").write_text(src.replace(old, new))
        shutil.copy(ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js",
                    tmp / "app" / "trade-value-chart" / "assets" / "value-model.js")
        shutil.copy(DRIVER, tmp / "tests" / "draft_engine_driver.js")
        return run("worked", variant=variant, driver=tmp / "tests" / "draft_engine_driver.js")

    def test_guard_max_bid_without_slot_reserve(self):
        board = self._mutated("team.budgetLeft - minBid * (open - 1)", "team.budgetLeft")
        self.assertNotEqual(worked_mismatches(board, fixture()["auction"]["expected"]), [])

    def test_guard_push_floor_without_rival_cap(self):
        a = fixture()["auction"]
        board = self._mutated("Math.floor(marketInfl + EPS) - 1, rivalCeiling - 1)",
                              "Math.floor(marketInfl + EPS) - 1)", variant="variant_rival_cap")
        self.assertNotEqual(worked_mismatches(board, a["variant_rival_cap"]["expected_rows"], rows_only=True), [])

    def test_guard_inflation_over_whole_board(self):
        board = self._mutated("avail.slice(0, openValued).reduce", "avail.reduce")
        self.assertNotEqual(worked_mismatches(board, fixture()["auction"]["expected"]), [])


def _league_input(scoring="half", lineup=True):
    """A synthetic 10-team league: 40 QB, 80 RB, 90 WR, 40 TE with a
    decreasing projection, two projection sources and one market."""
    players, p1, p2, mkt = {}, {}, {}, {}
    key = 1000
    for pos, n, top in (("QB", 40, 380.0), ("RB", 80, 300.0), ("WR", 90, 290.0), ("TE", 40, 220.0)):
        for i in range(n):
            key += 1
            k = str(key)
            players[k] = {"pos": pos, "name": f"{pos}{i + 1}"}
            pts = top * (0.985 ** i) - i * 0.6
            p1[k] = pts
            p2[k] = pts * (1.03 if i % 2 else 0.97)
            mkt[k] = max(0.0, 60.0 * (0.94 ** (i * (1.0 if pos in ("RB", "WR") else 1.6))))
    doc = {
        "league": {"teams": 10, "budget": 200, "minBid": 1, "scoring": scoring,
                   "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "K": 1, "DST": 1, "BN": 6}},
        "players": players,
        "projections": {"proj_a": p1, "proj_b": p2},
        "markets": {"market_a": mkt},
    }
    if lineup:
        doc["lineupConfig"] = json.loads(LINEUP.read_text())
    return doc


class FullLeagueBuild(unittest.TestCase):
    def _build(self, **kw):
        tmp = Path(tempfile.mkdtemp()) / "league.json"
        tmp.write_text(json.dumps(_league_input(**kw)))
        return run("build", file=tmp)

    def test_uses_expected_starts_like_the_live_page(self):
        out = self._build()
        self.assertEqual(out["method"], "expected-starts")

    def test_prices_spend_exactly_the_budget(self):
        out = self._build()
        shape = out["shape"]
        pool = shape["teams"] * shape["valuedSlotsPerTeam"]
        priced = len(out["ours"])
        self.assertLessEqual(priced, pool)
        total = sum(out["ours"].values()) + (pool - priced + shape["teams"] * shape["minBidSlotsPerTeam"]) * shape["minBid"]
        self.assertAlmostEqual(total, shape["teams"] * shape["budget"], places=6)
        self.assertTrue(all(v >= shape["minBid"] for v in out["ours"].values()))

    def test_snake_rank_follows_draft_value(self):
        out = self._build()
        order = sorted(out["values"], key=lambda k: out["snake"][k])
        vals = [out["values"][k] for k in order]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_slices_fallback_without_lineup_config(self):
        out = self._build(lineup=False)
        self.assertEqual(out["method"], "slices")


class ScoringAndInputs(unittest.TestCase):
    def _eval(self, expr):
        js = f"const E=require('./app/draft/draft-engine.js');process.stdout.write(JSON.stringify({expr}))"
        out = subprocess.run([_node(), "-e", js], capture_output=True, text=True, check=True, cwd=ROOT)
        return json.loads(out.stdout)

    def test_fantasy_points_by_preset(self):
        stats = {"rec": 100, "rec_yds": 1200, "rec_tds": 8, "rush_yds": 50, "fum_lost": 1}
        # 120 + 48 + 5 - 2 = 171 standard; +50 half; +100 ppr
        got = self._eval(f"['standard','half','ppr'].map(s=>E.fantasyPoints({json.dumps(stats)},s))")
        for g, want in zip(got, (171, 221, 271)):
            self.assertAlmostEqual(g, want, places=9)

    def test_vegas_line_fills_missing_stats_from_projection(self):
        got = self._eval("E.vegasStatLine({season_rec_yds:1100,season_rec_tds:7.5},{rec:90,rec_yds:1000,rec_tds:6,rush_yds:20})")
        self.assertEqual((got["rec"], got["rec_yds"], got["rec_tds"], got["rush_yds"]), (90, 1100, 7.5, 20))
        self.assertIsNone(self._eval("E.vegasStatLine({}, {rec: 90})"))

    def test_rank_implied_dollars(self):
        got = self._eval("E.rankImpliedDollars({x:2,y:1,z:3},[10,40,25])")
        self.assertEqual(got, {"y": 40, "x": 25, "z": 10})

    def test_rescale_keeps_surplus_shares(self):
        # 1 team, $20, 2 slots: surplus 18; raw 31 and 11 -> weights 30, 10 -> 1+13.5, 1+4.5
        got = self._eval("E.rescaleDollars({a:31,b:11,c:1},{teams:1,budget:20,slots:{RB:1,WR:1}})")
        self.assertEqual(got, {"a": 14.5, "b": 5.5})


class NotLive(unittest.TestCase):
    """Hold (Jeremy, 2026-11-16): nothing references the draft engine yet."""

    def test_no_live_page_or_build_references_the_engine(self):
        hits = []
        for base in (ROOT / "dist", ROOT / "app", ROOT / "pipelines"):
            for p in base.rglob("*"):
                if p.is_file() and p.suffix in (".html", ".js", ".py", ".mjs") and "draft" not in p.parts:
                    try:
                        if "draft-engine" in p.read_text(errors="ignore"):
                            hits.append(str(p.relative_to(ROOT)))
                    except OSError:
                        pass
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
