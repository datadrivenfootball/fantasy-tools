"""JEG-1599 / JEG-1600: tests for the chart decomposition (tools/research/jeg1597/decompose.py)
and the DDF_cur reproduction of the step-3 runner (rebuild_ddf.py). Research prototype only."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools" / "research" / "jeg1597"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO / "pipelines"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dc = _load("decompose", TOOLS / "decompose.py")


def _world(n=30, pos="WR", a=1.5, b=2.0, games=9.0):
    """A chart that is an exact power law of projected Standard points."""
    keys = list(range(1, n + 1))
    lines, natives, pts, pos_of = {}, {}, {}, {}
    for k in keys:
        std = 4.0 + 0.4 * k
        rec = 1.0 + 0.23 * ((k * 7) % 11)        # reception mix not tied to std rank
        lines[k] = {"razzball": [std, std + 0.5 * rec, std + rec]}
        pts[k] = std * games
        natives[k] = math.exp(a) * pts[k] ** b
        pos_of[k] = pos
    return keys, lines, natives, pts, pos_of


def _ratios(lines, s0, s):
    return {k: dc.player_ratio(ln, s0, s) for k, ln in lines.items()}


@pytest.mark.parametrize("mode", dc.MODES)
@pytest.mark.parametrize("s", dc.SCORINGS)
def test_identity_at_anchor(mode, s):
    _keys, lines, natives, _pts, pos_of = _world()
    pts = {k: dc.points_from_triplet(ln["razzball"], s) * 9 for k, ln in lines.items()}
    r = dc.rescale_chart(natives, pos_of, _ratios(lines, s, s), pts, 1.0, mode=mode)
    assert all(r.ratio[k] == 1.0 for k in natives)
    assert r.natives == pytest.approx(natives, rel=1e-12)


def test_monotone_order_kept_at_anchor():
    keys, lines, natives, pts, pos_of = _world()
    # Scramble the projections so the chart and projections disagree on who.
    pts = {k: pts[keys[(i * 7) % len(keys)]] for i, k in enumerate(keys)}
    fit = dc.fit_chart([(natives[k], pts[k]) for k in keys])
    assert fit.identifiable and fit.b > 0
    implied = {k: dc.implied_points(natives[k], fit) for k in keys}
    by_native = sorted(keys, key=lambda k: -natives[k])
    by_implied = sorted(keys, key=lambda k: -implied[k])
    assert by_native == by_implied
    for k in keys:
        assert fit.to_native(fit.to_points(natives[k])) == pytest.approx(natives[k], rel=1e-12)


def test_rank_matched_fit_recovers_power_law():
    keys, _lines, natives, pts, _pos = _world(a=0.7, b=2.6)
    fit = dc.fit_chart([(natives[k], pts[k]) for k in keys])
    assert fit.b == pytest.approx(2.6, rel=1e-9) and fit.a == pytest.approx(0.7, abs=1e-9)
    assert fit.r2 == pytest.approx(1.0)


def test_pure_receiver_gains_one_point_per_reception_std_to_full():
    keys, lines, natives, pts, _pos = _world(games=9.0)
    fit = dc.fit_chart([(natives[k], pts[k]) for k in keys])
    ratios = _ratios(lines, "standard", "ppr")
    for k in keys:
        rec_per_game = lines[k]["razzball"][2] - lines[k]["razzball"][0]
        gain = (dc.implied_points(natives[k], fit, ratios[k].value, 1.0)
                - dc.implied_points(natives[k], fit, 1.0, 1.0))
        assert gain == pytest.approx(rec_per_game * 9.0, rel=1e-9)
    # A pure receiver line scored with lib/scoring.py weights: Full - Std = receptions.
    line = [10.0, 13.0, 16.0]
    assert dc.points_from_triplet(line, "ppr") - dc.points_from_triplet(line, "standard") == 6.0


@pytest.mark.parametrize("mode", dc.MODES)
def test_lambda_zero_returns_natives_unchanged(mode):
    _keys, lines, natives, pts, pos_of = _world()
    r = dc.rescale_chart(natives, pos_of, _ratios(lines, "ppr", "standard"), pts, 0.0, mode=mode)
    assert r.natives == natives


def test_modes_position_level_and_same_fit():
    keys, lines, natives, pts, pos_of = _world(b=2.0)
    ratios = _ratios(lines, "ppr", "standard")
    same = dc.rescale_chart(natives, pos_of, ratios, pts, 1.0, mode="same_fit")
    scaled = dc.rescale_chart(natives, pos_of, ratios, pts, 1.0, mode="position_scaled")
    fit = same.fits["WR"]
    kp = scaled.position_ratio["WR"]
    for k in keys:
        r = ratios[k].value
        assert same.natives[k] == pytest.approx(natives[k] * r ** fit.b, rel=1e-9)
        assert scaled.natives[k] == pytest.approx(natives[k] * kp * (r / kp) ** fit.b, rel=1e-9)
    # damping: lam 0.5 is the square root of the full move in the same-fit mode
    half = dc.rescale_chart(natives, pos_of, ratios, pts, 0.5, mode="same_fit")
    k = keys[3]
    assert half.natives[k] / natives[k] == pytest.approx(math.sqrt(same.natives[k] / natives[k]), rel=1e-9)


def test_missing_stat_line_uses_median_ratio_and_is_flagged():
    keys, lines, natives, pts, pos_of = _world()
    ratios = _ratios(lines, "ppr", "standard")
    gone = keys[5]
    del ratios[gone]
    r = dc.rescale_chart(natives, pos_of, ratios, pts, 1.0)
    med = sorted(x.value for x in ratios.values())
    m = (med[len(med) // 2 - 1] + med[len(med) // 2]) / 2 if len(med) % 2 == 0 else med[len(med) // 2]
    assert r.median_ratio_keys == [gone]
    assert r.ratio[gone] == pytest.approx(m)


def test_not_identifiable_position_keeps_natives():
    keys, lines, natives, pts, pos_of = _world(n=5)
    r = dc.rescale_chart(natives, pos_of, _ratios(lines, "ppr", "standard"), pts, 1.0)
    assert r.not_identifiable == ["WR"] and r.natives == natives


def test_ratio_prefers_primary_sources_and_reports_spread():
    lines = {"razzball": [10, 12, 14], "cbsros": [8, 9, 10], "espn": [20, 20, 20]}
    r = dc.player_ratio(lines, "ppr", "standard")
    assert r.basis == "primary" and r.value == pytest.approx(18 / 24)
    assert r.spread == (pytest.approx(10 / 14), 1.0) and r.n_sources == 3
    only_espn = dc.player_ratio({"espn": [10, 12, 14]}, "ppr", "standard")
    assert only_espn.basis == "fallback"
    assert dc.player_ratio({"razzball": [0, 0, 0]}, "ppr", "standard") is None


def test_schedule_games_and_expected_games():
    assert dc.schedule_games(9, 11) == 9 and dc.schedule_games(9, 7) == 10
    assert dc.expected_games("RB", 9, 11, None) == (pytest.approx(9 * 0.86), "schedule")
    assert dc.expected_games("RB", 9, 11, 8.0) == (8.0, "cbs_gp")


def test_ddf_cur_reproduces_live_reference_week9():
    """The runner's history-path DDF_cur equals value_reference on the live
    fixture (week 9) and the reference's own prior-week run (week 8)."""
    rb = _load("jeg1597_rebuild_ddf", TOOLS / "rebuild_ddf.py")
    vr = rb.vr
    inp, hist, *_ = rb.load_world()
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    s = vr.Setting(inp, "ppr", 12, hist=hist)
    st = s.state()
    for week, ref in ((9, s.result()), (8, s.prior_result())):
        natives, _lines = rb.week_inputs(inp, hist, week)
        mine = rb.run(s.league, s.lineup, {k: natives[k]["ppr"] for k in vr.SOURCES}, pos_of,
                      st["included"], st["hidden"])
        worst = 0.0
        for k, r in ref["rows"].items():
            a = r["ddf"]["blended"]["value"]
            b = mine["rows"][k]["ddf"]["blended"]["value"]
            assert (a is None) == (b is None)
            if a is not None:
                worst = max(worst, abs(a - b))
        assert worst <= 1e-9, (week, worst)
