"""JEG-1601: unit tests of the step 4 metric code on synthetic data."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import rankdata, spearmanr

PATH = Path(__file__).resolve().parents[1] / "tools" / "research" / "jeg1597" / "step4_tests.py"
spec = importlib.util.spec_from_file_location("step4_tests", PATH)
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)


def test_weighted_ranks_match_expanded_rankdata():
    x = np.array([3.0, 1.0, 3.0, 2.0, 5.0])
    w = np.array([2, 0, 1, 3, 1])
    got = st.weighted_ranks(x, w)[0]
    expanded = np.repeat(x, w)
    ranks = rankdata(expanded)
    for i in range(len(x)):
        if w[i]:
            assert got[i] == pytest.approx(ranks[np.flatnonzero(expanded == x[i])[0]])


def test_spearman_matches_scipy_with_ties():
    rng = np.random.default_rng(0)
    x = rng.integers(0, 6, 40).astype(float)
    y = x + rng.normal(0, 2, 40)
    assert st.spearman(x, y)[0] == pytest.approx(spearmanr(x, y)[0])


def test_spearman_weights_equal_expansion():
    rng = np.random.default_rng(1)
    x, y = rng.normal(size=15), rng.normal(size=15)
    w = rng.integers(0, 4, 15)
    ex, ey = np.repeat(x, w), np.repeat(y, w)
    assert st.spearman(x, y, w[None, :])[0] == pytest.approx(spearmanr(ex, ey)[0])


def test_spearman_perfect_and_reversed():
    x = np.arange(10.0)
    assert st.spearman(x, x ** 3)[0] == pytest.approx(1.0)
    assert st.spearman(x, -x)[0] == pytest.approx(-1.0)


def test_pair_concordance_counts():
    target = np.array([4.0, 3.0, 2.0, 1.0])
    assert st.pair_concordance(target, target)[0] == pytest.approx(1.0)
    assert st.pair_concordance(-target, target)[0] == pytest.approx(0.0)
    # one adjacent swap: 5 of 6 pairs concordant
    assert st.pair_concordance(np.array([4.0, 2.0, 3.0, 1.0]), target)[0] == pytest.approx(5 / 6)
    # method tie counts half
    assert st.pair_concordance(np.array([4.0, 3.0, 3.0, 1.0]), target)[0] == pytest.approx(5.5 / 6)


def test_pair_concordance_skips_target_ties_and_self_copies():
    target = np.array([2.0, 2.0, 1.0])
    value = np.array([1.0, 3.0, 0.0])
    # pair (0,1) tied on target, not scored; (0,2) and (1,2) concordant
    assert st.pair_concordance(value, target)[0] == pytest.approx(1.0)
    # a duplicated player adds no self-pair; pairs weighted w_i * w_j
    w = np.array([[3.0, 0.0, 1.0]])
    assert st.pair_concordance(value, target, w)[0] == pytest.approx(1.0)
    value2 = np.array([0.5, 3.0, 1.0])   # player 0 now below player 2: discordant
    w2 = np.array([[2.0, 1.0, 1.0]])
    # scored pairs: (0,2) x2 discordant, (1,2) x1 concordant -> 1/3
    assert st.pair_concordance(value2, target, w2)[0] == pytest.approx(1 / 3)


def test_bootstrap_deterministic_with_seed_1597():
    a = st.bootstrap_counts(50, 200, seed=1597)
    b = st.bootstrap_counts(50, 200, seed=1597)
    c = st.bootstrap_counts(50, 200, seed=1598)
    assert st.SEED == 1597 and st.N_BOOT == 2000
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert np.all(a.sum(1) == 50)


def test_interval_ignores_nan():
    lo, hi = st.interval(np.r_[np.arange(101.0), np.nan])
    assert lo == pytest.approx(2.5) and hi == pytest.approx(97.5)


def test_missing_row_is_value_zero():
    rows = {(5, "standard", "DDF_cur", 1): 10.0, (5, "standard", "DDF_cur", 2): 4.0,
            (6, "standard", "DDF_cur", 3): 7.0}
    lk = st.value_lookup(rows, 5, "standard", "DDF_cur")
    assert [lk.get(k, 0.0) for k in (1, 2, 3)] == [10.0, 4.0, 0.0]


def test_realized_missing_week_is_zero():
    act = {(5, 1): {"std": 10.0}, (7, 1): {"std": 2.0}, (6, 2): {"std": 5.0}}
    got = st.realized_points(act, [1, 2, 3], range(5, 9), "std")
    assert got == {1: 12.0, 2: 5.0, 3: 0.0}


def test_verdict_rules():
    def d(diff, lo, hi, s="standard", m="M1", a="x"):
        return {"diff": diff, "ci95": [lo, hi], "scoring": s, "metric": m, "a": a}
    assert st.verdict_h1([d(1, 0.1, 2), d(1, 0.1, 2)]) == "PASS"
    assert st.verdict_h1([d(1, 0.1, 2), d(0.1, -0.1, 2)]) == "NOT SHOWN"
    assert st.verdict_h1([d(1, 0.1, 2), d(-1, -2, -0.1)]) == "FAIL"
    prim = [d(1, 0.1, 2)] * 4
    ok = [d(0.5, -1, 2)] * 4
    flip = [d(0.5, -1, 2)] * 3 + [d(-0.5, -1, 2)]
    assert st.verdict_h2(prim, ok, ok)[0] == "PASS"
    assert st.verdict_h2(prim, ok, flip)[0] == "FAIL (not robust)"
