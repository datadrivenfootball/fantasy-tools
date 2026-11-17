"""JEG-1691 v5.1 backtest: catch-share rules on historical actuals (B0-B5, sensitivities, outcome).

Spec: docs/research/jeg1691/v51-preregistration.md (approved at e915a661). Binding. Every rule is
two-bucket (catches, other points). q = receptions per anchor point (Half by default).

Rules at origin o (season Y, week w), from the player's games strictly before o:
  RL  : q = a q_hist + (1 - a) q_pos, a = n / (n + k_p), all games weighted 1; k_p in G_L by
        nested forward CV, ties to the smaller k.
  R0  : k = 0.  Rpos: k = inf.
  Rv5 : the same form with v5's frozen catch strength and half-life (recency weights 0.5**(age/t)).
q_hist = total receptions / total anchor points (ratio of totals). q_pos = games-weighted mean of
q_hist over the position's players with >= 8 history games, from games before o only.
Pure functions; I/O only in the loaders. Research only.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
V5 = HERE.parent
REPO = HERE.parents[3]
sys.path.insert(0, str(V5))

import mix as mx  # noqa: E402  (v5 module, imported unchanged)

NFLVERSE = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
PGS = V5 / "cache" / "pgs_weekly_2024_2026.json.gz"
IDMAP = REPO / "data" / "inputs" / "sleeper_projection_idmap.csv"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
V5_SELECTION = V5 / "out" / "decisive" / "selection.json"

POOL = ("RB", "WR", "TE")
POS_ALL = ("QB", "RB", "WR", "TE")
G_L = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
CAP = 8.0
PRIOR_MIN_GAMES = 8
MIN_TRUTH_GAMES = 2
TRUTH_WEEKS = 4
SEED = 16911
N_BOOT = 2000
N_SHUFFLE = 1000
B3_BAND = (2.0 / 3.0, 1.5)
MAX_SEASON = 2025          # the backtest never reads 2026
INTEGRITY_TOL = 0.011
INTEGRITY_MAX_SHARE = 0.005


@dataclass(frozen=True)
class Config:
    name: str = "primary"
    anchor: str = "half_ppr"                 # or "ppr" (S-anchor-Full)
    truth: str = "w4"                        # or "ros" (S-truth-ROS)
    origins: tuple = (5, 9, 13)
    eval_seasons: tuple = tuple(range(2017, 2026))
    sel_start: int = 2016
    drop_seasons: tuple = ()
    b1_needed: int = 7
    b5: bool = True
    b5_origins: tuple = tuple(range(4, 15))
    b5_season: int = 2025
    # dry run only: select k on these origins of the same (only) season, evaluate on the others
    dry_sel_origins: tuple = ()


PRIMARY = Config()
SENSITIVITIES = (
    replace(PRIMARY, name="S-anchor-Full", anchor="ppr"),
    replace(PRIMARY, name="S-truth-ROS", truth="ros"),
    replace(PRIMARY, name="S-origins-alt", origins=(4, 8, 12)),
    replace(PRIMARY, name="S-no-2020", drop_seasons=(2020,), b1_needed=6),
    replace(PRIMARY, name="S-no-2025", drop_seasons=(2025,), b1_needed=6, b5=False),
)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_nflverse(path: Path = NFLVERSE, max_season: int = MAX_SEASON):
    """{gsis: [(season, week, pos, rec, half, ppr)]} sorted by time, games = rows with nonzero
    Standard or PPR points; plus the integrity counts of B0."""
    games, n, bad, neg_rec, zero = {}, 0, 0, 0, 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = int(r["season"])
            if s > max_season:
                raise SystemExit(f"row of season {s}: the backtest reads no season after {max_season}")
            n += 1
            std, half, ppr = float(r["std"] or 0), float(r["half_ppr"] or 0), float(r["ppr"] or 0)
            if abs(half - (std + ppr) / 2) > INTEGRITY_TOL:
                bad += 1
            if std == 0 and ppr == 0:
                zero += 1
                continue
            rec = ppr - std
            neg_rec += rec < -1e-9
            games.setdefault(r["player_id"], []).append((s, int(r["week"]), r["pos"], rec, half, ppr))
    for v in games.values():
        v.sort(key=lambda g: (g[0], g[1]))
    return games, {"rows": n, "integrity_bad": bad, "zero_rows_dropped": zero, "negative_receptions": neg_rec}


def v5_params(path: Path = V5_SELECTION) -> dict:
    """{pos: (k_rec, half-life t)} frozen by v5's decisive run (read-only)."""
    sel = json.loads(path.read_text(encoding="utf-8"))["selection"]
    f = lambda x: math.inf if x in ("inf", math.inf) else float(x)  # noqa: E731
    return {p: (f(v["k"]["rec"]), f(v["t"])) for p, v in sel.items()}


def load_pgs_twobucket(anchor: str, path: Path = PGS, max_season: int = MAX_SEASON):
    """B5: {player_key: [(season, week, pos, rec, pts_anchor, cats_line)]} from the per-stat cache,
    seasons <= max_season, keyed rows only; position from the idmap, else players.json."""
    import history5 as h5
    H = h5.load(path)
    pos = {}
    with IDMAP.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("player_key") or "").isdigit() and r.get("pos"):
                pos.setdefault(int(r["player_key"]), r["pos"])
    for p in json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]:
        pos.setdefault(int(p["player_key"]), p["pos"])
    out, unpos = {}, 0
    for k, rows in H["by_player"].items():
        if k not in pos:
            unpos += 1
            continue
        g = [(s, w, pos[k], ln["rec"], mx.F(ln, anchor), ln) for (s, w), ln in rows
             if s <= max_season and mx.game_has_stats(ln)]
        if g:
            out[k] = g
    return out, {"players": len(out), "keyed_without_position": unpos,
                 "unkeyed_rows_with_stats": H["unkeyed_rows_with_stats"]}


# ---------------------------------------------------------------------------
# Origin rows
# ---------------------------------------------------------------------------

def history_share(hist, anchor, t=math.inf):
    """(q_hist, n, n_eff, q_hist_weighted): ratio of totals, all games weight 1 for q_hist;
    recency weights 0.5**(age/t) for the weighted variant (age 0 = most recent)."""
    n = len(hist)
    sr = sum(g[3] for g in hist)
    sp = sum(_pts(g, anchor) for g in hist)
    q = sr / sp if sp > 0 else None
    if math.isinf(t):
        ws = [1.0] * n
    else:
        ws = [0.5 ** ((n - 1 - j) / t) for j in range(n)]
    wr = sum(w * g[3] for w, g in zip(ws, hist))
    wp = sum(w * _pts(g, anchor) for w, g in zip(ws, hist))
    qw = wr / wp if wp > 0 else None
    return q, n, sum(ws), qw


def _pts(g, anchor):
    # nflverse tuples: (s, w, pos, rec, half, ppr); per-stat tuples: (s, w, pos, rec, pts_anchor, line)
    if isinstance(g[5], dict):
        return g[4]
    return g[4] if anchor == "half_ppr" else g[5]


def truth_window(games, season, w, cfg):
    hi = 99 if cfg.truth == "ros" else w + TRUTH_WEEKS - 1
    return [g for g in games if g[0] == season and w <= g[1] <= hi]


def origin_rows(players: dict, season: int, w: int, cfg: Config, v5p: dict) -> dict:
    """{'rows': [...], 'q_pos': {pos: q}, 'excluded': counts} at origin (season, w)."""
    cut = (season, w)
    hists = {}
    for pid, gs in players.items():
        h = [g for g in gs if (g[0], g[1]) < cut]
        if h:
            hists[pid] = h
    qpos = {}
    for p in POS_ALL:
        num = den = 0.0
        for pid, h in hists.items():
            if h[-1][2] != p or len(h) < PRIOR_MIN_GAMES:
                continue
            q, n, _ne, _qw = history_share(h, cfg.anchor)
            if q is not None:
                num += n * q
                den += n
        qpos[p] = num / den if den > 0 else None
    rows, excl = [], {"no_history": 0, "nonpositive_history_points": 0, "no_position_share": 0}
    for pid, gs in players.items():
        tw = truth_window(gs, season, w, cfg)
        if len(tw) < MIN_TRUTH_GAMES:
            continue
        pts_t = sum(_pts(g, cfg.anchor) for g in tw)
        if not pts_t > 0:
            continue
        h = hists.get(pid)
        if not h:
            excl["no_history"] += 1
            continue
        p = h[-1][2]
        if p not in POS_ALL:
            continue
        if qpos.get(p) is None:
            excl["no_position_share"] += 1
            continue
        k5, t5 = v5p.get(p, (math.inf, math.inf))
        q, n, _ne, _ = history_share(h, cfg.anchor)
        _q, _n, ne5, qw5 = history_share(h, cfg.anchor, t5)
        if q is None:
            excl["nonpositive_history_points"] += 1
            continue
        rows.append({"pid": pid, "pos": p, "season": season, "anchor": cfg.anchor, "origin": w, "n": n, "q_hist": q,
                     "q_pos": qpos[p], "neff5": ne5, "q_hist5": qw5 if qw5 is not None else q, "k5": k5,
                     "tg": len(tw), "rec_t": sum(g[3] for g in tw), "pts_t": pts_t, "tw": tw, "hist": h})
    return {"rows": rows, "q_pos": qpos, "excluded": excl}


def shrink(q_hist, q_pos, n, k):
    """The one shrinkage formula every rule uses (so B0's identities are exact)."""
    a = 0.0 if math.isinf(k) else n / (n + k)
    return a * q_hist + (1.0 - a) * q_pos


def pred(row, rule, k=None):
    if rule == "RL":
        return shrink(row["q_hist"], row["q_pos"], row["n"], k)
    if rule == "R0":
        return shrink(row["q_hist"], row["q_pos"], row["n"], 0.0)
    if rule == "Rpos":
        return shrink(row["q_hist"], row["q_pos"], row["n"], math.inf)
    if rule == "Rv5":
        return shrink(row["q_hist5"], row["q_pos"], row["neff5"], row["k5"])
    raise ValueError(rule)


def err(row, q):
    """E: (q x realized anchor points per game - realized catches per game) ** 2."""
    return (q * row["pts_t"] / row["tg"] - row["rec_t"] / row["tg"]) ** 2


# ---------------------------------------------------------------------------
# Selection (nested forward CV) and statistics
# ---------------------------------------------------------------------------

def select_k(rows: list, pos: str) -> float | None:
    rs = [r for r in rows if r["pos"] == pos]
    if not rs:
        return None
    best = None
    for k in G_L:            # ascending: strict improvement only, so ties keep the smaller k
        e = float(np.mean([err(r, pred(r, "RL", k)) for r in rs]))
        if best is None or e < best[1]:
            best = (k, e)
    return best[0]


def wls_slope(x, y, w):
    x, y, w = np.asarray(x, float), np.asarray(y, float), np.asarray(w, float)
    if len(x) < 3 or w.sum() <= 0:
        return None
    mx_, my = (w * x).sum() / w.sum(), (w * y).sum() / w.sum()
    sxx = (w * (x - mx_) ** 2).sum()
    if sxx <= 1e-12 * max(1.0, (w * x * x).sum()):
        return None
    return float((w * (x - mx_) * (y - my)).sum() / sxx)


def ols_slope(x, y):
    return wls_slope(x, y, np.ones(len(x)))


def cluster_ci(pids, diffs, rng, n=N_BOOT):
    """2.5 / 97.5 percentiles of the mean of diffs, resampling players (clusters)."""
    pids = np.asarray(pids)
    d = np.asarray(diffs, float)
    uniq, inv = np.unique(pids, return_inverse=True)
    sums = np.bincount(inv, weights=d)
    cnts = np.bincount(inv).astype(float)
    m = len(uniq)
    draws = np.empty(n)
    for b in range(n):
        idx = rng.integers(0, m, m)
        draws[b] = sums[idx].sum() / cnts[idx].sum()
    return float(d.mean()), (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))


def shuffle_p5(rows, preds, rng, n=N_SHUFFLE):
    """5th percentile of the mean E when predictions are permuted within (season, origin)."""
    groups = {}
    for i, r in enumerate(rows):
        groups.setdefault((r["season"], r["origin"]), []).append(i)
    q = np.asarray(preds, float)
    a = np.asarray([r["pts_t"] / r["tg"] for r in rows])
    c = np.asarray([r["rec_t"] / r["tg"] for r in rows])
    vals = np.empty(n)
    for b in range(n):
        qq = q.copy()
        for idx in groups.values():
            qq[idx] = q[rng.permutation(idx)]
        vals[b] = np.mean((qq * a - c) ** 2)
    return float(np.percentile(vals, 5))


def label_pos(ci):
    lo, hi = ci
    return "PASS" if lo > 0 else ("FAIL" if hi < 0 else "INCONCLUSIVE")


def label_harm(ci):
    lo, hi = ci
    return "PASS" if lo > 0 else ("HARM" if hi < 0 else "INCONCLUSIVE")


# ---------------------------------------------------------------------------
# The battery
# ---------------------------------------------------------------------------

def b0(players, integrity, rows_sample, v5p):
    """Identities (exact) and data integrity."""
    ident = {"RL_k0_eq_R0": True, "RL_kinf_eq_Rpos": True, "Rv5_k0_tinf_eq_R0": True}
    for r in rows_sample:
        if pred(r, "RL", 0.0) != pred(r, "R0"):
            ident["RL_k0_eq_R0"] = False
        if pred(r, "RL", math.inf) != pred(r, "Rpos"):
            ident["RL_kinf_eq_Rpos"] = False
        _q, _n, ne, qw = history_share(r["hist"], r.get("anchor", "half_ppr"), math.inf)
        if shrink(qw, r["q_pos"], ne, 0.0) != pred(r, "R0"):
            ident["Rv5_k0_tinf_eq_R0"] = False
    share = integrity.get("integrity_bad", 0) / max(1, integrity.get("rows", 1))
    ok = all(ident.values()) and share <= INTEGRITY_MAX_SHARE
    return {"identities": ident, "integrity": integrity, "integrity_share": share, "pass": ok}


def battery(players: dict, cfg: Config, v5p: dict, integrity: dict | None = None, pgs: dict | None = None,
            n_boot=N_BOOT, n_shuffle=N_SHUFFLE) -> dict:
    rng = np.random.default_rng(SEED)
    seasons = [s for s in range(cfg.sel_start, max(cfg.eval_seasons) + 1) if s not in cfg.drop_seasons]
    by_origin = {}
    excluded = {}
    for s in seasons:
        for w in cfg.origins:
            o = origin_rows(players, s, w, cfg, v5p)
            by_origin[(s, w)] = o["rows"]
            excluded[f"{s}-{w}"] = o["excluded"]
    evals = [s for s in cfg.eval_seasons if s not in cfg.drop_seasons]
    k_by = {}
    rows_eval = []
    for Y in evals:
        if cfg.dry_sel_origins:
            sel_rows = [r for (s, w), rs in by_origin.items() if s == Y and w in cfg.dry_sel_origins for r in rs]
        else:
            sel_rows = [r for (s, _w), rs in by_origin.items() if cfg.sel_start <= s < Y for r in rs]
        k_by[Y] = {p: select_k(sel_rows, p) for p in POS_ALL}
        for (s, w), rs in by_origin.items():
            if s != Y or w in cfg.dry_sel_origins:
                continue
            for r in rs:
                k = k_by[Y].get(r["pos"])
                if k is None:
                    continue
                rows_eval.append(dict(r, k=k))
    out = {"config": cfg.__dict__, "k_by_season": k_by,
           "cap_hits": {str(Y): [p for p, k in ks.items() if k == CAP] for Y, ks in k_by.items()},
           "excluded": excluded, "n_eval_rows": len(rows_eval), "B1": {}, "B2": {}, "B3": {}, "B4": {},
           "reported": {}}
    if integrity is not None:
        out["B0"] = b0(players, integrity, rows_eval, v5p)
    for p in POS_ALL:
        rs = [r for r in rows_eval if r["pos"] == p]
        if len(rs) < 10:
            continue
        P = {rule: [pred(r, rule, r["k"]) for r in rs] for rule in ("RL", "R0", "Rv5", "Rpos")}
        E = {rule: [err(r, q) for r, q in zip(rs, P[rule])] for rule in P}
        pids = [r["pid"] for r in rs]
        qtrue = [r["rec_t"] / r["pts_t"] for r in rs]
        wts = [r["pts_t"] for r in rs]
        cat_true = [r["rec_t"] / r["tg"] for r in rs]
        slopes = {rule: wls_slope(P[rule], qtrue, wts) for rule in P}
        cat_slopes = {rule: ols_slope([q * r["pts_t"] / r["tg"] for q, r in zip(P[rule], rs)], cat_true) for rule in P}
        spear = {}
        for rule in P:
            spear[rule] = float(spearmanr([q * r["pts_t"] / r["tg"] for q, r in zip(P[rule], rs)], cat_true)[0])
        out["reported"][p] = {"E": {rule: float(np.mean(v)) for rule, v in E.items()}, "share_slope": slopes,
                              "catch_slope_descriptive": cat_slopes, "spearman": spear, "n_rows": len(rs),
                              "n_players": len(set(pids))}
        if p not in POOL:
            continue
        won = 0
        per_season = {}
        for Y in evals:
            ix = [i for i, r in enumerate(rs) if r["season"] == Y]
            if not ix:
                continue
            eR, eP = np.mean([E["RL"][i] for i in ix]), np.mean([E["Rpos"][i] for i in ix])
            per_season[Y] = {"E_RL": float(eR), "E_pos": float(eP)}
            won += eR < eP
        d_pos = [a - b for a, b in zip(E["Rpos"], E["RL"])]
        pt, ci = cluster_ci(pids, d_pos, rng, n_boot)
        p5 = shuffle_p5(rs, P["RL"], rng, n_shuffle)
        e_rl = float(np.mean(E["RL"]))
        lab = label_pos(ci)
        if lab == "PASS" and not (won >= cfg.b1_needed and e_rl < p5):
            lab = "INCONCLUSIVE"
        out["B1"][p] = {"seasons_won": int(won), "seasons": len(per_season), "needed": cfg.b1_needed,
                        "diff": pt, "ci95": ci, "E_RL": e_rl, "shuffle_p5": p5, "label": lab, "per_season": per_season}
        d_v5 = [a - b for a, b in zip(E["Rv5"], E["RL"])]
        pt2, ci2 = cluster_ci(pids, d_v5, rng, n_boot)
        out["B2"][p] = {"diff": pt2, "ci95": ci2, "label": label_harm(ci2)}
        sl = slopes["RL"]
        out["B3"][p] = {"slope": sl, "band": B3_BAND,
                        "pass": sl is not None and B3_BAND[0] <= sl <= B3_BAND[1],
                        "slope_Rv5": slopes["Rv5"], "slope_R0": slopes["R0"], "slope_Rpos": slopes["Rpos"]}
        out["B4"][p] = {"E_R0": float(np.mean(E["R0"])), "slope_R0": slopes["R0"]}
    if cfg.b5 and pgs is not None:
        k25 = k_by.get(cfg.b5_season) or {}
        out["B5"] = b5(pgs, cfg, v5p, k25, rng, n_boot, n_shuffle)
    return out


def b5(pgs: dict, cfg: Config, v5p: dict, k25: dict, rng, n_boot, n_shuffle) -> dict:
    """Catch reconstruction on the chain's own history source (per-stat 2024+, keyed subset)."""
    rows = []
    for w in cfg.b5_origins:
        for r in origin_rows(pgs, cfg.b5_season, w, cfg, v5p)["rows"]:
            if r["pos"] in POOL and k25.get(r["pos"]) is not None:
                rows.append(dict(r, k=k25[r["pos"]]))
    if not rows:
        return {"label": "NA", "n_rows": 0}
    per = {}
    allE = {rule: [] for rule in ("RL", "Rv5", "Rpos")}
    pids, posl, preds_rl = [], [], []
    for r in rows:
        for rule in allE:
            allE[rule].append(err(r, pred(r, rule, r["k"])))
        pids.append(r["pid"])
        posl.append(r["pos"])
        preds_rl.append(pred(r, "RL", r["k"]))
    # pooled RB/WR/TE with equal weight per position: each bootstrap draw resamples players within
    # every position and averages the per-position means
    def pooled_diff(a, b, rng_):
        parts = []
        for p in POOL:
            ix = [i for i, x in enumerate(posl) if x == p]
            if not ix:
                continue
            pp = np.asarray([pids[i] for i in ix])
            d = np.asarray([allE[a][i] - allE[b][i] for i in ix], float)
            uniq, inv = np.unique(pp, return_inverse=True)
            parts.append((np.bincount(inv, weights=d), np.bincount(inv).astype(float), d.mean()))
        pt = float(np.mean([x[2] for x in parts]))
        draws = np.empty(n_boot)
        for bb in range(n_boot):
            vals = []
            for sums, cnts, _m in parts:
                idx = rng_.integers(0, len(sums), len(sums))
                vals.append(sums[idx].sum() / cnts[idx].sum())
            draws[bb] = np.mean(vals)
        return pt, (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
    pt, ci = pooled_diff("Rpos", "RL", rng)
    pt2, ci2 = pooled_diff("Rv5", "RL", rng)
    p5s = []
    e_rl = []
    for p in POOL:
        ix = [i for i, x in enumerate(posl) if x == p]
        if ix:
            p5s.append(shuffle_p5([rows[i] for i in ix], [preds_rl[i] for i in ix], rng, n_shuffle))
            e_rl.append(float(np.mean([allE["RL"][i] for i in ix])))
    e_rl_pooled, p5 = float(np.mean(e_rl)), float(np.mean(p5s))
    passed = ci[0] > 0 and e_rl_pooled < p5
    harm = ci2[1] < 0
    out = {"n_rows": len(rows), "k": k25, "diff_vs_pos": pt, "ci95_vs_pos": ci, "diff_vs_v5": pt2,
           "ci95_vs_v5": ci2, "E_RL": e_rl_pooled, "shuffle_p5": p5, "label": "PASS" if passed else "NOT_PASS",
           "harm_vs_v5": harm, "note": "pooled = equal-weight mean of per-position means; joint bootstrap within position"}
    out["custom_scoring_reported"] = custom_report(rows, cfg, v5p)
    return out


def custom_report(rows, cfg, v5p):
    """Reported only: T1b custom scorings with v5's frozen seven-category mix, and with the same mix
    whose catch share is replaced by RL's (other categories rescaled so F(m, Half) = 1)."""
    if cfg.anchor != "half_ppr":
        return None
    sel = json.loads(V5_SELECTION.read_text(encoding="utf-8"))["selection"]
    f = lambda x: math.inf if x in ("inf", math.inf) else float(x)  # noqa: E731
    # v5's seven-category position prior per (origin, position), from the rows' histories (players
    # with >= 8 history games); an approximation of v5's prior over all players, labelled as such
    priors = {}
    for r in rows:
        key = (r["origin"], r["pos"])
        if key not in priors:
            t = f(sel[r["pos"]]["t"])
            hs = {x["pid"]: mx.history_rates([g[5] for g in x["hist"]], t) for x in rows
                  if (x["origin"], x["pos"]) == key}
            pr = mx.position_prior({k: v for k, v in hs.items() if v is not None},
                                   {k: r["pos"] for k in hs}, "half_ppr")
            priors[key] = pr.get(r["pos"])
    out = {}
    for name, base, over, te in mx.CUSTOM[:2]:
        e_v5, e_rl = [], []
        for r in rows:
            p = r["pos"]
            prior = priors.get((r["origin"], p))
            if prior is None:
                continue
            t = f(sel[p]["t"])
            k = {c: f(v) for c, v in sel[p]["k"].items()}
            h = mx.history_rates([g[5] for g in r["hist"]], t)
            m = mx.shrunk_mix(h, prior, k, "half_ppr").m
            q = pred(r, "RL", r["k"])
            scale = (1 - 0.5 * q) / (1 - 0.5 * m["rec"]) if 1 - 0.5 * m["rec"] > 0 else 1.0
            m2 = {c: (q if c == "rec" else v * scale) for c, v in m.items()}
            tot = {c: sum(g[5].get(c, 0.0) for g in r["tw"]) for c in mx.CATS}
            T = mx.F(tot, "half_ppr")
            kw = {"overrides": over, "te_extra": te, "pos": p}
            truth = mx.F(tot, base, **kw) / r["tg"]
            e_v5.append(abs(T / r["tg"] * mx.F(m, base, **kw) - truth))
            e_rl.append(abs(T / r["tg"] * mx.F(m2, base, **kw) - truth))
        out[name] = {"mae_v5_mix": float(np.mean(e_v5)), "mae_v5_mix_with_RL_catch_share": float(np.mean(e_rl)),
                     "note": "v5 prior approximated from the eligible rows at the origin; reported only, never a gate"}
    return out


# ---------------------------------------------------------------------------
# Outcome (void / A / C), section 5
# ---------------------------------------------------------------------------

def c_conditions(b: dict) -> list:
    """[(name, ok or None if absent)] of every C condition in one battery."""
    conds = []
    for p in POOL:
        conds.append((f"B1 PASS at {p}", b["B1"].get(p, {}).get("label") == "PASS" if p in b["B1"] else False))
        conds.append((f"B3 in band at {p}", bool(b["B3"].get(p, {}).get("pass")) if p in b["B3"] else False))
    conds.append(("B2 PASS at WR", b["B2"].get("WR", {}).get("label") == "PASS"))
    for p in ("RB", "TE"):
        conds.append((f"B2 no HARM at {p}", b["B2"].get(p, {}).get("label") in ("PASS", "INCONCLUSIVE")))
    if "B5" in b:
        conds.append(("B5 PASS", b["B5"].get("label") == "PASS"))
        conds.append(("B5 no HARM vs Rv5", not b["B5"].get("harm_vs_v5", True)))
    else:
        conds.append(("B5 PASS", None))
    return conds


def decide(primary: dict, sens: dict) -> dict:
    fired = []
    if not primary.get("B0", {}).get("pass", False):
        fired.append(("void", "B0 failed: fix with a dated amendment, then rerun once"))
        return {"outcome": "void", "rules_fired": [{"outcome": o, "rule": r} for o, r in fired]}
    for name, ok in c_conditions(primary):
        if ok is None:
            fired.append(("A", f"{name}: absent in the primary"))
        elif not ok:
            fired.append(("A", f"{name} fails (primary)"))
    for sname, b in sens.items():
        for name, ok in c_conditions(b):
            if ok is False:
                fired.append(("A", f"{name} fails under {sname} (a flip blocks C)"))
    if fired:
        return {"outcome": "A", "rules_fired": [{"outcome": o, "rule": r} for o, r in fired]}
    return {"outcome": "C", "rules_fired": [{"outcome": "C", "rule": "every C condition holds in the primary and "
                                                                     "in every sensitivity run (absent tests ignored)"}]}
