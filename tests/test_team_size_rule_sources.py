"""Every reader of a team count uses the same rule (Jeremy, 2026-11-24): a count between the sizes the values run
(8, 10, 12, 14) rounds up, below 8 uses 8, above 14 uses 14.

The rule lives in several small readers: the Sleeper import, the paste reader and four page-link readers. This runs
each one's rule on the same counts in node and checks they agree, so one cannot drift from the others.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

NEXT = Path(__file__).resolve().parents[1] / "app" / "next"
COUNTS = [2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 32]
WANT = [8, 8, 8, 8, 10, 10, 12, 12, 14, 14, 14, 14, 14, 14]
# the expression each page-link reader uses, as it appears in the file (teams/t/n is the count read from the link)
LINK_READERS = {
    "ddf-engine.js": r"\[8, 10, 12, 14\]\.filter\(function \(t\) \{ return t >= teams; \}\)\[0\] \|\| 14",
    "build-trade.js": r"\[8, 10, 12, 14\]\.find\(t => t >= teams\) \|\| 14",
    "learn/numbers/numbers.js": r"\[8, 10, 12, 14\]\.filter\(function \(x\) \{ return x >= t; \}\)\[0\] \|\| 14",
    "legacy-routes.js": r"TEAMS_ALLOWED\.filter\(function \(t\) \{ return t >= n; \}\)\[0\] \|\| 14",
}


def node(js: str):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TeamSizeRuleTest(unittest.TestCase):

    def test_sleeper_import_rounds_up(self):
        got = node(f"""
            global.window = global; global.DDF = {{}};
            const S = require({json.dumps(str(NEXT / 'sleeper-import.js'))});
            console.log(JSON.stringify({json.dumps(COUNTS)}.map(n => S.settingsOf({{total_rosters: n, roster_positions: ['QB'], scoring_settings: {{rec: 1}}}}).teams)));""")
        self.assertEqual(got, WANT)

    def test_espn_import_rounds_up(self):
        got = node(f"""
            global.window = global; global.DDF = {{}};
            const E = require({json.dumps(str(NEXT / 'espn-import.js'))});
            console.log(JSON.stringify({json.dumps(COUNTS)}.map(n => E.settingsOf({{settings: {{size: n, rosterSettings: {{lineupSlotCounts: {{"0": 1}}}}}}}}).teams)));""")
        self.assertEqual(got, WANT)

    def test_paste_reader_rounds_up_from_six(self):
        got = node(f"""
            global.window = global;
            require({json.dumps(str(NEXT / 'league-paste.js'))});
            const LP = global.DDF.leaguePaste;
            const league = n => ({{teams: Array.from({{length: n}}, (_, i) => ({{name: 'T' + i, players: [{{line: 'a' + i}}], unmatched: []}}))}});
            console.log(JSON.stringify({json.dumps(COUNTS)}.map(n => LP.inferSettings('', league(n)).teams)));""")
        self.assertEqual(got, [None, None] + WANT[2:12] + [14, None], "2 to 5 teams read ask; 6 to 20 round up; more than 20 asks")

    def test_page_link_readers_share_the_rule(self):
        for f, pattern in LINK_READERS.items():
            with self.subTest(file=f):
                src = (NEXT / f).read_text(encoding="utf-8")
                self.assertRegex(src, pattern, f"{f} no longer rounds a link's team count up")
                expr = re.search(pattern, src).group(0).replace("TEAMS_ALLOWED", "[8, 10, 12, 14]")
                var = {"ddf-engine.js": "teams", "build-trade.js": "teams", "learn/numbers/numbers.js": "t", "legacy-routes.js": "n"}[f]
                got = node(f"console.log(JSON.stringify({json.dumps(COUNTS)}.map({var} => {expr})))")
                self.assertEqual(got, WANT)


if __name__ == "__main__":
    unittest.main()
