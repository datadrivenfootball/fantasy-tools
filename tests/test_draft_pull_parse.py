"""Draft tool daily pull parsers (JEG-1667): supabase/functions/draft-pull/parse.js.

Synthetic pages only (no third-party content in the repo). The parsers must
keep the season the source states and fail closed on another season, another
format, or a short table, so 2026 data is never labeled anything else.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def _run(js):
    code = ("import * as P from './supabase/functions/draft-pull/parse.js';"
            "const out = (() => { try { return {ok: " + js + "}; } catch (e) { return {error: String(e.message)}; } })();"
            "process.stdout.write(JSON.stringify(out));")
    res = subprocess.run([_node(), "--input-type=module", "-e", code], capture_output=True, text=True,
                         check=True, cwd=ROOT)
    return json.loads(res.stdout)


def _page(year=2026, scoring="STD", n=160, rtype="draft"):
    players = [{"player_id": i, "player_name": f"Player {i}", "player_position_id": "RB", "player_team_id": "DET",
                "player_bye_week": "6", "rank_ecr": i, "pos_rank": f"RB{i}", "tier": 1, "rank_std": "1.5"}
               for i in range(1, n + 1)]
    d = {"year": str(year), "scoring": scoring, "ranking_type_name": rtype, "last_updated_ts": 1788999551,
         "note": "brace } and quote \" inside a string", "players": players}
    return "<script>var ecrData = " + json.dumps(d) + ";\nvar other = {};</script>"


class FantasyProsEcr(unittest.TestCase):
    def test_parses_rows_with_stated_season(self):
        out = _run(f"P.parseFpEcr({json.dumps(_page())}, 'STD', 2026)")["ok"]
        self.assertEqual(out["season"], 2026)
        self.assertEqual(len(out["rows"]), 160)
        row = out["rows"][0]
        self.assertEqual((row["season"], row["scoring"], row["rank_overall"], row["bye"]), (2026, "STD", 1, 6))
        self.assertEqual(out["sourceUpdatedAt"], "2026-09-10T00:19:11.000Z")

    def test_fails_closed(self):
        for page, why in ((_page(year=2027), "season 2027"), (_page(scoring="PPR"), "scoring PPR"),
                          (_page(n=20), "only 20"), (_page(rtype="weekly"), "ranking type weekly"),
                          ("<html></html>", "ecrData not found")):
            out = _run(f"P.parseFpEcr({json.dumps(page)}, 'STD', 2026)")
            self.assertIn(why, out.get("error", ""), why)


class Espn(unittest.TestCase):
    def test_two_formats_per_player(self):
        players = [{"player": {"id": i, "fullName": f"P{i}", "defaultPositionId": 3, "proTeamId": 8,
                               "draftRanksByRankType": {"STANDARD": {"rank": i, "auctionValue": 40},
                                                        "PPR": {"rank": i, "auctionValue": 42}},
                               "ownership": {"auctionValueAverage": 38.5, "averageDraftPosition": 12.1}}}
                   for i in range(1, 161)]
        out = _run(f"P.parseEspn({json.dumps({'players': players})}, 2026)")["ok"]
        self.assertEqual(len(out["rows"]), 320)
        std = [r for r in out["rows"] if r["scoring"] == "STD"][0]
        self.assertEqual((std["season"], std["dollars"], std["aav"], std["team"], std["pos"]), (2026, 40, 38.5, "DET", "WR"))

    def test_short_list_fails(self):
        self.assertIn("only", _run("P.parseEspn({players: []}, 2026)")["error"])


if __name__ == "__main__":
    unittest.main()
