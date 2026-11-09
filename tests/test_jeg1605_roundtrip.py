"""JEG-1605: property tests of the v2 round trip (docs/research/jeg1605/preregistration.md, section 3).
Synthetic worlds only; research prototype."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / "tools" / "research" / "jeg1605" / "roundtrip.py"
spec = importlib.util.spec_from_file_location("jeg1605_roundtrip", PATH)
rt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rt          # dataclasses look the module up while it loads
spec.loader.exec_module(rt)

N_PLAYERS = {"QB": 40, "RB": 70, "WR": 90, "TE": 40}
N_P = {"QB": 14, "RB": 30, "WR": 34, "TE": 13}
REC_SHARE = {"QB": 0.0, "RB": 0.25, "WR": 0.4, "TE": 0.45}


def world(seed=0, uniform_share=False, noise=0.15):
    """Players with three sources' triplets, games, and a chart that lists
    the top of each position (noisy around a power law in projected VORP)."""
    rng = np.random.default_rng(seed)
    pos_of, lines, games = {}, {}, {}
    key = 0
    for p, n in N_PLAYERS.items():
        for i in range(n):
            key += 1
            pos_of[key] = p
            games[key] = float(rng.uniform(7, 10))
            base = 22.0 * math.exp(-i / 18.0) + 1.0
            share = REC_SHARE[p] if uniform_share else min(max(REC_SHARE[p] + rng.normal(0, 0.12), 0.0), 0.8)
            by = {}
            for src in rt.SOURCES:
                ppr = base * float(rng.uniform(0.9, 1.1)) if not uniform_share else base
                rec = ppr * share
                by[src] = [ppr - rec, ppr - rec / 2, ppr]
            lines[key] = by
    return pos_of, lines, games


def chart_values(pos_of, lines, games, s0, n_list=None, noise=0.15, seed=1, exact=False):
    rng = np.random.default_rng(seed)
    p0 = rt.projected_points(lines, pos_of, games, s0)
    rp = rt.replacement(p0, pos_of, N_P)
    vals = {}
    for p in rt.POSITIONS:
        ks = sorted((k for k in p0 if pos_of[k] == p), key=lambda k: -p0[k])[:(n_list or {}).get(p, 30)]
        for k in ks:
            v = p0[k] - rp[p]
            if v > 0:
                x = 100.0 * v ** 1.5
                vals[k] = x if exact else x * math.exp(rng.normal(0, noise))
            elif not exact:                          # exact: only players above replacement are listed
                vals[k] = float(rng.uniform(5, 50))
    return vals


@pytest.mark.parametrize("s0", rt.ANCHOR_SCORINGS)
@pytest.mark.parametrize("split", ["uniform", "additive"])
@pytest.mark.parametrize("curve_mode", ["pooled", "per_position"])
def test_identity_at_anchor(s0, split, curve_mode):
    pos_of, lines, games = world()
    vals = chart_values(pos_of, lines, games, s0)
    # a listed player no source projects (fallback line), and one listed at 0
    pos_of[9001], games[9001] = "WR", 8.0
    vals[9001] = 1234.5
    some = next(k for k in vals if pos_of[k] == "RB")
    vals[some] = 0.0
    res = rt.chain(vals, pos_of, lines, games, N_P, N_P, s0, s0, split=split, curve_mode=curve_mode)
    assert 9001 in res.fallback
    assert set(res.values) == {k for k, x in vals.items() if x > 0}
    assert max(abs(res.values[k] - vals[k]) for k in res.values) < 1e-9


def test_identity_for_anchor_mix_and_source_variant():
    pos_of, lines, games = world(3)
    vals = chart_values(pos_of, lines, games, "half_ppr")
    nps = {s: N_P for s in rt.ANCHOR_SCORINGS}
    out = rt.chain_mix(vals, {"half_ppr": 1.0}, pos_of, lines, games, nps, "half_ppr", mix_sources=("espn",))
    assert max(abs(out["values"][k] - vals[k]) for k in vals) < 1e-9


def test_pure_receiver_gains_one_point_per_reception_additive():
    pos_of, lines, games = world(4)
    vals = chart_values(pos_of, lines, games, "standard")
    pr = 9100
    pos_of[pr], games[pr] = "WR", 8.5
    lines[pr] = {src: [0.0, 2.5, 5.0] for src in rt.SOURCES}       # 5 receptions, 0 non-reception points
    vals[pr] = 900.0
    res = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "ppr", split="additive")
    assert res.pc[pr] - res.pc0[pr] == pytest.approx(games[pr] * 5.0 * 1.0, abs=1e-9)
    # Half: half a point per reception
    res_h = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "half_ppr", split="additive")
    assert res_h.pc[pr] - res_h.pc0[pr] == pytest.approx(games[pr] * 5.0 * 0.5, abs=1e-9)


def test_receptions_gain_one_point_each_uniform_on_the_chart_line():
    """Uniform split: the chart's line is the projected line times k_i, so a
    player gains exactly G x (k_i x projected receptions) Standard -> Full. A
    pure receiver has no Standard points to scale and takes the position line."""
    pos_of, lines, games = world(5)
    vals = chart_values(pos_of, lines, games, "standard")
    pr = 9200
    pos_of[pr], games[pr] = "WR", 8.0
    lines[pr] = {src: [0.0, 2.0, 4.0] for src in rt.SOURCES}
    vals[pr] = 700.0
    res = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "ppr")
    assert pr in res.zero_anchor_line
    k = next(k for k in res.values if pos_of[k] == "WR" and k != pr)
    ln = res.line[k]
    k_i = res.pc0[k] / (games[k] * ln["std"])
    assert res.pc[k] - res.pc0[k] == pytest.approx(games[k] * k_i * ln["rec"], rel=1e-12)


def test_uniform_position_change_scales_vorp_without_b_amplification():
    pos_of, lines, games = world(6, uniform_share=True)
    vals = chart_values(pos_of, lines, games, "standard", exact=True)
    res = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "ppr")
    assert res.curve.b == pytest.approx(1.5, abs=1e-9)
    for p in ("RB", "WR", "TE"):
        f = 1.0 / (1.0 - REC_SHARE[p])                    # Full / Standard points, every player at p
        assert res.r0[p] == pytest.approx(res.rproj0[p], rel=1e-9)
        assert res.r[p] == pytest.approx(f * res.r0[p], rel=1e-9)
        for k in res.values:
            if pos_of[k] == p:
                assert res.vc[k] == pytest.approx(f * res.vc0[k], rel=1e-9)
                assert res.values[k] == pytest.approx(vals[k] * f ** 1.5, rel=1e-9)


def test_unlisted_player_gets_no_value_but_counts_in_the_pool():
    pos_of, lines, games = world(7)
    vals = chart_values(pos_of, lines, games, "standard")
    res = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "ppr")
    unlisted = [k for k in lines if k not in vals]
    assert unlisted and not any(k in res.values for k in unlisted)
    # removing an unlisted player who sits in the WR replacement band changes R
    p_s = rt.projected_points(lines, pos_of, games, "ppr")
    rebuilt = {**p_s, **res.pc}
    order = sorted((k for k in rebuilt if pos_of[k] == "WR"), key=lambda k: (-rebuilt[k], k))
    band = order[N_P["WR"]:N_P["WR"] + rt.BAND]
    k_out = next(k for k in band if k not in vals)
    lines2 = {k: v for k, v in lines.items() if k != k_out}
    res2 = rt.chain(vals, pos_of, lines2, games, N_P, N_P, "standard", "ppr")
    assert res2.r["WR"] != res.r["WR"]


def test_anchor_mix_is_weighted_mean_with_min_max_interval():
    pos_of, lines, games = world(8)
    vals = chart_values(pos_of, lines, games, "ppr")
    nps = {s: N_P for s in rt.ANCHOR_SCORINGS}
    w = {"standard": 0.25, "half_ppr": 0.0, "ppr": 0.75}
    out = rt.chain_mix(vals, w, pos_of, lines, games, nps, "standard")
    assert set(out["runs"]) == {"standard", "ppr"}
    a = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "standard").values
    b = rt.chain(vals, pos_of, lines, games, N_P, N_P, "ppr", "standard").values
    for k in vals:
        assert out["values"][k] == pytest.approx(0.25 * a[k] + 0.75 * b[k], rel=1e-12)
        assert out["interval"][k] == (min(a[k], b[k]), max(a[k], b[k]))
    thirds = rt.chain_mix(vals, {s: 1.0 for s in rt.ANCHOR_SCORINGS}, pos_of, lines, games, nps, "ppr")
    c = rt.chain(vals, pos_of, lines, games, N_P, N_P, "half_ppr", "ppr").values
    d = rt.chain(vals, pos_of, lines, games, N_P, N_P, "standard", "ppr").values
    k = next(iter(vals))
    assert thirds["values"][k] == pytest.approx((vals[k] + c[k] + d[k]) / 3, rel=1e-12)


def test_te_premium_raises_te_only():
    pos_of, lines, games = world(9)
    vals = chart_values(pos_of, lines, games, "ppr")
    res = rt.chain(vals, pos_of, lines, games, N_P, N_P, "ppr", "ppr_te_premium")
    for k in res.values:
        if pos_of[k] == "TE":
            assert res.pc[k] > res.pc0[k]
        else:
            assert res.pc[k] == res.pc0[k]


def test_anchor_estimator_finds_the_generating_scoring():
    pos_of, lines, games = world(10)
    nps = {s: N_P for s in rt.ANCHOR_SCORINGS}
    for s0 in rt.ANCHOR_SCORINGS:
        vals = chart_values(pos_of, lines, games, s0, noise=0.0, exact=True)
        curves = rt.anchor_residuals(vals, pos_of, lines, games, nps)
        assert rt.estimate_anchor(curves) == s0
