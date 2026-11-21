"""JEG-1611 steps 5-6: cross-validated shrinkage model of rest-of-season
receptions per game (A-F of the lane brief). Research only, actuals only.

Run: /usr/bin/python3 tools/research/jeg1611/shrink/run_shrink.py
Writes out/shrink/results.json, results.md, model.json.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
import model as M  # noqa: E402

NFLVERSE = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
ACT_2426 = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
PGS = REPO / "tools" / "research" / "jeg1610" / "cache" / "player_game_stats_2024_2026.json"
OUT = HERE.parent / "out" / "shrink"

POS = ("RB", "WR", "TE")
WEEKS = (5, 6, 7, 8, 9, 10)
TOP_N = {"RB": 36, "WR": 36, "TE": 18}
HALF_LIVES = (4, 8, 12, 17, 25, 34, 51, math.inf)
DECAYS = (1.0, 0.7, 0.5, 0.3)
KS = (0, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 75, 100, 150)
COMBOS = [(h, d) for h in HALF_LIVES for d in DECAYS]
N_BOOT = 2000
SEED = 1611
T975_10 = 2.228  # t quantile, 10 df (11 seasons)


def clean(o):
    """JSON-safe: inf/nan -> None, numpy scalars -> python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    return o


def r3(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), 3)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_games():
    games = defaultdict(list)          # pid -> [(season, week, std, half, ppr, rec)]
    pos_count = defaultdict(Counter)   # (pid, season) -> pos counts
    with gzip.open(NFLVERSE, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s, wk = int(r["season"]), int(r["week"])
            std, half, ppr = float(r["std"] or 0), float(r["half_ppr"] or 0), float(r["ppr"] or 0)
            games[r["player_id"]].append((s, wk, std, half, ppr, round(ppr - std, 2)))
            pos_count[(r["player_id"], s)][r["pos"]] += 1
    for g in games.values():
        g.sort()
    pos = {k: c.most_common(1)[0][0] for k, c in pos_count.items()}
    last_week = defaultdict(int)
    for g in games.values():
        for s, wk, *_ in g:
            last_week[s] = max(last_week[s], wk)
    return games, pos, dict(last_week)


def build_rows(games, pos, last_week):
    """Decision rows: (season, week, player) with >= 1 row in the season and >= 1
    prior game. Features for every (half_life, decay) combo."""
    lam = np.array([1.0 if math.isinf(h) else 0.5 ** (1 / h) for h, _ in COMBOS])
    dec = np.array([d for _, d in COMBOS])
    recs, feats = [], []
    for pid, g in games.items():
        seasons = sorted({x[0] for x in g})
        events = [(x[0], x[1], 1, x) for x in g]
        for s in seasons:
            if (pid, s) not in pos or pos[(pid, s)] not in ("QB",) + POS:
                continue
            for w in WEEKS:
                events.append((s, w, 0, None))
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        st = np.zeros((len(COMBOS), 4))    # n_eff, std, rec, half
        last = None
        raw = np.zeros(4)
        for s, wk, kind, x in events:
            if kind == 1:
                if last is not None and s > last:
                    st *= (dec ** (s - last))[:, None]
                st = st * lam[:, None] + np.array([1.0, x[2], x[5], x[3]])
                raw += np.array([1.0, x[2], x[5], x[3]])
                last = s
                continue
            if raw[0] < 1:
                continue
            f = dec ** (s - last) if s > last else np.ones(len(COMBOS))
            cur = st * f[:, None]
            seas = [y for y in g if y[0] == s]
            trail = [y for y in seas if y[1] < wk]
            ros = [y for y in seas if y[1] >= wk]
            nr = len(ros)
            recs.append(dict(
                pid=pid, season=s, week=wk, pos=pos[(pid, s)],
                ros_games=nr,
                ros_rec=np.mean([y[5] for y in ros]) if nr else np.nan,
                ros_std=np.mean([y[2] for y in ros]) if nr else np.nan,
                ros_ppr=np.mean([y[4] for y in ros]) if nr else np.nan,
                ros_std_total=sum(y[2] for y in ros),
                ros_ppr_total=sum(y[4] for y in ros),
                raw_n=raw[0], raw_std=raw[1] / raw[0], raw_rec=raw[2] / raw[0],
                cur_n=len(trail),
                cur_std=np.mean([y[2] for y in trail]) if trail else np.nan,
                cur_rec=np.mean([y[5] for y in trail]) if trail else np.nan,
                cur_half=np.mean([y[3] for y in trail]) if trail else np.nan,
            ))
            feats.append(cur.copy())
    F = np.stack(feats)  # rows x combos x 4
    cols = {k: np.array([r[k] for r in recs]) for k in recs[0]}
    N = F[:, :, 0].T
    with np.errstate(invalid="ignore", divide="ignore"):
        STD = (F[:, :, 1] / F[:, :, 0]).T
        REC = (F[:, :, 2] / F[:, :, 0]).T
        HALF = (F[:, :, 3] / F[:, :, 0]).T
    return cols, N, STD, REC, HALF


def consistency_check(games, cols, N, REC, n_check=300):
    """model.recency_sums must reproduce the batch features."""
    rnd = random.Random(SEED)
    idx = rnd.sample(range(len(cols["season"])), n_check)
    worst = 0.0
    for i in idx:
        pid, s, w = cols["pid"][i], int(cols["season"][i]), int(cols["week"][i])
        hist = [(x[0], x[1], x[2], x[4]) for x in games[pid]]
        for c in (0, 13, len(COMBOS) - 1):
            h, d = COMBOS[c]
            n, _ss, sr, _ = M.recency_sums(hist, s, w, h, d)
            worst = max(worst, abs(n - N[c, i]), abs(sr / n - REC[c, i]))
    assert worst < 1e-8, worst
    return worst


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def rankdata(x):
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def spearman(a, b):
    if len(a) < 3:
        return np.nan
    ra, rb = rankdata(a), rankdata(b)
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def group_spearman(pred, y, groups):
    """Mean of within-group Spearman."""
    out = []
    for g in np.unique(groups):
        m = groups == g
        v = spearman(pred[m], y[m])
        if np.isfinite(v):
            out.append(v)
    return float(np.mean(out)) if out else np.nan


def t_interval(v):
    v = np.asarray([x for x in v if np.isfinite(x)])
    m = v.mean()
    h = T975_10 * v.std(ddof=1) / math.sqrt(len(v)) if len(v) > 1 else np.nan
    return m, m - h, m + h


def demean(x, groups):
    out = x.astype(float).copy()
    for g in np.unique(groups):
        m = groups == g
        out[m] -= out[m].mean()
    return out


def slope(y, x):
    x = x - x.mean()
    return float((x * (y - y.mean())).sum() / (x * x).sum()) if (x * x).sum() > 0 else np.nan


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def fit_B(N, REC, y, tr):
    """Constant prior = train mean of y; choose combo and k by train MSE."""
    prior = y[tr].mean()
    best = None
    for c in range(len(COMBOS)):
        n, r = N[c, tr], REC[c, tr]
        for k in KS:
            w = n / (n + k) if k > 0 else np.ones_like(n)
            mse = np.mean((w * r + (1 - w) * prior - y[tr]) ** 2)
            if best is None or mse < best[0]:
                best = (mse, c, k)
    return {"form": "mean", "combo": best[1], "k": best[2], "mean": float(prior), "train_mse": best[0]}


def pred_B(p, N, REC, STD, idx):
    c, k = p["combo"], p["k"]
    n, r = N[c, idx], REC[c, idx]
    w = n / (n + k) if k > 0 else np.ones_like(n)
    return w * r + (1 - w) * p["mean"], w


def fit_C(N, REC, STD, y, tr, form):
    """Role-aware prior, fitted jointly with k: y - w r = (1 - w)(a + b std_h),
    or bins (quintiles of std_h) for form == 'bins'."""
    best = None
    for c in range(len(COMBOS)):
        n, r, s = N[c, tr], REC[c, tr], STD[c, tr]
        edges = np.quantile(s, [0.2, 0.4, 0.6, 0.8]) if form == "bins" else None
        for k in KS:
            if k == 0:
                continue
            w = n / (n + k)
            if form == "linear_std":
                X = np.column_stack([(1 - w), (1 - w) * s])
            else:
                b = np.searchsorted(edges, s, side="right")
                X = np.column_stack([(1 - w) * (b == j) for j in range(5)])
            coef, *_ = np.linalg.lstsq(X, y[tr] - w * r, rcond=None)
            mse = np.mean((w * r + X @ coef - y[tr]) ** 2)
            if best is None or mse < best[0]:
                best = (mse, c, k, coef, edges)
    out = {"form": form, "combo": best[1], "k": best[2], "coef": best[3].tolist(), "train_mse": best[0],
           "mean": float(y[tr].mean())}
    if form == "bins":
        out["edges"] = best[4].tolist()
    return out


def prior_C(p, s):
    if p["form"] == "linear_std":
        return np.maximum(0.0, p["coef"][0] + p["coef"][1] * s)
    b = np.searchsorted(np.array(p["edges"]), s, side="right")
    return np.array(p["coef"])[b]


def pred_C(p, N, REC, STD, idx):
    c, k = p["combo"], p["k"]
    n, r, s = N[c, idx], REC[c, idx], STD[c, idx]
    w = n / (n + k)
    return w * r + (1 - w) * prior_C(p, s), w


def ratio_feat(STD, REC, c, idx):
    """Recency-weighted history log(1 + rec/std); nan where std_h < 1."""
    s, r = STD[c, idx], REC[c, idx]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s >= 1.0, np.log1p(r / np.maximum(s, 1e-9)), np.nan)


def fit_R(N, REC, STD, z, tr):
    """Reception-share model: z = log(1 + rec/std) of the ROS, shrunk to the train mean."""
    best = None
    prior = float(np.nanmean(z[tr]))
    for c in range(len(COMBOS)):
        zh = ratio_feat(STD, REC, c, tr)
        n = np.where(np.isfinite(zh), N[c, tr], 0.0)
        zh = np.where(np.isfinite(zh), zh, prior)
        for k in KS:
            w = n / (n + k) if k > 0 else (n > 0).astype(float)
            mse = np.mean((w * zh + (1 - w) * prior - z[tr]) ** 2)
            if best is None or mse < best[0]:
                best = (mse, c, k)
    return {"combo": best[1], "k": best[2], "mean": prior, "train_mse": best[0]}


def pred_R(p, N, REC, STD, idx):
    c, k = p["combo"], p["k"]
    zh = ratio_feat(STD, REC, c, idx)
    n = np.where(np.isfinite(zh), N[c, idx], 0.0)
    zh = np.where(np.isfinite(zh), zh, p["mean"])
    w = n / (n + k) if k > 0 else (n > 0).astype(float)
    return w * zh + (1 - w) * p["mean"]


def choose_forms(A):
    """Per position: role-aware C_linear if it beats B on pooled MSE and in >= 7 of 11 seasons."""
    return {p: "C_linear" if (A[p]["C_linear"]["mse"] < A[p]["B"]["mse"]
                              and A[p]["C_linear"]["seasons_beating_B_mse"] >= 7) else "B" for p in POS}


# ---------------------------------------------------------------------------
# A-D: LOSO CV
# ---------------------------------------------------------------------------

def run_cv(cols, N, STD, REC, HALF):
    seasons = sorted(set(cols["season"].tolist()))
    elig = (cols["ros_games"] >= 3) & (cols["raw_n"] >= 1)
    y_all = cols["ros_rec"]
    group = np.array([f"{s}|{w}|{p}" for s, w, p in zip(cols["season"], cols["week"], cols["pos"])])
    preds = {m: np.full(len(y_all), np.nan) for m in ("pos_mean", "raw_all", "raw_cur", "B", "C_linear", "C_bins", "ratio")}
    combo_of = {m: np.full(len(y_all), -1) for m in ("B", "C_linear")}
    with np.errstate(invalid="ignore", divide="ignore"):
        z_all = np.where(cols["ros_std"] >= 2.0, np.log1p(cols["ros_rec"] / cols["ros_std"]), np.nan)
    wts = {m: np.full(len(y_all), np.nan) for m in ("B", "C_linear", "C_bins")}
    fold_combo = np.full(len(y_all), -1)
    chosen = defaultdict(list)
    for p in POS:
        pm = elig & (cols["pos"] == p)
        for T in seasons:
            tr = np.where(pm & (cols["season"] != T))[0]
            te = np.where(pm & (cols["season"] == T))[0]
            ytr = y_all
            mean = y_all[tr].mean()
            preds["pos_mean"][te] = mean
            preds["raw_all"][te] = cols["raw_rec"][te]
            cur = cols["cur_rec"][te]
            preds["raw_cur"][te] = np.where(cols["cur_n"][te] >= 1, cur, mean)
            fB = fit_B(N, REC, ytr, tr)
            preds["B"][te], wts["B"][te] = pred_B(fB, N, REC, STD, te)
            fold_combo[te] = fB["combo"]
            combo_of["B"][te] = fB["combo"]
            fCl = fit_C(N, REC, STD, ytr, tr, "linear_std")
            preds["C_linear"][te], wts["C_linear"][te] = pred_C(fCl, N, REC, STD, te)
            combo_of["C_linear"][te] = fCl["combo"]
            trz = tr[np.isfinite(z_all[tr])]
            fR = fit_R(N, REC, STD, z_all, trz)
            preds["ratio"][te] = pred_R(fR, N, REC, STD, te)
            fCb = fit_C(N, REC, STD, ytr, tr, "bins")
            preds["C_bins"][te], wts["C_bins"][te] = pred_C(fCb, N, REC, STD, te)
            chosen[p].append({"test": T,
                              "B": {"half_life": COMBOS[fB["combo"]][0], "decay": COMBOS[fB["combo"]][1], "k": fB["k"]},
                              "C_linear": {"half_life": COMBOS[fCl["combo"]][0], "decay": COMBOS[fCl["combo"]][1],
                                           "k": fCl["k"], "a": fCl["coef"][0], "b": fCl["coef"][1]},
                              "ratio": {"half_life": COMBOS[fR["combo"]][0], "decay": COMBOS[fR["combo"]][1], "k": fR["k"]}})
    # metrics
    A = {}
    for p in POS:
        pm = elig & (cols["pos"] == p)
        A[p] = {"n_rows": int(pm.sum()), "n_players": len(set(cols["pid"][pm].tolist()))}
        per_season = defaultdict(dict)
        for m, pr in preds.items():
            if m == "ratio":
                continue
            mse_s, sp_s = [], []
            for T in seasons:
                te = pm & (cols["season"] == T)
                mse_s.append(np.mean((pr[te] - y_all[te]) ** 2))
                sp_s.append(group_spearman(pr[te], y_all[te], group[te]))
                per_season[T][m] = mse_s[-1]
            sp = t_interval(sp_s)
            A[p][m] = {"mse": r3(np.mean((pr[pm] - y_all[pm]) ** 2)), "rmse": r3(math.sqrt(np.mean((pr[pm] - y_all[pm]) ** 2))),
                       "spearman": r3(sp[0]), "spearman_ci95": [r3(sp[1]), r3(sp[2])]}
        for m in ("raw_all", "raw_cur", "B", "C_linear", "C_bins"):
            A[p][m]["seasons_beating_raw_all_mse"] = int(sum(per_season[T][m] < per_season[T]["raw_all"] for T in seasons))
            A[p][m]["seasons_beating_B_mse"] = int(sum(per_season[T][m] < per_season[T]["B"] for T in seasons))
        d = [per_season[T]["C_linear"] - per_season[T]["B"] for T in seasons]
        A[p]["C_linear_minus_B_mse"] = [r3(x) for x in t_interval(d)]
        d = [per_season[T]["C_bins"] - per_season[T]["B"] for T in seasons]
        A[p]["C_bins_minus_B_mse"] = [r3(x) for x in t_interval(d)]
        A[p]["mean_w"] = {m: r3(np.nanmean(wts[m][pm])) for m in wts}
        zm = pm & np.isfinite(z_all)
        A[p]["ratio_model_mse_log_ratio"] = r3(np.mean((preds["ratio"][zm] - z_all[zm]) ** 2))
        with np.errstate(invalid="ignore", divide="ignore"):
            zr = np.log1p(cols["raw_rec"][zm] / np.maximum(cols["raw_std"][zm], 1e-9))
        ok = np.isfinite(zr) & (cols["raw_std"][zm] >= 1)
        A[p]["raw_all_mse_log_ratio"] = r3(np.mean((zr[ok] - z_all[zm][ok]) ** 2))
        A[p]["ratio_model_mse_same_rows"] = r3(np.mean((preds["ratio"][zm][ok] - z_all[zm][ok]) ** 2))
    forms = choose_forms(A)
    preds["chosen"] = np.full(len(y_all), np.nan)
    wts["chosen"] = np.full(len(y_all), np.nan)
    for p in POS:
        pm = elig & (cols["pos"] == p)
        preds["chosen"][pm] = preds[forms[p]][pm]
        wts["chosen"][pm] = wts[forms[p]][pm]
        fold_combo[pm] = combo_of[forms[p]][pm]
    for p in POS:
        pm = elig & (cols["pos"] == p)
        A[p]["chosen_form"] = forms[p]
        A[p]["mean_w"]["chosen"] = r3(np.nanmean(wts["chosen"][pm]))
    return dict(A=A, chosen=chosen, preds=preds, elig=elig, group=group, fold_combo=fold_combo, forms=forms, z=z_all)


def season_boot(fn, seasons_arr, seasons, rng):
    """Season-block bootstrap of a pooled statistic fn(mask)."""
    idx_by = {s: np.where(seasons_arr == s)[0] for s in seasons}
    vals = []
    for _ in range(N_BOOT):
        pick = rng.choice(seasons, len(seasons), replace=True)
        idx = np.concatenate([idx_by[s] for s in pick])
        vals.append(fn(idx))
    vals = np.array(vals)
    vals = vals[np.isfinite(vals)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def run_D(cols, N, STD, REC, HALF, cv, model_key):
    seasons = sorted(set(cols["season"].tolist()))
    rng = np.random.default_rng(SEED)
    elig, group = cv["elig"], cv["group"]
    c_idx = cv["fold_combo"]
    rows = np.arange(len(elig))
    fc_std = np.where(c_idx >= 0, STD[np.maximum(c_idx, 0), rows], np.nan)
    fc_rec = np.where(c_idx >= 0, REC[np.maximum(c_idx, 0), rows], np.nan)
    forecast_ppr = fc_std + fc_rec
    # chart pool: top-N per group by recency-weighted history ppr ppg (ex ante)
    chart = np.zeros(len(elig), bool)
    for g in np.unique(group[elig]):
        m = np.where(elig & (group == g))[0]
        p = g.split("|")[2]
        if p not in POS:
            continue
        top = m[np.argsort(-forecast_ppr[m], kind="mergesort")][:TOP_N[p]]
        chart[top] = True
    y = cols["ros_rec"]
    raw_cur = np.where(cols["cur_n"] >= 1, cols["cur_rec"], cols["raw_rec"])
    out = {}
    for variant in ("P_realized", "P_forecast"):
        out[variant] = {}
        P_or = cols["ros_std"]
        P_mod = cols["ros_std"] if variant == "P_realized" else fc_std
        for pool_name, pool, floor in (("chart_top_n", chart, 2.0), ("all_eligible", elig, 3.0)):
            out[variant][pool_name] = {}
            for p in POS:
                m = np.where(pool & (cols["pos"] == p) & (P_or >= floor) & (P_mod >= floor))[0]
                gm = group[m]
                oracle = np.log((P_or[m] + y[m]) / P_or[m])
                moves = {"model": np.log((P_mod[m] + cv["preds"][model_key][m]) / P_mod[m]),
                         "B": np.log((P_mod[m] + cv["preds"]["B"][m]) / P_mod[m]),
                         "ratio_model": cv["preds"]["ratio"][m],
                         "raw_all": np.log((P_mod[m] + cols["raw_rec"][m]) / P_mod[m]),
                         "raw_cur": np.log((P_mod[m] + raw_cur[m]) / P_mod[m])}
                od = demean(oracle, gm)
                res = {"n_rows": int(len(m)), "sd_oracle_within": r3(od.std())}
                sarr = cols["season"][m]
                for name, mv in moves.items():
                    md = demean(mv, gm)
                    sl = slope(od, md)
                    lo, hi = season_boot(lambda ix: slope(od[ix], md[ix]), sarr, seasons, rng)
                    sp_s = [group_spearman(mv[sarr == T], oracle[sarr == T], gm[sarr == T]) for T in seasons]
                    sp = t_interval(sp_s)
                    res[name] = {"slope": r3(sl), "slope_ci95": [r3(lo), r3(hi)],
                                 "slope_by_season": {int(T): r3(slope(od[sarr == T], md[sarr == T])) for T in seasons},
                                 "spearman": r3(sp[0]), "spearman_ci95": [r3(sp[1]), r3(sp[2])],
                                 "sd_within": r3(md.std()),
                                 "rmse_vs_oracle_within": r3(math.sqrt(np.mean((od - md) ** 2)))}
                out[variant][pool_name][p] = res
    return out, chart


# ---------------------------------------------------------------------------
# E: mechanism test
# ---------------------------------------------------------------------------

def ols(X, y):
    coef, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(y)), X]), y, rcond=None)
    return coef


def run_E(cols, cv, model_key, weeks, target, require_ros3):
    seasons = sorted(set(cols["season"].tolist()))
    group = cv["group"]
    rec_hat = cv["preds"][model_key]
    zhat = cv["preds"]["ratio"]
    # M-style pool: top N by trailing half-PPR rate among >= 2 current-season games (ex ante)
    cand = (cols["cur_n"] >= 2) & np.isin(cols["week"], weeks) & np.isin(cols["pos"], POS) & (cols["raw_n"] >= 1)
    pool = np.zeros(len(cand), bool)
    for g in np.unique(group[cand]):
        m = np.where(cand & (group == g))[0]
        p = g.split("|")[2]
        top = m[np.argsort(-cols["cur_half"][m], kind="mergesort")][:TOP_N[p]]
        pool[top] = True
    if require_ros3:
        pool &= cols["ros_games"] >= 3
    y = cols["ros_std"] if target == "ros_std_pg" else cols["ros_std_total"]
    y_full = cols["ros_ppr"] if target == "ros_std_pg" else cols["ros_ppr_total"]
    # games scale of the deduction: 1 per game, or remaining weeks for the total target
    scale = np.ones(len(y)) if target == "ros_std_pg" else (
        np.where(cols["season"] >= 2021, 18, 17) - cols["week"] + 1).astype(float)
    # rec_hat is defined for eligible rows (>= 3 ROS games); for the ROS-total
    # replication, rows with < 3 ROS games get rec_hat from the B fit of their fold
    missing = pool & ~(np.isfinite(rec_hat) & np.isfinite(zhat))
    pool &= ~missing
    full = cols["cur_std"] + cols["cur_rec"]
    preds = {"i_trailing_full": full, "ii_trailing_std": cols["cur_std"],
             "iii_full_minus_rec_hat": full - rec_hat}
    reg_iv = np.full(len(y), np.nan)
    reg_v = np.full(len(y), np.nan)
    full_fc = np.full(len(y), np.nan)
    coefs = defaultdict(list)
    for p in POS:
        pm = pool & (cols["pos"] == p)
        for T in seasons:
            tr, te = pm & (cols["season"] != T), pm & (cols["season"] == T)
            b = ols(np.column_stack([cols["cur_std"][tr], cols["cur_rec"][tr]]), y[tr])
            reg_iv[te] = b[0] + b[1] * cols["cur_std"][te] + b[2] * cols["cur_rec"][te]
            coefs[(p, "iv")].append(b)
            b5 = ols(np.column_stack([cols["cur_std"][tr], cols["cur_rec"][tr], rec_hat[tr]]), y[tr])
            reg_v[te] = b5[0] + b5[1] * cols["cur_std"][te] + b5[2] * cols["cur_rec"][te] + b5[3] * rec_hat[te]
            coefs[(p, "v")].append(b5)
            b6 = ols(np.column_stack([cols["cur_std"][tr], cols["cur_rec"][tr], rec_hat[tr]]), y_full[tr])
            full_fc[te] = b6[0] + b6[1] * cols["cur_std"][te] + b6[2] * cols["cur_rec"][te] + b6[3] * rec_hat[te]
    preds["iv_ols_std_rec"] = reg_iv
    preds["v_ols_std_rec_rechat"] = reg_v
    # a calibrated Full forecast (OLS on train seasons, target ROS Full) and the two conversions
    preds["vi_full_forecast"] = full_fc
    preds["vii_full_forecast_minus_rec_hat"] = full_fc - rec_hat * scale
    preds["viii_full_forecast_over_share"] = full_fc / np.exp(zhat)
    out = {"weeks": list(weeks), "target": target, "n_rows": int(pool.sum()),
           "n_players": len(set(cols["pid"][pool].tolist())), "methods": {}}
    per = {m: {} for m in preds}
    for m, pr in preds.items():
        for T in seasons:
            te = pool & (cols["season"] == T)
            per[m][T] = group_spearman(pr[te], y[te], group[te])
        out["methods"][m] = {"spearman": r3(np.mean(list(per[m].values())))}
    for m in preds:
        if m == "i_trailing_full":
            continue
        d = [per[m][T] - per["i_trailing_full"][T] for T in seasons]
        mm, lo, hi = t_interval(d)
        out["methods"][m].update({"diff_vs_full": r3(mm), "ci95": [r3(lo), r3(hi)],
                                  "seasons_beating_full": int(sum(x > 0 for x in d)),
                                  "by_season_diff": {int(T): r3(x) for T, x in zip(seasons, d)}})
    for m in ("vii_full_forecast_minus_rec_hat", "viii_full_forecast_over_share"):
        d = [per[m][T] - per["vi_full_forecast"][T] for T in seasons]
        mm, lo, hi = t_interval(d)
        out["methods"][m].update({"diff_vs_full_forecast": r3(mm), "ci95_vs_full_forecast": [r3(lo), r3(hi)],
                                  "seasons_beating_full_forecast": int(sum(x > 0 for x in d))})
    out["by_position"] = {}
    for p in POS:
        pm = pool & (cols["pos"] == p)
        out["by_position"][p] = {m: r3(np.mean([group_spearman(pr[pm & (cols["season"] == T)], y[pm & (cols["season"] == T)],
                                                                  group[pm & (cols["season"] == T)]) for T in seasons]))
                                 for m, pr in preds.items()}
        biv = np.array(coefs[(p, "iv")])
        bv = np.array(coefs[(p, "v")])
        out["by_position"][p]["coef_iv_mean_over_folds"] = {"const": r3(biv[:, 0].mean()), "trailing_std": r3(biv[:, 1].mean()),
                                                            "trailing_rec": r3(biv[:, 2].mean()),
                                                            "rec_over_std_ratio": r3((biv[:, 2] / biv[:, 1]).mean())}
        out["by_position"][p]["coef_v_mean_over_folds"] = {"const": r3(bv[:, 0].mean()), "trailing_std": r3(bv[:, 1].mean()),
                                                           "trailing_rec": r3(bv[:, 2].mean()), "rec_hat": r3(bv[:, 3].mean())}
    return out


# ---------------------------------------------------------------------------
# F: share stability 2024-2026
# ---------------------------------------------------------------------------

def run_F():
    d = json.loads(PGS.read_text(encoding="utf-8"))
    ci = {c: i for i, c in enumerate(d["cols"])}
    poscount = defaultdict(Counter)
    with ACT_2426.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            poscount[(int(r["player_key"]), int(r["season"]))][r["pos"]] += 1
    pos = {k: c.most_common(1)[0][0] for k, c in poscount.items()}
    by = {}
    for row in d["totals"]:
        k, s, g = int(row[ci["player_key"]]), int(row[ci["season"]]), int(row[ci["games"]])
        p = pos.get((k, s))
        if p not in POS or g < 6:
            continue
        v = {c: float(row[ci[c]] or 0) for c in d["cols"]}
        rec_pts = v["rec"]
        yds_pts = (v["rush_yds"] + v["rec_yds"] + v["pass_yds"] / 2.5) / 10
        td_pts = 6 * (v["rush_td"] + v["rec_td"]) + 4 * v["pass_td"]
        other = -2 * v["int"] - 2 * v["fumbles_lost"]
        ppr = rec_pts + yds_pts + td_pts + other
        if ppr / g < 5:
            continue
        by[(k, s)] = {"pos": p, "g": g, "ppr_pg": ppr / g, "rec_share": rec_pts / ppr, "yds_share": yds_pts / ppr,
                      "td_share": td_pts / ppr, "rec_pg": rec_pts / g, "yds_pts_pg": yds_pts / g, "td_pts_pg": td_pts / g,
                      "targets_pg": v["targets"] / g}
    metrics = ("rec_share", "yds_share", "td_share", "rec_pg", "yds_pts_pg", "td_pts_pg", "targets_pg")
    out = {"filter": "season games >= 6 (2026: weeks to date, partial), PPR ppg >= 5 from categories",
           "pairs": {}}
    for p in POS:
        out["pairs"][p] = {}
        for s0, s1 in ((2024, 2025), (2025, 2026)):
            ks = [k for (k, s) in by if s == s0 and (k, s1) in by and by[(k, s)]["pos"] == p]
            res = {"n": len(ks)}
            for m in metrics:
                a = np.array([by[(k, s0)][m] for k in ks])
                b = np.array([by[(k, s1)][m] for k in ks])
                res[m] = {"pearson": r3(np.corrcoef(a, b)[0, 1]) if len(ks) > 2 else None,
                          "spearman": r3(spearman(a, b))}
            out["pairs"][p][f"{s0}-{s1}"] = res
        # ICC(1) over players with >= 2 qualifying seasons
        icc = {}
        for m in metrics:
            groups = defaultdict(list)
            for (k, s), v in by.items():
                if v["pos"] == p:
                    groups[k].append(v[m])
            gs = [np.array(x) for x in groups.values() if len(x) >= 2]
            allv = np.concatenate(gs)
            grand = allv.mean()
            nt = len(allv)
            kk = len(gs)
            ssb = sum(len(x) * (x.mean() - grand) ** 2 for x in gs)
            ssw = sum(((x - x.mean()) ** 2).sum() for x in gs)
            msb, msw = ssb / (kk - 1), ssw / (nt - kk)
            n0 = (nt - sum(len(x) ** 2 for x in gs) / nt) / (kk - 1)
            icc[m] = r3((msb - msw) / (msb + (n0 - 1) * msw))
        icc["n_players"] = len(gs)
        out.setdefault("icc", {})[p] = icc
    return out


# ---------------------------------------------------------------------------
# Final fit, QB, report
# ---------------------------------------------------------------------------

def neff_scenarios(h, d, k):
    lam = 1.0 if math.isinf(h) else 0.5 ** (1 / h)

    def neff(cur, prev_seasons=0, per=17):
        n = sum(lam ** a for a in range(cur))
        for j in range(prev_seasons):
            n += d ** (j + 1) * lam ** (cur + j * per) * sum(lam ** a for a in range(per))
        return n
    scen = {"6_current_games": neff(6), "6_current_plus_1_prior_season": neff(6, 1),
            "6_current_plus_2_prior_seasons": neff(6, 2), "17_prior_season_only_week1": d * neff(17)}
    wf = (lambda n: n / (n + k)) if k > 0 else (lambda n: 1.0)
    return ({str(n): r3(wf(n)) for n in (6, 17, 34)},
            {kq: {"n_eff": r3(v), "w": r3(wf(v))} for kq, v in scen.items()},
            r3(1 / (1 - lam)) if lam < 1 else None)


def final_fit(cols, N, STD, REC, forms):
    """Fit on all 11 seasons; forms = {pos: 'B' | 'C_linear'}."""
    elig = (cols["ros_games"] >= 3) & (cols["raw_n"] >= 1)
    y = cols["ros_rec"]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(cols["ros_std"] >= 2.0, np.log1p(cols["ros_rec"] / cols["ros_std"]), np.nan)
    out = {}
    for p in POS:
        tr = np.where(elig & (cols["pos"] == p))[0]
        res = {}
        for form in ("B", "C_linear"):
            f = fit_B(N, REC, y, tr) if form == "B" else fit_C(N, REC, STD, y, tr, "linear_std")
            h, d = COMBOS[f["combo"]]
            w_at, scen, cap = neff_scenarios(h, d, f["k"])
            res[form] = {"prior_form": "mean" if form == "B" else "linear_std",
                         "half_life_games": None if math.isinf(h) else h, "season_decay": d, "k": f["k"],
                         "mean": f["mean"], "a": f["coef"][0] if form != "B" else None,
                         "b": f["coef"][1] if form != "B" else None,
                         "w_at_n_eff": w_at, "n_eff_scenarios": scen, "n_eff_cap": cap,
                         "train_mse": r3(f["train_mse"])}
        trz = tr[np.isfinite(z[tr])]
        fR = fit_R(N, REC, STD, z, trz)
        h, d = COMBOS[fR["combo"]]
        w_at, scen, cap = neff_scenarios(h, d, fR["k"])
        res["ratio"] = {"target": "log(1 + rec/std) of the ROS", "half_life_games": None if math.isinf(h) else h,
                        "season_decay": d, "k": fR["k"], "mean": fR["mean"], "w_at_n_eff": w_at,
                        "n_eff_scenarios": scen, "min_std_h": 1.0}
        res["chosen"] = forms[p]
        out[p] = res
    return out


def qb_summary(cols):
    m = (cols["pos"] == "QB") & (cols["ros_games"] >= 3)
    return {"mean_rec_pg": r3(np.mean(cols["ros_rec"][m])), "share_rows_any_rec": r3(np.mean(cols["ros_rec"][m] > 0)),
            "p99_rec_pg": r3(np.percentile(cols["ros_rec"][m], 99)), "max_rec_pg": r3(np.max(cols["ros_rec"][m])),
            "rec_over_std": r3(np.mean(cols["ros_rec"][m]) / np.mean(cols["ros_std"][m])), "n_rows": int(m.sum())}


def fill_missing(cols, N, STD, REC, cv):
    """B/C/ratio predictions exist only on eligible rows (>= 3 ROS games); the
    ROS-total replication of M also needs rows with fewer ROS games. Refit each
    fold's parameters on the same train rows and predict those rows."""
    preds = {k: v.copy() for k, v in cv["preds"].items()}
    need = ~cv["elig"] & np.isin(cols["pos"], POS) & (cols["raw_n"] >= 1)
    seasons = sorted(set(cols["season"].tolist()))
    z = cv["z"]
    for p in POS:
        for T in seasons:
            tr = np.where(cv["elig"] & (cols["pos"] == p) & (cols["season"] != T))[0]
            te = np.where(need & (cols["pos"] == p) & (cols["season"] == T))[0]
            if len(te) == 0:
                continue
            f = (fit_B(N, REC, cols["ros_rec"], tr) if cv["forms"][p] == "B"
                 else fit_C(N, REC, STD, cols["ros_rec"], tr, "linear_std"))
            preds["chosen"][te] = (pred_B if cv["forms"][p] == "B" else pred_C)(f, N, REC, STD, te)[0]
            fR = fit_R(N, REC, STD, z, tr[np.isfinite(z[tr])])
            preds["ratio"][te] = pred_R(fR, N, REC, STD, te)
    return dict(cv, preds=preds)


def main():
    games, pos, last_week = load_games()
    cols, N, STD, REC, HALF = build_rows(games, pos, last_week)
    worst = consistency_check(games, cols, N, REC)
    cv = run_cv(cols, N, STD, REC, HALF)
    A, forms = cv["A"], cv["forms"]
    D, _chart = run_D(cols, N, STD, REC, HALF, cv, "chosen")
    cv_all = fill_missing(cols, N, STD, REC, cv)
    E = {"primary_ros_ppg_w5_10": run_E(cols, cv, "chosen", WEEKS, "ros_std_pg", True),
         "replication_M_ros_total_w5_8": run_E(cols, cv_all, "chosen", (5, 6, 7, 8), "ros_std_total", False)}
    F = run_F()
    final = final_fit(cols, N, STD, REC, forms)
    qb = qb_summary(cols)
    positions = {}
    for p in POS:
        c = final[p][forms[p]]
        positions[p] = {k: c[k] for k in ("prior_form", "half_life_games", "season_decay", "k", "mean", "a", "b",
                                          "w_at_n_eff", "n_eff_cap")}
    model_json = {
        "ticket": "JEG-1611",
        "fitted_on": "nflverse weekly actuals 2015-2025; decision weeks 5-10; RB/WR/TE with >= 3 ROS games and >= 1 prior game",
        "formula": "rec_hat = (n_eff*rec_h + k*prior)/(n_eff + k); game weight 0.5**(age_games/half_life) * "
                   "season_decay**seasons_back; prior = mean or max(0, a + b*std_h) (std_h = same-weighted Standard ppg)",
        "positions": positions,
        "ratio_model": {p: final[p]["ratio"] for p in POS},
        "qb": {"mean_rec_pg": qb["mean_rec_pg"], "rule": "left alone (w = 0)"},
        "half_life_games": None, "season_decay": 1.0,
        "selection_rule": "per position: role-aware prior if it beats the constant prior on LOSO pooled MSE and in >= 7 of 11 seasons",
    }
    results = {"ticket": "JEG-1611", "lane": "steps 5-6 shrinkage", "seed": SEED, "n_boot": N_BOOT,
               "grid": {"half_lives": [None if math.isinf(h) else h for h in HALF_LIVES], "decays": DECAYS, "k": KS},
               "consistency_check_max_abs_err": worst,
               "n_decision_rows_total": int(len(cols["season"])), "chosen_forms": forms,
               "A_B_C": A, "cv_chosen_params": {p: v for p, v in cv["chosen"].items()},
               "D": D, "E": E, "F": F, "final_model": final, "QB": qb}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(clean(results), indent=1), encoding="utf-8")
    (OUT / "model.json").write_text(json.dumps(clean(model_json), indent=1), encoding="utf-8")
    print("done", forms)


if __name__ == "__main__":
    main()
