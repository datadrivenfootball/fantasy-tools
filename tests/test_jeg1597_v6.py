"""JEG-1597 v6 (research only): the scoring-aware metric's steps 5-7 and its identities.

Skipped when the pinned prior research tree (tools/research/jeg1597v6/prior.py) is not checked
out, as in CI: v6 imports the v4/v5 lane code from it read-only.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
V6 = REPO / "tools" / "research" / "jeg1597v6"
PRIOR = Path(os.environ.get("V6_PRIOR_TREE", str(REPO.parent / "ft-wt-jeg1597-v6-prior")))
pytestmark = pytest.mark.skipif(not (PRIOR / ".git").exists(), reason="prior research tree not checked out")

if (PRIOR / ".git").exists():
    sys.path.insert(0, str(V6))
    import v6  # noqa: E402
    import mix as mx  # noqa: E402


def line(rec=0.0, rec_yds=0.0, rec_td=0.0, rush_yds=0.0, rush_td=0.0, pass_yds=0.0, pass_td=0.0):
    return {"rec": rec, "rec_yds": rec_yds, "rec_td": rec_td, "rush_yds": rush_yds, "rush_td": rush_td,
            "pass_yds": pass_yds, "pass_td": pass_td, "int": 0.0, "targets": rec}


def test_catch_history_ratio_of_totals():
    games = [line(rec=5, rec_yds=60), line(rec=1, rec_yds=40, rec_td=1), line()]  # last one is not a game
    h = v6.catch_history(games, "half_ppr")
    assert h["n"] == 2
    pts = (2.5 + 6.0) + (0.5 + 4.0 + 6.0)
    assert h["q"] == pytest.approx(6 / pts)
    assert mx.F({**h["comp"], "rec": 0.0}, "standard") == pytest.approx(1.0)


def test_pull_limits():
    assert v6.pull(0.4, 0.3, 10, 0.0) == 0.4
    assert v6.pull(0.4, 0.3, 10, math.inf) == 0.3
    assert v6.pull(0.4, 0.3, 10, 10.0) == pytest.approx(0.35)


@pytest.mark.parametrize("s0", ["standard", "half_ppr", "ppr"])
def test_mix_is_per_anchor_point_and_line_reproduces_points(s0):
    h = v6.catch_history([line(rec=6, rec_yds=70, rec_td=0.5, rush_yds=5)] * 12, s0)
    prior = {"q": 0.3 if s0 != "standard" else 0.08, "comp": {c: 0.0 for c in v6.OTHER}}
    prior["comp"]["rec_yds"], prior["comp"]["rec_td"] = 6.0, 0.06  # 0.6 + 0.36 = 0.96 ...
    prior["comp"]["rush_yds"] = 0.4                                  # ... + 0.04 = 1 Standard point
    m, label, info = v6.v6_mix(h, prior, 24.0, 8.0, s0)
    assert label == "own"
    assert mx.F(m, s0) == pytest.approx(1.0)
    ln = v6.assumed_line(17.3, m)
    assert mx.F(ln, s0) == pytest.approx(17.3)
    assert info["a"] == pytest.approx(12 / 36)
    # Full minus Standard points of the line = its catches, exactly
    assert mx.F(ln, "ppr") - mx.F(ln, "standard") == pytest.approx(ln["rec"])


def test_fallback_uses_position_prior():
    prior = {"q": 0.35, "comp": {**{c: 0.0 for c in v6.OTHER}, "rec_yds": 10.0}}
    m, label, info = v6.v6_mix(None, prior, 24.0, 8.0, "half_ppr")
    assert label == "fallback_position" and info["n"] == 0
    assert m["rec"] == pytest.approx(0.35)


def test_position_prior_needs_eight_games():
    pos_of = {1: "WR", 2: "WR"}
    hs = {1: v6.catch_history([line(rec=5, rec_yds=50)] * 8, "half_ppr"),
          2: v6.catch_history([line(rec=1, rec_yds=90)] * 3, "half_ppr")}
    pri = v6.position_prior(hs, pos_of)
    assert pri["WR"]["q"] == pytest.approx(hs[1]["q"])


def test_share_selection_ties_go_to_smaller_k():
    import share_bt as sb
    rows = [{"q_hist": 0.4, "q_pos": 0.4, "n": 10, "pts_t": 30.0, "tg": 3, "rec_t": 12.0, "pid": "a"}] * 5
    assert sb.select(rows, "E") == 0.0


def test_params_frozen_values():
    p = v6.load_params()
    assert p["k_catch"] == {"QB": math.inf, "RB": 8.0, "WR": 24.0, "TE": 16.0}


@pytest.fixture(scope="module")
def week10():
    _ctx, Ws = v6.load((10,))
    W = Ws[0]
    return W, W.chain(kinds=("v5",))


def test_identity_at_the_anchor_and_ddf_reproduced(week10):
    W, ch = week10
    for c in v6.CHARTS:
        u = ch["U"][c]
        a = W.av5(ch, c, "v5", u.s0)
        assert max(abs(a[k] - u.records[k]["A"]) for k in a) == 0.0
    for s in mx.SCORINGS:
        _new, cur = W.metric(ch, s)
        today = W.wk.current(s)["ddf"]
        assert max(abs((cur[i] or 0.0) - (today.get(i) or 0.0)) for i in cur) <= 1e-9


def test_metric_at_full_differs_only_through_fantasypros(week10):
    W, ch = week10
    new, cur = W.metric(ch, "ppr")
    fc_only = W.metric(ch, "ppr", lists={"fantasycalc": W.av5(ch, "fantasycalc", "v5", "ppr")})[0]
    assert max(abs((fc_only[i] or 0.0) - (cur[i] or 0.0)) for i in cur) <= 1e-9
    assert any(abs((new[i] or 0.0) - (cur[i] or 0.0)) > 1e-6 for i in cur)
