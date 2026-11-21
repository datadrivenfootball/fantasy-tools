"""Page speed with league settings: a saved league costs one engine rebuild on load, not one per setting.

DDF.engine restored a saved league by calling setScoring, setTeams and setRosterSpot one at a time, and each
call rebuilt the whole value pipeline. A Half PPR league with 3 WR and 5 bench (the USO league) rebuilt three
times on every engine page load, and a settings change with several fields (DDF.engine.apply) once per field.
TradeValueCurveControls.setLeague applies them together with one rebuild and the same end state.

What we guard, as call counts (stable in CI, no timings): with that league saved, the first load makes exactly
one rebuild's worth of ValueModel.runValuePipeline calls more than with no league; DDF.engine.apply with
scoring, teams and two roster spots makes one rebuild's worth. The values parity suites guard the numbers.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve

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
# The USO league's saved settings (Half PPR, 12 teams, QB1 RB2 WR3 TE1 FLEX1 BN5): three changes from the defaults.
USO = {"v": 1, "scoring": "half_ppr", "teams": 12,
       "roster": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 5, "K": 1, "DST": 1}}


def setUpModule():
    _render_env.ensure_built()


def runs(page: str, saved: dict | None) -> dict:
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
            if saved:
                ctx.add_init_script(f"localStorage.setItem('ddf.v2.league-settings', {json.dumps(json.dumps(saved))});")
            pg = ctx.new_page()
            pg.goto(f"{base}/{page}", wait_until="load")
            pg.wait_for_function(READY, timeout=90000)
            pg.evaluate("() => DDF.engine.ready")
            out = {"boot": pg.evaluate("() => window.__pipelineRuns"), "settings": pg.evaluate("() => DDF.engine.settings()")}
            other = pg.evaluate("() => TradeValueCurveControls.getState().scoring === 'standard' ? 'ppr' : 'standard'")
            pg.evaluate("(s) => { window.__pipelineRuns = 0; TradeValueCurveControls.setScoring(s, false); }", other)
            out["one"] = pg.evaluate("() => window.__pipelineRuns")
            pg.evaluate("() => { window.__pipelineRuns = 0; DDF.engine.apply({scoring: 'half_ppr', teams: 10, roster: {WR: 2, BENCH: 4}}); }")
            out["apply"] = pg.evaluate("() => window.__pipelineRuns")
            out["applied"] = pg.evaluate("() => DDF.engine.settings()")
            return out
        finally:
            browser.close()


class SavedLeaguePipelineRunsTest(unittest.TestCase):
    def test_saved_league_costs_one_rebuild(self):
        for page in ("values.html", "team.html"):
            with self.subTest(page=page):
                none, uso = runs(page, None), runs(page, USO)
                self.assertEqual((uso["settings"]["scoring"], uso["settings"]["roster"]["WR"], uso["settings"]["roster"]["BENCH"]),
                                 ("half_ppr", 3, 5), "the saved league must be applied")
                self.assertGreater(none["one"], 0)
                self.assertEqual(uso["boot"] - none["boot"], none["one"],
                                 f"{page}: the saved league cost {uso['boot'] - none['boot']} pipeline calls, one rebuild is {none['one']}")
                self.assertEqual(uso["apply"], uso["one"], f"{page}: apply() with four changes made {uso['apply']} calls")
                self.assertEqual((uso["applied"]["scoring"], uso["applied"]["teams"], uso["applied"]["roster"]["WR"],
                                  uso["applied"]["roster"]["BENCH"]), ("half_ppr", 10, 2, 4))


if __name__ == "__main__":
    unittest.main()
