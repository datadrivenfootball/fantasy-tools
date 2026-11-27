"""Draft tool strategy layer (JEG-1667, Phase 0): opponent model, push-floor
candidates, personal inflation, nomination plays (app/draft/draft-engine.js)
and the seeded auction simulator (tools/draft_sim.mjs). Synthetic data only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
WORKED = json.loads((ROOT / "tests" / "fixtures" / "draft_worked_example.json").read_text())["auction"]


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def _cjs(expr):
    js = ("const E=require('./app/draft/draft-engine.js');const W=" + json.dumps(WORKED) + ";"
          "const pos={},ours={},market={};for(const[k,p] of Object.entries(W.players)){pos[k]=p.pos;ours[k]=p.ours;market[k]=p.market}"
          "const st=(o)=>Object.assign({league:W.league,me:'A',teams:W.teams,available:Object.keys(W.players),pos,prices:{ours,market}},o||{});"
          f"process.stdout.write(JSON.stringify({expr}))")
    out = subprocess.run([_node(), "-e", js], capture_output=True, text=True, check=True, cwd=ROOT)
    return json.loads(out.stdout)


class OpponentModel(unittest.TestCase):
    def test_need_factor(self):
        got = _cjs("[E.needFactor({open:{RB:1}},'RB'),E.needFactor({open:{FLEX:1}},'TE'),"
                   "E.needFactor({open:{BN:1}},'QB'),E.needFactor({open:{WR:1}},'QB'),E.needFactor({open:{SUPERFLEX:1}},'QB')]")
        self.assertEqual(got, [1, 1, 0.6, 0, 1])

    def test_rivals_and_cost_to_win(self):
        # P5 (QB): only C has a QB slot; room price = inflated market 19.75.
        m = _cjs("E.opponentModel(st(),'P5')")
        self.assertEqual([r["id"] for r in m["rivals"]], ["C"])
        self.assertAlmostEqual(m["w1"], 19.75)
        pf = _cjs("E.pushFloors(st(),'P5')")
        self.assertEqual(pf["classification"], "fade")
        self.assertAlmostEqual(pf["costToWin"], 20.75)


class PushFloorCandidates(unittest.TestCase):
    def test_candidate_a_is_the_board_rule(self):
        got = _cjs("['P5','P6','P8','P9','P11'].map(k=>E.pushFloors(st({ourFactor:'room'}),k).pushFloor.A)")
        self.assertEqual(got, [13, 8, 3, 5, 1])

    def test_candidate_b_never_above_roster_value(self):
        rows = _cjs("Object.keys(W.players).map(k=>E.pushFloors(st(),k))")
        for r in rows:
            if r["pushFloor"]["B"] is not None:
                self.assertLessEqual(r["pushFloor"]["B"], r["rosterValue"] + 1e-9, r["key"])

    def test_candidate_c_bounds_expected_loss(self):
        rows = _cjs("Object.keys(W.players).map(k=>E.pushFloors(st(),k))")
        for r in rows:
            c = r["pushFloor"]["C"]
            if c is None:
                continue
            self.assertGreaterEqual(c, r["pushFloor"]["B"] or 0, r["key"])
            if r["candidateC"]:
                self.assertLessEqual(r["candidateC"]["expectedLoss"], 1 + 1e-9, r["key"])

    LATE = ("{league:{teams:2,budget:30,minBid:1,slots:{RB:2,WR:1}},me:'us',"
            "teams:[{id:'us',budgetLeft:20,open:{RB:1,WR:1}},{id:'them',budgetLeft:3,open:{RB:1}}],"
            "available:['x'],pos:{x:'RB'},prices:{ours:{x:2},market:{x:2}}}")

    def test_buy_limit_separate_from_push_floor_b(self):
        """Review of f662c66, item 4: in the late probe our buy limit is $4,
        but no rival can top $3, so push floor B stops at $2."""
        pf = _cjs(f"E.pushFloors({self.LATE},'x')")
        self.assertEqual((pf["buyLimit"], pf["pushFloor"]["B"]), (4, 2))

    def test_top_rival_max_bid_is_the_room_max(self):
        # Rival r1 has the highest estimate (need 1) but r2 has more money (bench only).
        st = ("{league:{teams:3,budget:60,minBid:1,slots:{RB:1,BN:2}},me:'us',teams:["
              "{id:'us',budgetLeft:24,open:{RB:1}},{id:'r1',budgetLeft:12,open:{RB:1}},"
              "{id:'r2',budgetLeft:40,open:{BN:1}}],available:['x','y','z'],pos:{x:'RB',y:'RB',z:'RB'},"
              "prices:{ours:{x:10,y:20,z:20},market:{x:10,y:20,z:20}}}")
        # Market factor (24+12+40-3)/(9+19+19) = 1.55: room price for x = $14.98,
        # so r1's estimate is $12 (its max) and r2's is 0.6 x 14.98 = $8.99.
        m = _cjs(f"E.opponentModel({st},'x')")
        self.assertEqual(m["rivals"][0]["id"], "r1")
        self.assertEqual(m["topRivalMaxBid"], 40)

    def test_no_slot_classification(self):
        self.assertEqual(_cjs("E.pushFloors(st(),'P7').classification"), "no slot")

    def test_bench_only_player_worth_half_to_us(self):
        # A has no RB slot and no bench: worth 0 to us. Give A a bench slot only.
        got = _cjs("E.pushFloors(st({ourFactor:'room',teams:[{id:'A',budgetLeft:15,open:{BN:3}},W.teams[1],W.teams[2]]}),'P7')")
        self.assertAlmostEqual(got["rosterValue"], 9.75 * 0.5)
        self.assertEqual(got["buyLimit"], 4)


class PersonalInflation(unittest.TestCase):
    def test_personal_factor_from_money_and_slot_share(self):
        # A: surplus 15 - 3 = 12 of the room's 50; 3 of 8 valued slots.
        # personal = 12 / (40 x 3/8) = 0.8; room factor stays 1.25.
        inf = _cjs("E.inflation(st(),ours)")
        self.assertAlmostEqual(inf["factor"], 1.25)
        self.assertAlmostEqual(inf["personalFactor"], 0.8)
        row = _cjs("E.boardRow(st({ourFactor:'personal'}),'P6')")
        self.assertAlmostEqual(row["oursInflated"], 1 + 9 * 0.8)
        self.assertEqual(row["walkAway"], 8)

    def test_personal_is_the_default_room_on_request(self):
        # Jeremy, 2026-11-27: "Personal by default (Recommended)" (the rule
        # changed, so this assertion flipped from the room factor).
        row = _cjs("E.boardRow(st(),'P6')")
        self.assertEqual((row["ourFactor"], row["walkAway"]), ("personal", 8))
        self.assertAlmostEqual(row["oursInflatedRoom"], 12.25)
        self.assertEqual(_cjs("E.boardRow(st({ourFactor:'room'}),'P6').walkAway"), 12)


class Nominations(unittest.TestCase):
    def test_plays_are_labeled_and_rosterable(self):
        plays = _cjs("E.nominationPlays(st(),{limit:3})")
        self.assertTrue(plays)
        for p in plays:
            self.assertIn(p["play"], {"uncontested", "drain", "endgame", "discovery"})
            self.assertNotEqual(p["key"], "P7")  # we have no RB slot


SIM_JS = """
import { simulate, POLICIES } from './tools/draft_sim.mjs';
const players = {}, ours = {}, market = {}, platform = {}, values = {};
let n = 0;
for (const [pos, count, top] of [['QB', 30, 40], ['RB', 70, 60], ['WR', 90, 58], ['TE', 45, 35]]) {
  for (let i = 0; i < count; i += 1) {
    const k = String(1000 + (n += 1));
    players[k] = { pos, name: pos + i };
    const v = Math.max(0, top * Math.pow(0.93, i) - 1);
    if (v > 0.5) { ours[k] = 1 + v; market[k] = 1 + v * (i % 3 ? 1.05 : 0.9); platform[k] = market[k]; values[k] = v; }
  }
}
const league = { teams: 12, budget: 200, minBid: 1, slots: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 5 } };
const prices = { players, ours, market, platform, values };
const out = POLICIES.map(policy => [0, 1].map(d => simulate({ prices, league, policy, draft: d, seed: 7 })));
const again = simulate({ prices, league, policy: POLICIES[3], draft: 0, seed: 7 });
process.stdout.write(JSON.stringify({ out, again, names: POLICIES.map(p => p.name) }));
"""


class Simulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res = subprocess.run([_node(), "--input-type=module", "-e", SIM_JS], capture_output=True, text=True,
                             check=True, cwd=ROOT)
        cls.data = json.loads(res.stdout)

    def test_every_draft_fills_our_roster_and_spends_within_budget(self):
        for runs in self.data["out"]:
            for r in runs:
                self.assertTrue(r["filled"])
                self.assertGreaterEqual(r["unspent"], 0)

    def test_seeded_runs_repeat_exactly(self):
        self.assertEqual(self.data["again"], self.data["out"][3][0])

    def test_roster_value_bid_never_buys_above_value(self):
        b = self.data["out"][self.data["names"].index("B")]
        self.assertTrue(all(r["aboveValue"] == 0 for r in b))


if __name__ == "__main__":
    unittest.main()
