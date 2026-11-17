"""JEG-1691 v5 research harness: pure-function tests and dev-week integration checks.

Dev weeks only (5-7); nothing here loads weeks 8-10 chart inputs or runs T1's test origins.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
H = REPO / "tools" / "research" / "jeg1691"
sys.path.insert(0, str(H))

import mix as mx  # noqa: E402
import stats5 as st  # noqa: E402

LINE = {"pass_yds": 0.0, "pass_td": 0.0, "rush_yds": 60.0, "rush_td": 0.5, "rec": 4.0, "rec_yds": 30.0, "rec_td": 0.2}


def test_scoring_weights_match_pipeline():
    sys.path.insert(0, str(REPO / "pipelines" / "lib"))
    from scoring import SCORING
    names = {"pass_yds": "passing_yards", "pass_td": "passing_tds", "rush_yds": "rushing_yards",
             "rush_td": "rushing_tds", "rec": "receptions", "rec_yds": "receiving_yards", "rec_td": "receiving_tds"}
    for s in mx.SCORINGS:
        w = mx.weights(s)
        for c, n in names.items():
            assert w[c] == SCORING[s][n]


def test_mix_normalised_and_assumed_line_exact_at_anchor():
    for s0 in ("half_ppr", "ppr"):
        m = mx.normalise(LINE, s0)
        assert mx.F(m, s0) == pytest.approx(1.0, abs=1e-15)
        line = mx.assumed_line(13.7, mx.Mix(m, "own", 10))
        assert mx.F(line, s0) == pytest.approx(13.7, abs=1e-12)
        assert mx.points_at(13.7, m, s0, s0) == 13.7


def test_presets_reduce_to_reception_share():
    """Section 1 algebra: P(s)/P(s0) = (1 + r_s rho) / (1 + r_s0 rho)."""
    s0 = "half_ppr"
    m = mx.normalise(LINE, s0)
    rho = mx.rho(m, s0)
    for s in mx.SCORINGS:
        assert mx.points_at(10.0, m, s, s0) == pytest.approx(10.0 * (1 + mx.REC_W[s] * rho) / (1 + 0.5 * rho))
    two = mx.two_bucket_mix(LINE["rec"], mx.F(LINE, "standard"), s0)
    for s in mx.SCORINGS:
        assert mx.points_at(10.0, two, s, s0) == pytest.approx(mx.points_at(10.0, m, s, s0))


def test_history_rates_recency_and_empty():
    lines = [dict(LINE, rec=2.0), dict(LINE, rec=6.0)]
    flat = mx.history_rates(lines, math.inf)
    assert flat.rates["rec"] == 4.0 and flat.n_eff == 2.0
    rec = mx.history_rates(lines, 1.0)
    assert rec.rates["rec"] > 4.0          # the latest game weighs more
    assert mx.history_rates([{c: 0.0 for c in mx.CATS}], 8.0) is None


def test_shrinkage_limits_and_fallback():
    prior = mx.normalise(dict(LINE, rec=1.0), "ppr")
    h = mx.history_rates([LINE] * 4, math.inf)
    own = mx.shrunk_mix(h, prior, {c: 0.0 for c in mx.CATS}, "ppr")
    assert own.m == pytest.approx(mx.normalise(LINE, "ppr"))
    pos = mx.shrunk_mix(h, prior, {c: math.inf for c in mx.CATS}, "ppr")
    assert pos.m == pytest.approx(prior)
    fb = mx.shrunk_mix(None, prior, {c: 4.0 for c in mx.CATS}, "ppr")
    assert fb.label == "fallback_position_mix" and fb.m == pytest.approx(prior)


def test_stats_helpers():
    assert st.ranks([3, 1, 1, 2]) == [4.0, 1.5, 1.5, 3.0]
    assert st.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    mv = st.moves({"a": 1, "b": 2}, {"a": 2, "b": 1}, ["a", "b"])
    assert mv == {"a": 0.5, "b": -0.5}
    assert st.no_harm_label((0.0, 0.1)) == "PASS"
    assert st.no_harm_label((-0.1, 0.1)) == "INCONCLUSIVE"
    assert st.no_harm_label((-0.2, -0.1)) == "HARM"


def test_runner_refuses_decisive_weeks_without_registration():
    r = subprocess.run([sys.executable, str(H / "run_v5.py"), "--weeks", "8", "9", "10"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "--decisive" in (r.stderr + r.stdout)
    r = subprocess.run([sys.executable, str(H / "run_v5.py"), "--weeks", "8", "--decisive", "0000000"],
                       capture_output=True, text=True)
    assert r.returncode != 0


def test_reference_caches_respect_cutoffs():
    """No reference comes from a vintage later than the week's DDF ESPN snapshot."""
    import refs as rf
    caps = json.loads((H / "cache" / "espn_captures_ros.json").read_text())
    for w in (7, 8, 9, 10):
        hist = json.loads((REPO / "data" / "history" / f"week-{w}.json").read_text())
        cutoff = hist["sources"]["espn"]["captured_at"]
        assert caps["meta"]["weeks"][f"w{w}"]["capture_at"] <= cutoff, w
    sl = json.loads((H / "cache" / "sleeper_ros_week10.json").read_text())
    assert sl["meta"]["as_of"] <= json.loads((REPO / "data" / "history" / "week-10.json").read_text())[
        "sources"]["espn"]["captured_at"]
    assert max(v["n_weeks"] for v in sl["players"].values()) <= 8
    for w, (_commit, snap) in rf.ESPN_COMMITS.items():
        hist = json.loads((REPO / "data" / "history" / f"week-{w}.json").read_text())
        assert hist["sources"]["espn"]["snapshot_date"] == snap


@pytest.fixture(scope="module")
def dev_week():
    import history5 as h5
    import t1 as T1
    import v5
    hist = h5.load()
    ctx = v5.R3.load_world()
    sel = T1.select(hist["by_player"], ctx["pos_of"])
    W = v5.Week5(ctx, 5, sel, hist["by_player"])
    return W, W.chain()


def test_t2_exactness_dev_week(dev_week):
    import tests5 as TS
    W, ch = dev_week
    r = TS.t2(W, ch)
    assert r["identity"] == 0.0
    assert r["espn_twin"] == 0.0
    assert r["ddf_repro"] <= 1e-9
    assert r["espn_scoring"] <= 1e-4
    assert r["pass"]


def test_pseudo_source_does_not_move_included_sources(dev_week):
    W, ch = dev_week
    for s in ("standard", "ppr"):
        cur = W.wk.current(s)
        rows = ch["runs"][s]["rows"]
        for k in ("fantasycalc", "fantasypros", "cbs", "usatoday", "espn"):
            a = {i: r["adjusted"].get(k) for i, r in rows.items() if r["adjusted"].get(k) is not None}
            b = cur["adj"]
            assert all(a[i] == b[i][k] for i in a if i in b and b[i].get(k) is not None)


def _battery(**over):
    """A synthetic battery where every Tier 1 chart test passes."""
    b = {"T2": {8: {"pass": True}}, "T3": {"fantasycalc": {"label": "PASS"}},
         "T4": {"fantasycalc": {"pass": True}}, "T5": {"fantasycalc": {"pass": True}},
         "T6": {"fantasycalc": {"WR/RB": {"pass": True}, "TE/RB": {"pass": True}}},
         "T7": {"fantasycalc|standard": {"label": "INCONCLUSIVE"}}, "T8": {"ppr": {"label": "PASS"}}}
    b.update(over)
    return b


T1_PASS = {"verdict": "PASS", "a": {"diff": 0.1}}


def test_outcome_rules_are_mechanical():
    import outcome as oc
    assert oc.decide(_battery(), {"S-FP-Full": _battery()}, T1_PASS)["outcome"] == "C"
    # a FantasyPros T5 failure under the Full anchor blocks C
    d = oc.decide(_battery(), {"S-FP-Full": _battery(T5={"fantasypros": {"pass": False}})}, T1_PASS)
    assert d["outcome"] == "B" and any("hinges on S-FP-Full" in r["rule"] for r in d["rules_fired"])
    assert oc.decide(_battery(T4={"x": {"pass": False}}), {}, T1_PASS)["outcome"] == "A"
    assert oc.decide(_battery(T8={"ppr": {"label": "HARM"}}), {}, T1_PASS)["outcome"] == "A"
    assert oc.decide(_battery(), {}, {"verdict": "INCONCLUSIVE", "a": {"diff": -0.01}})["outcome"] == "A"
    assert oc.decide(_battery(), {}, {"verdict": "INCONCLUSIVE", "a": {"diff": 0.01}})["outcome"] == "B"
    assert oc.decide(_battery(), {}, {"verdict": "FAIL", "a": {"diff": -0.1}})["outcome"] == "A"
    assert oc.decide(_battery(T2={8: {"pass": False}}), {}, T1_PASS)["outcome"] == "B (void run)"
    assert oc.decide(_battery(), {"S-drop-cbs": _battery(T8={"ppr": {"label": "HARM"}})}, T1_PASS)["outcome"] == "B"
    assert oc.decide(_battery(), {"W10-only (fresh Sleeper)": _battery(T3={"f": {"label": "PARTIAL"}})},
                     T1_PASS)["outcome"] == "B"
    assert oc.decide(_battery(T6={"f": {"WR/RB": {"pass": None}}}), {}, T1_PASS)["outcome"] == "B"


def test_guard_requires_committed_approval():
    r = subprocess.run([sys.executable, str(H / "run_v5.py"), "--weeks", "8", "9", "10", "--decisive", "HEAD"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "APPROVAL" in (r.stderr + r.stdout)
    r = subprocess.run([sys.executable, str(H / "run_v5.py"), "--weeks", "8", "--decisive", "HEAD"],
                       capture_output=True, text=True)
    assert r.returncode != 0          # all three decisive weeks, never a subset


def test_manifest_covers_the_executed_tree():
    import run_v5 as R
    for p in ("pipelines/value_reference.py", "tools/research/jeg1611/v4.py",
              "data/inputs/weekly_projections_sleeper.csv.gz", "tools/research/jeg1691/v5.py",
              "tools/research/jeg1691/cache/sleeper_ros_week10.json", "tools/research/jeg1691/out/t6_widening.json",
              "docs/research/jeg1691/preregistration.md"):
        assert R.in_manifest(p), p
    for p in ("tools/research/jeg1691/out/decisive/verdict.json", "tools/research/jeg1691/APPROVAL.json",
              "tools/research/jeg1691/DECISIVE.lock"):
        assert not R.in_manifest(p), p


def test_espn_left_out_of_step4_keeps_references(dev_week):
    W, ch = dev_week
    cx = W.chain(exclude=("espn",))
    for s in ("standard", "ppr"):
        a, b = ch["runs"][s]["rows"], cx["runs"][s]["rows"]
        assert all(a[i]["adjusted"].get("espn") == b[i]["adjusted"].get("espn") for i in a if i in b)
        assert ch["ps_adj"][("sleeper_own", s)] == cx["ps_adj"][("sleeper_own", s)]
    p0 = {k: v[0] for k, v in ch["P"][("fantasycalc", "v5")].items()}
    p1 = {k: v[0] for k, v in cx["P"][("fantasycalc", "v5")].items()}
    assert any(abs(p0[k] - p1[k]) > 1e-9 for k in p0 if k in p1)


@pytest.mark.parametrize("flag", ["--decisive", "--replication"])
def test_no_sensitivity_refused_outside_dev(flag):
    weeks = ["8", "9", "10"] if flag == "--decisive" else ["11", "12", "13", "14"]
    snap = {n: ((H / n).read_bytes() if (H / n).exists() else None) for n in ("DECISIVE.lock", "REPLICATION.lock")}
    r = subprocess.run([sys.executable, str(H / "run_v5.py"), "--weeks", *weeks, flag, "HEAD", "--no-sensitivity"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "--no-sensitivity is dev only" in (r.stderr + r.stdout)
    # 2026-11-17 (after the v5 lock was committed): the refused call must leave both locks as they were
    assert {n: ((H / n).read_bytes() if (H / n).exists() else None) for n in snap} == snap
