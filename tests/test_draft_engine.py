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


def run(mode, file=FIXTURE, variant=None, driver=DRIVER, factor=None):
    cmd = [_node(), str(driver), mode, str(file)] + ([variant or "-"] if (variant or factor) else []) + \
        ([factor] if factor else [])
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
        board = run("worked", factor="room")
        self.assertEqual(worked_mismatches(board, fixture()["auction"]["expected"]), [])

    def test_default_personal_inflation_matches_hand_check(self):
        """Jeremy, 2026-11-27: "Personal by default (Recommended)". A's
        personal factor is 0.8; the room price stays on the row for reference."""
        exp = fixture()["auction"]["expected_personal"]
        board = run("worked")
        self.assertAlmostEqual(board["inflation"]["ours"]["personalFactor"], exp["personalFactor"])
        self.assertEqual(worked_mismatches(board, exp["rows"], rows_only=True), [])
        self.assertTrue(all(r["ourFactor"] == "personal" for r in board["rows"]))

    def test_rival_cap_variant(self):
        a = fixture()["auction"]
        board = run("worked", variant="variant_rival_cap", factor="room")
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
        return run("worked", variant=variant, driver=tmp / "tests" / "draft_engine_driver.js", factor="room")

    def test_guard_max_bid_without_slot_reserve(self):
        board = self._mutated("team.budgetLeft - minBid * (open - 1)", "team.budgetLeft")
        self.assertNotEqual(worked_mismatches(board, fixture()["auction"]["expected"]), [])

    def test_guard_push_floor_without_rival_cap(self):
        a = fixture()["auction"]
        board = self._mutated("var pb = Math.min(buyLimit, rivalCeiling - minBid);",
                              "var pb = buyLimit;", variant="variant_rival_cap")
        self.assertNotEqual(worked_mismatches(board, a["variant_rival_cap"]["expected_rows"], rows_only=True), [])

    def test_guard_inflation_over_whole_board(self):
        board = self._mutated("avail.slice(0, openValued).reduce", "avail.reduce")
        self.assertNotEqual(worked_mismatches(board, fixture()["auction"]["expected"]), [])


def _stat_line(pos, pts):
    """A stat line worth `pts` half-PPR points (receptions 0): QBs pass,
    RBs rush and catch, WRs and TEs catch."""
    if pos == "QB":
        return {"pass_yds": pts * 25.0}
    if pos == "RB":
        return {"rush_yds": pts * 6.0, "rec_yds": pts * 4.0}
    return {"rec_yds": pts * 10.0}


def _league_input(scoring="standard", lineup=True, bump=None, vegas=None, no_proj=()):
    """A synthetic 10-team league: 40 QB, 80 RB, 90 WR, 40 TE with FantasyPros-
    style stat-line projections and one market. vegas: {key: stat line} props.
    no_proj: keys left out of the projection (market fallback)."""
    players, fp, mkt = {}, {}, {}
    key = 1000
    for pos, n, top in (("QB", 40, 380.0), ("RB", 80, 300.0), ("WR", 90, 290.0), ("TE", 40, 220.0)):
        for i in range(n):
            key += 1
            k = str(key)
            players[k] = {"pos": pos, "name": f"{pos}{i + 1}"}
            pts = top * (0.985 ** i) - i * 0.6
            if bump and k in bump.get("proj", {}):
                pts *= bump["proj"][k]
            if k not in no_proj:
                fp[k] = _stat_line(pos, pts)
            mkt[k] = max(0.0, 60.0 * (0.94 ** (i * (1.0 if pos in ("RB", "WR") else 1.6))))
            if bump and k in bump.get("market", {}):
                mkt[k] *= bump["market"][k]
    doc = {
        "league": {"teams": 10, "budget": 200, "minBid": 1, "scoring": scoring,
                   "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "K": 1, "DST": 1, "BN": 6}},
        "players": players,
        "projections": {"fp": fp},
        "markets": {"market_a": mkt},
    }
    if vegas is not None:
        doc["vegas"] = vegas
    if lineup:
        doc["lineupConfig"] = json.loads(LINEUP.read_text())
    return doc


PROBE_RB = "1061"  # RB20 of the synthetic league: inside the priced pool, not a star


class FullLeagueBuild(unittest.TestCase):
    def _build(self, **kw):
        return self._build_doc(_league_input(**kw))

    def _build_doc(self, doc):
        tmp = Path(tempfile.mkdtemp()) / "league.json"
        tmp.write_text(json.dumps(doc))
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

    def test_lineup_config_is_required(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self._build(lineup=False)

    def test_projection_change_moves_ours(self):
        """Review of f8123a4: on the charts-only basis a 1.6x projection moved
        this RB $0.00."""
        base = self._build()["ours"][PROBE_RB]
        up = self._build(bump={"proj": {PROBE_RB: 1.6}})["ours"][PROBE_RB]
        self.assertGreater(up - base, 3.0)

    # Jeremy, 2026-11-27: "Vegas when available is there, then projections,
    # then market. We are picking by what's available, not averaging."
    def _fp(self):
        return _league_input()["projections"]["fp"]

    def _rb_market(self, fp, probe_mult=None):
        """Props equal to the projection for 20 RBs (so each market's scale
        factor is 1), with the probe RB's lines times probe_mult."""
        players = _league_input()["players"]
        rbs = [k for k in fp if players[k]["pos"] == "RB"][:20]
        if PROBE_RB not in rbs:
            rbs.append(PROBE_RB)
        out = {}
        for k in rbs:
            m = probe_mult if (k == PROBE_RB and probe_mult) else 1.0
            out[k] = {"rush_yds": fp[k]["rush_yds"] * m, "rec_yds": fp[k]["rec_yds"] * m, "covered": ["rush_yds", "rec_yds"]}
        return out

    def test_all_props_present_price_uses_vegas(self):
        fp = self._fp()
        base = self._build()
        out = self._build(vegas=self._rb_market(fp, probe_mult=1.5))
        self.assertEqual(out["source"][PROBE_RB], "vegas")
        self.assertAlmostEqual(out["vegasFactors"]["rush_yds"], 1.0, places=9)
        # The price follows the props, not an average with the projection.
        bumped = self._build(bump={"proj": {PROBE_RB: 1.5}})
        self.assertAlmostEqual(out["ours"][PROBE_RB], bumped["ours"][PROBE_RB], places=6)
        self.assertGreater(out["ours"][PROBE_RB], base["ours"][PROBE_RB])

    # Jeremy, 2026-11-27: "Scale to projections (Recommended)".
    def test_vegas_lines_scaled_to_projection_level(self):
        """Every line exactly 0.9x the projection: the scale factor is 1/0.9,
        so ours equals projections only."""
        fp = self._fp()
        players = _league_input()["players"]
        low = {k: {"rush_yds": fp[k]["rush_yds"] * 0.9, "rec_yds": fp[k]["rec_yds"] * 0.9, "covered": ["rush_yds", "rec_yds"]}
               for k in fp if players[k]["pos"] == "RB"}
        out = self._build(vegas=low)
        self.assertAlmostEqual(out["vegasFactors"]["rush_yds"], 1 / 0.9, places=9)
        self.assertEqual(out["vegasFactorN"]["rush_yds"], len(low))
        base = self._build()["ours"]
        self.assertEqual(set(out["ours"]), set(base))
        self.assertLess(max(abs(out["ours"][k] - base[k]) for k in base), 1e-9)

    def test_unscaled_lines_would_move_ours(self):
        """Discrimination for the scaling test: with scaling off, 0.9x lines
        lower every RB with a prop."""
        fp = self._fp()
        players = _league_input()["players"]
        low = {k: {"rush_yds": fp[k]["rush_yds"] * 0.9, "rec_yds": fp[k]["rec_yds"] * 0.9, "covered": ["rush_yds", "rec_yds"]}
               for k in fp if players[k]["pos"] == "RB"}
        doc = _league_input(vegas=low)
        doc["vegasScale"] = False
        off = self._build_doc(doc)
        self.assertIsNone(off["vegasFactors"])
        base = self._build()["ours"]
        self.assertGreater(max(abs(off["ours"].get(k, 0) - base.get(k, 0)) for k in set(off["ours"]) | set(base)), 0.5)

    def test_partial_props_fill_missing_stats_from_projection(self):
        fp = self._fp()
        rb = fp[PROBE_RB]
        out = self._build(vegas={PROBE_RB: {"rush_yds": rb["rush_yds"], "covered": ["rush_yds"]}})
        self.assertEqual(out["source"][PROBE_RB], "vegas+proj")
        # Rushing from Vegas (equal here) and receiving from the projection:
        # the same line as the projection, so the same price.
        self.assertAlmostEqual(out["ours"][PROBE_RB], self._build()["ours"][PROBE_RB], places=9)

    def test_no_props_uses_projection(self):
        out = self._build(vegas={})
        self.assertEqual(out["source"][PROBE_RB], "proj")
        self.assertEqual(out["counts"]["vegas"] + out["counts"]["vegas+proj"], 0)

    def test_no_projection_uses_market(self):
        out = self._build(no_proj=(PROBE_RB,))
        self.assertEqual(out["source"][PROBE_RB], "market")
        self.assertGreater(out["ours"][PROBE_RB], 1.0)
        # A market change moves him; it does not move a projected player.
        up = self._build(no_proj=(PROBE_RB,), bump={"market": {PROBE_RB: 1.6, "1062": 1.6}})
        self.assertGreater(up["ours"][PROBE_RB] - out["ours"][PROBE_RB], 1.0)
        self.assertAlmostEqual(up["values"]["1062"], out["values"]["1062"], places=9)

    def test_vegas_equal_to_fp_leaves_ours_unchanged(self):
        """Vegas lines equal to the projection price exactly like the
        projection alone (max difference 0)."""
        fp = self._fp()
        some = [k for k in fp if _league_input()["players"][k]["pos"] in ("RB", "WR")][:40]
        vegas = {k: dict(fp[k], covered=list(fp[k])) for k in some}
        a, b = self._build(vegas=vegas)["ours"], self._build()["ours"]
        self.assertEqual(set(a), set(b))
        self.assertEqual(max(abs(a[k] - b[k]) for k in a), 0)

    # Third review (bc19862), item 6: a prop but no projection.
    def test_partial_props_without_projection_use_market(self):
        fp = self._fp()
        wr = "1131"  # WR11
        partial = {wr: {"rec_yds": fp[wr]["rec_yds"], "covered": ["rec_yds"]}}
        out = self._build(no_proj=(wr,), vegas=partial)
        self.assertEqual(out["source"][wr], "market")
        market_only = self._build(no_proj=(wr,))
        self.assertAlmostEqual(out["ours"][wr], market_only["ours"][wr], places=9)

    def test_full_position_props_without_projection_use_vegas(self):
        fp = self._fp()
        wr = "1131"
        full = {wr: {"rec": 90.0, "rec_yds": fp[wr]["rec_yds"], "rec_tds": 7.5, "covered": ["rec", "rec_yds", "rec_tds"]}}
        out = self._build(no_proj=(wr,), vegas=full)
        self.assertEqual(out["source"][wr], "vegas")
        self.assertGreater(out["ours"][wr], 1.0)

    def test_null_in_a_plain_vegas_line_is_missing(self):
        fp = self._fp()
        rb = fp[PROBE_RB]
        with_null = {PROBE_RB: {"rush_yds": rb["rush_yds"], "rec_yds": None, "rush_tds": None}}
        out = self._build(vegas=with_null)
        self.assertEqual(out["source"][PROBE_RB], "vegas+proj")
        self.assertAlmostEqual(out["ours"][PROBE_RB], self._build()["ours"][PROBE_RB], places=9)

    # Item 7: the market fallback lands on the market price.
    def test_market_fallback_maps_dollars_above_the_floor(self):
        """Projected players a and b have DDF values in proportion to their
        market dollars above $1, so market-only c must land on exactly his
        market price. The old whole-dollar mapping gave 11 x 40/42 = 10.48."""
        js = ("const E=require('./app/draft/draft-engine.js');"
              "const v=E.marketFallbackValues({a:30,b:10},{a:31,b:11,c:11},1,k=>k==='c');"
              "const L={teams:1,budget:63,slots:{RB:1,WR:1,TE:1}};"
              "process.stdout.write(JSON.stringify({v:v,ours:E.pricesFromWeights({a:30,b:10,c:v.c},L),mkt:E.rescaleDollars({a:31,b:11,c:11},L)}))")
        out = json.loads(subprocess.run([_node(), "-e", js], capture_output=True, text=True, check=True, cwd=ROOT).stdout)
        self.assertAlmostEqual(out["v"]["c"], 10.0, places=9)
        for k in ("a", "b", "c"):
            self.assertAlmostEqual(out["ours"][k], out["mkt"][k], places=9)

    def test_stale_or_rejected_vegas_falls_back_to_projection(self):
        fp = self._fp()
        props = {PROBE_RB: {"rush_yds": 0.0, "rec_yds": 0.0, "covered": ["rush_yds", "rec_yds"]}}
        base = self._build()["ours"]
        for status in ("stale", "rejected"):
            doc = _league_input(vegas=props)
            doc["vegasStatus"] = status
            out = self._build_doc(doc)
            self.assertEqual(out["source"][PROBE_RB], "proj", status)
            self.assertAlmostEqual(out["ours"][PROBE_RB], base[PROBE_RB], places=9)
            self.assertGreater(out["ours"][PROBE_RB], 1.0)


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


class ReviewCases(unittest.TestCase):
    """Cases from the Opus math review of 2026-11-27 (PR 1556 at f8123a4)."""

    def _eval(self, expr):
        js = f"const E=require('./app/draft/draft-engine.js');process.stdout.write(JSON.stringify({expr}))"
        out = subprocess.run([_node(), "-e", js], capture_output=True, text=True, cwd=ROOT)
        if out.returncode:
            errs = [ln for ln in out.stderr.splitlines() if "Error" in ln]
            return {"error": errs[0] if errs else "failed"}
        return json.loads(out.stdout)

    LATE = ("{league:{teams:2,budget:30,minBid:1,slots:{RB:2,WR:1}},me:'us',"
            "teams:[{id:'us',budgetLeft:20,open:{RB:1,WR:1}},{id:'them',budgetLeft:3,open:{RB:1}}],"
            "available:['x'],pos:{x:'RB'},prices:{ours:{x:2},market:{x:2}}}")

    def test_late_draft_walk_away_capped_by_rival_max(self):
        """Finding 2: $20 and 2 open slots vs a rival with $3 for 1 slot, one $2
        player left. Factor is 20 and inflated ours is $21, but no rival can
        bid past $3, so walk-away is $4 and the push floor is $2."""
        b = self._eval(f"E.board({self.LATE})")
        self.assertAlmostEqual(b["inflation"]["ours"]["factor"], 20)
        row = b["rows"][0]
        self.assertEqual((row["walkAway"], row["pushFloor"], row["rivalCeiling"]), (4, 2, 3))

    def test_walk_away_one_dollar_when_no_rival_can_roster(self):
        st = self.LATE.replace("open:{RB:1}}", "open:{WR:0}}")
        row = self._eval(f"E.board({st}).rows[0]")
        self.assertEqual((row["walkAway"], row["pushFloor"]), (1, None))

    def test_walk_away_one_dollar_outside_priced_pool(self):
        st = self.LATE.replace("ours:{x:2}", "ours:{}")
        self.assertEqual(self._eval(f"E.board({st}).rows[0].walkAway"), 1)

    def test_plain_count_open_is_refused(self):
        st = self.LATE.replace("open:{RB:1,WR:1}", "open:2")
        self.assertIn("per-slot", self._eval(f"E.board({st})").get("error", ""))

    def test_ir_slot_is_not_a_draft_slot(self):
        self.assertEqual(self._eval("E.maxBid({budgetLeft:10,open:{BN:2,IR:1}},{teams:1,budget:10,slots:{BN:2}})"), 9)

    def test_inflation_is_one_at_draft_start_with_k_and_dst(self):
        """Finding 3: K and DST slots are $1 slots, not valued ones."""
        js = ("(()=>{const L={teams:2,budget:20,minBid:1,slots:{RB:1,WR:1,K:1,DST:1}};"
              "const w={a:9,b:7,c:5,d:3,e:1};const p=E.pricesFromWeights(w,L);"
              "const o=()=>({RB:1,WR:1,K:1,DST:1});"
              "return E.inflation({league:L,teams:[{id:1,budgetLeft:20,open:o()},{id:2,budgetLeft:20,open:o()}],"
              "available:Object.keys(w),pos:{a:'RB',b:'WR',c:'RB',d:'WR',e:'RB'}},p).factor})()")
        self.assertAlmostEqual(self._eval(js), 1.0, places=9)

    def test_slot_eligibility(self):
        cases = [("{FLEX:1}", "RB", True), ("{FLEX:1}", "TE", True), ("{FLEX:1}", "QB", False),
                 ("{SUPERFLEX:1}", "QB", True), ("{SUPERFLEX:1}", "WR", True), ("{BN:1}", "QB", True),
                 ("{WR:1}", "RB", False), ("{K:1}", "K", True), ("{K:1}", "RB", False), ("{IR:2}", "RB", False)]
        for open_, pos, want in cases:
            self.assertEqual(self._eval(f"E.canRoster({{open:{open_}}},'{pos}')"), want, (open_, pos))

    def test_pool_is_exactly_teams_times_valued_slots(self):
        """1 team, $10, RB + WR (+ K, not valued): pool 2, surplus 10 - 3 = 7.
        x = 1 + 3/5 x 7 = 5.2, y = 1 + 2/5 x 7 = 3.8, z unpriced. A pool one
        too large would price z and give x 1 + 3/6 x 7 = 4.5."""
        got = self._eval("E.pricesFromWeights({x:3,y:2,z:1},{teams:1,budget:10,slots:{RB:1,WR:1,K:1}})")
        self.assertEqual(set(got), {"x", "y"})
        self.assertAlmostEqual(got["x"], 5.2, places=9)
        self.assertAlmostEqual(got["y"], 3.8, places=9)

    def test_yahoo_presets_differ_only_on_interceptions(self):
        got = self._eval("['half','yahoo_half'].map(s=>E.fantasyPoints({ints:10,rec:10},s))")
        self.assertEqual(got, [-15, -5])


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
