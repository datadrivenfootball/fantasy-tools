"""JEG-1569: DDF_VALUE_SPLIT=charts builds DDF Value's position split (VP-4) from
the trade charts in I only, and DDF Projections' from the projections in I only.
Default off (DDF_VALUE_SPLIT_DEFAULT "all"); the flip waits for Jeremy's go.

Checks, on the week-9 fixture at half PPR 12 teams, 1QB and superflex:
- the default (no flag) equals ddf_split="all" exactly;
- with the flag the weights equal the mean of the included charts' own
  ES-15.1 weights (the projections contribute nothing to the split);
- the flag moves nothing else upstream: allocation and waiver lines are equal;
- the projections are priced on the mean of the projections' own weights;
- in a 2-QB league with no superflex slot the charts' split is the charts' mean
  (no JEG-1366 projection rule; Jeremy 2026-11-07, decision 4);
- the live result carries none of the new keys.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
RUNNER = ["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tests" / "_edge_pipeline_runner.cjs")]
TOL = 1e-6
import value_reference as vr  # noqa: E402


class ChartsOnlySplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("DDF_VALUE_SPLIT", None)
        cls.inp = vr.Inputs.load(today=date(2026, 11, 7))

    def _pair(self, sf):
        return (vr.Setting(self.inp, "half_ppr", 12, sf).diagnostics(),
                vr.Setting(self.inp, "half_ppr", 12, sf, ddf_split="all").diagnostics(),
                vr.Setting(self.inp, "half_ppr", 12, sf, ddf_split="charts").diagnostics())

    def test_split(self):
        for sf in (0, 1):
            default, live, charts = self._pair(sf)
            self.assertEqual(default["ddfWeights"], live["ddfWeights"])
            inc = [k for k in charts["included"]
                   if vr.FAMILY[k] == "chart" and charts["sources"][k]["weights"] is not None]
            self.assertGreaterEqual(len(inc), 1)
            for g, w in charts["ddfWeights"].items():
                mean = sum(charts["sources"][k]["weights"][g] for k in inc) / len(inc)
                self.assertAlmostEqual(w, mean, places=12, msg=f"sf={sf} {g}")
            self.assertEqual(live["allocation"], charts["allocation"])
            for k in live["included"]:
                for p in vr.POSITIONS:
                    self.assertEqual(live["sources"][k]["positions"][p]["waiver"],
                                     charts["sources"][k]["positions"][p]["waiver"])
            if sf:
                qb_live = live["ddfWeights"]["QB|starter"] + live["ddfWeights"]["QB|bench"]
                qb_charts = charts["ddfWeights"]["QB|starter"] + charts["ddfWeights"]["QB|bench"]
                self.assertGreater(qb_live - qb_charts, 0.03)  # discrimination: the flag really moves the split


    def _mean(self, diag, family):
        keys = [k for k in diag["included"]
                if vr.FAMILY[k] == family and diag["sources"][k]["weights"] is not None]
        return {g: sum(diag["sources"][k]["weights"][g] for k in keys) / len(keys) for g in diag["ddfWeights"]}

    def test_projections_split(self):
        for sf in (0, 1):
            _default, live, charts = self._pair(sf)
            self.assertNotIn("ddfWeightsProjections", live)
            live_res = vr.Setting(self.inp, "half_ppr", 12, sf, ddf_split="all").result()
            for key in ("ddf_split", "ddf_weights_projections", "group_budgets_projections"):
                self.assertNotIn(key, live_res)
            proj = self._mean(charts, "projection")
            for g, w in charts["ddfWeightsProjections"].items():
                self.assertAlmostEqual(w, proj[g], places=12, msg=f"sf={sf} {g}")
            # Each source is paid its own family's budgets (groups it funds, no unfunded move).
            res = vr.Setting(self.inp, "half_ppr", 12, sf, ddf_split="charts").result()
            for k in res["included"]:
                d = res["sources"][k]
                budgets = res["group_budgets_projections"] if vr.FAMILY[k] == "projection" else res["group_budgets"]
                moved = {m["from"] for m in d["unfunded_moved"]} | {m["to"] for m in d["unfunded_moved"]}
                for g, b in budgets.items():
                    if d["groups"][g] > 0 and g not in moved:
                        self.assertAlmostEqual(d["budgets_paid"][g], b, places=6, msg=f"{k} {g}")

    def test_two_qb_league_uses_charts_only(self):
        live = vr.Setting(self.inp, "half_ppr", 12, 0, qb=2, ddf_split="all").diagnostics()
        charts = vr.Setting(self.inp, "half_ppr", 12, 0, qb=2, ddf_split="charts").diagnostics()
        mean = self._mean(charts, "chart")
        for g, w in charts["ddfWeights"].items():
            self.assertAlmostEqual(w, mean[g], places=12, msg=g)
        qb = lambda d: d["ddfWeights"]["QB|starter"] + d["ddfWeights"]["QB|bench"]  # noqa: E731
        self.assertNotAlmostEqual(qb(live), qb(charts), places=3)


class EngineEqualsReferenceOnTheChartsSplit(unittest.TestCase):
    """The engine (built dist, through get-values' own league mapping, league.split) equals the
    Python reference on the "charts" split: weights, both splits' bench share, DDF Value. A
    default request (no split) stays on the live split."""

    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        from tests.test_week_history import _fixture_today
        _render_env.ensure_built()
        today = _fixture_today()
        cls.env = {k: v for k, v in os.environ.items() if k != "DDF_VALUE_SPLIT"}
        cls.env["TRADE_VALUE_TODAY"] = today
        cls.inp = vr.Inputs.load(today=date.fromisoformat(today))

    def edge(self, league, *extra):
        out = subprocess.run(RUNNER + ["--league", json.dumps(league), "--dist", str(ROOT / "dist"), *extra],
                             capture_output=True, text=True, timeout=180, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        return json.loads(out.stdout)

    CASES = [
        ({"scoring": "ppr", "teams": 12}, dict(scoring="ppr", teams=12), ()),
        ({"scoring": "half_ppr", "teams": 12, "roster": {"SUPERFLEX": 1}}, dict(scoring="half_ppr", teams=12, superflex=1), ()),
        ({"scoring": "standard", "teams": 10, "roster": {"QB": 2}}, dict(scoring="standard", teams=10, qb=2), ()),
        ({"scoring": "ppr", "teams": 12, "roster": {"QB": 2}}, dict(scoring="ppr", teams=12, qb=2, bench_share_override=0.1),
         ("--bench-share-override", "0.1")),
    ]

    def test_weights_and_values(self):
        for league, kw, extra in self.CASES:
            with self.subTest(league=league, extra=extra):
                st = vr.Setting(self.inp, ddf_split="charts", **kw)
                res = st.result()
                got = self.edge({**league, "split": "charts"}, "--dump-weights", "1", *extra)
                self.assertEqual(got.get("ddf_split"), "charts")
                for key, want in (("ddf_weights", res["ddf_weights"]), ("ddf_weights_projections", res["ddf_weights_projections"])):
                    for g, v in want.items():
                        self.assertAlmostEqual(got[key][g], v, places=9, msg=f"{key} {g}")
                self.assertAlmostEqual(got["bench_share_applied"], res["bench_share_applied"], places=9)
                edge = {int(k): v for k, v in self.edge({**league, "split": "charts"}, *extra).items()}
                want = {int(k): v["ddf_value"] for k, v in st.rows("adj").items()
                        if isinstance(v.get("ddf_value"), (int, float))}
                self.assertGreater(len(edge), 50)
                bad = [k for k in set(edge) | set(want) if abs(edge.get(k, 0) - want.get(k, 0)) > TOL]
                self.assertEqual(bad[:10], [], f"{len(bad)} players differ")

    def test_default_request_is_the_live_split(self):
        got = self.edge({"scoring": "ppr", "teams": 12}, "--dump-weights", "1")
        self.assertNotIn("ddf_split", got)
        res = vr.Setting(self.inp, "ppr", 12, ddf_split="all").result()
        for g, v in res["ddf_weights"].items():
            self.assertAlmostEqual(got["ddf_weights"][g], v, places=9, msg=g)
        bogus = self.edge({"scoring": "ppr", "teams": 12, "split": "projections"}, "--dump-weights", "1")
        self.assertEqual(bogus, got)


if __name__ == "__main__":
    unittest.main()
