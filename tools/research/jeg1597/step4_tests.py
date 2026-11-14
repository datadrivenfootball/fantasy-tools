"""JEG-1601 (step 4a of JEG-1597): the pre-registered tests, run as written.

Research only. docs/research/jeg1597/step4-preregistration.md is the spec;
deviations are logged in its "Changes after this commit" list. Reads the step 3
outputs (out/rebuild_values.csv, out/rescaled_natives.csv), the 2026 weekly
actuals, the 2015-2025 nflverse actuals, and (through rebuild_ddf.py, read-only)
the week history for projections, allocation and the CBS / USA Today columns.

Run:  python3 tools/research/jeg1597/step4_tests.py
Out:  tools/research/jeg1597/out/step4_results.json

Pure metric functions come first (unit-tested in tests/test_jeg1597_step4.py).
"""
from __future__ import annotations

import csv
import gzip
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "out"
SEED = 1597
N_BOOT = 2000
SNAP_WEEKS = (5, 6, 7, 8)          # realized summed over w..8 of 2026
CHART_WEEKS = (5, 6, 7, 8, 9)      # tests without realized points (FP, L)
LAST_ACTUAL_WEEK = 8
SET_SIZE = {"QB": 18, "RB": 36, "WR": 36, "TE": 18}
M1_POS = ("RB", "WR", "TE")
BAND = 7                           # ranks N_p .. N_p + 6
SCORINGS = ("standard", "half_ppr", "ppr")
ACT_COL = {"standard": "std", "half_ppr": "half_ppr", "ppr": "ppr"}


# ---------------------------------------------------------------------------
# Metrics (pure, weighted so a bootstrap resample is a vector of counts)
# ---------------------------------------------------------------------------

def weighted_ranks(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Average ranks of x when observation i is repeated w_i times (rows of w
    are resamples). Equal to scipy.stats.rankdata on the expanded data.
    x: (n,), w: (B, n) or (n,). Returns the same shape as w."""
    x = np.asarray(x, float)
    w = np.atleast_2d(np.asarray(w, float))
    less = (x[None, :] < x[:, None]).astype(float)      # [i, j] = x_j < x_i
    equal = (x[None, :] == x[:, None]).astype(float)
    # errstate: macOS Accelerate matmul raises spurious FP warnings on finite
    # inputs; the result is checked against scipy in the unit tests.
    with np.errstate(all="ignore"):
        r = w @ less.T + (w @ equal.T + 1.0) / 2.0
    return r


def weighted_pearson(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Pearson correlation per row of w (weights). a, b: (n,) or (B, n)."""
    w = np.atleast_2d(np.asarray(w, float))
    a = np.broadcast_to(np.asarray(a, float), w.shape)
    b = np.broadcast_to(np.asarray(b, float), w.shape)
    sw = w.sum(1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        ma = (w * a).sum(1, keepdims=True) / sw
        mb = (w * b).sum(1, keepdims=True) / sw
        cov = (w * (a - ma) * (b - mb)).sum(1)
        va = (w * (a - ma) ** 2).sum(1)
        vb = (w * (b - mb) ** 2).sum(1)
        return cov / np.sqrt(va * vb)


def spearman(x, y, w=None) -> np.ndarray:
    """Spearman correlation (average ranks for ties), weighted by repeat
    counts w (B, n); w None = each observation once. NaN when a side is
    constant."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if w is None:
        w = np.ones((1, len(x)))
    w = np.atleast_2d(np.asarray(w, float))
    rx, ry = weighted_ranks(x, w), weighted_ranks(y, w)
    return weighted_pearson(rx, ry, w)


def pair_matrices(value, target):
    """(A, D) for pair concordance: D[i, j] = 1 when the target differs
    (pairs tied on the target are not scored, which also drops a player's
    pairs with his own bootstrap copies); A[i, j] = 1 concordant, 0.5 when the
    method ties, 0 discordant, on D's pairs. Diagonal 0."""
    v, t = np.asarray(value, float), np.asarray(target, float)
    sv = np.sign(v[:, None] - v[None, :])
    st = np.sign(t[:, None] - t[None, :])
    D = (st != 0).astype(float)
    A = (1.0 + sv * st) / 2.0 * D
    np.fill_diagonal(A, 0.0)
    np.fill_diagonal(D, 0.0)
    return A, D


def pair_concordance(value, target, w=None) -> np.ndarray:
    """Share of scored pairs (any positions) the method orders as the
    target does, weighted by w_i * w_j per pair (B, n). Ties in the method
    count half."""
    A, D = pair_matrices(value, target)
    if w is None:
        w = np.ones((1, len(A)))
    w = np.atleast_2d(np.asarray(w, float))
    num = np.einsum("bi,ij,bj->b", w, A, w)
    den = np.einsum("bi,ij,bj->b", w, D, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def bootstrap_counts(n_units: int, n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    """(n_boot, n_units) repeat counts of a with-replacement resample of
    units, deterministic for a seed."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_units, size=(n_boot, n_units))
    out = np.zeros((n_boot, n_units))
    np.add.at(out, (np.arange(n_boot)[:, None], idx), 1.0)
    return out


def interval(samples: np.ndarray) -> list:
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    if not len(s):
        return [None, None]
    return [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]


def value_lookup(rows, week, scoring, method) -> dict:
    """{player_key: value} for a method; a missing row is value 0 (the
    caller reads with .get(k, 0.0))."""
    return {k: v for (w, s, m, k), v in rows.items() if w == week and s == scoring and m == method}


def realized_points(actuals: dict, keys, weeks, col) -> dict:
    """Sum of a scoring column over weeks; no row in a week = 0."""
    return {k: sum(actuals.get((wk, k), {}).get(col, 0.0) for wk in weeks) for k in keys}


def r3(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 4)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_values():
    rows, methods = {}, set()
    with (OUT / "rebuild_values.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = (int(r["week"]), r["scoring"], r["method"], int(r["player_key"]))
            rows[k] = float(r["value"])
            methods.add(r["method"])
    return rows, sorted(methods)


def load_actuals_2026():
    out = {}
    with (REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["season"]) != 2026:
                continue
            out[(int(r["week"]), int(r["player_key"]))] = {c: float(r[c] or 0) for c in ("std", "half_ppr", "ppr")}
    return out


def load_rescaled():
    out = defaultdict(dict)
    with (OUT / "rescaled_natives.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (int(r["week"]), r["target_scoring"], r["chart"], r["anchor"], float(r["lam"]), r["mode"])
            out[key][int(r["player_key"])] = {"native": float(r["native_rescaled"]), "base": float(r["native_base"]),
                                              "ratio": float(r["ratio"]), "pos": r["pos"],
                                              "published": float(r["native_published_at_target"])
                                              if r["native_published_at_target"] else None}
    return out


def load_world():
    """Projections, allocation and chart columns per week, through
    rebuild_ddf.py's loaders (read-only)."""
    sys.path.insert(0, str(HERE))
    import rebuild_ddf as rb
    vr, dc = rb.vr, rb.dc
    inp, hist, team, byes, gp = rb.load_world()
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    name_of = {k: p["name"] for k, p in inp.players.items()}
    live = {s: vr.Setting(inp, s, rb.TEAMS, hist=hist) for s in SCORINGS}
    included = {s: live[s].state()["included"] for s in SCORINGS}
    weeks = {}
    for w in CHART_WEEKS:
        natives, lines = rb.week_inputs(inp, hist, w)
        ppg_half = {}
        for k, by_src in lines.items():
            vals = [dc.points_from_triplet(t, "half_ppr") for t in by_src.values()]
            vals = [v for v in vals if v is not None and v > 0]
            if vals and pos_of.get(k) in dc.POSITIONS:
                ppg_half[k] = statistics.fmean(vals)
        proj = {s: rb.projected_points(lines, pos_of, w, team, byes, gp, s)[0] for s in SCORINGS}
        alloc = {}
        for s in SCORINGS:
            sources = {k: vr.SourceInput(k, vr.FAMILY[k], dict(natives[k][s])) for k in vr.SOURCES}
            for src in sources.values():
                src.values = {i: float(x) for i, x in src.values.items() if i in pos_of}
            inc = [k for k in sources if k in set(included[s])]
            m = vr.mean_ppg(sources, inc)
            order = {p: sorted((i for i in m if pos_of.get(i) == p), key=lambda i: (-m[i], i)) for p in dc.POSITIONS}
            a = vr.allocate(live[s].league, order, m, flex_bench_seats=True)
            alloc[s] = {p: int(a[p].get("replacement", a[p]["rostered"])) for p in dc.POSITIONS}
        weeks[w] = {"natives": natives, "lines": lines, "ppg_half": ppg_half, "proj": proj, "alloc": alloc}
    return {"pos_of": pos_of, "name_of": name_of, "weeks": weeks, "dc": dc}


def player_set(ppg_half, pos_of):
    out = []
    for p, n in SET_SIZE.items():
        out += sorted((k for k in ppg_half if pos_of.get(k) == p), key=lambda k: (-ppg_half[k], k))[:n]
    return out


# ---------------------------------------------------------------------------
# Main tests (H1, H2, H3, S): M1 / M2 with a paired player bootstrap
# ---------------------------------------------------------------------------

def build_cells(world, values, methods, actuals):
    """Per (week, scoring): player list, positions, realized, VAR target and
    every method's values (missing = 0)."""
    pos_of = world["pos_of"]
    cells = {}
    for w in SNAP_WEEKS:
        wk = world["weeks"][w]
        keys = player_set(wk["ppg_half"], pos_of)
        for s in SCORINGS:
            col = ACT_COL[s]
            all_keys = set(wk["proj"][s]) | set(keys)
            real_all = realized_points(actuals, all_keys, range(w, LAST_ACTUAL_WEEK + 1), col)
            repl = {}
            for p in SET_SIZE:
                order = sorted((k for k in wk["proj"][s] if pos_of.get(k) == p), key=lambda k: (-wk["proj"][s][k], k))
                n_p = wk["alloc"][s][p]
                band = order[n_p:n_p + BAND]
                repl[p] = statistics.fmean(real_all[k] for k in band) if band else 0.0
            real = np.array([real_all[k] for k in keys])
            var = np.array([real_all[k] - repl[pos_of[k]] for k in keys])
            vals = {}
            for m in methods:
                lk = value_lookup(values, w, s, m)
                vals[m] = np.array([lk.get(k, 0.0) for k in keys])
            proj = np.array([wk["proj"][s].get(k, 0.0) for k in keys])
            vals["PROJ"] = proj
            # Not pre-registered, reported beside PROJ: projected points above the
            # same band's projected mean (PROJ in VAR units, fair across positions).
            prepl = {}
            for p in SET_SIZE:
                order = sorted((k for k in wk["proj"][s] if pos_of.get(k) == p), key=lambda k: (-wk["proj"][s][k], k))
                band = order[wk["alloc"][s][p]:wk["alloc"][s][p] + BAND]
                prepl[p] = statistics.fmean(wk["proj"][s][k] for k in band) if band else 0.0
            vals["PROJ_VAR"] = proj - np.array([prepl[pos_of[k]] for k in keys])
            cells[(w, s)] = {"keys": keys, "pos": np.array([pos_of[k] for k in keys]), "real": real, "var": var,
                             "vals": vals, "repl": repl, "n_p": wk["alloc"][s]}
    return cells


def metric_samples(cells, methods, unit_index, W):
    """{(scoring, method): {"M1": (B+1,), "M1_QB": .., "M2": .., per-week ..}}.
    Row 0 is the full sample, rows 1.. the bootstrap."""
    B1 = W.shape[0] + 1
    out = {}
    for s in SCORINGS:
        for m in methods:
            m1_w, qb_w, m2_w = {}, {}, {}
            for w in SNAP_WEEKS:
                c = cells[(w, s)]
                idx = np.array([unit_index[k] for k in c["keys"]])
                Ww = np.vstack([np.ones(len(idx)), W[:, idx]])
                pos_m1 = []
                for p in M1_POS + ("QB",):
                    sel = c["pos"] == p
                    r = spearman(c["vals"][m][sel], c["real"][sel], Ww[:, sel])
                    if p == "QB":
                        qb_w[w] = r
                    else:
                        pos_m1.append(r)
                m1_w[w] = np.nanmean(np.vstack(pos_m1), axis=0)
                m2_w[w] = pair_concordance(c["vals"][m], c["var"], Ww)
            out[(s, m)] = {"M1": np.nanmean(np.vstack(list(m1_w.values())), axis=0),
                           "M1_QB": np.nanmean(np.vstack(list(qb_w.values())), axis=0),
                           "M2": np.nanmean(np.vstack(list(m2_w.values())), axis=0),
                           "M1_by_week": m1_w, "M2_by_week": m2_w}
            assert len(out[(s, m)]["M1"]) == B1
    return out


def diff(ms, s, a, b, metric):
    d = ms[(s, a)][metric] - ms[(s, b)][metric]
    lo, hi = interval(d[1:])
    return {"a": a, "b": b, "scoring": s, "metric": metric, "a_value": r3(ms[(s, a)][metric][0]),
            "b_value": r3(ms[(s, b)][metric][0]), "diff": r3(d[0]), "ci95": [r3(lo), r3(hi)],
            "by_week": {w: r3(ms[(s, a)][f"{metric}_by_week"][w][0] - ms[(s, b)][f"{metric}_by_week"][w][0])
                        for w in SNAP_WEEKS} if metric in ("M1", "M2") else None}


def ci_state(d):
    lo, hi = d["ci95"]
    if lo is not None and lo > 0:
        return "above"
    if hi is not None and hi < 0:
        return "below"
    return "includes0"


def verdict_h1(rows):
    """rows: the Standard M1 and M2 differences."""
    st = [ci_state(d) for d in rows]
    if any(x == "below" for x in st):
        return "FAIL"
    if all(x == "above" for x in st):
        return "PASS"
    return "NOT SHOWN"


def verdict_h2(primary, sens_fchalf, sens_nofc):
    base = verdict_h1(primary)
    flips = [p["scoring"] + " " + p["metric"] + " vs " + q["a"]
             for p, q in zip(primary * 2, sens_fchalf + sens_nofc)
             if p["diff"] is not None and q["diff"] is not None and np.sign(p["diff"]) != np.sign(q["diff"])]
    if base == "PASS" and flips:
        return "FAIL (not robust)", flips
    return base, flips


def steelman(cells, unit_index, W, s):
    """S: correlation of the correction (FC_corr - FC_raw) with the realized
    residual (realized - FC_raw), both in rank units (the values and points
    are in different units; deviation logged). Primary: ranks across the whole
    player set against realized points above replacement. Secondary: ranks
    within position against realized points."""
    res = {}
    for name in ("whole_set_VAR", "within_position_points"):
        xs, ys, us = [], [], []
        for w in SNAP_WEEKS:
            c = cells[(w, s)]
            idx = np.array([unit_index[k] for k in c["keys"]])
            one = np.ones((1, len(idx)))
            groups = [np.ones(len(idx), bool)] if name == "whole_set_VAR" else [c["pos"] == p for p in M1_POS]
            for g in groups:
                n = g.sum()
                tgt = c["var"][g] if name == "whole_set_VAR" else c["real"][g]
                rr = weighted_ranks(c["vals"]["FC_raw"][g], one[:, g])[0] / n
                rc = weighted_ranks(c["vals"]["FC_corr"][g], one[:, g])[0] / n
                rt = weighted_ranks(tgt, one[:, g])[0] / n
                xs.append(rc - rr)
                ys.append(rt - rr)
                us.append(idx[g])
        x, y, u = np.concatenate(xs), np.concatenate(ys), np.concatenate(us)
        Wf = np.vstack([np.ones(len(u)), W[:, u]])
        r = weighted_pearson(x, y, Wf)
        lo, hi = interval(r[1:])
        state = "above" if lo > 0 else "below" if hi < 0 else "includes0"
        verdict = ("PASS (steelman supported)" if state == "below" else
                   "FAIL (steelman rejected)" if state == "above" else "NOT SHOWN")
        res[name] = {"corr": r3(r[0]), "ci95": [r3(lo), r3(hi)], "n_rows": int(len(u)), "verdict": verdict,
                     "share_rows_changed": r3(float(np.mean(np.abs(x) > 1e-12)))}
    return res


# ---------------------------------------------------------------------------
# FP: within-position reorders of a rescaled scoring-blind chart
# ---------------------------------------------------------------------------

def fp_test(world, rescaled, actuals):
    pos_of, dc = world["pos_of"], world["dc"]
    out = {}
    for chart, anchor in (("fantasycalc", "ppr"), ("fantasypros", "half_ppr")):
        for lam, mode in ((1.0, "position_scaled"), (0.5, "position_scaled"), (1.0, "same_fit")):
            tot = {"swaps": 0, "right_proj": 0, "right_ratio": 0, "right_trailing": 0, "scored_trailing": 0}
            by_week = {}
            for w in CHART_WEEKS:
                std = rescaled.get((w, "standard", chart, anchor, lam, mode))
                full = rescaled.get((w, "ppr", chart, anchor, lam, mode))
                if not std or not full:
                    continue
                lines = world["weeks"][w]["lines"]
                rs_proj = {}
                for k, by_src in lines.items():
                    p = [dc.points_from_triplet(t, "ppr") for t in by_src.values()]
                    q = [dc.points_from_triplet(t, "standard") for t in by_src.values()]
                    pairs = [(a, b) for a, b in zip(p, q) if a is not None and b is not None and a > 0]
                    if pairs:
                        rs_proj[k] = statistics.fmean((a - b) / a for a, b in pairs)
                rs_trail = {}
                for k in std:
                    ppr = sum(actuals.get((wk, k), {}).get("ppr", 0.0) for wk in range(1, w))
                    sd = sum(actuals.get((wk, k), {}).get("std", 0.0) for wk in range(1, w))
                    if ppr > 0:
                        rs_trail[k] = (ppr - sd) / ppr
                wk_t = dict.fromkeys(tot, 0)
                for p in M1_POS:
                    top = sorted((k for k in std if std[k]["pos"] == p), key=lambda k: (-std[k]["base"], k))[:36]
                    for i in range(len(top)):
                        for j in range(i + 1, len(top)):
                            a, b = top[i], top[j]
                            ds = std[a]["native"] - std[b]["native"]
                            df = full[a]["native"] - full[b]["native"]
                            if ds * df >= 0:
                                continue
                            up = a if df > 0 else b      # higher in Full
                            dn = b if up == a else a
                            wk_t["swaps"] += 1
                            wk_t["right_proj"] += rs_proj.get(up, 0) > rs_proj.get(dn, 0)
                            # tautology check: the ratio the rescale used (std / anchor), lower = more receptions
                            wk_t["right_ratio"] += std[up]["ratio"] < std[dn]["ratio"]
                            if up in rs_trail and dn in rs_trail:
                                wk_t["scored_trailing"] += 1
                                wk_t["right_trailing"] += rs_trail[up] > rs_trail[dn]
                by_week[w] = {"swaps": wk_t["swaps"], "share_right_proj": r3(wk_t["right_proj"] / wk_t["swaps"])
                              if wk_t["swaps"] else None}
                for k in tot:
                    tot[k] += wk_t[k]
            sw = tot["swaps"]
            share = tot["right_proj"] / sw if sw else None
            out[f"{chart}|lam{lam}|{mode}"] = {
                "swaps": sw, "share_right_projected_reception_share": r3(share),
                "share_right_ratio_used": r3(tot["right_ratio"] / sw) if sw else None,
                "share_right_trailing_2026_reception_share": r3(tot["right_trailing"] / tot["scored_trailing"])
                if tot["scored_trailing"] else None, "n_trailing_scored": tot["scored_trailing"],
                "by_week": by_week,
                "verdict": None if share is None else ("PASS" if share >= 0.90 else "FAIL")}
    return out


# ---------------------------------------------------------------------------
# L: CBS / USA Today Standard column rescaled to Full vs their own Full column
# ---------------------------------------------------------------------------

LAMBDA_GRID = tuple(round(0.05 * i, 2) for i in range(0, 41))   # 0 .. 2


def l_test(world, rescaled):
    pos_of, dc = world["pos_of"], world["dc"]
    rat_cache = {}

    def within(w, chart, vals):
        wk = world["weeks"][w]
        keys = player_set(wk["ppg_half"], pos_of)
        std, full = wk["natives"][chart]["standard"], wk["natives"][chart]["ppr"]
        rs = []
        for p in M1_POS:
            ks = [k for k in keys if pos_of[k] == p and k in std and k in full]
            if len(ks) >= 3:
                rs.append(spearman([vals[k] for k in ks], [full[k] for k in ks])[0])
        whole_ks = [k for k in keys if k in std and k in full]
        whole = spearman([vals[k] for k in whole_ks], [full[k] for k in whole_ks])[0]
        return float(np.nanmean(rs)), float(whole), len(whole_ks)

    def rescaled_at(w, chart, lam, mode="position_scaled"):
        wk = world["weeks"][w]
        if (w,) not in rat_cache:
            rat_cache[(w,)] = {k: dc.player_ratio(ln, "standard", "ppr") for k, ln in wk["lines"].items()}
        return dc.rescale_chart(wk["natives"][chart]["standard"], pos_of, rat_cache[(w,)], wk["proj"]["standard"],
                                lam, mode=mode).natives

    out = {"by_chart": {}}
    for chart in ("cbs", "usatoday"):
        rows, wins = {}, 0
        for w in CHART_WEEKS:
            std = world["weeks"][w]["natives"][chart]["standard"]
            un_w, un_all, n = within(w, chart, std)
            r1 = rescaled_at(w, chart, 1.0)
            r1_w, r1_all, _ = within(w, chart, r1)
            r1s_all = within(w, chart, rescaled_at(w, chart, 1.0, "same_fit"))[1]
            # reuse check against step 3's file
            ref = rescaled.get((w, "ppr", chart, "standard", 1.0, "position_scaled"), {})
            mx = max((abs(ref[k]["native"] - r1[k]) for k in ref if k in r1), default=None)
            wins += r1_w > un_w
            rows[w] = {"n": n, "unchanged_within": r3(un_w), "rescaled_within": r3(r1_w),
                       "diff_within": r3(r1_w - un_w), "unchanged_whole_set": r3(un_all),
                       "rescaled_whole_set_position_scaled": r3(r1_all), "rescaled_whole_set_same_fit": r3(r1s_all),
                       "max_abs_diff_vs_step3_file": r3(mx) if mx is not None else None}
        out["by_chart"][chart] = {"weeks": rows, "weeks_better": wins, "n_weeks": len(CHART_WEEKS)}
    out["verdict"] = "PASS" if all(v["weeks_better"] > len(CHART_WEEKS) / 2 for v in out["by_chart"].values()) else "FAIL"

    # lambda fitted on CBS (mean within-position Spearman over weeks), tested on USA Today
    curve = {}
    for chart in ("cbs", "usatoday"):
        curve[chart] = {}
        for lam in LAMBDA_GRID:
            vals = [within(w, chart, rescaled_at(w, chart, lam))[0] for w in CHART_WEEKS]
            curve[chart][lam] = float(np.mean(vals))
    best = max(LAMBDA_GRID, key=lambda l: (curve["cbs"][l], -l))
    best_usa = max(LAMBDA_GRID, key=lambda l: (curve["usatoday"][l], -l))
    out["lambda"] = {"grid": [LAMBDA_GRID[0], LAMBDA_GRID[-1], 0.05], "fitted_on_cbs": best,
                     "cbs_at_fitted": r3(curve["cbs"][best]), "cbs_at_0": r3(curve["cbs"][0.0]),
                     "cbs_at_1": r3(curve["cbs"][1.0]),
                     "usatoday_at_cbs_lambda": r3(curve["usatoday"][best]), "usatoday_at_0": r3(curve["usatoday"][0.0]),
                     "usatoday_at_1": r3(curve["usatoday"][1.0]), "usatoday_own_best": best_usa,
                     "curve": {c: {str(l): r3(v) for l, v in cv.items()} for c, cv in curve.items()}}
    return out


# ---------------------------------------------------------------------------
# M: 2015-2025 mechanism test
# ---------------------------------------------------------------------------

def m_test(dc):
    path = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
    data = defaultdict(dict)    # season -> {(week, pid): row}
    pos_of = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["pos"] not in M1_POS:
                continue
            s, wk = int(r["season"]), int(r["week"])
            data[s][(wk, r["player_id"])] = (float(r["std"] or 0), float(r["half_ppr"] or 0), float(r["ppr"] or 0))
            pos_of[(s, r["player_id"])] = r["pos"]
    last = {s: max(wk for wk, _ in d) for s, d in data.items()}
    groups = []   # (season, week, pos, unit ids, unscaled, rescaled, target)
    units = {}
    for s in sorted(data):
        d = data[s]
        pids = {pid for _, pid in d}
        for w in SNAP_WEEKS:
            trail = {}
            for pid in pids:
                rows = [d[(wk, pid)] for wk in range(1, w) if (wk, pid) in d]
                if len(rows) < 2:
                    continue
                g = len(rows)
                trail[pid] = tuple(sum(r[i] for r in rows) / g for i in range(3))
            ros = {pid: sum(d.get((wk, pid), (0, 0, 0))[0] for wk in range(w, last[s] + 1)) for pid in trail}
            pos = {pid: pos_of[(s, pid)] for pid in trail}
            native = {pid: t[2] for pid, t in trail.items() if t[2] > 0}
            ratios = {pid: trail[pid][0] / trail[pid][2] for pid in native}
            # the trailing Full PPR rate is the "chart"; its points at the anchor are the rate itself
            resc = dc.rescale_chart(native, pos, ratios, dict(native), 1.0, mode="position_scaled").natives
            for p in M1_POS:
                n = {"RB": 36, "WR": 36, "TE": 18}[p]
                ks = sorted((k for k in native if pos[k] == p), key=lambda k: (-trail[k][1], k))[:n]
                for k in ks:
                    units.setdefault(k, len(units))
                groups.append((s, w, p, np.array([units[k] for k in ks]), np.array([native[k] for k in ks]),
                               np.array([resc[k] for k in ks]), np.array([ros[k] for k in ks])))
    W = bootstrap_counts(len(units))
    res_un, res_rs, by_season = [], [], defaultdict(list)
    for s, w, p, idx, un, rs, tg in groups:
        Ww = np.vstack([np.ones(len(idx)), W[:, idx]])
        a, b = spearman(rs, tg, Ww), spearman(un, tg, Ww)
        res_rs.append(a)
        res_un.append(b)
        by_season[s].append(a[0] - b[0])
    rs_m, un_m = np.nanmean(np.vstack(res_rs), 0), np.nanmean(np.vstack(res_un), 0)
    d = rs_m - un_m
    lo, hi = interval(d[1:])
    return {"n_groups": len(groups), "n_player_units": len(units), "seasons": sorted(data),
            "rescaled_M1": r3(rs_m[0]), "unscaled_M1": r3(un_m[0]), "diff": r3(d[0]), "ci95": [r3(lo), r3(hi)],
            "by_season_diff": {s: r3(float(np.mean(v))) for s, v in by_season.items()},
            "seasons_positive": int(sum(np.mean(v) > 0 for v in by_season.values())),
            "verdict": "PASS" if lo > 0 else "FAIL"}


# ---------------------------------------------------------------------------

def main():
    values, methods = load_values()
    actuals = load_actuals_2026()
    rescaled = load_rescaled()
    world = load_world()
    cells = build_cells(world, values, methods, actuals)
    all_methods = methods + ["PROJ", "PROJ_VAR"]
    units = sorted({k for c in cells.values() for k in c["keys"]})
    unit_index = {k: i for i, k in enumerate(units)}
    W = bootstrap_counts(len(units))
    ms = metric_samples(cells, all_methods, unit_index, W)

    table = {f"{s}|{m}": {k: r3(ms[(s, m)][k][0]) for k in ("M1", "M1_QB", "M2")} |
             {"M1_by_week": {w: r3(ms[(s, m)]["M1_by_week"][w][0]) for w in SNAP_WEEKS},
              "M2_by_week": {w: r3(ms[(s, m)]["M2_by_week"][w][0]) for w in SNAP_WEEKS}}
             for s in SCORINGS for m in all_methods}

    H1 = {s: [diff(ms, s, "FC_corr", "FC_raw", k) for k in ("M1", "M2", "M1_QB")] for s in SCORINGS}
    H1_sens = {s: {v: [diff(ms, s, v, "FC_raw", k) for k in ("M1", "M2")]
                   for v in ("FC_corr_samefit", "FC_corr_l05", "FC_corr_half")} for s in SCORINGS}
    H2 = {s: [diff(ms, s, "DDF_new", "DDF_cur", k) for k in ("M1", "M2", "M1_QB")] for s in SCORINGS}
    H2_sens = {s: {v: [diff(ms, s, v, "DDF_cur", k) for k in ("M1", "M2")]
                   for v in ("DDF_new_samefit", "DDF_new_l05", "DDF_new_fchalf", "DDF_new_noFC")} for s in SCORINGS}
    H3 = {s: [diff(ms, s, "FC_corr", "DDF_new", k) for k in ("M1", "M2", "M1_QB")] for s in SCORINGS}
    PROJ = {s: {m: [diff(ms, s, "PROJ", m, k) for k in ("M1", "M2")]
                for m in ("DDF_cur", "DDF_new", "FC_raw", "FC_corr")} for s in SCORINGS}
    PROJ_VAR = {s: {m: [diff(ms, s, "PROJ_VAR", m, "M2")] for m in ("DDF_cur", "DDF_new")} for s in SCORINGS}

    prim_h2 = [H2["standard"][0], H2["standard"][1], H2["ppr"][0], H2["ppr"][1]]
    fch = [H2_sens[s]["DDF_new_fchalf"][i] for s in ("standard", "ppr") for i in (0, 1)]
    nofc = [H2_sens[s]["DDF_new_noFC"][i] for s in ("standard", "ppr") for i in (0, 1)]
    h2_verdict, h2_flips = verdict_h2(prim_h2, fch, nofc)

    results = {
        "spec": "docs/research/jeg1597/step4-preregistration.md",
        "seed": SEED, "n_boot": N_BOOT, "snapshot_weeks": SNAP_WEEKS, "realized_through_week": LAST_ACTUAL_WEEK,
        "player_set": {w: {"n": len(cells[(w, "standard")]["keys"]),
                           "replacement_index_N_p": {s: cells[(w, s)]["n_p"] for s in SCORINGS},
                           "replacement_points": {s: {p: r3(v) for p, v in cells[(w, s)]["repl"].items()}
                                                  for s in SCORINGS}} for w in SNAP_WEEKS},
        "bootstrap_units": len(units),
        "methods": table,
        "H1": {"rows": H1, "sensitivity": H1_sens, "verdict": verdict_h1(H1["standard"][:2]),
               "verdict_half_info": verdict_h1(H1["half_ppr"][:2])},
        "H2": {"rows": H2, "sensitivity": H2_sens, "verdict": h2_verdict, "sign_flips": h2_flips,
               "verdict_without_robustness": verdict_h1(prim_h2),
               "verdict_half_info": verdict_h1(H2["half_ppr"][:2])},
        "H3": {"rows": H3},
        "PROJ": PROJ, "PROJ_VAR_not_preregistered": PROJ_VAR,
        "S": {s: steelman(cells, unit_index, W, s) for s in ("standard", "half_ppr")},
        "FP": fp_test(world, rescaled, actuals),
        "L": l_test(world, rescaled),
        "M": m_test(world["dc"]),
    }
    (OUT / "step4_results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print("H1", results["H1"]["verdict"], "H2", h2_verdict, h2_flips)
    for s in SCORINGS:
        for d in H1[s][:2] + H2[s][:2]:
            print(s, d["a"], d["b"], d["metric"], d["diff"], d["ci95"])
    print("S", json.dumps(results["S"]))
    print("FP", {k: (v["share_right_projected_reception_share"], v["verdict"]) for k, v in results["FP"].items()})
    print("L", results["L"]["verdict"], json.dumps(results["L"]["lambda"])[:400])
    print("M", {k: results["M"][k] for k in ("diff", "ci95", "verdict", "seasons_positive")})


if __name__ == "__main__":
    main()
