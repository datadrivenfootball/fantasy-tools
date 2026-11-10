"""JEG-1611 v4 runner: G1 (labelled), G2 (response test), G3 (DDF v4 vs
current), coverage and extreme pairs, on the weeks given (default the
development weeks 5-7; weeks 8-9 are the holdout and are run only by the lead).

Spec: docs/research/jeg1611/iteration-log.md, iteration 3 and readings 3a.
Research only; saved snapshots only (no network).

Run:  /usr/bin/python3 tools/research/jeg1611/run_v4.py [--weeks 5,6,7] [--only g1|g2|g3|cov]
Out:  tools/research/jeg1611/out/v4/{g1,g2,g3,coverage,extremes}.json, summary.md
      (other week sets: out/v4/weeks_<list>/)
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v4  # noqa: E402

R3, uw, hs = v4.R3, v4.uw, v4.hs
lg, rtest, s4 = R3.lg, R3.rtest, R3.s4
DEV_WEEKS = (5, 6, 7)
G1_CHARTS, G1_DIRECTIONS, G1_MEASURES = R3.G1_CHARTS, R3.G1_DIRECTIONS, R3.G1_MEASURES
# name -> (mixkind, form) of the native-list variants
LIST_VARIANTS = {"v4": ("share", "delta"), "v4_mult": ("share", "mult"), "v4_tail": ("share", "tail"),
                 "v4_raw": ("raw", "delta"), "v4_recg": ("recg", "delta"), "v4_assumed": ("assumed", "delta"),
                 "v4_chartzero": ("share", "chartzero")}
r4, rnd = R3.r4, R3.rnd
G1_MEASURES_ALL = G1_MEASURES + ("levels_norm", "levels_norm_pos")
LOWER_BETTER = ("levels", "levels_norm", "levels_norm_pos")
SHARE_POS = ("RB", "WR", "TE")


def better(measure, a, b):
    if a is None or b is None:
        return None
    return a < b if measure in LOWER_BETTER else a > b


def level_threshold(weeks):
    """The G2 (c) / G3 levels rule is 4 of 5 weeks; read as at least 80% of the weeks."""
    return math.ceil(0.8 * len(weeks))


# ---------------------------------------------------------------------------
# G1
# ---------------------------------------------------------------------------

def pos_shares(ctx, keys, vals):
    """Iteration 4: RB/WR/TE shares of the scored set's total (QB in the total)."""
    tot = sum(vals[k] for k in keys)
    return {p: sum(vals[k] for k in keys if ctx["pos_of"][k] == p) / tot for p in SHARE_POS}


def scale_free(ctx, keys, vals, tgt):
    """Iteration 4: MALE after scaling vals to tgt's total over the scored set,
    and the mean absolute log error of the RB/WR/TE shares."""
    f = sum(tgt[k] for k in keys) / sum(vals[k] for k in keys)
    pos_l = [k for k in keys if vals[k] > 0 and tgt[k] > 0]
    male = statistics.fmean(abs(math.log(f * vals[k]) - math.log(tgt[k])) for k in pos_l)
    sv, st = pos_shares(ctx, keys, vals), pos_shares(ctx, keys, tgt)
    return male, statistics.fmean(abs(math.log(sv[p] / st[p])) for p in SHARE_POS), sv


def g1_row(ctx, wkl, keys, vals, inp, tgt):
    m = lg.metrics(ctx, wkl, keys, vals, inp, tgt)
    ln, lnp, sh = scale_free(ctx, keys, vals, tgt)
    return {"within": m["within"], "levels": m["male"], "xpos": m["whole_set"], "within_by_pos": m["within_by_pos"],
            "median_ratio_to_input": m["median_ratio_to_input"], "n_levels": m["n_male"],
            "levels_norm": ln, "levels_norm_pos": lnp, "pos_share": sh}


def g1(ctx, weeks, wkls, W):
    cells = {}
    for chart in G1_CHARTS:
        for s0, s in G1_DIRECTIONS:
            name = f"{chart}|{s0}->{s}"
            cell = {}
            for w in W:
                wk, wkl = weeks[w], wkls[w]
                inp, tgt = wk.natives[chart][s0], wk.natives[chart][s]
                keys = [k for k in wkl["keys"] if inp.get(k, 0) > 0 and tgt.get(k, 0) > 0]
                row = {"n": len(keys), "unchanged": g1_row(ctx, wkl, keys, inp, inp, tgt),
                       "published_median_ratio": g1_row(ctx, wkl, keys, tgt, inp, tgt)["median_ratio_to_input"]}
                for vname, (kind, form) in LIST_VARIANTS.items():
                    vals, u, _ = wk.v4_list(chart, s, s0=s0, mixkind=kind, form=form)
                    row[vname] = g1_row(ctx, wkl, keys, vals, inp, tgt)
                    row[vname]["floored_zero_in_set"] = sum(vals[k] <= 0 for k in keys)
                    if vname == "v4":
                        row["scored_not_invertible"] = sum(u.records[k]["label"] != "invertible" for k in keys
                                                           if k in u.records)
                        row["scored_fallback_prior"] = sum(u.records[k]["mix"].label == "fallback_prior"
                                                           for k in keys if k in u.records)
                # Iteration 4: per-position share move, log(share Full / share Standard)
                sgn = 1.0 if s == "ppr" else -1.0
                sh_in = row["unchanged"]["pos_share"]
                tgt_sh = pos_shares(ctx, keys, tgt)
                row["share_move_full_over_std"] = {
                    "published": {p: sgn * math.log(tgt_sh[p] / sh_in[p]) for p in SHARE_POS}, "unchanged": 0.0,
                    **{v: {p: sgn * math.log(row[v]["pos_share"][p] / sh_in[p]) for p in SHARE_POS}
                       for v in LIST_VARIANTS}}
                row["within_diff_by_pos"] = {v: {p: row[v]["within_by_pos"][p] - row["unchanged"]["within_by_pos"][p]
                                                 for p in SHARE_POS} for v in LIST_VARIANTS}
                cell[w] = row
            cells[name] = cell
    table = {}
    for name, cell in cells.items():
        for meas in G1_MEASURES_ALL:
            t = {"unchanged": {w: cell[w]["unchanged"][meas] for w in W}}
            for vname in LIST_VARIANTS:
                t[vname] = {w: cell[w][vname][meas] for w in W}
                t[f"weeks_won|{vname}"] = sum(bool(better(meas, cell[w][vname][meas], cell[w]["unchanged"][meas]))
                                              for w in W)
            table[f"{name}|{meas}"] = t
    totals = {v: sum(t[f"weeks_won|{v}"] for k, t in table.items() if k.split("|")[-1] in G1_MEASURES)
              for v in LIST_VARIANTS}
    return {"weeks": list(W), "table": table, "weeks_won_totals_of": 12 * len(W), "weeks_won_totals": totals,
            "cells": cells}


# ---------------------------------------------------------------------------
# G2
# ---------------------------------------------------------------------------

G2_METHODS = tuple(LIST_VARIANTS) + ("v4_fchalf",)


def add_v4(lists, wk, drop=()):
    for subj in rtest.SUBJECTS:
        base = lists[subj]["base"]["standard"]
        meths = [(n, "primary", k, f) for n, (k, f) in LIST_VARIANTS.items()]
        if subj == "fantasycalc":
            meths.append(("v4_fchalf", "fchalf", "share", "delta"))
        for name, var, kind, form in meths:
            lists[subj][name] = {s: {k: wk.v4_list(subj, s, variant=var, drop=drop, mixkind=kind, form=form)[0]
                                     .get(k, 0.0) for k in base} for s in rtest.TARGETS}
    return lists


def level_verdict(lv, meth, W):
    t = level_threshold(W)
    s = {subj: lv["summary"][f"{subj}|{meth}"]["mean"] for subj in rtest.SUBJECTS}
    if all(x["weeks_lower_than_today"] >= t for x in s.values()):
        return "moves toward"
    if any(x["weeks_higher_than_today"] >= t for x in s.values()):
        return "moves away"
    return "mixed"


def g2_by_position(ctx, worlds, lists, W, meths, ref="mean"):
    """Iteration 4: corr and closer of the Standard-to-Full percentile move per
    position (RB, WR, TE), same bootstrap rows as response_test.run_cells."""
    out = {}
    for subj in rtest.SUBJECTS:
        sets_w = {w: rtest.player_set(ctx, worlds[w], subj, ref) for w in W}
        units = sorted({k for w in W for p in rtest.POS for k in sets_w[w][p]})
        unit = {k: i for i, k in enumerate(units)}
        Wb = np.vstack([np.ones(len(units)), s4.bootstrap_counts(len(units), rtest.N_BOOT, rtest.SEED_BOOT)])
        for m in meths + ("base",):
            for p in rtest.POS:
                acc = {"corr": [], "closer": []}
                for w in W:
                    ks = sets_w[w][p]
                    by_s = lists[w][subj][m]
                    rm = rtest.ref_pct(worlds[w], ref, ks, "ppr") - rtest.ref_pct(worlds[w], ref, ks, "standard")
                    mv = rtest.pct([by_s["ppr"][k] for k in ks]) - rtest.pct([by_s["standard"][k] for k in ks])
                    c, _sl, cl = rtest.move_stats(mv, rm, Wb[:, [unit[k] for k in ks]])
                    acc["corr"].append(c)
                    acc["closer"].append(cl)
                row = {}
                for stat, arrs in acc.items():
                    arr = np.mean(arrs, axis=0)
                    row[stat] = {"est": r4(arr[0]), "ci": [r4(x) for x in s4.interval(arr[1:])],
                                 "by_week": [r4(a[0]) for a in arrs]}
                out[f"{subj}|{m}|{p}"] = row
    return out


def g2_level_moves(lv, W):
    """Iteration 4: per week, each method's log WR/RB and TE/RB move (Standard to
    Full) against CBS's, USA Today's and the mean reference move; abs difference
    vs 'unchanged' (move 0, i.e. |reference move|)."""
    out = {}
    for w in W:
        bw = lv["by_week"][w]
        refm = bw["ref_move"]
        for key, d in bw.items():
            if "|" not in key:
                continue
            subj, meth = key.split("|", 1)
            if meth not in ("base", "today", "v2") + G2_METHODS:
                continue
            row = {"move": d["move"]}
            for r in rtest.REFS:
                row[f"absdiff|{r}"] = {q: r4(abs(d["move"][q] - refm[r][q])) for q in ("WR/RB", "TE/RB")}
                row[f"absdiff_unchanged|{r}"] = {q: r4(abs(refm[r][q])) for q in ("WR/RB", "TE/RB")}
            out[f"{w}|{key}"] = row
        out[f"{w}|ref_move"] = refm
    summ = {}
    for key in {k.split("|", 1)[1] for k in out if not k.endswith("ref_move")}:
        for r in rtest.REFS:
            for q in ("WR/RB", "TE/RB"):
                closer = sum(out[f"{w}|{key}"][f"absdiff|{r}"][q] < out[f"{w}|{key}"][f"absdiff_unchanged|{r}"][q]
                             for w in W)
                summ.setdefault(key, {})[f"{r}|{q}"] = {
                    "weeks_closer_than_unchanged": int(closer),
                    "mean_move": r4(statistics.fmean(out[f"{w}|{key}"]["move"][q] for w in W)),
                    "mean_ref_move": r4(statistics.fmean(out[f"{w}|ref_move"][r][q] for w in W))}
    return {"by_week": out, "summary": summ}


def g2(ctx, weeks, W):
    worlds = {w: rtest.week_world(ctx, w) for w in W}
    lists = {w: add_v4(rtest.adjusted_lists(ctx, worlds[w]), weeks[w]) for w in W}
    main = rtest.run_cells(ctx, worlds, lists, W)
    worlds_loo = {w: rtest.week_world(ctx, w, loo=True) for w in W}
    lists_loo = {w: add_v4(rtest.adjusted_lists(ctx, worlds_loo[w]), weeks[w], drop=("cbsros", "cbs")) for w in W}
    loo = rtest.run_cells(ctx, worlds_loo, lists_loo, W, refs=("mean", "cbs"))
    print("g2 main+loo", flush=True)
    plc = {}
    for m in G2_METHODS:
        refs = rtest.REFS if m == "v4" else ("mean",)
        for subj in rtest.SUBJECTS:
            if m == "v4_fchalf" and subj != "fantasycalc":
                continue
            for ref in refs:
                plc[f"{subj}|{ref}|{m}"] = rtest.placebo(ctx, worlds, lists, W, subj, ref, m)
    lv = rtest.levels(ctx, worlds, lists, W)
    verdicts = {}
    for m in G2_METHODS + ("v1", "v2"):
        if m == "v4_fchalf":
            continue
        p = dict(plc)
        if m in ("v1", "v2"):
            p.update({f"{s}|mean|{m}": rtest.placebo(ctx, worlds, lists, W, s, "mean", m) for s in rtest.SUBJECTS})
        verdicts[m] = {"ranking": rtest.verdict(main, loo, p, m), "levels": level_verdict(lv, m, W)}
    by_pos = g2_by_position(ctx, worlds, lists, W, ("v4", "v4_chartzero", "v2"))
    level_moves = g2_level_moves(lv, W)
    pick = ("base", "today", "v1", "v2") + G2_METHODS
    short = {k: {m: v["methods"][m] for m in pick if m in v["methods"]} | {"info": v["info"]} for k, v in main.items()}
    short_loo = {k: {m: v["methods"][m] for m in G2_METHODS if m in v["methods"]} for k, v in loo.items()}
    return {"weeks": list(W), "level_rule_weeks": level_threshold(W), "verdicts": verdicts, "main": short,
            "loo": short_loo, "placebo": plc,
            "levels_summary": {k: v for k, v in lv["summary"].items() if k.split("|")[1] in pick},
            "levels_by_week": lv["by_week"], "by_position_mean_ref": by_pos, "level_moves": level_moves}


# ---------------------------------------------------------------------------
# G3
# ---------------------------------------------------------------------------

G3_PAIRS = {"primary": ("v4", "current"), "fchalf": ("v4_fchalf", "current"),
            "noFC": ("v4_noFC", "current_noFC"), "alloc_fixed_half": ("v4_alloc_half", "current"),
            "chartzero": ("v4_chartzero", "current")}


def g3_lists(ctx, weeks, W, scorings=("standard", "ppr")):
    lists, ddf_full = {}, {}
    for w in W:
        wk = weeks[w]
        runs = {s: {"current": wk.current(s), "v4": v4.v4_run(wk, s),
                    "v4_fchalf": v4.v4_run(wk, s, fc_variant="fchalf"),
                    "current_noFC": wk.current(s, drop=("fantasycalc",)),
                    "v4_noFC": v4.v4_run(wk, s, drop=("fantasycalc",)),
                    "v4_alloc_half": v4.v4_run(wk, s, alloc="half_fixed"),
                    "v4_chartzero": v4.v4_run(wk, s, form="chartzero")} for s in scorings}
        for R in R3.G3_REFS:
            lists[(w, R)] = {m: {s: R3.ddf_minus(runs[s][m], R) for s in scorings} for m in runs[scorings[0]]}
        ddf_full[w] = {s: {"current": runs[s]["current"]["ddf"], "v4": runs[s]["v4"]["ddf"]} for s in scorings}
    return lists, ddf_full


def g3(ctx, weeks, W):
    worlds = {w: rtest.week_world(ctx, w) for w in W}
    lists, ddf_full = g3_lists(ctx, weeks, W)
    thr = level_threshold(W)
    res = {}
    for setsubj in R3.G3_SETS:
        for R in R3.G3_REFS:
            sets_w = {w: rtest.player_set(ctx, worlds[w], setsubj, R) for w in W}
            units = sorted({k for w in W for p in rtest.POS for k in sets_w[w][p]})
            unit = {k: i for i, k in enumerate(units)}
            Wb = np.vstack([np.ones(len(units)), s4.bootstrap_counts(len(units), rtest.N_BOOT, rtest.SEED_BOOT)])
            per_week = []
            for w in W:
                L = {m: {s: {k: v.get(k, 0.0) for p in rtest.POS for k in sets_w[w][p]} for s, v in by.items()}
                     for m, by in lists[(w, R)].items()}
                L["base"] = L["current"]
                L["today"] = L["current"]
                cell, _info, _ = rtest.week_cell(ctx, worlds[w], {setsubj: L}, setsubj, R, Wb, unit)
                per_week.append(cell)
            row = {}
            for label, (a, b) in G3_PAIRS.items():
                st = {}
                for stat in ("a_standard", "a_ppr", "corr", "closer", "slope"):
                    dd = np.mean([pw[a][stat] - pw[b][stat] for pw in per_week], axis=0)
                    st[stat + "_diff"] = {"est": r4(dd[0]), "ci": [r4(x) for x in s4.interval(dd[1:])]}
                    for m in (a, b):
                        arr = np.mean([pw[m][stat] for pw in per_week], axis=0)
                        st[f"{stat}|{m}"] = {"est": r4(arr[0]), "ci": [r4(x) for x in s4.interval(arr[1:])]}
                row[label] = st
            lv = {}
            for label, (a, b) in G3_PAIRS.items():
                lower = higher = 0
                errs = []
                for w in W:
                    nat = worlds[w]["natives"]
                    ref = {s: rtest.level(nat[R][s], ctx["pos_of"]) for s in rtest.TARGETS}
                    err = {}
                    for m in (a, b):
                        mv = {s: rtest.level(lists[(w, R)][m][s], ctx["pos_of"]) for s in rtest.TARGETS}
                        err[m] = sum(abs(math.log(mv[s][q]) - math.log(ref[s][q])) for s in rtest.TARGETS
                                     for q in ("WR/RB", "TE/RB"))
                    errs.append((err[a], err[b]))
                    lower += err[a] < err[b] - 1e-12
                    higher += err[a] > err[b] + 1e-12
                lv[label] = {"weeks_lower_error": lower, "weeks_higher_error": higher,
                             "mean_err": [r4(statistics.fmean(e[0] for e in errs)), r4(statistics.fmean(e[1] for e in errs))],
                             "verdict": "moves toward" if lower >= thr else "moves away" if higher >= thr else "mixed"}
            row["levels"] = lv
            res[f"{setsubj}_set|{R}"] = row
    verdicts = {}
    for label in G3_PAIRS:
        by_set = {}
        for setsubj in R3.G3_SETS:
            rows = [res[f"{setsubj}_set|{R}"][label] for R in R3.G3_REFS]
            good = all(r["a_standard_diff"]["est"] > 0 and rtest.above(r["a_standard_diff"]["ci"])
                       and not rtest.below(r["a_ppr_diff"]["ci"]) and not rtest.below(r["closer_diff"]["ci"])
                       for r in rows)
            bad = any(rtest.below(r["a_standard_diff"]["ci"]) or rtest.below(r["a_ppr_diff"]["ci"])
                      or rtest.below(r["closer_diff"]["ci"]) for r in rows)
            by_set[setsubj] = "better" if good else "worse" if bad else "not shown"
        vs = set(by_set.values())
        verdicts[label] = {"by_set": by_set,
                           "overall": "worse" if "worse" in vs else "better" if vs == {"better"} else "not shown"}
    hinge = {}
    for label in ("fchalf", "noFC", "alloc_fixed_half", "chartzero"):
        for key, row in res.items():
            p, q = row["primary"]["a_standard_diff"]["est"], row[label]["a_standard_diff"]["est"]
            hinge[f"{label}|{key}"] = bool(p is not None and q is not None and (p > 0) != (q > 0))
    return {"weeks": list(W), "verdicts": verdicts, "hinges_on_sign_flip_a_standard": hinge, "cells": res}, ddf_full


# ---------------------------------------------------------------------------
# Coverage and extremes
# ---------------------------------------------------------------------------

UNWINDS = (("fantasycalc", None, "primary"), ("fantasycalc", None, "fchalf"), ("fantasypros", None, "primary"),
           ("cbs", "standard", "primary"), ("cbs", "ppr", "primary"),
           ("usatoday", "standard", "primary"), ("usatoday", "ppr", "primary"))


def coverage(ctx, weeks, W):
    out = {"per_chart_week": {}, "replacement_ppg": {}, "pooled": {}}
    for w in W:
        wk = weeks[w]
        for chart, s0, var in UNWINDS:
            u, x, dg, tag = wk.unwound(chart, s0, var)
            key = f"{chart}|{u.s0}|{var}|{w}"
            out["per_chart_week"][key] = v4.counts4(u)
            z = v4.chart_zero(u)
            for p in v4.POSITIONS:
                out["per_chart_week"][key][p].update(chart_zero_ppg=z[p]["zero"], chart_zero_fallback=z[p]["fallback"],
                                                     R_s0=u.R0[p], intercept=u.b[p]["intercept"])
            rkey = f"{tag}|{w}"
            if rkey not in out["replacement_ppg"]:
                out["replacement_ppg"][rkey] = {
                    "R_s0": u.R0, **{f"R_{s}": wk.fixed(dg, tag, s)["R"] for s in R3.SCORINGS}}
    for key, byp in out["per_chart_week"].items():
        chart, s0, var, _w = key.split("|")
        a = out["pooled"].setdefault(f"{chart}|{s0}|{var}", {f: 0 for f in ("priced", "invertible", "below_waiver",
                                                                           "no_inverse", "fallback_prior")})
        for c in byp.values():
            for f in a:
                a[f] += c[f]
    return out


def extremes(ctx, weeks, W, ddf_full):
    out = {}
    cats = ctx["cats"]
    for w in W:
        wk = weeks[w]
        nat = wk.natives
        world = rtest.week_world(ctx, w)
        g2_sets = {subj: rtest.player_set(ctx, world, subj, "mean") for subj in rtest.SUBJECTS}
        lists = {c: {s: wk.v4_list(c, s)[0] for s in ("standard", "ppr")} for c in ("fantasycalc", "fantasypros")}
        mixes = R3.history_mixes(ctx, w, set(nat["fantasycalc"]["ppr"]) | set(nat["fantasypros"]["half_ppr"]), "ppr")
        pool = {p: sorted({k for subj in rtest.SUBJECTS for k in g2_sets[subj].get(p, [])}) for p in ("RB", "TE")}
        qbs = sorted((k for k, v in nat["fantasycalc"]["ppr"].items() if ctx["pos_of"].get(k) == "QB" and v > 0),
                     key=lambda k: -nat["fantasycalc"]["ppr"][k])[:24]

        def mv(a_d, b_d, k):
            a, b = a_d.get(k), b_d.get(k)
            return math.log(b / a) if a and b and a > 0 and b > 0 else None

        def describe(k):
            sh = wk.mixes("share", [k])[k]
            d = {"player": ctx["name_of"].get(k), "pos": ctx["pos_of"].get(k), "hist_rec_share": R3.hist_share(mixes.get(k)),
                 "shrunk_share_rec_per_std": sh.sh, "shrunk_label": sh.label}
            for c in ("fantasycalc", "fantasypros"):
                d[f"{c}_v4"] = mv(lists[c]["standard"], lists[c]["ppr"], k)
            for c in ("cbs", "usatoday"):
                d[c] = mv(nat[c]["standard"], nat[c]["ppr"], k)
            d["ddf_current"] = mv(ddf_full[w]["standard"]["current"], ddf_full[w]["ppr"]["current"], k)
            d["ddf_v4"] = mv(ddf_full[w]["standard"]["v4"], ddf_full[w]["ppr"]["v4"], k)
            return d
        rows = {}
        for p, label in (("RB", "pass_catching_backs"), ("TE", "receiving_tight_ends")):
            ks = [k for k in pool[p] if R3.hist_share(mixes.get(k)) is not None]
            ks.sort(key=lambda k: -R3.hist_share(mixes[k]))
            rows[label] = [describe(k) for k in ks[:6]]
            rows[label.replace("pass_catching", "least_pass_catching").replace("receiving", "least_receiving")] = \
                [describe(k) for k in ks[-6:]]
        qs = [k for k in qbs if R3.rush_share(cats, k) is not None]
        qs.sort(key=lambda k: -R3.rush_share(cats, k))
        rows["rushing_quarterbacks"] = [describe(k) for k in qs[:6]]
        fields = ("fantasycalc_v4", "fantasypros_v4", "cbs", "usatoday", "ddf_current", "ddf_v4")
        summ = {label: {f: (statistics.fmean(v[f] for v in lst if v.get(f) is not None)
                            if any(v.get(f) is not None for v in lst) else None) for f in fields}
                for label, lst in rows.items()}
        out[w] = {"players": rows, "group_mean_log_move": summ}
    groups = list(out[W[0]]["group_mean_log_move"])
    fields = list(out[W[0]]["group_mean_log_move"][groups[0]])
    out["mean_over_weeks"] = {g: {f: statistics.fmean(out[w]["group_mean_log_move"][g][f] for w in W
                                                      if out[w]["group_mean_log_move"][g][f] is not None)
                                  for f in fields} for g in groups}
    return out


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def ci(d):
    return f"{d['est']:+.3f} [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]" if d and d.get("est") is not None else "n/a"


def summary_md(W, G1, G2, G3, COV, EXT):
    L = [f"# JEG-1611 v4 run, weeks {', '.join(map(str, W))} (generated by run_v4.py)", ""]
    if G1:
        L += ["## G1: weeks won over unchanged (of %d)" % len(W), "",
              "| Cell | " + " | ".join(LIST_VARIANTS) + " |", "| --- |" + " --- |" * len(LIST_VARIANTS)]
        for name, t in G1["table"].items():
            L.append(f"| {name} | " + " | ".join(str(t[f"weeks_won|{v}"]) for v in LIST_VARIANTS) + " |")
        L.append(f"| **total of {G1['weeks_won_totals_of']}** | " +
                 " | ".join(str(G1["weeks_won_totals"][v]) for v in LIST_VARIANTS) + " |")
        L += ["", "Week ranges, v4 vs unchanged:", ""]
        for name, t in G1["table"].items():
            a, b = list(t["v4"].values()), list(t["unchanged"].values())
            L.append(f"- {name}: v4 {min(a):.3f}-{max(a):.3f}, unchanged {min(b):.3f}-{max(b):.3f}")
        L += ["", "Median rebuilt-to-input ratio by position (v4 / published), mean over weeks:", ""]
        for name, cell in G1["cells"].items():
            parts = []
            for p in ("RB", "WR", "TE"):
                a = statistics.fmean(cell[w]["v4"]["median_ratio_to_input"][p] for w in W)
                b = statistics.fmean(cell[w]["published_median_ratio"][p] for w in W)
                parts.append(f"{p} {a:.2f} / {b:.2f}")
            wp = {p: statistics.fmean(cell[w]["v4"]["within_by_pos"][p] for w in W) for p in ("RB", "WR", "TE")}
            wu = {p: statistics.fmean(cell[w]["unchanged"]["within_by_pos"][p] for w in W) for p in ("RB", "WR", "TE")}
            L.append(f"- {name}: " + ", ".join(parts) + "; within by pos v4 " +
                     ", ".join(f"{p} {wp[p]:.3f} (unch {wu[p]:.3f})" for p in wp))
        L.append("")
    if G2:
        L += ["## G2: response test, mean reference", "",
              "| Method | verdict | levels | FC (a) Std diff | FC closer | FC corr | FP (a) Std diff | FP closer | FP corr |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for m, v in G2["verdicts"].items():
            fc, fp = G2["main"]["fantasycalc|mean"][m], G2["main"]["fantasypros|mean"][m]
            L.append(f"| {m} | {v['ranking']['verdict']} | {v['levels']} | {ci(fc['a_standard_diff'])} | "
                     f"{ci(fc['closer'])} | {ci(fc['corr'])} | {ci(fp['a_standard_diff'])} | {ci(fp['closer'])} | "
                     f"{ci(fp['corr'])} |")
        L.append("")
    if G3:
        L += ["## G3: DDF^-R, v4 minus current", "", "| Pair | verdict | by set |", "| --- | --- | --- |"]
        for label, v in G3["verdicts"].items():
            L.append(f"| {label} | {v['overall']} | {v['by_set']} |")
        L += ["", "| Set, ref | (a) Std diff | (a) Full diff | closer diff | corr diff | levels |",
              "| --- | --- | --- | --- | --- | --- |"]
        for key, row in G3["cells"].items():
            r = row["primary"]
            L.append(f"| {key} | {ci(r['a_standard_diff'])} | {ci(r['a_ppr_diff'])} | {ci(r['closer_diff'])} | "
                     f"{ci(r['corr_diff'])} | {row['levels']['primary']['verdict']} |")
        L.append("")
    if COV:
        L += ["## Coverage (pooled over weeks)", "", "| Unwind | priced | invertible | below_waiver | no_inverse | fallback_prior |",
              "| --- | --- | --- | --- | --- | --- |"]
        for k, a in COV["pooled"].items():
            L.append(f"| {k} | {a['priced']} | {a['invertible']} | {a['below_waiver']} | {a['no_inverse']} | "
                     f"{a['fallback_prior']} |")
        L += ["", "b_p (R^2) per position, mean over weeks:", ""]
        groups = {}
        for key, byp in COV["per_chart_week"].items():
            g = "|".join(key.split("|")[:3])
            for p, c in byp.items():
                if c["b"] is not None:
                    groups.setdefault((g, p), []).append((c["b"], c["b_r2"]))
        for (g, p), vals in groups.items():
            r2 = [v[1] for v in vals if v[1] is not None]
            L.append(f"- {g} {p}: b {statistics.fmean(v[0] for v in vals):.3f}, R^2 "
                     f"{min(r2):.3f}-{max(r2):.3f}" if r2 else f"- {g} {p}: b {statistics.fmean(v[0] for v in vals):.3f}")
        L.append("")
    if EXT:
        L += ["## Extreme pairs, log(Full / Standard), mean over weeks", "",
              "| Group | FC v4 | FP v4 | CBS | USA Today | DDF current | DDF v4 |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for g, d in EXT["mean_over_weeks"].items():
            L.append(f"| {g} | " + " | ".join(f"{d[f]:+.2f}" for f in d) + " |")
        L.append("")
    L += summary_iter4(W, G1, G2, G3, COV)
    return "\n".join(L)


def summary_iter4(W, G1, G2, G3, COV):
    L = ["## Iteration 4 additions", ""]
    if G1:
        L += ["### G1 scale-free levels: weeks won over unchanged (of %d)" % len(W), "",
              "| Cell | measure | v4 | v4_chartzero | v4_mult | unchanged by week | v4 by week | chartzero by week |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for name, t in G1["table"].items():
            meas = name.split("|")[-1]
            if meas not in ("levels_norm", "levels_norm_pos") and not name.endswith("|levels"):
                continue
            f = lambda d: ", ".join(f"{v:.3f}" for v in d.values())
            L.append(f"| {'|'.join(name.split('|')[:2])} | {meas} | {t['weeks_won|v4']} | {t['weeks_won|v4_chartzero']} | "
                     f"{t['weeks_won|v4_mult']} | {f(t['unchanged'])} | {f(t['v4'])} | {f(t['v4_chartzero'])} |")
        L += ["", "### G1 per-position share move, log(share Full / share Standard), by week (unchanged = 0)", "",
              "| Cell | week | published RB/WR/TE | v4 | v4_chartzero |", "| --- | --- | --- | --- | --- |"]
        for name, cell in G1["cells"].items():
            for w in W:
                sm = cell[w]["share_move_full_over_std"]
                f = lambda d: " / ".join(f"{d[p]:+.3f}" for p in SHARE_POS)
                L.append(f"| {name} | {w} | {f(sm['published'])} | {f(sm['v4'])} | {f(sm['v4_chartzero'])} |")
        L += ["", "### G1 within-position diffs (method minus unchanged) by week, RB / WR / TE", "",
              "| Cell | week | v4 | v4_chartzero |", "| --- | --- | --- | --- |"]
        for name, cell in G1["cells"].items():
            for w in W:
                d = cell[w]["within_diff_by_pos"]
                f = lambda x: " / ".join(f"{x[p]:+.4f}" for p in SHARE_POS)
                L.append(f"| {name} | {w} | {f(d['v4'])} | {f(d['v4_chartzero'])} |")
        L += ["", "Weeks won (original measures, of %d): " % G1["weeks_won_totals_of"] +
              ", ".join(f"{k} {v}" for k, v in G1["weeks_won_totals"].items()), ""]
    if G2:
        L += ["### G2 per position, mean reference (corr, closer)", "",
              "| Subject | method | RB corr | RB closer | WR corr | WR closer | TE corr | TE closer |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        bp = G2["by_position_mean_ref"]
        for subj in rtest.SUBJECTS:
            for m in ("v4", "v4_chartzero", "v2"):
                cells = []
                for p in rtest.POS:
                    r = bp[f"{subj}|{m}|{p}"]
                    cells += [ci(r["corr"]), ci(r["closer"])]
                L.append(f"| {subj} | {m} | " + " | ".join(cells) + " |")
        L += ["", "### G2 level move, log ratio Standard to Full, mean over weeks; weeks closer than unchanged (of %d)" % len(W),
              "", "| Subject, method | WR/RB move | TE/RB move | vs CBS (WR/RB, TE/RB) | vs USA Today | vs mean |",
              "| --- | --- | --- | --- | --- | --- |"]
        sm = G2["level_moves"]["summary"]
        rm = {r: [sm[next(iter(sm))][f"{r}|{q}"]["mean_ref_move"] for q in ("WR/RB", "TE/RB")] for r in rtest.REFS}
        L.append(f"| reference moves | CBS {rm['cbs'][0]:+.3f}, USAT {rm['usatoday'][0]:+.3f}, mean {rm['mean'][0]:+.3f} | "
                 f"CBS {rm['cbs'][1]:+.3f}, USAT {rm['usatoday'][1]:+.3f}, mean {rm['mean'][1]:+.3f} | | | |")
        for key in sorted(sm):
            d = sm[key]
            if key.split("|")[1] not in ("base", "v2", "v4", "v4_chartzero", "v4_mult", "v4_raw", "v4_recg", "v4_assumed"):
                continue
            L.append(f"| {key} | {d['mean|WR/RB']['mean_move']:+.3f} | {d['mean|TE/RB']['mean_move']:+.3f} | " +
                     " | ".join(f"{d[r + '|WR/RB']['weeks_closer_than_unchanged']}, {d[r + '|TE/RB']['weeks_closer_than_unchanged']}"
                                for r in ("cbs", "usatoday", "mean")) + " |")
        v = G2["verdicts"].get("v4_chartzero")
        if v:
            L += ["", f"v4_chartzero G2 verdict: {v['ranking']['verdict']}, levels {v['levels']}"]
        L.append("")
    if G3:
        r = G3["verdicts"]["chartzero"]
        L += [f"### G3 chartzero: {r['overall']} ({r['by_set']})", ""]
        for key, row in G3["cells"].items():
            c = row["chartzero"]
            L.append(f"- {key}: (a) Std {ci(c['a_standard_diff'])}, (a) Full {ci(c['a_ppr_diff'])}, closer "
                     f"{ci(c['closer_diff'])}, levels {row['levels']['chartzero']['verdict']}")
        L.append("")
    if COV:
        L += ["### Chart zero (ppg) vs R_p(s0), mean over weeks; fallbacks counted", "",
              "| Unwind | pos | chart zero | R_p(s0) | fallbacks |", "| --- | --- | --- | --- | --- |"]
        g = {}
        for key, byp in COV["per_chart_week"].items():
            gk = "|".join(key.split("|")[:3])
            for p, c in byp.items():
                g.setdefault((gk, p), []).append(c)
        for (gk, p), cs in g.items():
            zs = [c["chart_zero_ppg"] for c in cs if c["chart_zero_ppg"] is not None]
            rs = [c["R_s0"] for c in cs if c["R_s0"] is not None]
            L.append(f"| {gk} | {p} | {statistics.fmean(zs):.2f} | {statistics.fmean(rs):.2f} | "
                     f"{sum(c['chart_zero_fallback'] for c in cs)} of {len(cs)} |")
        L.append("")
    return L


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", default="5,6,7")
    ap.add_argument("--only", default=None, choices=("g1", "g2", "g3", "cov"))
    a = ap.parse_args(argv)
    W = tuple(int(x) for x in a.weeks.split(","))
    out = HERE / "out" / "v4"
    if W != DEV_WEEKS:
        out = out / ("weeks_" + "_".join(map(str, W)))
    out.mkdir(parents=True, exist_ok=True)
    ctx = R3.load_world()
    model = v4.sm.load_model()
    weeks = {w: v4.Week4(ctx, w, model) for w in W}
    G1 = G2 = G3 = COV = EXT = None
    if a.only in (None, "g1"):
        wkls = {w: lg.load_week(ctx, w) for w in W}
        G1 = g1(ctx, weeks, wkls, W)
        (out / "g1.json").write_text(json.dumps(rnd(G1), indent=1), encoding="utf-8")
        print("G1 totals", G1["weeks_won_totals"], flush=True)
    if a.only in (None, "g2"):
        G2 = g2(ctx, weeks, W)
        (out / "g2.json").write_text(json.dumps(rnd(G2), indent=1, sort_keys=True), encoding="utf-8")
        print("G2", json.dumps({m: v["ranking"]["verdict"] + "/" + v["levels"] for m, v in G2["verdicts"].items()}),
              flush=True)
    if a.only in (None, "g3"):
        G3, ddf_full = g3(ctx, weeks, W)
        (out / "g3.json").write_text(json.dumps(rnd(G3), indent=1), encoding="utf-8")
        print("G3", json.dumps({k: v["overall"] for k, v in G3["verdicts"].items()}), flush=True)
        EXT = extremes(ctx, weeks, W, ddf_full)
        (out / "extremes.json").write_text(json.dumps(rnd(EXT), indent=1), encoding="utf-8")
    if a.only in (None, "cov"):
        COV = coverage(ctx, weeks, W)
        (out / "coverage.json").write_text(json.dumps(rnd(COV), indent=1), encoding="utf-8")
    if a.only is None:
        (out / "summary.md").write_text(summary_md(W, G1, G2, G3, COV, EXT), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
