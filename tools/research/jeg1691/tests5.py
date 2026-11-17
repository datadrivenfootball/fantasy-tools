"""JEG-1691 v5: Tier 1 chart tests T2-T8 and the descriptive G2, over a list of Week5.

Spec: docs/research/jeg1691/preregistration.md 3.2-3.3 (binding). Statistics pool RB, WR,
TE with equal weight, then average the weeks. Intervals: paired player bootstrap within
(week, position), 2,000 draws, seed 16911. Shuffle control: 1,000 within-position
permutations of the mixes, priced through each pseudo-source's own ppg -> Adjusted map
from the primary run (amendment 5), seed 16911.
"""
from __future__ import annotations

import math
import random
import statistics

import mix as mx
import stats5 as st
import v5

uw = v5.uw
POOL = v5.POOL
LO, HI = "standard", "ppr"
T5_BAND = (2.0 / 3.0, 1.5)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def ppos(ctx, keys, p):
    return [k for k in keys if ctx["pos_of"].get(k) == p]


def pooled(per_pos: dict):
    return st.mean_or_none([per_pos.get(p) for p in POOL])


def fwd(pairs, x):
    return uw.forward(uw.build_map(pairs), x)


# ---------------------------------------------------------------------------
# T2 exactness
# ---------------------------------------------------------------------------

def t2(W, ch):
    ctx = W.ctx
    out = {"identity": 0.0, "ddf_repro": 0.0, "espn_twin": 0.0, "espn_scoring": None}
    for c in ch["U"]:
        u = ch["U"][c]
        a = W.av5(ch, c, "v5", u.s0)
        out["identity"] = max(out["identity"], max((abs(a[k] - u.records[k]["A"]) for k in a), default=0.0))
    for s in v5.SCORINGS:
        res = ch["runs"][s]
        dd = v5.ddf_from_rows(res, v5.chart_keys(ctx, res, s))
        cur = W.wk.current(s, ch["drop"])["ddf"]
        out["ddf_repro"] = max(out["ddf_repro"], max(abs((dd[i] or 0.0) - (cur.get(i) or 0.0)) for i in dd))
        if ("espn_twin", s) in ch["ps_adj"]:
            e = ch["ps_adj"][("espn_twin", s)]
            rows = res["rows"]
            out["espn_twin"] = max(out["espn_twin"], max(abs(e[i] - float(rows[i]["adjusted"]["espn"]))
                                                         for i in e if rows[i]["adjusted"].get("espn") is not None))
    # scoring parity: ESPN's ppg(s) / ppg(half) equals F(line, s) / F(line, half) (bake rounds ppg)
    nat = v5.R3.current_natives(W.wk.natives, "half_ppr")["espn"]
    worst = 0.0
    for s in ("standard", "ppr"):
        ns = v5.R3.current_natives(W.wk.natives, s)["espn"]
        for k, ln in W.refs.espn.items():
            if k in nat and k in ns and nat[k] > 1.0 and mx.F(ln, "half_ppr") > 0:
                pred = nat[k] * mx.F(ln, s) / mx.F(ln, "half_ppr")
                worst = max(worst, abs(pred - ns[k]))
    out["espn_scoring"] = worst
    out["pass"] = (out["identity"] == 0.0 and out["ddf_repro"] <= 1e-9 and out["espn_twin"] == 0.0
                   and out["espn_scoring"] <= 1e-4)
    return out


# ---------------------------------------------------------------------------
# per chart-week pieces
# ---------------------------------------------------------------------------

def common_set(W, ch, c):
    """Invertible RB/WR/TE with an own-or-fallback v5 mix and both references."""
    u = ch["U"][c]
    return [k for k in ch["P"][(c, "v5")] if W.ctx["pos_of"].get(k) in POOL
            and W.refs.ref_mix(k, u.s0) is not None]


def t3_week(W, ch, c, rng, n_shuffle):
    u = ch["U"][c]
    keys = common_set(W, ch, c)
    per, per_src, shuf = {}, {}, {p: [] for p in POOL}
    for p in POOL:
        ks = ppos(W.ctx, keys, p)
        rows = []
        for k in ks:
            qv = ch["P"][(c, "v5")][k][1]["rec"]
            qe = W.refs.espn_mix(k, u.s0)["rec"]
            qs = W.refs.sleeper_mix(k, u.s0)["rec"]
            if qv > 0 and qe > 0 and qs > 0:
                rows.append((qv, qe, qs))
        if len(rows) < 5:
            continue
        per[p] = statistics.median(abs(math.log(qv / math.sqrt(qe * qs))) for qv, qe, qs in rows)
        per_src[p] = statistics.median(abs(math.log(qe / qs)) for _qv, qe, qs in rows)
        qvs = [r[0] for r in rows]
        for _ in range(n_shuffle):
            perm = qvs[:]
            rng.shuffle(perm)
            shuf[p].append(statistics.median(abs(math.log(q / math.sqrt(qe * qs)))
                                             for q, (_a, qe, qs) in zip(perm, rows)))
    return {"D_v5": pooled(per), "D_src": pooled(per_src), "per_position": per,
            "shuffle": [pooled({p: shuf[p][j] for p in POOL if shuf[p]}) for j in range(n_shuffle)]}


def moves_week(W, ch, c, kind="v5"):
    """Percentile moves Standard -> Full of v5 and of the reference-mix rebuild, per position."""
    keys = common_set(W, ch, c)
    a_lo, a_hi = W.chart_list(ch, c, kind, LO), W.chart_list(ch, c, kind, HI)
    r_lo, r_hi = W.chart_list(ch, c, "ref", LO), W.chart_list(ch, c, "ref", HI)
    out = {}
    for p in POOL:
        ks = ppos(W.ctx, keys, p)
        if len(ks) < 5:
            continue
        out[p] = (ks, st.moves(a_lo, a_hi, ks), st.moves(r_lo, r_hi, ks))
    return out


def shuffle_moves(W, ch, c, rng, n):
    """Placebo: permute the v5 mixes within position, price through the primary run's maps."""
    u = ch["U"][c]
    keys = common_set(W, ch, c)
    name = f"ps|{c}|v5"
    maps = {s: uw.build_map(ch["ps_maps"][(name, s)]) for s in v5.SCORINGS}
    r_lo, r_hi = W.chart_list(ch, c, "ref", LO), W.chart_list(ch, c, "ref", HI)
    base0 = {k: uw.forward(maps[u.s0], ch["P"][(c, "v5")][k][0]) for k in keys}
    out = []
    by = {p: ppos(W.ctx, keys, p) for p in POOL}
    for _ in range(n):
        per = {}
        for p, ks in by.items():
            if len(ks) < 5:
                continue
            mixes = [ch["P"][(c, "v5")][k][1] for k in ks]
            rng.shuffle(mixes)
            lo, hi = {}, {}
            for k, m in zip(ks, mixes):
                P0 = ch["P"][(c, "v5")][k][0]
                A = u.records[k]["A"]
                for s, dst in ((LO, lo), (HI, hi)):
                    dst[k] = A if s == u.s0 else max(0.0, A + uw.forward(maps[s], mx.points_at(P0, m, s, u.s0)) - base0[k])
            mv = st.moves(lo, hi, ks)
            rv = st.moves(r_lo, r_hi, ks)
            per[p] = st.spearman([mv[k] for k in ks], [rv[k] for k in ks])
        out.append(pooled(per))
    return out


def corr_sd(mvs: dict):
    corr, ratio = {}, {}
    for p, (ks, a, r) in mvs.items():
        corr[p] = st.spearman([a[k] for k in ks], [r[k] for k in ks])
        sa, sr = st.sd([a[k] for k in ks]), st.sd([r[k] for k in ks])
        ratio[p] = sa / sr if sa is not None and sr else None
    return corr, ratio


def boot_moves(weeks_mvs: list, rng, n):
    draws_c, draws_r = [], []
    for _ in range(n):
        cs, rs = [], []
        for mvs in weeks_mvs:
            cc, rr = {}, {}
            for p, (ks, a, r) in mvs.items():
                pick = [ks[rng.randrange(len(ks))] for _ in ks]
                cc[p] = st.spearman([a[k] for k in pick], [r[k] for k in pick])
                sa, sr = st.sd([a[k] for k in pick]), st.sd([r[k] for k in pick])
                rr[p] = sa / sr if sa is not None and sr else None
            cs.append(pooled(cc))
            rs.append(pooled(rr))
        draws_c.append(st.mean_or_none(cs))
        draws_r.append(st.mean_or_none(rs))
    return st.ci(draws_c), st.ci(draws_r)


def levels(vals: dict, pos_of) -> dict:
    tot = {}
    for p, n in v5.TOP_N.items():
        xs = sorted((v for k, v in vals.items() if pos_of.get(k) == p and v is not None), reverse=True)[:n]
        tot[p] = sum(xs)
    return tot


def level_moves(lo: dict, hi: dict, pos_of) -> dict:
    a, b = levels(lo, pos_of), levels(hi, pos_of)
    out = {}
    for p in ("WR", "TE"):
        if a["RB"] > 0 and b["RB"] > 0 and a[p] > 0 and b[p] > 0:
            out[f"{p}/RB"] = math.log((b[p] / b["RB"]) / (a[p] / a["RB"]))
    return out


def ref_adjusted(W, ch, s):
    rows = ch["runs"][s]["rows"]
    e = {i: float(r["adjusted"]["espn"]) for i, r in rows.items() if r["adjusted"].get("espn") is not None}
    sl = ch["ps_adj"][("sleeper_own", s)]
    return {k: 0.5 * (e[k] + sl[k]) for k in e if k in sl and e[k] > 0 and sl[k] > 0}


def rho_diff_week(ctx, a: dict, b: dict, ref: dict, keys):
    """Per position: (keys, a, b, ref) for the paired no-harm statistic."""
    out = {}
    for p in POOL:
        ks = [k for k in keys if ctx["pos_of"].get(k) == p and k in a and k in b and k in ref]
        if len(ks) >= 5:
            out[p] = ks
    return out


def nh_stat(pieces: list, pick=None):
    vals = []
    for per, a, b, ref in pieces:
        dd = {}
        for p, ks in per.items():
            kk = ks if pick is None else pick[id(per)][p]
            ra = st.spearman([a[k] for k in kk], [ref[k] for k in kk])
            rb = st.spearman([b[k] for k in kk], [ref[k] for k in kk])
            dd[p] = None if ra is None or rb is None else ra - rb
        vals.append(pooled(dd))
    return st.mean_or_none(vals)


def nh_boot(pieces, rng, n):
    draws = []
    for _ in range(n):
        pick = {id(per): {p: [ks[rng.randrange(len(ks))] for _ in ks] for p, ks in per.items()}
                for per, _a, _b, _r in pieces}
        draws.append(nh_stat(pieces, pick))
    return st.ci(draws)


# ---------------------------------------------------------------------------
# the battery
# ---------------------------------------------------------------------------

def battery(weeks: list, chains: dict, n_boot=st.N_BOOT, n_shuffle=st.N_SHUFFLE, widening=None):
    """weeks: [Week5]; chains: {w: chain dict}. Returns every Tier 1 statistic and G2."""
    rng = random.Random(st.SEED)
    ctx = weeks[0].ctx
    out = {"weeks": [W.w for W in weeks], "T2": {}, "T3": {}, "T4": {}, "T5": {}, "T6": {}, "T7": {},
           "T8": {}, "G2": {}, "coverage": {}}
    for W in weeks:
        out["T2"][W.w] = t2(W, chains[W.w])
        ch = chains[W.w]
        out["coverage"][W.w] = {c: {"invertible": len(ch["P"][(c, "v5")]),
                                    "fallback": sum(1 for v in ch["labels"][(c, "v5")].values() if v != "own"),
                                    "common_set": len(common_set(W, ch, c))} for c in ch["U"]}
        out["coverage"][W.w]["refs"] = {"espn": W.refs.espn_meta, "espn_lines": len(W.refs.espn),
                                        "sleeper": W.refs.sleeper_source, "sleeper_players": len(W.refs.sleeper),
                                        "captures": len(W.refs.captures)}
    for c in v5.CHARTS5:
        Ws = [W for W in weeks if c in chains[W.w]["U"]]
        if not Ws:
            continue
        # T3
        t3s = [t3_week(W, chains[W.w], c, rng, n_shuffle) for W in Ws]
        dv = st.mean_or_none([x["D_v5"] for x in t3s])
        ds = st.mean_or_none([x["D_src"] for x in t3s])
        sh = [st.mean_or_none([x["shuffle"][j] for x in t3s]) for j in range(n_shuffle)]
        p5 = sorted(v for v in sh if v is not None)[int(0.05 * n_shuffle)] if n_shuffle else None
        lab = ("PASS" if dv is not None and ds is not None and dv <= ds and p5 is not None and dv < p5 else
               "FAIL" if dv is not None and ds is not None and dv > 2 * ds else "PARTIAL")
        out["T3"][c] = {"D_v5": dv, "D_src": ds, "shuffle_p5": p5, "label": lab,
                        "per_week": [{p: x["per_position"].get(p) for p in POOL} for x in t3s]}
        # T4 / T5
        mvs = [moves_week(W, chains[W.w], c) for W in Ws]
        cr = [corr_sd(m) for m in mvs]
        corr = st.mean_or_none([pooled(x[0]) for x in cr])
        ratio = st.mean_or_none([pooled(x[1]) for x in cr])
        ci_c, ci_r = boot_moves(mvs, rng, n_boot)
        plac = [st.mean_or_none(v) for v in zip(*[shuffle_moves(W, chains[W.w], c, rng, n_shuffle) for W in Ws])]
        p95 = sorted(v for v in plac if v is not None)[int(0.95 * len(plac))] if plac else None
        out["T4"][c] = {"corr": corr, "ci95": ci_c, "shuffle_p95": p95,
                        "pass": bool(ci_c[0] is not None and ci_c[0] > 0 and p95 is not None and corr > p95),
                        "per_position": [{p: x[0].get(p) for p in POOL} for x in cr]}
        out["T5"][c] = {"sd_ratio": ratio, "ci95": ci_r,
                        "pass": bool(ratio is not None and T5_BAND[0] <= ratio <= T5_BAND[1]),
                        "per_position": [{p: x[1].get(p) for p in POOL} for x in cr]}
        # T6
        lv = {"v5": [], "espn": [], "sleeper": []}
        for W in Ws:
            ch = chains[W.w]
            lv["v5"].append(level_moves(W.chart_list(ch, c, "v5", LO), W.chart_list(ch, c, "v5", HI), ctx["pos_of"]))
            rows_lo, rows_hi = ch["runs"][LO]["rows"], ch["runs"][HI]["rows"]
            e_lo = {i: float(r["adjusted"]["espn"]) for i, r in rows_lo.items() if r["adjusted"].get("espn") is not None}
            e_hi = {i: float(r["adjusted"]["espn"]) for i, r in rows_hi.items() if r["adjusted"].get("espn") is not None}
            lv["espn"].append(level_moves(e_lo, e_hi, ctx["pos_of"]))
            lv["sleeper"].append(level_moves(ch["ps_adj"][("sleeper_own", LO)], ch["ps_adj"][("sleeper_own", HI)],
                                             ctx["pos_of"]))
        t6 = {}
        for r in ("WR/RB", "TE/RB"):
            m = {k: st.mean_or_none([x.get(r) for x in v]) for k, v in lv.items()}
            wd = (widening or {}).get(r)
            env = None
            if m["espn"] is not None and m["sleeper"] is not None and wd is not None:
                env = (min(m["espn"], m["sleeper"]) - wd, max(m["espn"], m["sleeper"]) + wd)
            t6[r] = {"v5": m["v5"], "espn": m["espn"], "sleeper": m["sleeper"], "widening": wd, "envelope": env,
                     "pass": None if env is None or m["v5"] is None else env[0] <= m["v5"] <= env[1],
                     "overshoot": (m["v5"] is not None and m["espn"] is not None and m["sleeper"] is not None and
                                   ((m["v5"] > max(m["espn"], m["sleeper"]) and min(m["espn"], m["sleeper"]) > 0) or
                                    (m["v5"] < min(m["espn"], m["sleeper"]) and max(m["espn"], m["sleeper"]) < 0))),
                     "espn_per_week": [x.get(r) for x in lv["espn"]]}
        out["T6"][c] = t6
        # G2 (descriptive): v5 moves vs the mean of CBS Sports and USA Today
        g = []
        for W in Ws:
            ch = chains[W.w]
            keys = [k for k in ch["P"][(c, "v5")] if ctx["pos_of"].get(k) in POOL]
            ref_lo = mean_charts(ch, LO)
            ref_hi = mean_charts(ch, HI)
            a_lo, a_hi = W.chart_list(ch, c, "v5", LO), W.chart_list(ch, c, "v5", HI)
            per_c, per_r = {}, {}
            for p in POOL:
                ks = [k for k in keys if ctx["pos_of"][k] == p and k in ref_lo and k in ref_hi]
                if len(ks) < 5:
                    continue
                mv, rv = st.moves(a_lo, a_hi, ks), st.moves(ref_lo, ref_hi, ks)
                per_c[p] = st.spearman([mv[k] for k in ks], [rv[k] for k in ks])
                sa, sr = st.sd([mv[k] for k in ks]), st.sd([rv[k] for k in ks])
                per_r[p] = sa / sr if sa is not None and sr else None
            g.append((pooled(per_c), pooled(per_r)))
        out["G2"][c] = {"corr": st.mean_or_none([x[0] for x in g]), "sd_ratio": st.mean_or_none([x[1] for x in g])}
    # T7: no harm vs unchanged
    for c, s in v5.T7_CELLS:
        pieces = []
        for W in weeks:
            ch = chains[W.w]
            if c not in ch["U"]:
                continue
            ref = ref_adjusted(W, ch, s)
            a, b = W.chart_list(ch, c, "v5", s), W.unchanged(ch, c, s)
            keys = [k for k in ch["P"][(c, "v5")]]
            pieces.append((rho_diff_week(ctx, a, b, ref, keys), a, b, ref))
        if pieces:
            pt, ci_ = nh_stat(pieces), nh_boot(pieces, rng, n_boot)
            out["T7"][f"{c}|{s}"] = {"diff": pt, "ci95": ci_, "label": st.no_harm_label(ci_)}
    # T8: no harm vs current DDF Value
    for s in v5.SCORINGS:
        pieces = []
        for W in weeks:
            ch = chains[W.w]
            res = ch["runs"][s]
            keys_c = v5.chart_keys(ctx, res, s)
            rep = {c: W.av5(ch, c, "v5", s) for c in ch["U"]}
            new, cur = v5.ddf_from_rows(res, keys_c, rep), v5.ddf_from_rows(res, keys_c)
            ref = ref_adjusted(W, ch, s)
            keys = [k for k, v in cur.items() if v]
            pieces.append((rho_diff_week(ctx, new, cur, ref, keys), new, cur, ref))
        pt, ci_ = nh_stat(pieces), nh_boot(pieces, rng, n_boot)
        out["T8"][s] = {"diff": pt, "ci95": ci_, "label": st.no_harm_label(ci_)}
    return out


def mean_charts(ch, s):
    rows = ch["runs"][s]["rows"]
    out = {}
    for i, r in rows.items():
        vs = [r["adjusted"].get(c) for c in v5.REFERENCE_CHARTS]
        if all(v is not None for v in vs):
            out[i] = sum(float(v) for v in vs) / len(vs)
    return out


def verdict(b: dict, t1: dict | None) -> dict:
    """Tier 1 verdicts and outcome A / B / C (preregistration section 5)."""
    v = {"T1": None if t1 is None else t1["verdict"],
         "T2": all(x["pass"] for x in b["T2"].values()),
         "T3": {c: x["label"] for c, x in b["T3"].items()},
         "T4": all(x["pass"] for x in b["T4"].values()),
         "T5": all(x["pass"] for x in b["T5"].values()),
         "T6": all(r["pass"] for x in b["T6"].values() for r in x.values()),
         "harm": any(x["label"] == "HARM" for x in list(b["T7"].values()) + list(b["T8"].values()))}
    return v
