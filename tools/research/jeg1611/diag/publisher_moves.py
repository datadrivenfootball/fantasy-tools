"""JEG-1611 diagnostic: is the publishers' own Standard-to-Full move within a
position a reproducible target, or mostly noise / hand edits?

Research only. Dev weeks 5, 6, 7 of 2026 only (8-9 are holdout: not loaded as
chart weeks; the actuals file is read through its last week for the realized
rest-of-season receptions, item 3c). Saved snapshots only, no network.

Run:  /usr/bin/python3 tools/research/jeg1611/diag/publisher_moves.py
Out:  tools/research/jeg1611/out/diag/publisher_moves.json, publisher_moves.md
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OUT = REPO / "tools" / "research" / "jeg1611" / "out" / "diag"
sys.path.insert(0, str(REPO / "tools" / "research" / "jeg1605"))
sys.path.insert(0, str(REPO / "tools" / "research" / "jeg1610"))

import l_gate as lg  # noqa: E402
import history as hi  # noqa: E402

s4 = lg.s4
DEV_WEEKS = (5, 6, 7)
POS = ("RB", "WR", "TE")
PUBS = ("cbs", "usatoday")
OTHER = {"cbs": "usatoday", "usatoday": "cbs"}
B = 2000
SEED = 1611


def r4(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 4)


# ---------------------------------------------------------------------------
# Weighted helpers (rows of W are bootstrap count vectors; row 0 = point est.)
# ---------------------------------------------------------------------------

def boot_W(clusters, rng):
    """(B+1, n) weights; row 0 all ones; resampling clusters (player keys)."""
    u = sorted(set(clusters))
    idx = {c: i for i, c in enumerate(u)}
    col = np.array([idx[c] for c in clusters])
    draws = rng.integers(0, len(u), size=(B, len(u)))
    counts = np.stack([np.bincount(d, minlength=len(u)) for d in draws]).astype(float)
    return np.vstack([np.ones(len(clusters)), counts[:, col]])


def gdemean(x, groups, W):
    """x minus its weighted mean within each group, per row of W. -> (B+1, n)."""
    x = np.asarray(x, float)
    out = np.broadcast_to(x, W.shape).copy()
    g = np.asarray(groups)
    for v in set(groups):
        m = g == v
        sw = W[:, m].sum(1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[:, m] -= (W[:, m] * x[m]).sum(1, keepdims=True) / sw
    return out


def wslope(x, y, W):
    """OLS slope of y on x (both already group de-meaned per row)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (W * x * y).sum(1) / (W * x * x).sum(1)


def summ(arr):
    arr = np.asarray(arr, float)
    est, bs = arr[0], arr[1:]
    bs = bs[np.isfinite(bs)]
    lo, hi_ = (np.percentile(bs, [2.5, 97.5]) if len(bs) else (np.nan, np.nan))
    return {"est": r4(est), "lo": r4(lo), "hi": r4(hi_)}


def fmt(d):
    return "n/a" if d is None or d.get("est") is None else f"{d['est']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load():
    ctx = lg.load_ctx()
    weeks = {w: lg.load_week(ctx, w) for w in DEV_WEEKS}
    rows = hi.load_rows()
    last = max((r[1] for r in rows if r[0] == hi.CURRENT_SEASON))
    hist = {w: hi.player_stats(hi.window_rows(rows, w)) for w in DEV_WEEKS}
    ros = {w: hi.player_stats([r for r in rows if r[0] == hi.CURRENT_SEASON and w <= r[1] <= last])
           for w in DEV_WEEKS}
    return ctx, weeks, hist, ros, last


def build_rows(ctx, weeks, hist, ros, set_name, pub=None):
    """Player-week rows on the 'common' set (all four columns > 0) or a
    publisher's own set (its two columns > 0). RB/WR/TE only."""
    pos_of = ctx["pos_of"]
    out = []
    for w in DEV_WEEKS:
        nat = weeks[w]["natives"]
        for k in weeks[w]["keys"]:
            p = pos_of[k]
            if p not in POS:
                continue
            pubs = PUBS if set_name == "common" else (pub,)
            if not all(nat[q]["standard"].get(k, 0) > 0 and nat[q]["ppr"].get(k, 0) > 0 for q in pubs):
                continue
            h = hist[w].get(k)
            hb = h is not None and h[0] >= hi.MIN_GAMES and h[1] > 0
            ro = ros[w].get(k)
            r = {"w": w, "k": k, "pos": p, "g": f"{w}|{p}", "hist_ok": hb,
                 "hist_games": h[0] if h else 0,
                 "std_h": h[1] if h else None, "rec_h": h[2] if h else None,
                 "ros_games": ro[0] if ro else 0, "rec_ros": ro[2] if ro else None}
            for q in PUBS:
                S, F = nat[q]["standard"].get(k, 0), nat[q]["ppr"].get(k, 0)
                H = nat[q]["half_ppr"].get(k, 0)
                r[q] = {"S": S, "F": F, "H": H, "m": math.log(F / S) if S > 0 and F > 0 else None}
            out.append(r)
    return out


def subsets(rows):
    """(label, rows) for each week and pooled."""
    yield from ((str(w), [r for r in rows if r["w"] == w]) for w in DEV_WEEKS)
    yield "pooled", rows


# ---------------------------------------------------------------------------
# Item 1: spread and flat-multiplier share
# ---------------------------------------------------------------------------

def item1(rows, pub):
    res = {}
    for lab, rs in subsets(rows):
        res[lab] = {}
        for p in POS + ("ALL",):
            sel = [r for r in rs if p == "ALL" or r["pos"] == p]
            dm, exact, within1, xs = [], 0, 0, []
            for g in sorted({r["g"] for r in sel}):
                gr = [r for r in sel if r["g"] == g]
                m = np.array([r[pub]["m"] for r in gr])
                ratio = np.exp(m)
                med = float(np.median(ratio))
                dm += list(m - m.mean())
                exact += int(np.sum(np.abs(ratio / med - 1) < 1e-6))
                within1 += int(np.sum(np.abs(ratio / med - 1) <= 0.01))
                x = [math.log((r["std_h"] + r["rec_h"]) / r["std_h"]) for r in gr if r["hist_ok"]]
                if len(x) >= 2:
                    xs += list(np.array(x) - np.mean(x))
            n = len(dm)
            res[lab][p] = {"n": n, "sd_demeaned_move": r4(np.std(dm, ddof=1)) if n > 1 else None,
                           "share_exact_median": r4(exact / n) if n else None,
                           "share_within_1pct_median": r4(within1 / n) if n else None,
                           "sd_full_strength_expected_move_hist": r4(np.std(xs, ddof=1)) if len(xs) > 1 else None}
    # median ratio (published flat part) per week and position
    res["median_ratio_F_over_S"] = {str(w): {p: r4(np.median([math.exp(r[pub]["m"]) for r in rows
                                                              if r["w"] == w and r["pos"] == p]))
                                             for p in POS} for w in DEV_WEEKS}
    # value granularity (are columns rounded to integers?)
    vals = [r[pub][c] for r in rows for c in ("S", "F")]
    res["share_integer_values"] = r4(np.mean([abs(v - round(v)) < 1e-9 for v in vals]))
    return res


# ---------------------------------------------------------------------------
# Generic correlation block (Spearman, Pearson, slope) with bootstrap
# ---------------------------------------------------------------------------

def corr_block(rs, xfun, yfun, rng, slope=True):
    """Within-position de-meaned y vs de-meaned x on rows where both exist;
    per position and ALL (stacked, de-meaned within week-position)."""
    out = {}
    for p in POS + ("ALL",):
        sel = [r for r in rs if (p == "ALL" or r["pos"] == p)]
        sel = [r for r in sel if xfun(r) is not None and yfun(r) is not None]
        if len(sel) < 5:
            out[p] = {"n": len(sel)}
            continue
        x = np.array([xfun(r) for r in sel])
        y = np.array([yfun(r) for r in sel])
        g = [r["g"] for r in sel]
        W = boot_W([r["k"] for r in sel], rng)
        xd, yd = gdemean(x, g, W), gdemean(y, g, W)
        single = len(set(g)) == 1
        # Spearman ranks use the point-estimate (unweighted) de-meaning, held fixed across resamples
        sp = s4.spearman(x, y, W) if single else s4.spearman(xd[0], yd[0], W)
        pe = s4.weighted_pearson(xd, yd, W)
        d = {"n": len(sel), "spearman": summ(sp), "pearson": summ(pe)}
        if slope:
            d["ols_slope"] = summ(wslope(xd, yd, W))
        out[p] = d
    return out


# ---------------------------------------------------------------------------
# Item 2: publisher vs publisher
# ---------------------------------------------------------------------------

def level_spearman(rs, col, rng):
    out = {}
    for p in POS:
        sel = [r for r in rs if r["pos"] == p]
        ws = sorted({r["w"] for r in sel})
        W = boot_W([r["k"] for r in sel], rng)
        per = []
        for w in ws:
            m = np.array([r["w"] == w for r in sel])
            a = np.array([r["cbs"][col] for r in sel])[m]
            b = np.array([r["usatoday"][col] for r in sel])[m]
            per.append(s4.spearman(a, b, W[:, m]))
        out[p] = {"n": len(sel), "spearman_mean_over_weeks": summ(np.mean(per, 0))}
    return out


def item2(rows, rng):
    res = {}
    for lab, rs in subsets(rows):
        res[lab] = {"move_cbs_vs_usatoday": corr_block(rs, lambda r: r["usatoday"]["m"], lambda r: r["cbs"]["m"],
                                                       rng, slope=True),
                    "full_level": level_spearman(rs, "F", rng),
                    "standard_level": level_spearman(rs, "S", rng)}
    return res


# ---------------------------------------------------------------------------
# Item 3: moves vs reception history and realized ROS receptions
# ---------------------------------------------------------------------------

def hx(r):
    return r["rec_h"] / (r["std_h"] + r["rec_h"]) if r["hist_ok"] else None


def xh(r):
    return math.log((r["std_h"] + r["rec_h"]) / r["std_h"]) if r["hist_ok"] else None


def xr(r):
    return (math.log((r["std_h"] + r["rec_ros"]) / r["std_h"])
            if r["hist_ok"] and r["rec_ros"] is not None else None)


def item3(rows, pub, rng):
    y = lambda r: r[pub]["m"]  # noqa: E731
    res = {}
    for lab, rs in subsets(rows):
        res[lab] = {
            "n_rows": len(rs), "n_fallback_hist": sum(not r["hist_ok"] for r in rs),
            "n_no_ros_games": sum(r["rec_ros"] is None for r in rs),
            "a_hist_rec_share": corr_block(rs, hx, y, rng, slope=False),
            "b_hist_rec_per_game": corr_block(rs, lambda r: r["rec_h"] if r["hist_ok"] else None, y, rng, slope=False),
            "c_ros_rec_per_game": corr_block(rs, lambda r: r["rec_ros"] if r["hist_ok"] and r["rec_ros"] is not None
                                             else None, y, rng, slope=False),
            "slope_on_full_strength_move_hist": corr_block(rs, xh, y, rng),
            "slope_on_full_strength_move_ros": corr_block(rs, xr, y, rng),
        }
    res["fallback_players"] = sorted({(r["k"], r["pos"], r["hist_games"]) for r in rows if not r["hist_ok"]})
    return res


# ---------------------------------------------------------------------------
# Item 4: reachable ceiling, l_gate.metrics 'within' (mean RB/WR/TE Spearman)
# ---------------------------------------------------------------------------

def within_W(rs, pred, tgt, W):
    """Per week: mean over RB/WR/TE of the weighted Spearman of pred vs tgt.
    Returns {week: (B+1,)} plus 'pooled' = mean over weeks."""
    out = {}
    for w in sorted({r["w"] for r in rs}):
        per = []
        for p in POS:
            m = np.array([r["w"] == w and r["pos"] == p for r in rs])
            per.append(s4.spearman(pred[m], tgt[m], W[:, m]))
        out[str(w)] = np.mean(per, 0)
    out["pooled"] = np.mean([out[str(w)] for w in sorted({r["w"] for r in rs})], 0)
    return out


def fit_slope(x, y, g):
    W1 = np.ones((1, len(x)))
    return float(wslope(gdemean(x, g, W1), gdemean(y, g, W1), W1)[0])


def item4(rows, rng, own_rows):
    res = {}
    g = [r["g"] for r in rows]
    W = boot_W([r["k"] for r in rows], rng)
    for pub in PUBS:
        o = OTHER[pub]
        S = np.array([r[pub]["S"] for r in rows])
        F = np.array([r[pub]["F"] for r in rows])
        m = np.array([r[pub]["m"] for r in rows])
        mo = np.array([r[o]["m"] for r in rows])
        W1 = np.ones((1, len(rows)))
        m_mean = m - gdemean(m, g, W1)[0]                      # group mean of the target move
        mo_dm = gdemean(mo, g, W1)[0]

        def xfill(fn):
            x = np.array([fn(r) if fn(r) is not None else np.nan for r in rows])
            for v in set(g):                                   # missing -> group mean (zero de-meaned move)
                k = np.array(g) == v
                x[k & np.isnan(x)] = np.nanmean(x[k]) if np.isfinite(x[k]).any() else 0.0
            return gdemean(x, g, W1)[0]

        x_h, x_r = xfill(xh), xfill(xr)
        preds = {
            "unchanged": (S, F),
            "other_publisher_move_fitted_slope": None,
            "hist_full_strength_fitted_slope": None,
            "oracle_ros_fitted_slope": None,
            "oracle_ros_slope_1": None,
        }
        slopes = {"other_publisher_move_fitted_slope": fit_slope(mo_dm, m, g),
                  "hist_full_strength_fitted_slope": fit_slope(x_h, m, g),
                  "oracle_ros_fitted_slope": fit_slope(x_r, m, g), "oracle_ros_slope_1": 1.0}
        xs = {"other_publisher_move_fitted_slope": mo_dm, "hist_full_strength_fitted_slope": x_h,
              "oracle_ros_fitted_slope": x_r, "oracle_ros_slope_1": x_r}
        for name in slopes:
            preds[name] = (S * np.exp(m_mean + slopes[name] * xs[name]), F)
        res[pub] = {"slopes_in_sample_pooled": {k: r4(v) for k, v in slopes.items()}, "S_to_F": {}, "F_to_S": {}}
        base_sf = within_W(rows, S, F, W)
        base_fs = within_W(rows, F, S, W)
        for name, (pf, _) in preds.items():
            sf = within_W(rows, pf, F, W)
            # Full -> Standard: predicted Standard = F / exp(move)
            ps = F / np.exp(m_mean + (slopes[name] * xs[name] if name != "unchanged" else 0.0)) \
                if name != "unchanged" else F
            fs = within_W(rows, ps, S, W)
            res[pub]["S_to_F"][name] = {wk: {"within": summ(v), "gain_vs_unchanged": summ(v - base_sf[wk])}
                                        for wk, v in sf.items()}
            res[pub]["F_to_S"][name] = {wk: {"within": summ(v), "gain_vs_unchanged": summ(v - base_fs[wk])}
                                        for wk, v in fs.items()}
        # unchanged on the publisher's own set (should equal the l_gate 'unchanged' within)
        orows = own_rows[pub]
        Wo = boot_W([r["k"] for r in orows], rng)
        So = np.array([r[pub]["S"] for r in orows])
        Fo = np.array([r[pub]["F"] for r in orows])
        res[pub]["unchanged_own_set_S_to_F"] = {wk: summ(v) for wk, v in within_W(orows, So, Fo, Wo).items()}
    return res


# ---------------------------------------------------------------------------
# Item 5: half column
# ---------------------------------------------------------------------------

def item5(ctx, weeks):
    pos_of = ctx["pos_of"]
    res = {}
    for pub in PUBS:
        res[pub] = {}
        for w in DEV_WEEKS:
            nat = weeks[w]["natives"][pub]
            ks = [k for k in nat["standard"] if pos_of.get(k) in POS + ("QB",)
                  and k in nat["ppr"] and k in nat["half_ppr"]]
            dev = np.array([nat["half_ppr"][k] - (nat["standard"][k] + nat["ppr"][k]) / 2 for k in ks])
            sc = set(weeks[w]["keys"])
            devs = np.array([d for k, d in zip(ks, dev) if k in sc])
            res[pub][str(w)] = {
                "n_all": len(ks), "max_abs_dev_all": r4(np.max(np.abs(dev))),
                "share_exact_all": r4(np.mean(np.abs(dev) < 1e-6)),
                "share_within_0p5_all": r4(np.mean(np.abs(dev) <= 0.5 + 1e-9)),
                "n_scored_set": len(devs), "max_abs_dev_scored": r4(np.max(np.abs(devs))) if len(devs) else None,
                "share_exact_scored": r4(np.mean(np.abs(devs) < 1e-6)) if len(devs) else None}
    return res


# ---------------------------------------------------------------------------
# Supplement (not in the brief): integer rounding noise, affine vs flat
# multiplier, move vs level. Point estimates, mean over dev weeks.
# ---------------------------------------------------------------------------

def item6(rows):
    res = {}
    for pub in PUBS:
        res[pub] = {}
        for p in POS:
            acc = []
            for w in DEV_WEEKS:
                sel = [r for r in rows if r["pos"] == p and r["w"] == w]
                S = np.array([r[pub]["S"] for r in sel], float)
                F = np.array([r[pub]["F"] for r in sel], float)
                md = np.log(F / S) - np.log(F / S).mean()
                rvar = np.mean((1 / S ** 2 + 1 / F ** 2) / 12)   # var of log(F/S) from rounding both to integers
                b, a = np.polyfit(S, F, 1)
                acc.append([md.var(ddof=1), rvar, a, b, np.std(F - (a + b * S)), np.std(F - np.median(F / S) * S),
                            float(s4.spearman(md, np.log(S))[0])])
            o = np.mean(acc, 0)
            res[pub][p] = {"var_demeaned_move": r4(o[0]), "rounding_var": r4(o[1]), "rounding_share": r4(o[1] / o[0]),
                           "affine_intercept": r4(o[2]), "affine_slope": r4(o[3]), "affine_resid_sd": r4(o[4]),
                           "flat_multiplier_resid_sd": r4(o[5]), "spearman_move_vs_log_standard": r4(o[6])}
    return res


# ---------------------------------------------------------------------------

def to_md(J):
    L = ["# JEG-1611 diagnostic: publishers' own Standard-to-Full moves (dev weeks 5-7)", "",
         f"Sets: common = RB/WR/TE in the l_gate scored set with all four columns > 0. "
         f"Intervals: 95% percentile bootstrap, {B} resamples over players (player-clustered when pooled), "
         f"seed {SEED}. ROS actuals: 2026 weeks w..{J['ros_last_week']}.", ""]
    L += ["## 1. Spread of the de-meaned move m = log(F/S) (common set, pooled weeks)", "",
          "| Pub | Pos | n | SD m (de-meaned) | SD full-strength hist move | share = median (exact) | share within 1% |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for pub in PUBS:
        for p in POS + ("ALL",):
            d = J["item1"]["common"][pub]["pooled"][p]
            L.append(f"| {pub} | {p} | {d['n']} | {d['sd_demeaned_move']} | {d['sd_full_strength_expected_move_hist']}"
                     f" | {d['share_exact_median']} | {d['share_within_1pct_median']} |")
    L += ["", "## 2. CBS vs USA Today (common set)", "",
          "| Week | Pos | n | move Spearman | move Pearson | slope CBS on USAT | Full level Sp. | Std level Sp. |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for lab in [str(w) for w in DEV_WEEKS] + ["pooled"]:
        d = J["item2"][lab]
        for p in POS + ("ALL",):
            mv = d["move_cbs_vs_usatoday"][p]
            fl = d["full_level"].get(p, {}).get("spearman_mean_over_weeks")
            sl = d["standard_level"].get(p, {}).get("spearman_mean_over_weeks")
            L.append(f"| {lab} | {p} | {mv['n']} | {fmt(mv.get('spearman'))} | {fmt(mv.get('pearson'))} | "
                     f"{fmt(mv.get('ols_slope'))} | {fmt(fl) if fl else ''} | {fmt(sl) if sl else ''} |")
    L += ["", "## 3. De-meaned move vs reception evidence (common set, pooled weeks; history players only)", "",
          "| Pub | Pos | n | Sp. hist share | Sp. hist rec/g | Sp. ROS rec/g | slope on hist full-strength | "
          "slope on ROS full-strength | Pearson ROS full-strength |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for pub in PUBS:
        d = J["item3"]["common"][pub]["pooled"]
        for p in POS + ("ALL",):
            L.append(f"| {pub} | {p} | {d['a_hist_rec_share'][p]['n']} | {fmt(d['a_hist_rec_share'][p].get('spearman'))}"
                     f" | {fmt(d['b_hist_rec_per_game'][p].get('spearman'))} | {fmt(d['c_ros_rec_per_game'][p].get('spearman'))}"
                     f" | {fmt(d['slope_on_full_strength_move_hist'][p].get('ols_slope'))}"
                     f" | {fmt(d['slope_on_full_strength_move_ros'][p].get('ols_slope'))}"
                     f" | {fmt(d['slope_on_full_strength_move_ros'][p].get('pearson'))} |")
    for pub in PUBS:
        d = J["item3"]["common"][pub]["pooled"]
        L.append(f"\n{pub}: rows {d['n_rows']}, history fallback {d['n_fallback_hist']}, no ROS games {d['n_no_ros_games']}.")
    L += ["", "## 4. Reachable ceiling: within (mean RB/WR/TE Spearman, l_gate.metrics) on the common set", "",
          "| Pub | Dir | Predictor | slope | within pooled | gain vs unchanged pooled | gain wk5 / wk6 / wk7 |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for pub in PUBS:
        d = J["item4"][pub]
        for dr in ("S_to_F", "F_to_S"):
            for name, v in d[dr].items():
                sl = d["slopes_in_sample_pooled"].get(name, "")
                gw = " / ".join(f"{v[str(w)]['gain_vs_unchanged']['est']:+.4f}" for w in DEV_WEEKS)
                L.append(f"| {pub} | {dr} | {name} | {sl} | {fmt(v['pooled']['within'])} | "
                         f"{fmt(v['pooled']['gain_vs_unchanged'])} | {gw} |")
        L.append(f"| {pub} | S_to_F | unchanged, own set | | {fmt(d['unchanged_own_set_S_to_F']['pooled'])} | | |")
    L += ["", "## 5. Half = (Standard + Full) / 2", "",
          "| Pub | Week | n | max abs dev | share exact | share within 0.5 |", "| --- | --- | --- | --- | --- | --- |"]
    for pub in PUBS:
        for w in DEV_WEEKS:
            d = J["item5"][pub][str(w)]
            L.append(f"| {pub} | {w} | {d['n_all']} | {d['max_abs_dev_all']} | {d['share_exact_all']} | "
                     f"{d['share_within_0p5_all']} |")
    L += ["", "## Supplement: integer rounding and additive part (common set, mean of weekly values)", "",
          "| Pub | Pos | var m (de-meaned) | integer-rounding var | share | F = a + bS: a, b | resid SD affine / flat mult | "
          "Sp. move vs log S |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for pub in PUBS:
        for p in POS:
            d = J["supplement_noise"][pub][p]
            L.append(f"| {pub} | {p} | {d['var_demeaned_move']} | {d['rounding_var']} | {d['rounding_share']} | "
                     f"{d['affine_intercept']}, {d['affine_slope']} | {d['affine_resid_sd']} / {d['flat_multiplier_resid_sd']}"
                     f" | {d['spearman_move_vs_log_standard']} |")
    return "\n".join(L) + "\n"


def main():
    ctx, weeks, hist, ros, last = load()
    rng = np.random.default_rng(SEED)
    common = build_rows(ctx, weeks, hist, ros, "common")
    own = {p: build_rows(ctx, weeks, hist, ros, "own", p) for p in PUBS}
    J = {"ticket": "JEG-1611", "dev_weeks": list(DEV_WEEKS), "ros_last_week": last,
         "ros_weeks": {str(w): [w, last] for w in DEV_WEEKS},
         "n_rows": {"common": len(common), **{f"own_{p}": len(own[p]) for p in PUBS}},
         "item1": {"common": {p: item1(common, p) for p in PUBS}, "own": {p: item1(own[p], p) for p in PUBS}},
         "item2": item2(common, rng),
         "item3": {"common": {p: item3(common, p, rng) for p in PUBS}, "own": {p: item3(own[p], p, rng) for p in PUBS}},
         "item4": item4(common, rng, own),
         "item5": item5(ctx, weeks), "supplement_noise": item6(common)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "publisher_moves.json").write_text(json.dumps(J, indent=1, default=str))
    (OUT / "publisher_moves.md").write_text(to_md(J))
    print("rows", J["n_rows"], "ros_last_week", last)


if __name__ == "__main__":
    main()
