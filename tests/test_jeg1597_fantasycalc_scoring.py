"""JEG-1598 sub-question 1 (part of JEG-1597): FantasyCalc pegged-or-blend method.

Synthetic generators pin the mechanics: a pegged list recovers its r, a blended list recovers
its mixture weight, and a multiplier-only switch is reported not identifiable within position.
Method and results: docs/research/jeg1597/fantasycalc-pegged-or-blend.md.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "research" / "jeg1597" / "fantasycalc_scoring.py"
_spec = importlib.util.spec_from_file_location("jeg1597_fantasycalc_scoring", SCRIPT)
fs = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = fs
_spec.loader.exec_module(fs)

BOOT = 80


def synthetic(seed=11, n_per_pos=45):
    rng = np.random.default_rng(seed)
    pos_of, ref, k = {}, {}, 1
    for p in ("QB", "RB", "WR", "TE"):
        for _ in range(n_per_pos):
            std = float(rng.uniform(4, 20))
            rec = 0.0 if p == "QB" else float(rng.uniform(0.0, 0.8) * std)
            pos_of[k], ref[k] = p, (std, rec)
            k += 1
    return pos_of, ref


def m(ref, k, r):
    return ref[k][0] + r * ref[k][1]


def pegged_chart(ref, pos_of, r, seed, gamma=1.8, noise=0.02):
    rng = np.random.default_rng(seed)
    return {k: float(m(ref, k, r) ** gamma * np.exp(rng.normal(0, noise))) for k in ref}


def blend_chart(ref, pos_of, weights, seed, gamma=1.8, noise=0.02):
    """Trades pooled across leagues: value = weighted mix of Standard, Half, Full value curves."""
    rng = np.random.default_rng(seed)
    return {k: float(sum(w * m(ref, k, r) ** gamma for w, r in zip(weights, (0.0, 0.5, 1.0)))
                     * np.exp(rng.normal(0, noise))) for k in ref}


def weekly(chart_fn, n_weeks=5):
    pos_of, ref = synthetic()
    out = []
    for w in range(n_weeks):
        rng = np.random.default_rng(100 + w)
        out.append(fs.within_profile(chart_fn(ref, pos_of, 200 + w), ref, pos_of, BOOT, rng))
    return out


def test_pegged_generator_recovers_its_r():
    est = weekly(lambda ref, pos_of, s: pegged_chart(ref, pos_of, 1.0, s))
    assert all(abs(e["r_hat"] - 1.0) <= 0.1 for e in est)
    assert fs.classify(est, calibrated=True)["verdict"] == "pegged at r=1.0"


def test_pegged_at_standard_is_not_called_full():
    est = weekly(lambda ref, pos_of, s: pegged_chart(ref, pos_of, 0.0, s))
    assert fs.classify(est, calibrated=True)["verdict"] == "pegged at r=0.0"


def test_blend_generator_recovers_its_mixture():
    weights = (0.25, 0.0, 0.75)            # mixture reception weight 0.75
    est = weekly(lambda ref, pos_of, s: blend_chart(ref, pos_of, weights, s))
    assert all(abs(e["r_hat"] - 0.75) <= 0.1 for e in est)
    v = fs.classify(est, calibrated=True)
    assert v["verdict"] == "stable blend"
    assert abs(v["r_mean"] - 0.75) <= 0.1


def test_uncalibrated_method_is_not_identifiable():
    est = weekly(lambda ref, pos_of, s: pegged_chart(ref, pos_of, 1.0, s))
    assert fs.classify(est, calibrated=False)["verdict"] == "not identifiable"


def test_multiplier_only_switch_is_not_identifiable_within_position():
    pos_of, ref = synthetic()
    v0 = {k: 100 * x for k, x in pegged_chart(ref, pos_of, 1.0, 5).items()}
    k_p = {"QB": 1.01, "RB": 0.994, "WR": 1.018, "TE": 1.023}
    v1 = {k: x * k_p[pos_of[k]] for k, x in v0.items()}
    res = fs.switch_test(v0, v1, ref, pos_of)
    assert res["verdict"] == "multiplier only"
    assert res["within_position"] == "not identifiable"
    assert all(row["reordered_pairs"] == 0 for row in res["positions"].values())
    # identical within-position order -> identical r-profile answers on both columns
    a = fs.within_profile(v0, ref, pos_of, BOOT, np.random.default_rng(1))
    b = fs.within_profile(v1, ref, pos_of, BOOT, np.random.default_rng(1))
    assert a["r_hat"] == b["r_hat"]


def test_real_scoring_switch_is_flagged_player_level():
    pos_of, ref = synthetic()
    v0 = {k: 100 * x for k, x in pegged_chart(ref, pos_of, 0.0, 5, noise=0.0).items()}
    v1 = {k: 100 * x for k, x in pegged_chart(ref, pos_of, 1.0, 5, noise=0.0).items()}
    res = fs.switch_test(v0, v1, ref, pos_of)
    assert res["verdict"] == "player-level term"
    assert res["positions"]["WR"]["spearman_resid_vs_rec_share"] > 0.5


def test_calibration_bar():
    assert fs.calibration([(0.0, 0.1)] * 16 + [(1.0, 0.2)] * 4)["pass"]
    assert not fs.calibration([(0.0, 0.1)] * 15 + [(1.0, 0.2)] * 5)["pass"]
