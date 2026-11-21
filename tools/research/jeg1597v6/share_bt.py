"""v6 step 5, EXPLORATORY: how hard to pull a player's catch share toward his position.

Not pre-registered. 2017-2025 were already seen by the v5.1 backtest (locked, PR #1478), so
nothing here is a holdout result. Reuses the v5.1 harness functions read-only (prior.py).

What is new against v5.1 (all dated in docs/research/jeg1597/v6-design.md, choice log):
- a wide grid of pull strengths, K_WIDE (v5.1 capped the pull at 8 games and hit the cap in
  every season, so a heavier pull was never tested);
- two forward selection rules: E-min (lowest catch error on earlier seasons, as v5.1) and
  CAL (the k whose pooled share slope on earlier seasons is closest to 1);
- a deployment-matched history window: the chart chain only has per-stat history from 2024,
  so at a 2026 chart week a player has at most about 2.5 seasons of games. HIST_SEASONS = 2
  keeps games from seasons Y-2..Y only, which is what the chain sees.
Metrics are v5.1's E (catches per game error) and the points-weighted share slope (B3 form).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prior  # noqa: E402

prior.activate()
import bt  # noqa: E402  (v5.1 harness, read-only)

K_WIDE = (0.0, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0, math.inf)
POOL = ("RB", "WR", "TE")
POS_ALL = ("QB", "RB", "WR", "TE")
SEED = 15976
OUT = HERE / "out"


def window_players(players: dict, season: int, hist_seasons: int | None) -> dict:
    if hist_seasons is None:
        return players
    lo = season - hist_seasons
    return {pid: [g for g in gs if g[0] >= lo] for pid, gs in players.items()}


def rows_by_origin(players, cfg, v5p, hist_seasons):
    seasons = range(cfg.sel_start, max(cfg.eval_seasons) + 1)
    out = {}
    for s in seasons:
        pl = window_players(players, s, hist_seasons)
        for w in cfg.origins:
            out[(s, w)] = bt.origin_rows(pl, s, w, cfg, v5p)["rows"]
    return out


def share_slope(rows, k):
    q = [bt.shrink(r["q_hist"], r["q_pos"], r["n"], k) for r in rows]
    return bt.wls_slope(q, [r["rec_t"] / r["pts_t"] for r in rows], [r["pts_t"] for r in rows])


def mean_err(rows, k):
    return float(np.mean([bt.err(r, bt.shrink(r["q_hist"], r["q_pos"], r["n"], k)) for r in rows]))


def select(rows, rule):
    """Forward selection on earlier-season rows of one position. Ties go to the smaller k."""
    if not rows:
        return None
    best = None
    for k in K_WIDE:
        if rule == "E":
            score = mean_err(rows, k)
        else:
            sl = share_slope(rows, k)
            score = math.inf if sl is None else abs(math.log(sl)) if sl > 0 else math.inf
        if best is None or score < best[1]:
            best = (k, score)
    return best[0]


def slope_ci(rows, preds, rng, n):
    pids = np.asarray([r["pid"] for r in rows])
    x = np.asarray(preds, float)
    y = np.asarray([r["rec_t"] / r["pts_t"] for r in rows])
    w = np.asarray([r["pts_t"] for r in rows])
    uniq, inv = np.unique(pids, return_inverse=True)
    members = [np.flatnonzero(inv == j) for j in range(len(uniq))]
    draws = []
    for _ in range(n):
        idx = np.concatenate([members[j] for j in rng.integers(0, len(uniq), len(uniq))])
        s = bt.wls_slope(x[idx], y[idx], w[idx])
        if s is not None:
            draws.append(s)
    return (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))


def run(hist_seasons: int | None = 2, n_boot: int = 1000) -> dict:
    players, integrity = bt.load_nflverse()
    v5p = bt.v5_params()
    cfg = bt.PRIMARY
    by_o = rows_by_origin(players, cfg, v5p, hist_seasons)
    rng = np.random.default_rng(SEED)
    res = {"hist_seasons": hist_seasons, "grid": [("inf" if math.isinf(k) else k) for k in K_WIDE],
           "integrity": integrity, "k_by_season": {}, "positions": {}}
    ev = {p: {"E": [], "CAL": []} for p in POS_ALL}
    for Y in cfg.eval_seasons:
        sel_rows = [r for (s, _w), rs in by_o.items() if cfg.sel_start <= s < Y for r in rs]
        ks = {}
        for p in POS_ALL:
            rp = [r for r in sel_rows if r["pos"] == p]
            ks[p] = {"E": select(rp, "E"), "CAL": select(rp, "CAL")}
        res["k_by_season"][Y] = {p: {r: ("inf" if v is not None and math.isinf(v) else v) for r, v in d.items()}
                                 for p, d in ks.items()}
        for (s, _w), rs in by_o.items():
            if s != Y:
                continue
            for r in rs:
                for rule in ("E", "CAL"):
                    k = ks[r["pos"]][rule]
                    if k is not None:
                        ev[r["pos"]][rule].append(dict(r, k=k))
    # the strengths the 2026 chart chain uses: selected on every season 2016-2025 (forward of 2026)
    all_rows = [r for (s, _w), rs in by_o.items() if cfg.sel_start <= s <= max(cfg.eval_seasons) for r in rs]
    res["k_2026"] = {p: {rule: select([r for r in all_rows if r["pos"] == p], rule) for rule in ("E", "CAL")}
                     for p in POS_ALL}
    for p in POS_ALL:
        rs = ev[p]["E"]
        if len(rs) < 10:
            continue
        rows_cal = ev[p]["CAL"]
        preds = {
            "v6_E": [bt.shrink(r["q_hist"], r["q_pos"], r["n"], r["k"]) for r in rs],
            "v6_CAL": [bt.shrink(r["q_hist"], r["q_pos"], r["n"], r["k"]) for r in rows_cal],
            "light_k8": [bt.shrink(r["q_hist"], r["q_pos"], r["n"], 8.0) for r in rs],
            "raw_k0": [r["q_hist"] for r in rs],
            "position": [r["q_pos"] for r in rs],
            "v5_heavy": [bt.pred(r, "Rv5") for r in rs],
        }
        E = {name: [bt.err(r, q) for r, q in zip(rs, qs)] for name, qs in preds.items()}
        pids = [r["pid"] for r in rs]
        block = {"n_rows": len(rs), "n_players": len(set(pids)), "E": {}, "slope": {}, "slope_ci": {},
                 "diff_vs_position": {}, "diff_vs_light": {}, "fixed_k": {}}
        for name, qs in preds.items():
            block["E"][name] = float(np.mean(E[name]))
            block["slope"][name] = bt.wls_slope(qs, [r["rec_t"] / r["pts_t"] for r in rs], [r["pts_t"] for r in rs])
            block["slope_ci"][name] = slope_ci(rs, qs, rng, n_boot)
        for name in ("v6_E", "v6_CAL", "light_k8", "raw_k0", "v5_heavy"):
            d = [a - b for a, b in zip(E["position"], E[name])]
            block["diff_vs_position"][name] = bt.cluster_ci(pids, d, rng, n_boot)
            d2 = [a - b for a, b in zip(E["light_k8"], E[name])]
            block["diff_vs_light"][name] = bt.cluster_ci(pids, d2, rng, n_boot)
        # the whole curve on the evaluation rows (descriptive: how E and slope trade off)
        for k in K_WIDE:
            block["fixed_k"]["inf" if math.isinf(k) else k] = {"E": mean_err(rs, k), "slope": share_slope(rs, k)}
        res["positions"][p] = block
    return res


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, float):
        return "inf" if math.isinf(x) else round(x, 6)
    return x


def main():
    OUT.mkdir(exist_ok=True)
    out = {"label": "EXPLORATORY (not pre-registered; 2017-2025 already seen by v5.1)",
           "deployment_matched": run(2), "all_history": run(None)}
    (OUT / "share_backtest.json").write_text(json.dumps(jsonable(out), indent=1))
    k26 = out["deployment_matched"]["k_2026"]
    params = {"_note": "v6 step 5 pull strengths (games), forward E-min on 2016-2025, deployment-matched "
                       "history window (2 prior seasons). EXPLORATORY; written by share_bt.py.",
              "k_catch": {p: d["E"] for p, d in k26.items()}, "k_catch_cal_rule": {p: d["CAL"] for p, d in k26.items()},
              "k_other": 8.0}
    (HERE / "params.json").write_text(json.dumps(jsonable(params), indent=1))
    print("k_2026", jsonable(k26))
    for name in ("deployment_matched", "all_history"):
        r = out[name]
        print(name, "k by season (E / CAL):")
        for Y, ks in r["k_by_season"].items():
            print(" ", Y, {p: (d["E"], d["CAL"]) for p, d in ks.items()})
        for p, b in r["positions"].items():
            print(f"  {p} n={b['n_rows']} E:", {k: round(v, 4) for k, v in b["E"].items()})
            print("     slope:", {k: (round(v, 3) if v else v) for k, v in b["slope"].items()})


if __name__ == "__main__":
    main()
