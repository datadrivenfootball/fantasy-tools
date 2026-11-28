"""v6 EXPLORATORY evidence on the 2026 chart weeks 5-10 (all already seen by v3-v5.1).

Nothing here is a pre-registered test or gate. Every number is descriptive, with intervals where
a resampling unit exists. Out: out/evidence.json (read by build_page.py and the design doc).

  E1 response size and direction against ESPN and Sleeper rescoring (v5's T4/T5 machinery),
     per kind, weeks 5-10 pooled and week 10 alone; plus the same with zero-value ties removed.
  E2 calibration on 2026 outcomes: catch shares of v6, the light pull, v5's pull, ESPN and
     Sleeper against realized shares in the following weeks (snapshot weeks 5-7, truth to week 10).
  E3 rank agreement with the projectors' own lists and with CBS Sports / USA Today, the metric
     against DDF Value (v5's T8 form plus absolute values).
  E4 robustness of the unwind: does the scoring change depend on the chart's cardinal points?
  E5 anchor sensitivity: the metric under the four anchor pairs.
  E6 coverage, fallbacks, zero-value counts, and QB.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v6  # noqa: E402
import tests5 as TS  # noqa: E402
import stats5 as st  # noqa: E402
import history5 as h5  # noqa: E402
import mix as mx  # noqa: E402

OUT = HERE / "out"
WEEKS = (5, 6, 7, 8, 9, 10)
POOL = ("RB", "WR", "TE")
LO, HI = "standard", "ppr"
N_BOOT, N_SHUFFLE = 1000, 500
SEED = 15976
ANCHOR_PAIRS = {"FC Full / FP Half (primary)": ("primary", "primary"), "FC Half / FP Half": ("fc_half", "primary"),
                "FC Full / FP Full": ("primary", "fp_full"), "FC Half / FP Full": ("fc_half", "fp_full")}


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (float, np.floating)):
        x = float(x)
        return None if math.isnan(x) else ("inf" if math.isinf(x) else round(x, 5))
    if isinstance(x, np.integer):
        return int(x)
    return x


# ---------------------------------------------------------------------------
# E1: response with zero-value ties removed
# ---------------------------------------------------------------------------

def moves_no_ties(W, ch, c, kind="v5"):
    """Like v5's moves_week, but players at 0 at Standard or Full under the method or the
    reference rebuild are dropped before percentiles (ties at 0 carry no order)."""
    keys = TS.common_set(W, ch, c)
    a_lo, a_hi = W.chart_list(ch, c, kind, LO), W.chart_list(ch, c, kind, HI)
    r_lo, r_hi = W.chart_list(ch, c, "ref", LO), W.chart_list(ch, c, "ref", HI)
    out, dropped = {}, {}
    for p in POOL:
        ks = TS.ppos(W.ctx, keys, p)
        kk = [k for k in ks if min(a_lo[k], a_hi[k], r_lo[k], r_hi[k]) > 0]
        dropped[p] = len(ks) - len(kk)
        if len(kk) >= 5:
            out[p] = (kk, st.moves(a_lo, a_hi, kk), st.moves(r_lo, r_hi, kk))
    return out, dropped


def response_summary(weeks, chains, kind, rng, no_ties=False):
    res = {}
    for c in v6.CHARTS:
        mvs, drops = [], []
        for W in weeks:
            cv = v6.as_primary(chains[W.w], kind)
            if no_ties:
                m, d = moves_no_ties(W, cv, c)
                drops.append(d)
            else:
                m = TS.moves_week(W, cv, c)
            mvs.append(m)
        cr = [TS.corr_sd(m) for m in mvs]
        ci_c, ci_r = TS.boot_moves(mvs, rng, N_BOOT)
        res[c] = {"corr": st.mean_or_none([TS.pooled(x[0]) for x in cr]), "corr_ci": ci_c,
                  "ratio": st.mean_or_none([TS.pooled(x[1]) for x in cr]), "ratio_ci": ci_r,
                  "ratio_pos": {p: st.mean_or_none([x[1].get(p) for x in cr]) for p in POOL},
                  "corr_pos": {p: st.mean_or_none([x[0].get(p) for x in cr]) for p in POOL},
                  "ratio_pos_ci": {}, "dropped_zero": drops or None}
        for p in POOL:
            sub = [{p: m[p]} for m in mvs if p in m]
            if sub:
                _cc, cr_p = TS.boot_moves(sub, rng, N_BOOT)
                res[c]["ratio_pos_ci"][p] = cr_p
    return res


# ---------------------------------------------------------------------------
# E2: calibration on 2026 outcomes
# ---------------------------------------------------------------------------

def realized(hist, k, w0, w1, s0="half_ppr"):
    lines = [ln for (s, w), ln in hist.get(k, []) if s == 2026 and w0 <= w <= w1 and v6.is_game(ln)]
    if len(lines) < 2:
        return None
    pts = sum(mx.F(ln, s0) for ln in lines)
    rec = sum(ln["rec"] for ln in lines)
    return (rec / pts, pts) if pts > 0 else None


def wls(x, y, w):
    x, y, w = (np.asarray(v, float) for v in (x, y, w))
    mx_, my = (w * x).sum() / w.sum(), (w * y).sum() / w.sum()
    sxx = (w * (x - mx_) ** 2).sum()
    return None if sxx <= 0 else float((w * (x - mx_) * (y - my)).sum() / sxx)


def calibration(Ws, hist, chains, truth_to=10):
    """Snapshot weeks 5-7, players invertible in FantasyPros (anchor Half), truth weeks w..10."""
    rows = []
    for W in Ws:
        if W.w > 7:
            continue
        ch = chains[W.w]
        for k in ch["P"][("fantasypros", "v5")]:
            p = W.ctx["pos_of"].get(k)
            if p not in POOL:
                continue
            tr = realized(hist, k, W.w, truth_to)
            e, s = W.refs.espn_mix(k, "half_ppr"), W.refs.sleeper_mix(k, "half_ppr")
            if tr is None or e is None or s is None:
                continue
            rows.append({"k": k, "pos": p, "w": W.w, "q_true": tr[0], "wt": tr[1],
                         "v6": ch["P"][("fantasypros", "v5")][k][1]["rec"],
                         "light8": ch["P"][("fantasypros", "light8")][k][1]["rec"],
                         "v5_heavy": ch["P"][("fantasypros", "heavy")][k][1]["rec"],
                         "espn": e["rec"], "sleeper": s["rec"]})
    rng = np.random.default_rng(SEED)
    out = {}
    for p in POOL:
        rs = [r for r in rows if r["pos"] == p]
        pids = np.asarray([r["k"] for r in rs])
        uniq, inv = np.unique(pids, return_inverse=True)
        members = [np.flatnonzero(inv == j) for j in range(len(uniq))]
        blk = {"n_rows": len(rs), "n_players": len(uniq)}
        for name in ("v6", "light8", "v5_heavy", "espn", "sleeper"):
            x = [r[name] for r in rs]
            y = [r["q_true"] for r in rs]
            wt = [r["wt"] for r in rs]
            sl = wls(x, y, wt)
            draws = []
            for _ in range(N_BOOT):
                idx = np.concatenate([members[j] for j in rng.integers(0, len(uniq), len(uniq))])
                d = wls(np.asarray(x)[idx], np.asarray(y)[idx], np.asarray(wt)[idx])
                if d is not None:
                    draws.append(d)
            err = float(np.average((np.asarray(x) - np.asarray(y)) ** 2, weights=wt))
            blk[name] = {"slope": sl, "ci": (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))),
                         "sd_pred": float(np.std(x)), "wmse": err}
        blk["sd_true"] = float(np.std([r["q_true"] for r in rs]))
        out[p] = blk
    return out


# ---------------------------------------------------------------------------
# E3: rank agreement
# ---------------------------------------------------------------------------

def spearman_within(a, b, keys, pos_of, positions):
    vals = {}
    for p in positions:
        ks = [k for k in keys if pos_of.get(k) == p and a.get(k) is not None and b.get(k) is not None]
        if len(ks) >= 8:
            vals[p] = st.spearman([a[k] for k in ks], [b[k] for k in ks])
    return vals


def agreement(Ws, chains):
    out = {}
    for s in mx.SCORINGS:
        rows = []
        for W in Ws:
            ch = chains[W.w]
            new, cur = W.metric(ch, s)
            ref = TS.ref_adjusted(W, ch, s)
            pub = TS.mean_charts(ch, s)
            keys = [k for k, v in cur.items() if v]
            pos_of = W.ctx["pos_of"]
            top = {p: set(sorted((k for k in keys if pos_of.get(k) == p), key=lambda k: -cur[k])[:v6.v5.TOP_N.get(p, 24)])
                   for p in v6.POSITIONS}
            topk = [k for p in v6.POSITIONS for k in top[p]]
            rows.append({"new_vs_proj": spearman_within(new, ref, topk, pos_of, v6.POSITIONS),
                         "ddf_vs_proj": spearman_within(cur, ref, topk, pos_of, v6.POSITIONS),
                         "new_vs_pub": spearman_within(new, pub, topk, pos_of, v6.POSITIONS),
                         "ddf_vs_pub": spearman_within(cur, pub, topk, pos_of, v6.POSITIONS),
                         "new_vs_ddf": spearman_within(new, cur, topk, pos_of, v6.POSITIONS),
                         "median_abs_pct_change": {p: statistics.median(abs(new[k] - cur[k]) / cur[k] for k in top[p])
                                                   for p in v6.POSITIONS if top[p]}})
        agg = {}
        for key in rows[0]:
            agg[key] = {p: st.mean_or_none([r[key].get(p) for r in rows]) for p in v6.POSITIONS}
        out[s] = agg
    return out


# ---------------------------------------------------------------------------
# E4: robustness of the unwind
# ---------------------------------------------------------------------------

def robustness(Ws, chains):
    """Per chart and position: Spearman and SD ratio of the Standard-to-Full value change
    (A6(Full) - A6(Std)) between chart points and the two variants that use less of the chart."""
    out = {}
    for c in v6.CHARTS:
        per = {}
        for alt in ("rankP", "projP", "light8", "calrule"):
            vals = {p: {"rho": [], "sd_ratio": []} for p in POOL}
            for W in Ws:
                ch = chains[W.w]
                a_lo, a_hi = W.av5(ch, c, "v5", LO), W.av5(ch, c, "v5", HI)
                b_lo, b_hi = W.av5(ch, c, alt, LO), W.av5(ch, c, alt, HI)
                for p in POOL:
                    ks = [k for k in a_lo if W.ctx["pos_of"].get(k) == p and k in b_lo]
                    if len(ks) < 8:
                        continue
                    da = [a_hi[k] - a_lo[k] for k in ks]
                    db = [b_hi[k] - b_lo[k] for k in ks]
                    vals[p]["rho"].append(st.spearman(da, db))
                    sa, sb = st.sd(da), st.sd(db)
                    vals[p]["sd_ratio"].append(sb / sa if sa else None)
            per[alt] = {p: {kk: st.mean_or_none(v) for kk, v in d.items()} for p, d in vals.items()}
        out[c] = per
    return out


# ---------------------------------------------------------------------------
# E5: anchors
# ---------------------------------------------------------------------------

def anchor_lists(W, chains_by_anchor):
    """{pair: {s: (metric, ddf)}} for the four anchor pairs (FC from one chain, FP from another)."""
    out = {}
    base = chains_by_anchor["primary"]
    for name, (fa, pa) in ANCHOR_PAIRS.items():
        cf, cp = chains_by_anchor[fa], chains_by_anchor[pa]
        out[name] = {}
        for s in mx.SCORINGS:
            lists = {"fantasycalc": W.av5(cf, "fantasycalc", "v5", s), "fantasypros": W.av5(cp, "fantasypros", "v5", s)}
            out[name][s] = W.metric(base, s, lists=lists)
    return out


def anchor_summary(Ws, anchors):
    out = {}
    for s in mx.SCORINGS:
        widths = {p: [] for p in v6.POSITIONS}
        for W in Ws:
            al = anchors[W.w]
            prim, cur = al["FC Full / FP Half (primary)"][s]
            pos_of = W.ctx["pos_of"]
            for p in v6.POSITIONS:
                top = sorted((k for k, v in cur.items() if v and pos_of.get(k) == p), key=lambda k: -cur[k])[:v6.v5.TOP_N.get(p, 24)]
                for k in top:
                    vs = [al[n][s][0].get(k) for n in ANCHOR_PAIRS]
                    vs = [v for v in vs if v is not None]
                    if vs and prim.get(k):
                        widths[p].append((max(vs) - min(vs)) / prim[k])
        out[s] = {p: {"median_rel_width": statistics.median(v) if v else None,
                      "p90_rel_width": float(np.percentile(v, 90)) if v else None} for p, v in widths.items()}
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    ctx, Ws = v6.load(WEEKS)
    hist = Ws[0].hist
    chains = {W.w: W.chain() for W in Ws}
    print(f"chains {time.time() - t0:.0f}s")
    anchors_ch = {W.w: {"primary": chains[W.w], "fc_half": W.chain(anchor="fc_half", kinds=("v5",)),
                        "fp_full": W.chain(anchor="fp_full", kinds=("v5",))} for W in Ws}
    print(f"anchor chains {time.time() - t0:.0f}s")
    rng = random.Random(SEED)
    ev = {"label": "EXPLORATORY: 2026 weeks 5-10 were all seen by v3-v5.1; nothing here is pre-registered",
          "weeks": WEEKS, "n_boot": N_BOOT, "n_shuffle": N_SHUFFLE, "params": v6.load_params()}
    # E1 via v5's battery (T2-T8 machinery) for the primary and the comparison kinds
    ev["battery"] = {}
    for kind in ("v5", "light8", "heavy", "calrule"):
        cv = {w: v6.as_primary(ch, kind) for w, ch in chains.items()}
        ev["battery"][kind] = TS.battery(Ws, cv, N_BOOT, N_SHUFFLE)
        print(f"battery {kind} {time.time() - t0:.0f}s")
    ev["battery_w10"] = TS.battery([W for W in Ws if W.w == 10], chains, N_BOOT, N_SHUFFLE)
    ev["response_no_ties"] = {kind: response_summary(Ws, chains, kind, rng, no_ties=True)
                              for kind in ("v5", "light8", "heavy", "calrule")}
    ev["response"] = {kind: response_summary(Ws, chains, kind, rng) for kind in ("v5", "light8", "heavy", "calrule")}
    print(f"response {time.time() - t0:.0f}s")
    ev["calibration_2026"] = calibration(Ws, hist, chains)
    print(f"calibration {time.time() - t0:.0f}s")
    ev["agreement"] = agreement(Ws, chains)
    ev["robustness"] = robustness(Ws, chains)
    anchors = {W.w: anchor_lists(W, anchors_ch[W.w]) for W in Ws}
    ev["anchors"] = anchor_summary(Ws, anchors)
    # E6 coverage and zero counts (per week, per chart, per position)
    cov = {}
    for W in Ws:
        ch = chains[W.w]
        cov[W.w] = {}
        for c in v6.CHARTS:
            lab = ch["labels"][(c, "v5")]
            u = ch["U"][c]
            d = {"labels": {}, "zero_std_v6": {}, "zero_std_unchanged": {}}
            for kk, r in u.records.items():
                d["labels"][r["label"]] = d["labels"].get(r["label"], 0) + 1
            lo, un = W.av5(ch, c, "v5", LO), W.unchanged(ch, c, LO)
            for p in v6.POSITIONS:
                ks = [k for k in lab if W.ctx["pos_of"].get(k) == p]
                d.setdefault("fallback", {})[p] = sum(1 for k in ks if lab[k] != "own")
                d.setdefault("invertible", {})[p] = len(ks)
                d["zero_std_v6"][p] = sum(1 for k in ks if lo[k] == 0)
                d["zero_std_unchanged"][p] = sum(1 for k in ks if (un.get(k) or 0) == 0)
            cov[W.w][c] = d
    ev["coverage"] = cov
    ev["seconds"] = round(time.time() - t0, 1)
    import prior
    ev["prior_tree_dirty"] = prior.dirty()
    (OUT / "evidence.json").write_text(json.dumps(jsonable(ev), indent=1))
    print(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
