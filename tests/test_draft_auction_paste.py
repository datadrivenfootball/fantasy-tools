"""Pasted auction draft results (JEG-1667; Jeremy, 2026-11-27: "Paste USO
XVIII"): app/draft/auction-paste.js and tools/draft_auction_paste.mjs.

Player matching is the live roster matcher (app/v2/roster-paste.js). The
invented sample mixes a one-line-per-sale table (tabs, pick numbers, manager
names, a keeper mark) and a sale spread over several lines, with a kicker,
a defense and a nickname.
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
FIX = ROOT / "tests" / "fixtures" / "draft_auction_paste"
SAMPLE = (FIX / "sample_ok.txt").read_text()
PLAYERS = json.loads((FIX / "players.json").read_text())
LEAGUE = ROOT / "tools" / "draft_leagues" / "uso-season-xviii-2026.json"


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def parse(text):
    js = ("const A=require('./app/draft/auction-paste.js');"
          f"process.stdout.write(JSON.stringify(A.parse({json.dumps(text)},{json.dumps(PLAYERS)},{{budget:200}})))")
    return json.loads(subprocess.run([_node(), "-e", js], capture_output=True, text=True, check=True, cwd=ROOT).stdout)


class ReadsTheSample(unittest.TestCase):
    def test_sales_costs_and_keepers(self):
        r = parse(SAMPLE)
        self.assertTrue(r["ok"], r["errors"])
        got = {s["key"]: (s["price"], s["keeper"]) for s in r["sales"]}
        self.assertEqual(got, {"202": (70, False), "201": (68, False), "301": (65, True), "302": (52, False),
                               "102": (31, False), "203": (1, False)})
        self.assertEqual([k["price"] for k in r["kdef"]], [2, 1])
        self.assertEqual(r["total"], 290)


class FailsClosed(unittest.TestCase):
    def _bad(self, extra, why):
        r = parse(SAMPLE + "\n" + extra)
        self.assertFalse(r["ok"])
        self.assertTrue(any(why in e["reason"] for e in r["errors"]), r["errors"])

    def test_unknown_player(self):
        self._bad("9\tZed Unknownson Det - WR\tTeam Six\t$12", "unknown player: Zed Unknownson")

    def test_cost_with_no_player(self):
        self._bad("Team Six\n$12", "cost with no player")

    def test_sold_twice(self):
        self._bad("9\tJosh Allen Buf - QB\tTeam Six\t$12", "sold twice")

    def test_missing_cost(self):
        self._bad("Josh Allen\nBuf - QB\nTeam Six", "no cost")

    def test_cost_over_budget(self):
        self._bad("9\tJosh Allen Buf - QB\tTeam Six\t$250", "outside")


class Tool(unittest.TestCase):
    def _run(self, text):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "paste.txt").write_text(text)
        players = [{"key": p["player_key"], "name": p["name"], "pos": p["pos"], "team": p["team"]} for p in PLAYERS]
        (tmp / "players.json").write_text(json.dumps(players))
        out = subprocess.run([_node(), "tools/draft_auction_paste.mjs", "--in", str(tmp / "paste.txt"),
                              "--players", str(tmp / "players.json"), "--league", str(LEAGUE),
                              "--out", str(tmp / "uso.json")], capture_output=True, text=True, cwd=ROOT)
        return out, tmp / "uso.json"

    def test_writes_backtest_auction_file_without_team_names(self):
        out, f = self._run(SAMPLE)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = json.loads(f.read_text())
        self.assertEqual(len(rows), 6)
        self.assertEqual(set(rows[0]), {"name", "price", "keeper"})
        self.assertNotIn("Team", f.read_text())
        # 12 teams x 15 slots (QB, 2 RB, 3 WR, TE, FLEX, K, DEF, 5 BN).
        self.assertIn("Check: 8 sales read; a full draft is 180", out.stdout)

    def test_refuses_on_error(self):
        out, f = self._run(SAMPLE + "\nTeam Six\n$12")
        self.assertEqual(out.returncode, 1)
        self.assertFalse(f.exists())


if __name__ == "__main__":
    unittest.main()
