"""Draft tool 2026 outcome test helper (JEG-1667): tools/draft_outcome.mjs.

realizedPoints sums one season's weeks 1..N for the players asked about and
scales to 17 games; weeks after N, other seasons and other players are left
out, and a player with no rows counts 0.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]

CSV = """season,week,player_key,pos,team,std,half_ppr,ppr
2026,1,10,WR,CIN,10,12,14
2026,2,10,WR,CIN,5,6,7
2026,12,10,WR,CIN,50,50,50
2025,1,10,WR,CIN,99,99,99
2026,1,20,RB,DET,8,9,10
2026,1,30,RB,ATL,40,40,40"""


class RealizedPoints(unittest.TestCase):
    def test_weeks_scaled_to_17(self):
        node = shutil.which("node")
        if node is None:
            if _render_env.required():
                raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
            raise unittest.SkipTest("node not installed")
        js = ("import { realizedPoints } from './tools/draft_outcome.mjs';"
              f"process.stdout.write(JSON.stringify(realizedPoints({json.dumps(CSV)}, 'half_ppr', 2, new Set(['10','20','40']))));")
        out = json.loads(subprocess.run([node, "--input-type=module", "-e", js], capture_output=True, text=True,
                                        check=True, cwd=ROOT).stdout)
        self.assertAlmostEqual(out["10"], (12 + 6) * 17 / 2)
        self.assertAlmostEqual(out["20"], 9 * 17 / 2)
        self.assertEqual(out["40"], 0)
        self.assertNotIn("30", out)


if __name__ == "__main__":
    unittest.main()


class CommonSet(unittest.TestCase):
    """Fourth review of 31faf01: every predictor is scored on one set picked
    by market and realized value only, so the market row cannot move when
    ours's scaling does, and the platform never adds players."""

    def _errors(self, maps):
        node = shutil.which("node")
        if node is None:
            if _render_env.required():
                raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
            raise unittest.SkipTest("node not installed")
        players = {"a": {"pos": "WR"}, "b": {"pos": "WR"}, "c": {"pos": "RB"}, "d": {"pos": "RB"}}
        real = {"a": 30, "b": 1, "c": 12}
        js = ("import { errors } from './tools/draft_outcome.mjs';"
              f"process.stdout.write(JSON.stringify(errors({json.dumps(maps)}, {json.dumps(real)}, {json.dumps(players)}, 1)));")
        return json.loads(subprocess.run([node, "--input-type=module", "-e", js], capture_output=True, text=True,
                                         check=True, cwd=ROOT).stdout)

    def test_market_row_ignores_ours_and_platform(self):
        market = {"a": 25, "b": 8}
        one = self._errors({"ours": {"a": 28}, "market": market, "platform": {"d": 40}})
        two = self._errors({"ours": {"a": 40, "d": 30}, "market": market, "platform": {"a": 20}})
        # a and b (market) and c (realized); d is priced only by ours or the platform.
        self.assertEqual((one["n"], two["n"]), (3, 3))
        self.assertEqual(one["byPredictor"]["market"], two["byPredictor"]["market"])
        self.assertEqual(one["byPredictor"]["market"]["ALL"]["n"], 3)
        self.assertNotEqual(one["byPredictor"]["ours"], two["byPredictor"]["ours"])
