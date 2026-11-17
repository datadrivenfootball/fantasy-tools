"""JEG-1691 v5.1 backtest harness: synthetic data with known answers, the outcome map, the guard.

No real backtest number is produced here: every battery runs on planted synthetic players.
"""
from __future__ import annotations

import math
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
V51 = REPO / "tools" / "research" / "jeg1691" / "v51"
sys.path.insert(0, str(V51))

import bt  # noqa: E402

SYN = replace(bt.PRIMARY, name="synthetic", eval_seasons=(2017, 2018, 2019), sel_start=2016, b1_needed=2,
              b5=False)
V5P = {"QB": (math.inf, 17.0), "RB": (8.0, 17.0), "WR": (64.0, 8.0), "TE": (2.0, 8.0)}


def planted(n_per_pos=40, seasons=range(2015, 2020), noise=0.15, seed=1, spread=0.12, weeks=range(1, 18)):
    """Players whose true catch share q_i is fixed; receptions = q_i x Half points + noise."""
    rng = random.Random(seed)
    base = {"RB": 0.25, "WR": 0.40, "TE": 0.45}
    players, truth = {}, {}
    for p, b in base.items():
        for j in range(n_per_pos):
            q = max(0.02, rng.gauss(b, spread))
            pid = f"{p}{j}"
            truth[pid] = q
            gs = []
            for s in seasons:
                for w in weeks:
                    half = rng.uniform(4, 20)
                    rec = max(0.0, q * half + rng.gauss(0, noise * half))
                    std = half - 0.5 * rec
                    gs.append((s, w, p, rec, half, std + rec))
            players[pid] = gs
    return players, truth


def test_rules_recover_a_planted_mix_and_position_average_fails():
    players, _ = planted()
    b = bt.battery(players, SYN, V5P, None, None, n_boot=200, n_shuffle=100)
    for p in bt.POOL:
        assert b["B1"][p]["label"] == "PASS", (p, b["B1"][p])
        assert b["B3"][p]["pass"], (p, b["B3"][p])
        # the position average fails the planted case on B1's metric (it is worse than RL)
        assert b["reported"][p]["E"]["Rpos"] > b["reported"][p]["E"]["RL"]
        assert b["B1"][p]["ci95"][0] > 0


def test_b3_can_fail_for_heavy_pull_and_for_raw_history():
    players, _ = planted()
    b = bt.battery(players, SYN, V5P, None, None, n_boot=50, n_shuffle=20)
    assert b["B3"]["WR"]["slope_Rv5"] > bt.B3_BAND[1]          # heavy pull (k 64) compresses
    # raw history over-disperses when own histories are short and noisy: newcomers with 3 games,
    # veterans (long histories) define the position share
    vets, _ = planted(n_per_pos=20, seasons=range(2015, 2018), seed=4)
    new, _ = planted(n_per_pos=60, seasons=(2017,), weeks=range(2, 9), noise=1.0, spread=0.02, seed=5)
    new = {"n" + k: v for k, v in new.items()}
    cfg = replace(SYN, origins=(5,), eval_seasons=(2017,), sel_start=2016)
    rows = [r for r in bt.origin_rows({**vets, **new}, 2017, 5, cfg, V5P)["rows"]
            if r["pid"].startswith("n") and r["pos"] == "WR"]
    x = [bt.pred(r, "R0") for r in rows]
    y = [r["rec_t"] / r["pts_t"] for r in rows]
    w = [r["pts_t"] for r in rows]
    assert bt.wls_slope(x, y, w) < bt.B3_BAND[0]


def test_b0_identities_hold_and_selection_ties_go_light():
    players, _ = planted(n_per_pos=10)
    rows = bt.origin_rows(players, 2017, 5, SYN, V5P)["rows"]
    r0 = bt.b0(players, {"rows": 100, "integrity_bad": 0}, rows, V5P)
    assert r0["pass"] and all(r0["identities"].values())
    assert not bt.b0(players, {"rows": 100, "integrity_bad": 1}, rows, V5P)["pass"]
    # identical rows: every k gives the same error, so the lightest (0) wins the tie
    flat = [dict(r, q_hist=r["q_pos"]) for r in rows]
    assert bt.select_k(flat, "WR") == 0.0


def test_position_share_uses_only_games_before_the_origin():
    players, _ = planted(n_per_pos=10)
    o1 = bt.origin_rows(players, 2017, 5, SYN, V5P)
    later = {k: v + [(2017, 6, v[0][2], 50.0, 1.0, 51.0)] for k, v in players.items()}
    o2 = bt.origin_rows(later, 2017, 5, SYN, V5P)
    assert o1["q_pos"] == o2["q_pos"]


def test_b5_on_planted_per_stat_players():
    rng = random.Random(5)
    pgs = {}
    for p, b in {"RB": 0.25, "WR": 0.4, "TE": 0.45}.items():
        for j in range(30):
            q = max(0.05, rng.gauss(b, 0.12))
            gs = []
            for s in (2024, 2025):
                for w in range(1, 18):
                    yds = rng.uniform(30, 120)
                    line = {"pass_yds": 0.0, "pass_td": 0.0, "rush_yds": 0.0, "rush_td": 0.0,
                            "rec_yds": yds, "rec_td": 0.2, "rec": 0.0, "targets": 1.0}
                    other = 0.1 * yds + 1.2
                    rec = q * other / (1 - 0.5 * q)
                    line["rec"] = max(0.0, rec + rng.gauss(0, 0.2))
                    gs.append((s, w, p, line["rec"], bt.mx.F(line, "half_ppr"), line))
            pgs[1000 * (j + 1) + len(p)] = gs
    k = {"RB": 0.0, "WR": 0.0, "TE": 0.0}
    cfg = replace(bt.PRIMARY, b5_origins=(6, 10))
    out = bt.b5(pgs, cfg, V5P, k, bt.np.random.default_rng(1), 100, 50)
    assert out["label"] == "PASS" and not out["harm_vs_v5"]


def _bat(**over):
    b = {"B0": {"pass": True},
         "B1": {p: {"label": "PASS"} for p in bt.POOL}, "B3": {p: {"pass": True} for p in bt.POOL},
         "B2": {"WR": {"label": "PASS"}, "RB": {"label": "INCONCLUSIVE"}, "TE": {"label": "PASS"}},
         "B5": {"label": "PASS", "harm_vs_v5": False}}
    b.update(over)
    return b


def test_outcome_map():
    assert bt.decide(_bat(), {"S-no-2020": _bat()})["outcome"] == "C"
    nob5 = _bat()
    del nob5["B5"]
    assert bt.decide(_bat(), {"S-no-2025": nob5})["outcome"] == "C"           # absent is not a flip
    assert bt.decide(nob5, {})["outcome"] == "A"                               # absent in the primary
    assert bt.decide(_bat(B0={"pass": False}), {})["outcome"] == "void"
    assert bt.decide(_bat(B1={"RB": {"label": "PASS"}, "WR": {"label": "INCONCLUSIVE"},
                              "TE": {"label": "PASS"}}), {})["outcome"] == "A"
    assert bt.decide(_bat(B2={"WR": {"label": "INCONCLUSIVE"}, "RB": {"label": "PASS"},
                              "TE": {"label": "PASS"}}), {})["outcome"] == "A"   # D-c
    assert bt.decide(_bat(B2={"WR": {"label": "PASS"}, "RB": {"label": "HARM"},
                              "TE": {"label": "PASS"}}), {})["outcome"] == "A"
    assert bt.decide(_bat(B3={"RB": {"pass": True}, "WR": {"pass": False}, "TE": {"pass": True}}), {})["outcome"] == "A"
    assert bt.decide(_bat(B5={"label": "PASS", "harm_vs_v5": True}), {})["outcome"] == "A"
    flip = _bat(B1={"RB": {"label": "PASS"}, "WR": {"label": "PASS"}, "TE": {"label": "FAIL"}})
    d = bt.decide(_bat(), {"S-no-2020": flip})
    assert d["outcome"] == "A" and any("S-no-2020" in r["rule"] for r in d["rules_fired"])


def test_sensitivity_configs_as_registered():
    s = {c.name: c for c in bt.SENSITIVITIES}
    assert s["S-no-2020"].drop_seasons == (2020,) and s["S-no-2020"].b1_needed == 6
    assert s["S-no-2025"].drop_seasons == (2025,) and s["S-no-2025"].b1_needed == 6 and not s["S-no-2025"].b5
    assert s["S-anchor-Full"].anchor == "ppr" and s["S-truth-ROS"].truth == "ros"
    assert s["S-origins-alt"].origins == (4, 8, 12)
    assert bt.PRIMARY.eval_seasons == tuple(range(2017, 2026)) and bt.PRIMARY.origins == (5, 9, 13)
    assert bt.G_L == (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)


def test_dropped_season_leaves_selection_folds():
    players, _ = planted(n_per_pos=8)
    cfg = replace(SYN, drop_seasons=(2017,), b1_needed=1)
    b = bt.battery(players, cfg, V5P, None, None, n_boot=20, n_shuffle=10)
    assert "2017" not in {str(k) for k in b["k_by_season"]}
    assert all(not k.startswith("2017-") for k in b["excluded"])


def _run(*a):
    return subprocess.run([sys.executable, str(V51 / "run_v51.py"), *a], capture_output=True, text=True)


def test_guard_refuses():
    r = _run("--mode", "backtest")
    assert r.returncode != 0 and "--approved" in r.stderr + r.stdout
    r = _run("--mode", "backtest", "--approved", "HEAD")
    assert r.returncode != 0 and "V51_APPROVAL" in r.stderr + r.stdout
    for extra in (("--n-boot", "10"), ("--n-shuffle", "10"), ("--no-sensitivity",)):
        r = _run("--mode", "backtest", "--approved", "HEAD", *extra)
        assert r.returncode != 0 and "dry-run only" in r.stderr + r.stdout
    assert not (V51 / "V51_BACKTEST.lock").exists()


def test_manifest_scope():
    import run_v51 as R
    for p in ("tools/research/jeg1691/v51/bt.py", "tools/research/jeg1691/mix.py",
              "tools/research/jeg1691/out/decisive/selection.json", "data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz",
              "tools/research/jeg1691/cache/pgs_weekly_2024_2026.json.gz", "docs/research/jeg1691/v51-preregistration.md"):
        assert R.in_manifest(p), p
    for p in ("tools/research/jeg1691/out51/backtest/verdict.json", "tools/research/jeg1691/v51/V51_APPROVAL.json",
              "tools/research/jeg1691/v51/V51_BACKTEST.lock"):
        assert not R.in_manifest(p), p


def test_loader_refuses_2026(tmp_path):
    import gzip
    f = tmp_path / "x.csv.gz"
    with gzip.open(f, "wt") as g:
        g.write("season,week,player_id,name,pos,team,std,half_ppr,ppr\n2026,1,a,b,WR,X,1,1.5,2\n")
    with pytest.raises(SystemExit):
        bt.load_nflverse(f)
