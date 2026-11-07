"""JEG-1569 prototype: DDF_VALUE_SPLIT=charts builds the DDF weights (VP-4) from
the trade charts in I only. Default off; not for merge without Jeremy's go.

Checks, on the week-9 fixture at half PPR 12 teams, 1QB and superflex:
- the default (no flag) equals ddf_split="all" exactly;
- with the flag the weights equal the mean of the included charts' own
  ES-15.1 weights (the projections contribute nothing to the split);
- the flag moves nothing else upstream: allocation and waiver lines are equal.
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


if __name__ == "__main__":
    unittest.main()
