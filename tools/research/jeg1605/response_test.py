"""JEG-1605 / JEG-1597: chart-to-chart scoring-response test.

Do the adjusted scoring-blind charts (FantasyCalc, FantasyPros) rank players
more like the charts that respond to scoring (CBS Sports, USA Today)?

Spec: docs/research/jeg1605/response-preregistration.md (committed before
this file). Research only; reads saved snapshots, no live requests.

Run:  /usr/bin/python3 tools/research/jeg1605/response_test.py
Out:  tools/research/jeg1605/out/response_test.json
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import l_gate as lg  # noqa: E402  (loaders: world, week inputs, allocation)

rt, rb, dc, s4, vr = lg.rt, lg.rb, lg.dc, lg.s4, lg.vr
OUT = HERE / "out"
ESPN_GAMES = HERE / "cache" / "espn_nonzero_games.json"
V1_CSV = rb.OUT / "rescaled_natives.csv"

WEEKS = (5, 6, 7, 8, 9)
GAMES_WEEKS = (7, 8, 9)
POS = ("RB", "WR", "TE")
N_SET = {"RB": 36, "WR": 36, "TE": 18}
K_LEVEL = {"RB": 24, "WR": 24, "TE": 10}
TARGETS = ("standard", "ppr")
REFS = ("mean", "cbs", "usatoday")
SUBJECTS = {"fantasycalc": "ppr", "fantasypros": "half_ppr"}      # base column
ANCHOR = {"fantasycalc": "ppr", "fantasypros": "half_ppr"}
N_BOOT, SEED_BOOT = 2000, 16052
N_PERM, SEED_PERM = 1000, 16053
V1_VARIANTS = {"v1": (1.0, "position_scaled"), "v1_l05": (0.5, "position_scaled"), "v1_literal": (1.0, "same_fit")}
PRIMARY = ("v1", "v2")


def r4(x):
    return None if x is None or not math.isfinite(float(x)) else round(float(x), 4)


# ---------------------------------------------------------------------------
# Inputs: games rules, leave-one-out
# ---------------------------------------------------------------------------

def espn_games():
    doc = json.loads(ESPN_GAMES.read_text(encoding="utf-8"))
    return {int(w): {int(k): float(v["nz"]) for k, v in d.items()} for w, d in doc["weeks"].items()}


def games_for(ctx, w, rule, loo, espn):
    """{key: expected games}. current: CBS gp, else schedule x (1 - miss).
    G1: CBS gp, else ESPN non-zero weeks, else schedule. G2: ESPN, else current.
    loo drops CBS gp."""
    out = {}
    ew = espn.get(w, {})
    for k, p in ctx["pos_of"].items():
        if p not in rt.POSITIONS:
            continue
        gp = None if loo else ctx["gp"].get(w, {}).get(k)
        bye = ctx["byes"].get(ctx["team"].get(k))
        cur, _ = dc.expected_games(p, w, bye, gp)
        has_gp = gp is not None and gp > 0
        if rule == "current":
            out[k] = cur
        elif rule == "G1":
            out[k] = cur if has_gp else ew.get(k, cur)
        elif rule == "G2":
            out[k] = ew.get(k, cur)
        else:
            raise ValueError(rule)
    return out


def allocation_loo(ctx, natives, s, drop):
    pos_of = ctx["pos_of"]
    sources = {k: vr.SourceInput(k, vr.FAMILY[k], {i: float(x) for i, x in natives[k][s].items() if i in pos_of})
               for k in vr.SOURCES}
    inc = [k for k in sources if k in ctx["included"][s] and k not in drop]
    m = vr.mean_ppg(sources, inc)
    order = {p: sorted((i for i in m if pos_of.get(i) == p), key=lambda i: (-m[i], i)) for p in rt.POSITIONS}
    a = vr.allocate(ctx["live"][s].league, order, m, flex_bench_seats=True)
    return {p: int(a[p].get("replacement", a[p]["rostered"])) for p in rt.POSITIONS}


def week_world(ctx, w, rule="current", loo=False, espn=None, base_week=None):
    natives, lines = rb.week_inputs(ctx["inp"], ctx["hist"], w)
    if loo:
        lines = {k: {s: t for s, t in d.items() if s != "cbsros"} for k, d in lines.items()}
        lines = {k: d for k, d in lines.items() if d}
        alloc = {s: allocation_loo(ctx, natives, s, {"cbsros"}) for s in lg.SCORINGS}
    else:
        alloc = {s: lg.allocation(ctx, natives, s) for s in lg.SCORINGS}
    games = games_for(ctx, w, rule, loo, espn or {})
    return {"natives": natives, "lines": lines, "games": games, "alloc": alloc}


# ---------------------------------------------------------------------------
# Adjusters (inputs: the subject's own list, projections, games, allocation)
# ---------------------------------------------------------------------------

def adjusted_lists(ctx, wk):
    """{subject: {method: {s: {key: value}}}} for s in TARGETS."""
    pos_of = ctx["pos_of"]
    lines, games = wk["lines"], wk["games"]
    pts = {s0: rt.projected_points(lines, pos_of, games, s0) for s0 in lg.SCORINGS}
    out = {}
    for subj, col in SUBJECTS.items():
        base = {k: float(x) for k, x in wk["natives"][subj][col].items()
                if pos_of.get(k) in rt.POSITIONS and x is not None and x > 0}
        m = {"base": {s: dict(base) for s in TARGETS},
             "today": {s: {k: float(wk["natives"][subj][s].get(k) or 0.0) for k in base} for s in TARGETS}}
        anchors = {"": ANCHOR[subj]}
        if subj == "fantasycalc":
            anchors["_fchalf"] = "half_ppr"
        for suf, a in anchors.items():
            for name, (lam, mode) in V1_VARIANTS.items():
                m[name + suf] = {}
                for s in TARGETS:
                    if s == a:
                        m[name + suf][s] = dict(base)
                        continue
                    ratios = {k: dc.player_ratio(ln, a, s) for k, ln in lines.items()}
                    m[name + suf][s] = dc.rescale_chart(base, pos_of, ratios, pts[a], lam, mode=mode).natives
            m["v2" + suf] = {}
            for s in TARGETS:
                if s == a:
                    m["v2" + suf][s] = dict(base)
                    continue
                res = rt.chain_mix(base, {a: 1.0}, pos_of, lines, games, wk["alloc"], s)
                m["v2" + suf][s] = {k: res["values"].get(k, 0.0) for k in base}
        out[subj] = m
    return out


def check_v1_reproduction(lists_by_week):
    """The v1 rerun reproduces rescaled_natives.csv (4-decimal rounding)."""
    worst, n = 0.0, 0
    name = {(1.0, "position_scaled"): "v1", (0.5, "position_scaled"): "v1_l05", (1.0, "same_fit"): "v1_literal"}
    with V1_CSV.open() as f:
        for r in csv.DictReader(f):
            subj, s = r["chart"], r["target_scoring"]
            if subj not in SUBJECTS or s not in TARGETS:
                continue
            suf = "_fchalf" if subj == "fantasycalc" and r["anchor"] == "half_ppr" else ""
            meth = name.get((float(r["lam"]), r["mode"]))
            if meth is None:
                continue
            v = lists_by_week[int(r["week"])][subj][meth + suf][s].get(int(r["player_key"]))
            if v is None:
                continue
            worst = max(worst, abs(v - float(r["native_rescaled"])))
            n += 1
    assert n > 10000 and worst < 1e-3, (n, worst)
    return {"rows_checked": n, "max_abs_diff": worst}


def check_projection_only(ctx, w, lists):
    """Shuffling CBS Sports' and USA Today's natives leaves every adjusted list identical."""
    wk = week_world(ctx, w)
    rng = random.Random(1)
    for c in ("cbs", "usatoday"):
        for s, d in wk["natives"][c].items():
            vals = list(d.values())
            rng.shuffle(vals)
            wk["natives"][c][s] = dict(zip(d.keys(), vals))
    wk["alloc"] = {s: lg.allocation(ctx, wk["natives"], s) for s in lg.SCORINGS}
    again = adjusted_lists(ctx, wk)
    for subj, ms in lists.items():
        for meth, by_s in ms.items():
            if meth == "today":
                continue
            for s, vals in by_s.items():
                assert vals == again[subj][meth][s], (subj, meth, s)
    return True


# ---------------------------------------------------------------------------
# Sets and percentiles
# ---------------------------------------------------------------------------

def priced(d, k):
    v = d.get(k)
    return v is not None and v > 0


def player_set(ctx, wk, subj, ref):
    nat = wk["natives"]
    refs = ("cbs", "usatoday") if ref == "mean" else (ref,)
    base = nat[subj][SUBJECTS[subj]]
    out = {}
    for p in POS:
        ok = [k for k in base if ctx["pos_of"].get(k) == p and priced(base, k)
              and all(priced(nat[r][s], k) for r in refs for s in TARGETS)]
        out[p] = sorted(ok, key=lambda k: (-base[k], k))[:N_SET[p]]
    return out


def pct(vals):
    x = np.asarray(vals, float)
    r = s4.weighted_ranks(x, np.ones(len(x)))[0]
    return r / len(x)


def ref_values(wk, ref, keys, s):
    """Reference vector for (a): raw values for a single chart, mean percentile for the mean."""
    nat = wk["natives"]
    if ref == "mean":
        return 0.5 * (pct([nat["cbs"][s][k] for k in keys]) + pct([nat["usatoday"][s][k] for k in keys]))
    return np.asarray([nat[ref][s][k] for k in keys], float)


def ref_pct(wk, ref, keys, s):
    nat = wk["natives"]
    if ref == "mean":
        return ref_values(wk, ref, keys, s)
    return pct([nat[ref][s][k] for k in keys])


# ---------------------------------------------------------------------------
# Measures (weighted: rows of W are bootstrap resamples)
# ---------------------------------------------------------------------------

def wmean(x, w):
    return (w * x).sum(1) / w.sum(1)


def move_stats(m, r, w):
    """corr, slope, closer for method move m against reference move r (1-D), weights w (B, n)."""
    if np.allclose(m, 0.0):
        corr = np.zeros(len(w))
        slope = np.zeros(len(w))
    else:
        corr = s4.weighted_pearson(m, r, w)
        mr, mm = wmean(r, w)[:, None], wmean(m, w)[:, None]
        cov = (w * (m - mm) * (r - mr)).sum(1)
        slope = cov / (w * (r - mr) ** 2).sum(1)
    closer = wmean(r ** 2, w) - wmean((m - r) ** 2, w)
    return corr, slope, closer


def week_cell(ctx, wk, lists, subj, ref, W, unit):
    """Per-week statistics for every method, as (B,) arrays (B = rows of W)."""
    sets = player_set(ctx, wk, subj, ref)
    pos_of = ctx["pos_of"]
    keys_all = [k for p in POS for k in sets[p]]
    idx_all = np.array([unit[k] for k in keys_all])
    w_all = W[:, idx_all]
    ms = lists[subj]
    ref_move = np.concatenate([ref_pct(wk, ref, sets[p], "ppr") - ref_pct(wk, ref, sets[p], "standard") for p in POS])
    # extremes: RB and TE top / bottom third by projected reception share
    ext = np.zeros(len(keys_all), bool)
    off = 0
    for p in POS:
        ks = sets[p]
        if p in lg.MIX_POS:
            sh = {k: lg.rec_share(wk["lines"].get(k)) for k in ks}
            have = sorted((k for k in ks if sh[k] is not None), key=lambda k: (sh[k], k))
            t = len(have) // 3
            pick = set(have[:t]) | set(have[-t:]) if t else set()
            for j, k in enumerate(ks):
                ext[off + j] = k in pick
        off += len(ks)
    out = {}
    for meth, by_s in ms.items():
        d = {}
        for s in TARGETS:
            per = []
            for p in POS:
                ks = sets[p]
                w = W[:, [unit[k] for k in ks]]
                per.append(s4.spearman([by_s[s][k] for k in ks], ref_values(wk, ref, ks, s), w))
            d[f"a_{s}"] = np.mean(per, axis=0)
        mv = np.concatenate([pct([by_s["ppr"][k] for k in sets[p]]) - pct([by_s["standard"][k] for k in sets[p]])
                             for p in POS])
        d["corr"], d["slope"], d["closer"] = move_stats(mv, ref_move, w_all)
        we = w_all[:, ext]
        d["ext_corr"], _, d["ext_closer"] = move_stats(mv[ext], ref_move[ext], we)
        nz = ref_move[ext] != 0
        agree = (np.sign(mv[ext][nz]) == np.sign(ref_move[ext][nz])).astype(float)
        d["ext_sign"] = wmean(agree, we[:, nz]) if nz.any() else np.full(len(W), np.nan)
        # value-share move
        sh = {}
        for s in TARGETS:
            v = np.array([by_s[s][k] for k in keys_all], float)
            sh[s] = v / v.sum()
        with np.errstate(divide="ignore"):
            smv = np.log(np.maximum(sh["ppr"], 1e-12) / np.maximum(sh["standard"], 1e-12))
        nat = wk["natives"]
        rs = {}
        for s in TARGETS:
            if ref == "mean":
                parts = []
                for r in ("cbs", "usatoday"):
                    v = np.array([nat[r][s][k] for k in keys_all], float)
                    parts.append(v / v.sum())
                rs[s] = 0.5 * (parts[0] + parts[1])
            else:
                v = np.array([nat[ref][s][k] for k in keys_all], float)
                rs[s] = v / v.sum()
        rsm = np.log(rs["ppr"] / rs["standard"])
        d["share_corr"], _, d["share_closer"] = move_stats(smv, rsm, w_all)
        out[meth] = d
    info = {"n": {p: len(sets[p]) for p in POS}, "n_ext": int(ext.sum()),
            "ref_move_sd": float(np.std(ref_move)), "ref_move_zero_share": float(np.mean(ref_move == 0))}
    return out, info, sets


def summarize(per_week, meths, diff_vs="base"):
    """Week-average with bootstrap interval; row 0 of each array is the full sample."""
    out = {}
    for meth in meths:
        row = {}
        for stat in per_week[0][meth]:
            arr = np.mean([pw[meth][stat] for pw in per_week], axis=0)
            row[stat] = {"est": r4(arr[0]), "ci": [r4(x) for x in s4.interval(arr[1:])]}
            if stat.startswith("a_") or stat == "share_closer":
                base = np.mean([pw[diff_vs if stat.startswith("a_") else "today"][stat] for pw in per_week], axis=0)
                dd = arr - base
                row[stat + "_diff"] = {"est": r4(dd[0]), "ci": [r4(x) for x in s4.interval(dd[1:])],
                                       "weeks_higher": int(sum(pw[meth][stat][0] > pw[diff_vs if stat.startswith("a_") else "today"][stat][0] + 1e-12
                                                               for pw in per_week))}
        row["by_week"] = {stat: [r4(pw[meth][stat][0]) for pw in per_week] for stat in ("a_standard", "a_ppr", "corr", "closer", "slope")}
        out[meth] = row
    return out


def run_cells(ctx, worlds, lists, weeks, refs=REFS, subjects=SUBJECTS):
    res = {}
    for subj in subjects:
        for ref in refs:
            sets_w = {w: player_set(ctx, worlds[w], subj, ref) for w in weeks}
            units = sorted({k for w in weeks for p in POS for k in sets_w[w][p]})
            unit = {k: i for i, k in enumerate(units)}
            W = np.vstack([np.ones(len(units)), s4.bootstrap_counts(len(units), N_BOOT, SEED_BOOT)])
            per_week, infos = [], {}
            for w in weeks:
                cell, info, _ = week_cell(ctx, worlds[w], lists[w], subj, ref, W, unit)
                per_week.append(cell)
                infos[w] = info
            meths = list(per_week[0])
            res[f"{subj}|{ref}"] = {"methods": summarize(per_week, meths), "info": infos, "n_units": len(units),
                                    "_raw": per_week}
    return res


# ---------------------------------------------------------------------------
# (c) levels
# ---------------------------------------------------------------------------

def level(vals, pos_of):
    lv = {}
    for p in POS:
        xs = sorted((v for k, v in vals.items() if pos_of.get(k) == p and v > 0), reverse=True)[:K_LEVEL[p]]
        lv[p] = math.exp(statistics.fmean(math.log(x) for x in xs))
    return {"WR/RB": lv["WR"] / lv["RB"], "TE/RB": lv["TE"] / lv["RB"]}


def levels(ctx, worlds, lists, weeks):
    pos_of = ctx["pos_of"]
    out = {}
    for w in weeks:
        nat = worlds[w]["natives"]
        refr = {r: {s: level(nat[r][s], pos_of) for s in TARGETS} for r in ("cbs", "usatoday")}
        refr["mean"] = {s: {q: math.sqrt(refr["cbs"][s][q] * refr["usatoday"][s][q]) for q in ("WR/RB", "TE/RB")}
                        for s in TARGETS}
        wk = {"ref": {r: {s: {q: r4(v) for q, v in d.items()} for s, d in x.items()} for r, x in refr.items()}}
        for subj, ms in lists[w].items():
            for meth, by_s in ms.items():
                lv = {s: level(by_s[s], pos_of) for s in TARGETS}
                err = {r: sum(abs(math.log(lv[s][q]) - math.log(refr[r][s][q])) for s in TARGETS for q in ("WR/RB", "TE/RB"))
                       for r in REFS}
                wk[f"{subj}|{meth}"] = {"ratio": {s: {q: r4(v) for q, v in d.items()} for s, d in lv.items()},
                                        "err": {r: r4(v) for r, v in err.items()},
                                        "move": {q: r4(math.log(lv["ppr"][q] / lv["standard"][q])) for q in ("WR/RB", "TE/RB")}}
        for r in REFS:
            wk.setdefault("ref_move", {})[r] = {q: r4(math.log(refr[r]["ppr"][q] / refr[r]["standard"][q])) for q in ("WR/RB", "TE/RB")}
        out[w] = wk
    summ = {}
    for subj in SUBJECTS:
        for meth in lists[weeks[0]][subj]:
            k = f"{subj}|{meth}"
            summ[k] = {r: {"weeks_lower_than_today": sum(out[w][k]["err"][r] < out[w][f"{subj}|today"]["err"][r] - 1e-12 for w in weeks),
                           "weeks_higher_than_today": sum(out[w][k]["err"][r] > out[w][f"{subj}|today"]["err"][r] + 1e-12 for w in weeks),
                           "mean_err": r4(statistics.fmean(out[w][k]["err"][r] for w in weeks))} for r in REFS}
    return {"by_week": out, "summary": summ}


# ---------------------------------------------------------------------------
# (d) placebo
# ---------------------------------------------------------------------------

def placebo(ctx, worlds, lists, weeks, subj, ref, meth):
    rng = np.random.default_rng(SEED_PERM)
    stats = {"a_standard": np.zeros(N_PERM), "corr": np.zeros(N_PERM), "closer": np.zeros(N_PERM)}
    zero_floor = 0
    for w in weeks:
        wk = worlds[w]
        sets = player_set(ctx, wk, subj, ref)
        ms = lists[w][subj]
        base, adj = ms["base"], ms[meth]
        fac = {}
        for p in POS:
            ks = sets[p]
            f = []
            for k in ks:
                pair = []
                for s in TARGETS:
                    v = adj[s][k]
                    if v <= 0:
                        zero_floor += 1
                    pair.append(math.log(max(v, 1e-9) / base[s][k]))
                f.append(pair)
            fac[p] = np.array(f)
        ref_move = np.concatenate([ref_pct(wk, ref, sets[p], "ppr") - ref_pct(wk, ref, sets[p], "standard") for p in POS])
        refa = {p: ref_values(wk, ref, sets[p], "standard") for p in POS}
        bvals = {p: np.array([base["standard"][k] for k in sets[p]]) for p in POS}
        one = np.ones((1, sum(len(sets[p]) for p in POS)))
        for i in range(N_PERM):
            a_per, mv = [], []
            for p in POS:
                perm = rng.permutation(len(sets[p]))
                f = fac[p][perm]
                vs, vf = bvals[p] * np.exp(f[:, 0]), bvals[p] * np.exp(f[:, 1])
                a_per.append(float(s4.spearman(vs, refa[p])[0]) - float(s4.spearman(bvals[p], refa[p])[0]))
                mv.append(pct(vf) - pct(vs))
            mv = np.concatenate(mv)
            c, _, cl = move_stats(mv, ref_move, one)
            stats["a_standard"][i] += statistics.fmean(a_per) / len(weeks)
            stats["corr"][i] += float(c[0]) / len(weeks)
            stats["closer"][i] += float(cl[0]) / len(weeks)
    return {k: {"mean": r4(v.mean()), "p95": r4(np.percentile(v, 95)), "p5": r4(np.percentile(v, 5))}
            for k, v in stats.items()} | {"zero_values_floored": zero_floor}


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def above(ci):
    return ci[0] is not None and ci[0] > 0


def below(ci):
    return ci[1] is not None and ci[1] < 0


def verdict(main, loo, plc, meth):
    rows, ok, harm = {}, True, False
    for subj in SUBJECTS:
        m = main[f"{subj}|mean"]["methods"][meth]
        l = loo[f"{subj}|mean"]["methods"][meth]
        p = plc[f"{subj}|mean|{meth}"]
        c1 = above(m["a_standard_diff"]["ci"])
        c2 = True if subj == "fantasycalc" else not below(m["a_ppr_diff"]["ci"])
        c3 = above(m["corr"]["ci"]) and above(m["closer"]["ci"])
        c4 = m["a_standard_diff"]["est"] > p["a_standard"]["p95"] and m["closer"]["est"] > p["closer"]["p95"]
        sg = lambda x: (x > 0) - (x < 0)
        c5 = all(sg(m[k]["est"]) == sg(l[k]["est"]) for k in ("a_standard_diff", "corr", "closer"))
        h = below(m["a_standard_diff"]["ci"]) or below(m["closer"]["ci"])
        rows[subj] = {"1_a_std": c1, "2_a_full": c2, "3_response": c3, "4_placebo": c4, "5_loo": c5, "harm": h}
        ok &= c1 and c2 and c3 and c4 and c5
        harm |= h
    return {"verdict": "PASS" if ok else ("FAIL" if harm else "NOT SHOWN"), "checks": rows}


def level_verdict(lv, meth):
    s = {subj: lv["summary"][f"{subj}|{meth}"]["mean"] for subj in SUBJECTS}
    if all(x["weeks_lower_than_today"] >= 4 for x in s.values()):
        return "moves toward"
    if any(x["weeks_higher_than_today"] >= 4 for x in s.values()):
        return "moves away"
    return "mixed"


def strip(res):
    return {k: {kk: vv for kk, vv in v.items() if kk != "_raw"} for k, v in res.items()}


def games_diff(ctx, base_res, var_res):
    """Variant minus current, same bootstrap rows (same weeks, same sets)."""
    out = {}
    for key in base_res:
        b, v = base_res[key]["_raw"], var_res[key]["_raw"]
        out[key] = {}
        for meth in PRIMARY:
            row = {}
            for stat in ("a_standard", "a_ppr", "corr", "closer"):
                d = np.mean([vw[meth][stat] - bw[meth][stat] for vw, bw in zip(v, b)], axis=0)
                row[stat] = {"est": r4(d[0]), "ci": [r4(x) for x in s4.interval(d[1:])]}
            out[key][meth] = row
    return out


def games_moves(ctx, worlds_cur, worlds_var, weeks):
    out = {}
    for w in weeks:
        gc, gv = worlds_cur[w]["games"], worlds_var[w]["games"]
        row = {}
        for subj, col in SUBJECTS.items():
            base = [k for k, x in worlds_cur[w]["natives"][subj][col].items()
                    if x and x > 0 and ctx["pos_of"].get(k) in POS]
            setk = {k for p in POS for k in player_set(ctx, worlds_cur[w], subj, "mean")[p]}
            row[subj] = {"priced_moved_gt1": sum(abs(gv[k] - gc[k]) > 1 for k in base), "priced": len(base),
                         "set_moved_gt1": sum(abs(gv[k] - gc[k]) > 1 for k in setk), "set": len(setk)}
        out[w] = row
    return out


def main():
    OUT.mkdir(exist_ok=True)
    ctx = lg.load_ctx()
    espn = espn_games()
    worlds = {w: week_world(ctx, w) for w in WEEKS}
    lists = {w: adjusted_lists(ctx, worlds[w]) for w in WEEKS}
    checks = {"v1_reproduction": check_v1_reproduction(lists),
              "projection_only": check_projection_only(ctx, 5, lists[5])}
    print("checks", checks, flush=True)
    main_res = run_cells(ctx, worlds, lists, WEEKS)
    print("main done", flush=True)
    worlds_loo = {w: week_world(ctx, w, loo=True) for w in WEEKS}
    lists_loo = {w: adjusted_lists(ctx, worlds_loo[w]) for w in WEEKS}
    # scored on the same reference natives; the sets do not depend on the adjuster inputs
    loo_res = run_cells(ctx, worlds_loo, lists_loo, WEEKS, refs=("mean", "cbs"))
    print("loo done", flush=True)
    meths_plc = ("v1", "v1_l05", "v1_literal", "v2")
    plc = {f"{subj}|{ref}|{m}": placebo(ctx, worlds, lists, WEEKS, subj, ref, m)
           for subj in SUBJECTS for ref in REFS for m in meths_plc}
    print("placebo done", flush=True)
    lv = levels(ctx, worlds, lists, WEEKS)
    # games variant, weeks 7-9
    cur79 = run_cells(ctx, worlds, lists, GAMES_WEEKS)
    games = {}
    for rule in ("G1", "G2"):
        wv = {w: week_world(ctx, w, rule=rule, espn=espn) for w in GAMES_WEEKS}
        lv_ = {w: adjusted_lists(ctx, wv[w]) for w in GAMES_WEEKS}
        vr_ = run_cells(ctx, wv, lv_, GAMES_WEEKS)
        games[rule] = {"diff_vs_current": games_diff(ctx, cur79, vr_), "players_moved": games_moves(ctx, worlds, wv, GAMES_WEEKS)}
    print("games done", flush=True)
    verdicts = {m: {"ranking": verdict(main_res, loo_res, plc, m), "levels": level_verdict(lv, m)} for m in PRIMARY}
    doc = {"spec": "docs/research/jeg1605/response-preregistration.md", "checks": checks, "verdicts": verdicts,
           "main": strip(main_res), "loo": strip(loo_res), "placebo": plc, "levels": lv, "games": games}
    (OUT / "response_test.json").write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdicts, indent=1))


if __name__ == "__main__":
    main()
