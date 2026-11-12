"""GAP-038: the scheduled live-page synthetic renders every reader-facing page.

tests/rendered_gate/live.mjs (run by .github/workflows/live-page-synthetic.yml,
dispatched by pg_cron live-page-synthetic-live) checks the root build tag, then
each redesigned root page (JEG-1539), the legacy-route redirects, /classic/ (a redirect to the root since
JEG-453) and the 404 page. This test serves the built dist/ under /fantasy-tools/ (as GitHub
Pages does) and requires:

- the real build passes;
- each simulated broken state fails, naming the broken page: a page whose <main>
  never shows, an empty values table, /classic/ still serving the old chart
  dashboard (no redirect), /classic/ redirecting to another build, and a 404
  that is not the site's own page.

Needs `make sync`, node with tests/rendered_gate/node_modules (npm ci) and a
Chromium (CHROMIUM_PATH). Skips, saying why, when any is missing.

This file replaced a pre-GAP-038 version that pinned symbols live.mjs never had
(verdict(), pieBad, the 12-shape sweep) and was not run by any Makefile target.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_launch_front_door import _pages_server  # noqa: E402
from _dist_server import ENGINE_PAGE  # noqa: E402

DIST = ROOT / "dist"
GATE_DIR = ROOT / "tests" / "rendered_gate"
LIVE_MJS = GATE_DIR / "live.mjs"


def _chromium():
    from tests._render_env import chromium_executable
    return chromium_executable()


def _build_tag(dist: Path) -> str:
    m = re.search(r'name="trade-chart-build" content="([^"]+)"', (dist / "index.html").read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def _run_live(dist: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp, _pages_server(dist) as base:
        out = Path(tmp) / "report.json"
        env = dict(os.environ, CHROMIUM_PATH=_chromium() or "")
        subprocess.run(["node", str(LIVE_MJS), "--url", base, "--expected-build", _build_tag(dist),
                        "--out", str(out)], env=env, capture_output=True, timeout=300)
        return json.loads(out.read_text(encoding="utf-8"))


class LivePageSyntheticPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = []
        if not (DIST / "classic" / "index.html").exists() or not ENGINE_PAGE.exists():
            missing.append("dist/classic and build/engine (run make sync)")
        if not shutil.which("node"):
            missing.append("node")
        if not (GATE_DIR / "node_modules" / "playwright-core").exists():
            missing.append("tests/rendered_gate/node_modules (npm ci)")
        if not _chromium():
            missing.append("Chromium (CHROMIUM_PATH)")
        if missing:
            raise unittest.SkipTest("needs " + ", ".join(missing))

    def _mutated(self, edit):
        tmp = Path(tempfile.mkdtemp(prefix="gap038-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        copy = tmp / "dist"
        shutil.copytree(DIST, copy, ignore=shutil.ignore_patterns("consolidated-values.json"))
        edit(copy)
        return copy

    def _failed_page(self, report, name):
        self.assertFalse(report["passed"], report.get("problems"))
        page = {p["name"]: p for p in report.get("pages", [])}.get(name)
        self.assertIsNotNone(page, f"no {name} page in report: {report.get('problems')}")
        self.assertFalse(page["passed"], f"{name} should fail: {page}")
        return page

    def test_real_build_passes_every_page(self):
        report = _run_live(DIST)
        self.assertTrue(report["passed"], report["problems"])
        names = [p["name"] for p in report["pages"]]
        # JEG-1539: the redesigned root pages and the legacy-route redirects replaced the v2 tab list.
        self.assertEqual(names, ["root", "values.html", "learn.html", "build.html", "team.html", "explore.html",
                                 "partners.html", "find.html", "waivers.html", "settings.html", "ai.html", "connect.html",
                                 "redirect v2/", "redirect #player-values", "redirect v2/#find-trade",
                                 "redirect #compare-trade", "redirect #waivers", "redirect #writing/manifesto",
                                 "redirect #s=AAAA", "classic-redirect", "not-found"])
        classic = {p["name"]: p for p in report["pages"]}["classic-redirect"]
        self.assertEqual(200, classic["httpStatus"])
        self.assertEqual(classic["landedAt"].split("#")[0], report["url"])

    def test_hidden_page_content_fails(self):
        def edit(d):
            p = d / "find.html"
            # The page stays in the DOM (no script error) but its <main> never shows.
            p.write_text(p.read_text(encoding="utf-8").replace(
                "</head>", "<style>main{display:none!important}</style></head>", 1))
        page = self._failed_page(_run_live(self._mutated(edit)), "find.html")
        self.assertTrue(any("<main> not visible" in s for s in page["problems"]), page["problems"])

    def test_empty_values_table_fails(self):
        def edit(d):
            p = d / "values.html"
            # The values table renders, then loses its rows (no script error).
            p.write_text(p.read_text(encoding="utf-8").replace(
                "</body>", "<script>setInterval(function () { var t = document.getElementById('rows');"
                " if (t) t.innerHTML = ''; }, 50);</script></body>", 1))
        page = self._failed_page(_run_live(self._mutated(edit)), "values.html")
        self.assertTrue(any("DDF Value" in s for s in page["problems"]), page["problems"])

    def test_classic_still_serving_old_dashboard_fails(self):
        def edit(d):
            # The pre-JEG-453 publish: the chart dashboard itself at /classic/.
            shutil.copy2(ENGINE_PAGE, d / "classic" / "index.html")
        page = self._failed_page(_run_live(self._mutated(edit)), "classic-redirect")
        self.assertTrue(any("expected a redirect" in s for s in page["problems"]), page["problems"])

    def test_foreign_404_page_fails(self):
        def edit(d):
            (d / "404.html").write_text("<!doctype html><title>404</title><h1>Not Found</h1>")
        self._failed_page(_run_live(self._mutated(edit)), "not-found")


if __name__ == "__main__":
    unittest.main()
