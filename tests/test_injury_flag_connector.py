"""Injury flags in the connector (Jeremy, 2026-11-22: "It is a flag, not a stopper").

tests/node/injury_flag_connector_check.mjs runs the deployed get-values handler on the built dist/ with the daily
Sleeper status copy swapped for a test copy, and the MCP tools on its answers:
- parity: get-values/injury.ts flags exactly what the site flags (app/next/injury-flag.js through app/v2/waivers.js);
- get-values: flagged players carry `injury`; every value, the order and every other field are unchanged; a missing
  or stale copy flags nobody;
- find_trades_league, find_trades, compare_trade and trade_targets on the USO 10-29 league (Team 3) give the same
  answer with half the players flagged as with no status copy, once the tags and "Injury flag:" lines are taken out,
  including how many trades are shown (the reply budget does not count the flags).
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ["node", "--experimental-strip-types", "--no-warnings"]


class InjuryFlagConnectorTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_flags_change_no_answer(self):
        if not (ROOT / "dist" / "index.html").exists():
            self.skipTest("dist/ not built")
        out = subprocess.run(NODE + [str(ROOT / "tests/node/injury_flag_connector_check.mjs"), str(ROOT / "dist")],
                             capture_output=True, text=True, timeout=600, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stdout[-4000:] + out.stderr[-4000:])
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
