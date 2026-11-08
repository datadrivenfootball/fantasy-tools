"""JEG-1569: DDF_VALUE_SPLIT=charts builds DDF Value's position split (VP-4) from
the trade charts in I only, and DDF Projections' from the projections in I only.
Live since the flip (DDF_VALUE_SPLIT_DEFAULT "charts"); "all" is the old split.

Checks, on the week-9 fixture at half PPR 12 teams, 1QB and superflex:
- the default (no flag) equals ddf_split="charts" exactly (the flip);
- with the flag the weights equal the mean of the included charts' own
  ES-15.1 weights (the projections contribute nothing to the split);
- the flag moves nothing else upstream: allocation and waiver lines are equal;
- the projections are priced on the mean of the projections' own weights;
- in a 2-QB league with no superflex slot the charts' split is the charts' mean
  (no JEG-1366 projection rule; Jeremy 2026-11-07, decision 4);
- the live result carries none of the new keys.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
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
            self.assertEqual(default["ddfWeights"], charts["ddfWeights"])  # the flip: default is "charts"
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
            self.assertIn("ddfWeightsProjections", _default)
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


if __name__ == "__main__":
    unittest.main()
