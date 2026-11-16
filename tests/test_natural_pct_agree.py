"""JEG-1639: the Natural fit label and the Why text's roster percent never disagree.

Decision (Jeremy, 2026-11-14, "A"): Natural fit also requires their roster change to be better than -3% (not "clearly
worse"), on the same measure and rounding as the Why text (ddf-opportunity.js rosterImprovementPct, which wraps
finder.js rosterChangePct). tests/node/natural_pct_agree_check.cjs judges every trade findTrades lists over the league
fixtures both ways. Discrimination: the same run on a finder.js without the new test must fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests/node/natural_pct_agree_check.cjs"
FINDER = ROOT / "app/v2/finder.js"
OPP = ROOT / "app/next/ddf-opportunity.js"
FIX = ROOT / "tests/fixtures/league"


def run(finder: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(SCRIPT), str(finder), str(OPP), str(FIX)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


class NaturalPctAgreeTests(unittest.TestCase):
    def test_label_and_text_agree(self):
        got = run(FINDER)
        self.assertEqual(got["failures"], [])
        # Not vacuous: the fixtures hold Natural fits, clearly-worse trades, and trades the new test moves out of Natural.
        self.assertGreater(got["natural"], 0)
        self.assertGreater(got["clearlyWorse"], 0)
        self.assertGreater(got["wouldBeNatural"], got["natural"])

    def test_fails_without_the_new_test(self):
        source = FINDER.read_text(encoding="utf-8")
        old = 'const pctOk = !(pct && pct.band === "clearly_worse");'
        self.assertIn(old, source)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "finder.js"
            path.write_text(source.replace(old, "const pctOk = true;", 1), encoding="utf-8")
            got = run(path)
        self.assertTrue(any("Natural fit but the Why text says" in f for f in got["failures"]))


if __name__ == "__main__":
    unittest.main()
