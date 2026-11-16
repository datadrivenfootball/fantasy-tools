#!/usr/bin/env python3
"""JEG-1630: FantasyCalc's six lists share one player set chosen by the 1-QB
value. A QB leaving the bottom of that set is churn in the 2-QB lists too,
even though his 2-QB value is above the 2-QB churn line.

Replays the 2026-11-16 00:40Z pulse shape (Kyler Murray live at 1-QB 18,
2-QB 145; the 21:05Z save had dropped him from every list)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from fidelity_pulse import compare, fc_list_churn  # noqa: E402

KYLER = 370
GRAINS = ("std|1", "half|1", "full|1", "std|2", "half|2", "full|2")


def _cells(values: dict[int, float]) -> dict:
    return {k: {"value": float(v), "text": str(int(v)), "name": f"p{k}", "pos": "QB" if k == KYLER else "WR"}
            for k, v in values.items()}


def _lists(kyler_1qb: float | None, kyler_2qb: float | None) -> dict:
    """100 shared players; 1-QB values 3..300, 2-QB values 100..1090 (2-QB churn line ~250)."""
    out = {}
    for g in GRAINS:
        two = g.endswith("|2")
        vals = {k: (100 + 10 * k if two else 3 * k) for k in range(1, 101)}
        kv = kyler_2qb if two else kyler_1qb
        if kv is not None:
            vals[KYLER] = kv
        out[g] = _cells(vals)
    return out


def _run(left: dict, right: dict) -> dict:
    cmp = compare(left, right, printed=False)
    fc_list_churn(cmp, left, right)
    return cmp


class SharedMembershipChurn(unittest.TestCase):
    def test_qb_leaving_shared_set_is_churn_in_2qb_lists(self):
        live = _lists(kyler_1qb=18, kyler_2qb=600)   # 600 is far above the 2-QB churn line
        stored = _lists(kyler_1qb=None, kyler_2qb=None)
        cmp = _run(live, stored)
        self.assertEqual(cmp["missing"], [], "Kyler is membership churn in every list")
        self.assertEqual({m["grain"] for m in cmp["churn"]}, set(GRAINS))

    def test_qb_entering_shared_set_is_churn_in_2qb_lists(self):
        live = _lists(kyler_1qb=None, kyler_2qb=None)
        stored = _lists(kyler_1qb=18, kyler_2qb=600)
        cmp = _run(live, stored)
        self.assertEqual(cmp["extra"], [])
        self.assertEqual(len(cmp["churn"]), 6)

    def test_valuable_1qb_player_missing_everywhere_still_holds(self):
        live = _lists(kyler_1qb=250, kyler_2qb=900)  # well above the 1-QB churn line
        stored = _lists(kyler_1qb=None, kyler_2qb=None)
        cmp = _run(live, stored)
        self.assertEqual(len(cmp["missing"]), 6)

    def test_dropped_from_2qb_only_is_not_churn(self):
        """A save that kept the player in 1-QB but lost him in 2-QB broke the shared set: not churn."""
        live = _lists(kyler_1qb=18, kyler_2qb=600)
        stored = _lists(kyler_1qb=18, kyler_2qb=None)
        cmp = _run(live, stored)
        self.assertEqual({m["grain"] for m in cmp["missing"]}, {"std|2", "half|2", "full|2"})
        self.assertEqual(cmp["churn"], [])

    def test_1qb_rule_unchanged(self):
        live = _lists(kyler_1qb=18, kyler_2qb=None)
        stored = _lists(kyler_1qb=None, kyler_2qb=None)
        cmp = _run(live, stored)
        self.assertEqual(cmp["missing"], [])
        self.assertEqual(len(cmp["churn"]), 3)


if __name__ == "__main__":
    unittest.main()
