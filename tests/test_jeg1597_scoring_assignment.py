"""JEG-1598 (step 1 of JEG-1597): scoring-assignment method.

Synthetic fixtures pin the method's mechanics; the real-data tests pin the
labelled CBS / USA Today result recorded in
docs/research/jeg1597/step1-scoring-assignment.md (the pre-stated method does
not recover single-column labels; a chart's own two columns do track receptions).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "research" / "jeg1597" / "scoring_assignment.py"
_spec = importlib.util.spec_from_file_location("jeg1597_scoring_assignment", SCRIPT)
sa = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sa
_spec.loader.exec_module(sa)


def synthetic(seed=7, n_per_pos=40):
    """Players with spread-out reception shares; returns pos_of, ref {key: (std, rec)}."""
    rng = np.random.default_rng(seed)
    pos_of, ref, k = {}, {}, 1
    for p in sa.POS:
        for _ in range(n_per_pos):
            std = float(rng.uniform(4, 20))
            rec = 0.0 if p == "QB" else float(rng.uniform(0.0, 0.8) * std)
            pos_of[k], ref[k] = p, (std, rec)
            k += 1
    return pos_of, ref


def chart_at(ref, pos_of, r_by_pos, scale_by_pos=None):
    """A chart whose within-position order is exactly m(r) (convex, arbitrary units)."""
    scale_by_pos = scale_by_pos or {}
    return {k: scale_by_pos.get(pos_of[k], 1.0) * (std + r_by_pos[pos_of[k]] * rec) ** 2.5
            for k, (std, rec) in ref.items()}


ALL = {p: None for p in sa.POS}


@pytest.mark.parametrize("col", sa.COLUMNS)
def test_synthetic_chart_recovers_its_scoring(col):
    pos_of, ref = synthetic()
    r = sa.LABEL_R[col]
    out = sa.assess(chart_at(ref, pos_of, {p: r for p in sa.POS}), ref, pos_of, 200, np.random.default_rng(1), 0.0)
    assert out["pooled"]["top"] == col
    assert abs(out["pooled"]["r_hat"] - r) <= 0.1
    assert out["pooled"]["dist"][col] > 0.9


def test_partial_correlation_sign_follows_scoring():
    pos_of, ref = synthetic()
    std = sa.assess(chart_at(ref, pos_of, {p: 0.0 for p in sa.POS}), ref, pos_of, 50, np.random.default_rng(1), 0.0)
    full = sa.assess(chart_at(ref, pos_of, {p: 1.0 for p in sa.POS}), ref, pos_of, 50, np.random.default_rng(1), 0.0)
    for p in sa.POOLED:
        assert std["positions"][p]["partial_rec_given_half"] < 0 < full["positions"][p]["partial_rec_given_half"]


def test_qb_without_receptions_is_not_identifiable():
    pos_of, ref = synthetic()
    out = sa.assess(chart_at(ref, pos_of, {p: 0.5 for p in sa.POS}), ref, pos_of, 50, np.random.default_rng(1))
    assert out["positions"]["QB"]["identifiable"] is False
    assert out["positions"]["QB"]["dist"] is None


def test_per_position_rescale_gives_identical_answers():
    """FantasyCalc-style switch: one factor per position leaves the within-position
    order, and so the answer, unchanged."""
    pos_of, ref = synthetic()
    base = chart_at(ref, pos_of, {p: 0.5 for p in sa.POS})
    scaled = chart_at(ref, pos_of, {p: 0.5 for p in sa.POS}, {"RB": 0.994, "WR": 1.018, "TE": 1.023, "QB": 1.012})
    a = sa.assess(base, ref, pos_of, 100, np.random.default_rng([1597, 0, 3]), 0.0)
    b = sa.assess(scaled, ref, pos_of, 100, np.random.default_rng([1597, 0, 3]), 0.0)
    assert a["pooled"] == b["pooled"]


def test_te_premium_probe():
    pos_of, ref = synthetic()
    prem = sa.assess(chart_at(ref, pos_of, {"QB": 1, "RB": 1, "WR": 1, "TE": 1.5}), ref, pos_of, 200,
                     np.random.default_rng(1), 0.0)
    plain = sa.assess(chart_at(ref, pos_of, {p: 1.0 for p in sa.POS}), ref, pos_of, 200, np.random.default_rng(1), 0.0)
    assert prem["te_premium_probe"]["flag"] is True
    assert plain["te_premium_probe"]["flag"] is False


def test_cost_of_half_value_error_is_true_over_assigned():
    pos_of, ref = synthetic()
    chart = chart_at(ref, pos_of, {p: 0.0 for p in sa.POS})
    cost = sa.cost_of_half(chart, ref, pos_of, "standard")
    keys = sa.select(chart, ref, pos_of, "RB", sa.TOP_N["RB"])
    errs = sorted(abs(ref[k][0] / (ref[k][0] + 0.5 * ref[k][1]) - 1) for k in keys)
    assert cost["RB"]["median_abs_value_error_pct"] == pytest.approx(100 * float(np.median(errs)), abs=0.06)
    assert cost["RB"]["pass_catching_backs"]["median_value_error_pct"] < 0  # Standard truth, Half assigned: overpriced catchers


# ---------------------------------------------------------------- real data (labelled CBS / USA Today)

@pytest.fixture(scope="module")
def real():
    return sa.run(boot=100)


def test_labelled_recovery_result_is_the_recorded_fail(real):
    """Pre-stated bar: >= 16/20 correct and Standard/Full separated in 10/10.
    Recorded result: the method fails it (single-list scoring is not identifiable)."""
    v = real["validation"]["prestated"]
    assert v["n"] == 20
    assert v["P1_pass"] is False and v["correct"] < 16
    for name in ("posthoc_all_positions", "posthoc_loco_bias"):
        assert real["validation"][name]["P1_pass"] is False


def test_projection_pseudo_charts_also_fail_absolute_level(real):
    """Even a projection's own Standard / Full column against the other two
    projections is mislabelled often: source opinion swamps the scoring signal."""
    sc = real["sanity_projection_pseudo_charts"]
    assert sc["n"] == 30 and sc["correct"] < 0.8 * sc["n"]


def test_two_published_columns_track_receptions(real):
    """CBS and USA Today: the Full/Standard ratio rises with reception share at
    RB, WR and TE every week (this is what is identifiable)."""
    for wk, row in real["two_column_ratio_vs_reception_share"].items():
        for chart in sa.LABELLED:
            for p in sa.POOLED:
                assert row[chart][p]["spearman_ratio_vs_rec_share"] > 0.1, (wk, chart, p)


def test_fantasycalc_and_fantasypros_columns_share_one_order(real):
    for wk, row in real["fantasycalc_multipliers"].items():
        for p in sa.POS:
            assert row[p]["same_within_position_order"] is True, (wk, p)
        assert row["wr_vs_rb"]["fc"] < 1.05 < row["wr_vs_rb"]["projections"]
    for wk, cols in real["summary"]["prestated"]["fantasycalc"].items():
        assert cols["standard"] == cols["ppr"], wk
    for wk, cols in real["summary"]["prestated"]["fantasypros"].items():
        assert cols["standard"] == cols["half_ppr"] == cols["ppr"], wk
