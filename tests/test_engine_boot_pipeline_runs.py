"""Page-speed guard: a first load runs the value pipeline once, not twice.

The engine's init built the domain, then makeViewModeTabs() entered the same view and rebuilt it again with
nothing changed: every engine page (values, team, find, build, ...) ran the whole value pipeline twice before
it showed a number (about 0.5 s of main thread on a desktop, several times that on a phone).

What we guard: the number of ValueModel.runValuePipeline calls the engine makes during its first load equals
the number one rebuild makes (measured on the same page by one explicit setting change). Counts, not timings,
so the check is stable in CI. Output is unchanged; the values parity tests guard the numbers.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve

# Count the engine's calls into the value model (value-model.js recurses through its own local reference, so
# only calls from the curve widget are counted).
COUNT_RUNS = """(() => {
  window.__pipelineRuns = 0;
  let model;
  Object.defineProperty(window, 'ValueModel', {configurable: true, get: () => model, set: (m) => {
    const run = m.runValuePipeline;
    m.runValuePipeline = function () { window.__pipelineRuns += 1; return run.apply(this, arguments); };
    model = m;
  }});
})();"""
READY = "() => window.DDF && DDF.engine && DDF.engine.ready && window.TradeValueCurveControls && TradeValueCurveControls.isReady()"


def setUpModule():
    _render_env.ensure_built()


def boot_and_one_rebuild(page: str, saved_league: str | None = None) -> tuple[int, int]:
    """(runs during the first load, runs one scoring change makes) on page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    if not (DIST / page).exists():
        raise _render_env.unavailable(f"dist/{page} is not built")
    with serve() as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        try:
            ctx = browser.new_context()
            ctx.add_init_script(COUNT_RUNS)
            if saved_league:
                ctx.add_init_script(f"localStorage.setItem('ddf.v2.league-settings', {saved_league!r});")
            pg = ctx.new_page()
            pg.goto(f"{base}/{page}", wait_until="load")
            pg.wait_for_function(READY, timeout=90000)
            pg.evaluate("() => DDF.engine.ready")
            boot = pg.evaluate("() => window.__pipelineRuns")
            other = pg.evaluate("() => TradeValueCurveControls.getState().scoring === 'standard' ? 'ppr' : 'standard'")
            pg.evaluate("(s) => { window.__pipelineRuns = 0; TradeValueCurveControls.setScoring(s, false); }", other)
            one = pg.evaluate("() => window.__pipelineRuns")
            return boot, one
        finally:
            browser.close()


class EngineBootPipelineRunsTest(unittest.TestCase):
    def test_first_load_runs_the_pipeline_once(self):
        for page in ("values.html", "team.html"):
            with self.subTest(page=page):
                boot, one = boot_and_one_rebuild(page)
                self.assertGreater(one, 0, "a scoring change must run the value pipeline")
                self.assertEqual(boot, one, f"{page}: the first load ran {boot} pipeline calls, one rebuild is {one}")


if __name__ == "__main__":
    unittest.main()
