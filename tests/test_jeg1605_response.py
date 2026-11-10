"""JEG-1605: unit tests of the chart-to-chart response measures
(docs/research/jeg1605/response-preregistration.md). Synthetic inputs only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "research" / "jeg1605"))
import response_test as T  # noqa: E402


def test_zero_move_scores_zero():
    r = np.array([0.1, -0.05, 0.0, 0.02])
    corr, slope, closer = T.move_stats(np.zeros(4), r, np.ones((1, 4)))
    assert corr[0] == 0 and slope[0] == 0 and abs(closer[0]) < 1e-12


def test_exact_move_gains_full_error():
    r = np.array([0.1, -0.05, 0.0, 0.02])
    corr, slope, closer = T.move_stats(r.copy(), r, np.ones((1, 4)))
    assert abs(corr[0] - 1) < 1e-12 and abs(slope[0] - 1) < 1e-12
    assert abs(closer[0] - np.mean(r ** 2)) < 1e-12


def test_right_direction_too_large_is_not_closer():
    r = np.array([0.1, -0.05, 0.0, 0.02])
    corr, slope, closer = T.move_stats(3 * r, r, np.ones((1, 4)))
    assert corr[0] > 0.99 and abs(slope[0] - 3) < 1e-9 and closer[0] < 0


def test_pct_ties_and_order():
    p = T.pct([3.0, 1.0, 1.0, 5.0])
    assert list(p) == [0.75, 0.375, 0.375, 1.0]


def test_games_rules():
    ctx = {"pos_of": {1: "RB", 2: "WR", 3: "TE"}, "gp": {7: {1: 10.0}}, "byes": {}, "team": {}}
    espn = {7: {1: 8.0, 2: 9.0}}
    cur = T.games_for(ctx, 7, "current", False, espn)
    g1 = T.games_for(ctx, 7, "G1", False, espn)
    g2 = T.games_for(ctx, 7, "G2", False, espn)
    loo = T.games_for(ctx, 7, "current", True, espn)
    assert cur[1] == 10.0 and g1[1] == 10.0 and g2[1] == 8.0
    assert g1[2] == 9.0 and g2[2] == 9.0 and cur[2] != 9.0
    assert g1[3] == cur[3] == g2[3]                     # no ESPN row: current rule
    assert loo[1] != 10.0                                # leave-one-out drops CBS gp
