"""Page speed (Jeremy, 2026-11-21): engine pages preload the engine's data files from the head.

Before, the engine's scripts fetched its data only after they had run, then one file after another (bundle,
history index, prior history week, lineup parameters, lineup signal): on a Fast 4G profile the last one landed
about 1.8 s after the page started. The head now carries <link rel="preload" as="fetch" crossorigin> for each.

What we guard:
- an engine page's head lists the engine data files; a page without the engine lists none;
- the history week preloaded is the one the engine reads (the week before each served week);
- on the built values.html and team.html every preload is used by the engine's own fetch (no "preloaded but not
  used" warning) and no data file is downloaded twice. Request counts, not timings, so it is stable in CI.
"""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST, serve
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
import build_root_pages as brp  # noqa: E402

ENGINE_HTML = ('<html><head><meta charset="utf-8"><meta name="trade-chart-build" content="tv-test"></head><body>'
               '<div id="curve"></div>' + brp.ENGINE_SCRIPT_MARKER + '<script src="assets/curve-widget.js"></script></body></html>')
PRELOAD = re.compile(r'<link rel="preload" href="([^"]+)" as="fetch" crossorigin>')


class PreloadLinksTest(unittest.TestCase):
    def page(self, body: str, name: str) -> str:
        return brp.root_page_html(f'<html><head><meta charset="utf-8"></head><body>{body}</body></html>', name,
                                  ENGINE_HTML, "tv-test", preload=("assets/comparison-sources-data.json", "assets/history/week-9.json"))

    def test_engine_page_head_preloads_the_data(self):
        html = self.page("<!-- ddf-engine --><script src=\"values-chart.js\"></script>", "values.html")
        head = html[:html.index("</head>")]
        self.assertEqual(PRELOAD.findall(head), ["assets/comparison-sources-data.json", "assets/history/week-9.json"])

    def test_page_without_engine_preloads_nothing(self):
        self.assertEqual(PRELOAD.findall(self.page("<p>home</p>", "setup.html")), [])

    def test_history_week_is_the_one_before_each_served_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "assets/history").mkdir(parents=True)
            for f in ("assets/comparison-sources-data.json", "assets/lineup-signal.json", "assets/history/week-9.json",
                      "assets/history/week-10.json"):
                (dist / f).write_text("{}")
            (dist / "assets/history/index.json").write_text(json.dumps({
                "served": {"cbs": {"week": 11}, "espn": {"week": 10}},
                "weeks": {"9": {"file": "assets/history/week-9.json"}, "10": {"file": "assets/history/week-10.json"}}}))
            files = brp.engine_data_files(dist)
        self.assertEqual(files, ("assets/comparison-sources-data.json", "assets/history/index.json",
                                 "assets/lineup-signal.json", "assets/history/week-9.json", "assets/history/week-10.json"))


def setUpModule():
    _render_env.ensure_built()


class BuiltPagesUsePreloadsTest(unittest.TestCase):
    def test_every_preload_is_used_once(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        with serve() as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except Exception as exc:  # noqa: BLE001
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                for page in ("values.html", "team.html"):
                    with self.subTest(page=page):
                        if not (DIST / page).exists():
                            raise _render_env.unavailable(f"dist/{page} is not built")
                        preloads = PRELOAD.findall((DIST / page).read_text(encoding="utf-8").split("</head>", 1)[0])
                        self.assertIn("assets/comparison-sources-data.json", preloads)
                        pg = browser.new_page()
                        warnings = []
                        pg.on("console", lambda m: warnings.append(m.text) if "preload" in m.text.lower() else None)
                        pg.goto(f"{base}/{page}", wait_until="load")
                        pg.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.ready", timeout=90000)
                        pg.evaluate("() => DDF.engine.ready")
                        pg.wait_for_timeout(3500)   # Chrome reports an unused preload a few seconds after load
                        entries = pg.evaluate("() => performance.getEntriesByType('resource').map(e => [new URL(e.name).pathname, e.initiatorType])")
                        pg.close()
                        for href in preloads:
                            hits = [kind for path, kind in entries if path.endswith("/" + href)]
                            self.assertEqual(hits, ["link"], f"{page}: {href} was fetched as {hits}")
                        self.assertEqual(warnings, [], f"{page}: {warnings}")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
