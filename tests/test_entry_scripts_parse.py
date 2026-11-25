"""Every script on the league-entry pages parses (node --check), so a merge that drops a brace fails here, not live.

The league-entry changes (Jeremy, 2026-11-20) land as separate PRs that edit the same files (connect-entry.js,
connect.html, settings.html). A hand-merged "keep both" can drop a shared closing brace and still look clean in a diff:
a syntax error in connect-entry.js stops the whole connect page. This checks every app/next/*.js file and every inline
<script> in the entry pages with node --check. No browser needed.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

NEXT = Path(__file__).resolve().parents[1] / "app" / "next"
PAGES = ("connect.html", "setup.html", "settings.html", "index.html", "team.html")
INLINE = re.compile(r"<script(\s+type=\"module\")?>(.*?)</script>", re.S)


def check(path: Path) -> str:
    proc = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=60)
    if proc.returncode == 0:
        return ""
    lines = proc.stderr.strip().splitlines()
    where = next((l for l in lines if ":" in l and l.strip().startswith("/")), "")
    what = next((l for l in lines if "Error" in l), "syntax error")
    return f"{what} ({where.rsplit('/', 1)[-1]})" if where else what


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class EntryScriptsParseTest(unittest.TestCase):

    def test_app_next_scripts_parse(self):
        bad = {p.name: err for p in sorted(NEXT.glob("*.js")) if (err := check(p))}
        self.assertEqual(bad, {})

    def test_inline_scripts_on_the_entry_pages_parse(self):
        bad = {}
        with tempfile.TemporaryDirectory() as tmp:
            for page in PAGES:
                for i, m in enumerate(INLINE.finditer((NEXT / page).read_text(encoding="utf-8"))):
                    f = Path(tmp) / f"{page}.{i}{'.mjs' if m.group(1) else '.js'}"
                    f.write_text(m.group(2), encoding="utf-8")
                    if err := check(f):
                        bad[f"{page} script {i}"] = err
        self.assertEqual(bad, {})


if __name__ == "__main__":
    unittest.main()
