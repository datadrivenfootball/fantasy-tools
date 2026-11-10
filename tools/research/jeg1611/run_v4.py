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
                 "v4_chartzero": ("share", "chartzero"), "v4_ddfrate": ("share", "ddfrate")}
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
            "chartzero": ("v4_chartzero", "current"), "ddfrate": ("v4_ddfrate", "current")}


def g3_lists(ctx, weeks, W, scorings=("standard", "ppr")):
    lists, ddf_full = {}, {}
    for w in W:
        wk = weeks[w]
        runs = {s: {"current": wk.current(s), "v4": v4.v4_run(wk, s),
                    "v4_fchalf": v4.v4_run(wk, s, fc_variant="fchalf"),
                    "current_noFC": wk.current(s, drop=("fantasycalc",)),
                    "v4_noFC": v4.v4_run(wk, s, drop=("fantasycalc",)),
                    "v4_alloc_half": v4.v4_run(wk, s, alloc="half_fixed"),
                    "v4_chartzero": v4.v4_run(wk, s, form="chartzero"),
                    "v4_ddfrate": v4.v4_run(wk, s, form="ddfrate")} for s in scorings}
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
    for label in ("fchalf", "noFC", "alloc_fixed_half", "chartzero", "ddfrate"):
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
# Iteration 5: review round 1 additions
# ---------------------------------------------------------------------------

ACTUALS = R3.REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
ROS_LAST_WEEK = 9          # realized games of 2026 weeks w..9 (week 9 partial in the file)
ACT_COL = {"standard": "std", "half_ppr": "half_ppr", "ppr": "ppr"}
SIZE_METHODS = ("v1", "v2") + tuple(LIST_VARIANTS) + ("v4_fchalf",)


def wsd(x, w):
    m = rtest.wmean(x, w)
    return np.sqrt(np.maximum(rtest.wmean(x * x, w) - m * m, 0.0))


def boot(n):
    return np.vstack([np.ones(n), s4.bootstrap_counts(n, rtest.N_BOOT, rtest.SEED_BOOT)])


def est_ci(arr):
    return {"est": r4(arr[0]), "ci": [r4(x) for x in s4.interval(arr[1:])]}


def pct_move(by_s, ks):
    return rtest.pct([by_s["ppr"][k] for k in ks]) - rtest.pct([by_s["standard"][k] for k in ks])


def g2_size(ctx, worlds, lists, W):
    """1. sd(method percentile move) / sd(reference move) and the slope of the
    reference move on the method move, per subject and reference."""
    out = {}
    for subj in rtest.SUBJECTS:
        for ref in rtest.REFS:
            sets_w = {w: rtest.player_set(ctx, worlds[w], subj, ref) for w in W}
            units = sorted({k for w in W for p in rtest.POS for k in sets_w[w][p]})
            unit = {k: i for i, k in enumerate(units)}
            Wb = boot(len(units))
            meths = [m for m in SIZE_METHODS if m in lists[W[0]][subj]]
            acc = {m: {"sd_ratio": [], "slope_ref_on_method": [], "closer_norm": []}
                   for m in meths + ["pub_cbs", "pub_usatoday"]}
            for w in W:
                wk, sets = worlds[w], sets_w[w]
                ks_all = [k for p in rtest.POS for k in sets[p]]
                ww = Wb[:, [unit[k] for k in ks_all]]
                rm = np.concatenate([rtest.ref_pct(wk, ref, sets[p], "ppr") - rtest.ref_pct(wk, ref, sets[p], "standard")
                                     for p in rtest.POS])
                movers = {m: np.concatenate([pct_move(lists[w][subj][m], sets[p]) for p in rtest.POS]) for m in meths}
                if ref == "mean":
                    for pub in ("cbs", "usatoday"):
                        movers[f"pub_{pub}"] = np.concatenate([pct_move(wk["natives"][pub], sets[p]) for p in rtest.POS])
                for m, mv in movers.items():
                    acc[m]["sd_ratio"].append(wsd(mv, ww) / wsd(rm, ww))
                    er2 = rtest.wmean(rm * rm, ww)
                    acc[m]["closer_norm"].append((er2 - rtest.wmean((mv - rm) ** 2, ww)) / er2)
                    mm, mr = rtest.wmean(mv, ww)[:, None], rtest.wmean(rm, ww)[:, None]
                    cov = (ww * (mv - mm) * (rm - mr)).sum(1)
                    var = (ww * (mv - mm) ** 2).sum(1)
                    with np.errstate(invalid="ignore", divide="ignore"):
                        acc[m]["slope_ref_on_method"].append(cov / var)
            for m, d in acc.items():
                if not d["sd_ratio"]:
                    continue
                out[f"{subj}|{ref}|{m}"] = {k: est_ci(np.mean(v, axis=0)) for k, v in d.items()}
    return out


def g1_paired(ctx, weeks, wkls, W, methods=tuple(LIST_VARIANTS)):
    """2. Paired player bootstrap of (method within - unchanged within) per
    cell, week and position; cell statistic = mean over weeks of the RB/WR/TE mean."""
    out = {}
    pos_of = ctx["pos_of"]
    for chart in G1_CHARTS:
        for s0, s in G1_DIRECTIONS:
            name = f"{chart}|{s0}->{s}"
            keys_w = {}
            for w in W:
                inp, tgt = weeks[w].natives[chart][s0], weeks[w].natives[chart][s]
                keys_w[w] = [k for k in wkls[w]["keys"] if inp.get(k, 0) > 0 and tgt.get(k, 0) > 0]
            units = sorted({k for w in W for k in keys_w[w]})
            unit = {k: i for i, k in enumerate(units)}
            Wb = boot(len(units))
            for m in methods:
                kind, form = LIST_VARIANTS[m]
                per_week, row = [], {"by_week": {}}
                for w in W:
                    wk = weeks[w]
                    inp, tgt = wk.natives[chart][s0], wk.natives[chart][s]
                    vals = wk.v4_list(chart, s, s0=s0, mixkind=kind, form=form)[0]
                    per_pos = {}
                    for p in SHARE_POS:
                        ks = [k for k in keys_w[w] if pos_of[k] == p]
                        ww = Wb[:, [unit[k] for k in ks]]
                        t = [tgt[k] for k in ks]
                        per_pos[p] = s4.spearman([vals[k] for k in ks], t, ww) - s4.spearman([inp[k] for k in ks], t, ww)
                    avg = np.mean([per_pos[p] for p in SHARE_POS], axis=0)
                    per_week.append(avg)
                    row["by_week"][w] = {"mean_RB_WR_TE": est_ci(avg), **{p: est_ci(v) for p, v in per_pos.items()}}
                row["cell"] = est_ci(np.mean(per_week, axis=0))
                out[f"{name}|{m}"] = row
    return out


def load_actuals():
    import csv
    out = {}
    with ACTUALS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["season"]) == 2026:
                out[(int(r["week"]), int(r["player_key"]))] = {c: float(r[c] or 0) for c in ("std", "half_ppr", "ppr")}
    return out


def ros(actuals, keys, w, s):
    """{key: realized points summed over 2026 weeks w..9} for players with >= 2 ROS game rows."""
    col = ACT_COL[s]
    out = {}
    for k in keys:
        rows = [actuals[(wk, k)][col] for wk in range(w, ROS_LAST_WEEK + 1) if (wk, k) in actuals]
        if len(rows) >= 2:
            out[k] = sum(rows)
    return out


def t8_score(ctx, W, sets_w, lists_w, real_w, comps):
    """Within-position Spearman of each list against realized points (RB/WR/TE
    mean and per position), paired bootstrap; comps = [(a, b)] diffs."""
    pos_of = ctx["pos_of"]
    units = sorted({k for w in W for k in sets_w[w]})
    unit = {k: i for i, k in enumerate(units)}
    Wb = boot(len(units))
    vals = {}
    # a week enters only when every position has >= 3 players with realized points
    Wk = [w for w in W if all(sum(pos_of[k] == p for k in sets_w[w] if k in real_w[w]) >= 3 for p in SHARE_POS)]
    n_by_week = {w: sum(k in real_w[w] for k in sets_w[w]) for w in W}
    if not Wk:
        return {"undefined": "no week with >= 3 realized players at every position", "n_by_week": n_by_week,
                "weeks_used": []}
    for m in lists_w[W[0]]:
        per_w, per_p = [], {p: [] for p in SHARE_POS}
        for w in Wk:
            ks_w = [k for k in sets_w[w] if k in real_w[w]]
            pp = []
            for p in SHARE_POS:
                ks = [k for k in ks_w if pos_of[k] == p]
                r = s4.spearman([lists_w[w][m].get(k, 0.0) for k in ks], [real_w[w][k] for k in ks],
                                Wb[:, [unit[k] for k in ks]])
                per_p[p].append(r)
                pp.append(r)
            per_w.append(np.mean(pp, axis=0))
        vals[m] = {"all": np.mean(per_w, axis=0), **{p: np.mean(v, axis=0) for p, v in per_p.items()}}
    out = {m: {k: est_ci(v) for k, v in d.items()} for m, d in vals.items()}
    out["diffs"] = {f"{a}-{b}": {k: est_ci(vals[a][k] - vals[b][k]) for k in vals[a]} for a, b in comps}
    out["n_by_week"] = n_by_week
    out["weeks_used"] = Wk
    return out


def t8(ctx, weeks, wkls, W):
    """3. Realized rest-of-season points at the target scoring (2026 weeks w..9)."""
    act = load_actuals()
    out = {}
    # (a) G1 publishers
    for chart in G1_CHARTS:
        for s0, s in G1_DIRECTIONS:
            sets_w, lists_w, real_w = {}, {}, {}
            for w in W:
                wk = weeks[w]
                inp, tgt = wk.natives[chart][s0], wk.natives[chart][s]
                sets_w[w] = [k for k in wkls[w]["keys"] if inp.get(k, 0) > 0 and tgt.get(k, 0) > 0
                             and ctx["pos_of"][k] in SHARE_POS]
                lists_w[w] = {"v4": wk.v4_list(chart, s, s0=s0)[0], "unchanged": inp, "published_target": tgt}
                real_w[w] = ros(act, sets_w[w], w, s)
            out[f"G1|{chart}|{s0}->{s}"] = t8_score(ctx, W, sets_w, lists_w, real_w,
                                                     [("v4", "unchanged"), ("published_target", "unchanged"),
                                                      ("v4", "published_target")])
    # (b) G2 subjects, at Standard and at Full
    for subj in rtest.SUBJECTS:
        for s in rtest.TARGETS:
            sets_w, lists_w, real_w = {}, {}, {}
            for w in W:
                wk = weeks[w]
                world = rtest.week_world(ctx, w)
                st = rtest.player_set(ctx, world, subj, "mean")
                sets_w[w] = [k for p in rtest.POS for k in st[p]]
                base = wk.natives[subj][rtest.SUBJECTS[subj]]
                lists_w[w] = {"v4": wk.v4_list(subj, s)[0], "base": base, "today": wk.natives[subj][s]}
                real_w[w] = ros(act, sets_w[w], w, s)
            out[f"G2|{subj}|{s}"] = t8_score(ctx, W, sets_w, lists_w, real_w, [("v4", "base"), ("today", "base")])
    # (c) G3: DDF Value v4 vs current, set = the L-gate projection set (RB/WR/TE)
    for s in rtest.TARGETS:
        sets_w, lists_w, real_w = {}, {}, {}
        for w in W:
            wk = weeks[w]
            sets_w[w] = [k for k in wkls[w]["keys"] if ctx["pos_of"][k] in SHARE_POS]
            lists_w[w] = {"ddf_v4": {k: v or 0.0 for k, v in v4.v4_run(wk, s)["ddf"].items()},
                          "ddf_current": {k: v or 0.0 for k, v in wk.current(s)["ddf"].items()}}
            real_w[w] = ros(act, sets_w[w], w, s)
        out[f"G3|ddf|{s}"] = t8_score(ctx, W, sets_w, lists_w, real_w, [("ddf_v4", "ddf_current")])
    return out


def overshoot(ctx, weeks, W, G1, G2, meth="v4"):
    """4. Cells where both publishers' own moves lie on the same side: does v4
    lie beyond both? (Standard-to-Full orientation.)"""
    items = []
    lvw = G2["levels_by_week"]
    for w in W:
        bw = lvw[w]
        for subj in rtest.SUBJECTS:
            for q in ("WR/RB", "TE/RB"):
                a, b = bw["ref_move"]["cbs"][q], bw["ref_move"]["usatoday"][q]
                items.append({"kind": "level_move", "week": w, "subject": subj, "measure": q, "cbs": a,
                              "usatoday": b, "v4": bw[f"{subj}|{meth}"]["move"][q]})
            # median Full/Standard ratio per position over the subject's G2 mean set
            world = rtest.week_world(ctx, w)
            st = rtest.player_set(ctx, world, subj, "mean")
            kind, form = LIST_VARIANTS[meth]
            v_std = weeks[w].v4_list(subj, "standard", mixkind=kind, form=form)[0]
            v_ppr = weeks[w].v4_list(subj, "ppr", mixkind=kind, form=form)[0]
            nat = weeks[w].natives
            for p in rtest.POS:
                ks = st[p]
                med = lambda d1, d2: statistics.median(d2[k] / d1[k] for k in ks if d1[k] > 0 and d2[k] > 0)
                items.append({"kind": "median_ratio", "week": w, "subject": subj, "measure": p,
                              "cbs": med(nat["cbs"]["standard"], nat["cbs"]["ppr"]),
                              "usatoday": med(nat["usatoday"]["standard"], nat["usatoday"]["ppr"]),
                              "v4": med(v_std, v_ppr), "side_ref": 1.0})
    # G1 rebuilt columns: v4 median ratio vs both publishers' published ratios (S->F orientation)
    for w in W:
        for s0, s in G1_DIRECTIONS:
            pub = {c: G1["cells"][f"{c}|{s0}->{s}"][w]["published_median_ratio"] for c in G1_CHARTS}
            for c in G1_CHARTS:
                reb = G1["cells"][f"{c}|{s0}->{s}"][w][meth]["median_ratio_to_input"]
                for p in SHARE_POS:
                    inv = (lambda x: x) if s == "ppr" else (lambda x: 1.0 / x)
                    items.append({"kind": f"G1_median_ratio|{c}|{s0}->{s}", "week": w, "subject": c, "measure": p,
                                  "cbs": inv(pub["cbs"][p]), "usatoday": inv(pub["usatoday"][p]),
                                  "v4": inv(reb[p]), "side_ref": 1.0})
    same, beyond = [], []
    for it in items:
        o = it.get("side_ref", 0.0)
        a, b, v = it["cbs"] - o, it["usatoday"] - o, it["v4"] - o
        if a * b > 0:
            same.append(it)
            it["beyond_both"] = (v > max(a, b)) if a > 0 else (v < min(a, b))
            if it["beyond_both"]:
                beyond.append(it)
    return {"n_items": len(items), "n_same_side": len(same), "n_v4_beyond_both": len(beyond),
            "same_side_items": same, "all_items": items}


def publisher_move_sd(G2, W):
    """5. Week-to-week SD of each publisher's own log WR/RB and TE/RB move."""
    lvw = G2["levels_by_week"]
    out = {}
    for q in ("WR/RB", "TE/RB"):
        var = []
        for r in ("cbs", "usatoday"):
            xs = [lvw[w]["ref_move"][r][q] for w in W]
            sd = statistics.stdev(xs)
            out[f"{r}|{q}"] = {"moves": xs, "sd": sd}
            var.append(sd * sd)
        out[f"pooled|{q}"] = {"sd": math.sqrt(statistics.fmean(var))}
    return out


def value_per_point(ctx, weeks, W):
    """6. OLS slope of Adjusted on ppg per position (players with Adjusted > 0)
    for each projection in today's runs at Standard and Full, ratio Full /
    Standard; the same for the rebuilt v4 FantasyCalc / FantasyPros Adjusted on P_i(s)."""
    out = {"projections": {}, "v4_charts": {}}
    for w in W:
        wk = weeks[w]
        slopes = {}
        for s in ("standard", "ppr"):
            dg = wk.current(s)
            for j, by in dg["pairs"].items():
                for p in v4.POSITIONS:
                    pr = [(x, a) for x, a in by[p] if a > 0]
                    slopes[(j, p, s)] = uw.ols_slope([x for x, _ in pr], [a for _, a in pr])
            run = v4.v4_run(wk, s)
            for c in ("fantasycalc", "fantasypros"):
                u = wk.unwound(c)[0]
                recs = run["charts"][c]
                for p in v4.POSITIONS:
                    pr = []
                    for i, r in u.records.items():
                        if r["pos"] == p and r["label"] == "invertible" and i in recs and recs[i][2] > 0:
                            pr.append((v4.points_at(r["P0"], r["mix"], s, u.s0), recs[i][2]))
                    slopes[(c, p, s)] = uw.ols_slope([x for x, _ in pr], [a for _, a in pr])
        for (src, p, s), b in slopes.items():
            if s != "ppr":
                continue
            b0 = slopes[(src, p, "standard")]
            key = "v4_charts" if src in ("fantasycalc", "fantasypros") else "projections"
            out[key].setdefault(f"{src}|{p}", {})[w] = {"slope_std": b0, "slope_full": b,
                                                        "ratio_full_over_std": b / b0 if b and b0 else None}
    summ = {}
    for key in ("projections", "v4_charts"):
        for p in v4.POSITIONS:
            rs = [d["ratio_full_over_std"] for k, byw in out[key].items() if k.endswith("|" + p) for d in byw.values()
                  if d["ratio_full_over_std"] is not None]
            summ[f"{key}|{p}"] = statistics.fmean(rs) if rs else None
    out["mean_ratio_full_over_std"] = summ
    out["publishers_quoted_by_lead"] = {"cbs": {"RB": 0.88, "WR": 0.73, "TE": 0.69},
                                        "usatoday": {"RB": 0.88, "WR": 0.70, "TE": 0.65}}
    return out


CALIB_UNWINDS = (("fantasycalc", None), ("fantasypros", None), ("cbs", "standard"), ("cbs", "ppr"),
                 ("usatoday", "standard"), ("usatoday", "ppr"))


def ros_ppg(actuals, keys, w, s):
    col = ACT_COL[s]
    out = {}
    for k in keys:
        rows = [actuals[(wk, k)][col] for wk in range(w, ROS_LAST_WEEK + 1) if (wk, k) in actuals]
        if len(rows) >= 2:
            out[k] = sum(rows) / len(rows)
    return out


def calibration(ctx, weeks, W):
    """7. Realized ROS ppg at the anchor scoring regressed on P_i(s0) (invertible
    RB/WR/TE players, weeks pooled), and on the projections' mean ppg at s0 for
    the same players; Spearman per week (mean over weeks)."""
    act = load_actuals()
    out = {}
    for chart, s0 in CALIB_UNWINDS:
        for p in SHARE_POS:
            xs_c, xs_p, ys, sp_c, sp_p = [], [], [], [], []
            for w in W:
                wk = weeks[w]
                u, _x, dg, _tag = wk.unwound(chart, s0)
                sc = u.s0
                inv = [k for k, r in u.records.items() if r["pos"] == p and r["label"] == "invertible"]
                real = ros_ppg(act, inv, w, sc)
                cw, pw, yw = [], [], []
                for k in inv:
                    pj = [wk.natives[j][sc].get(k) for j in dg["projections"]]
                    pj = [v for v in pj if v is not None and v > 0]
                    if k not in real or not pj:
                        continue
                    cw.append(u.records[k]["P0"])
                    pw.append(sum(pj) / len(pj))
                    yw.append(real[k])
                xs_c += cw
                xs_p += pw
                ys += yw
                if len(yw) >= 3:
                    sp_c.append(float(s4.spearman(cw, yw)[0]))
                    sp_p.append(float(s4.spearman(pw, yw)[0]))
            row = {"n": len(ys)}
            for lab, xs, sp in (("chart_P0", xs_c, sp_c), ("projections_mean_ppg", xs_p, sp_p)):
                b, a, r2 = v4.ols(xs, ys) if len(ys) >= 3 else (None, None, None)
                row[lab] = {"slope": b, "intercept": a, "r2": r2, "spearman_mean_over_weeks": statistics.fmean(sp)
                            if sp else None, "mean_x": statistics.fmean(xs) if xs else None}
            row["mean_realized"] = statistics.fmean(ys) if ys else None
            out[f"{chart}|{weeks[W[0]].unwound(chart, s0)[0].s0}|{p}"] = row
    return out


def exactness(ctx, weeks, W):
    """T2 on the weeks run: identity at s = s0 on every chart-week, mix model and
    form; current DDF reproduced at s0; the fixed-allocation run reproduces the anchor."""
    worst, n, bad = 0.0, 0, []
    ddf_ok = fixed_ok = True
    for w in W:
        wk = weeks[w]
        cases = [(c, s0, "primary") for c in ("cbs", "usatoday", "fantasycalc", "fantasypros")
                 for s0 in R3.SCORINGS] + [("fantasycalc", None, "fchalf")]
        for c, s0, var in cases:
            for kind in v4.MIX_MODELS:
                u, x, _dg, _tag = wk.unwound(c, s0, var, (), kind)
                for form in v4.FORMS:
                    out = wk.v4_list(c, u.s0, s0, var, (), kind, form)[0]
                    d = max(abs(out[k] - x[k]) for k in x)
                    worst = max(worst, d)
                    n += 1
                    if out != x:
                        bad.append([w, c, s0, var, kind, form])
        for s in R3.SCORINGS:
            nat = R3.current_natives(wk.natives, s)
            for c in R3.CHARTS:
                nat[c] = wk.v4_list(c, s, s0=s)[0]
            ddf_ok &= v4.digest4(ctx, R3.run_at(ctx, nat, s), s)["ddf"] == wk.current(s)["ddf"]
            cur = wk.current(s)
            fx = wk.fixed(cur, f"current_{s}", s)
            fixed_ok &= fx["ddf"] == cur["ddf"] and fx["adj"] == cur["adj"] and fx["waiver"] == cur["waiver"]
        ddf_ok &= wk.v4_list("fantasycalc", "ppr")[0] == wk.natives["fantasycalc"]["ppr"]
        ddf_ok &= wk.v4_list("fantasypros", "half_ppr")[0] == wk.natives["fantasypros"]["half_ppr"]
    return {"identity_combinations": n, "identity_max_abs_diff": worst, "identity_not_bitwise": bad,
            "current_ddf_reproduced": bool(ddf_ok), "fixed_allocation_reproduces_anchor": bool(fixed_ok),
            "pass": bool(not bad and ddf_ok and fixed_ok)}


def review1(ctx, weeks, W, G1, G2):
    wkls = {w: lg.load_week(ctx, w) for w in W}
    worlds = {w: rtest.week_world(ctx, w) for w in W}
    lists = {w: add_v4(rtest.adjusted_lists(ctx, worlds[w]), weeks[w]) for w in W}
    print("review: lists", flush=True)
    return {"weeks": list(W), "g2_size": g2_size(ctx, worlds, lists, W), "g1_within_paired": g1_paired(ctx, weeks, wkls, W),
            "t8_realized": t8(ctx, weeks, wkls, W), "overshoot": overshoot(ctx, weeks, W, G1, G2),
            "overshoot_by_method": {m: {k: v for k, v in overshoot(ctx, weeks, W, G1, G2, m).items() if k.startswith("n_")}
                                    for m in LIST_VARIANTS},
            "exactness": exactness(ctx, weeks, W),
            "publisher_move_sd": publisher_move_sd(G2, W), "value_per_point": value_per_point(ctx, weeks, W),
            "calibration": calibration(ctx, weeks, W)}


def summary_review1(W, RV):
    L = ["## Iteration 5 additions (review round 1)", "", "### 1. G2 size: sd(method move) / sd(reference move); slope of reference on method", "",
         "| Subject, reference | method | sd ratio | slope ref on method |", "| --- | --- | --- | --- |"]
    for k, d in RV["g2_size"].items():
        subj, ref, m = k.split("|")
        if m in ("v1", "v2", "v4", "v4_mult", "v4_chartzero", "v4_raw", "v4_recg", "v4_fchalf", "pub_cbs", "pub_usatoday") \
                and (ref == "mean" or m == "v4"):
            L.append(f"| {subj}, {ref} | {m} | {ci(d['sd_ratio'])} | {ci(d['slope_ref_on_method'])} |")
    L += ["", "### 2. G1 within, paired (method minus unchanged), mean over weeks of the RB/WR/TE mean", "",
          "| Cell | v4 | v4_mult | v4_chartzero |", "| --- | --- | --- | --- |"]
    gp = RV["g1_within_paired"]
    for name in dict.fromkeys("|".join(k.split("|")[:2]) for k in gp):
        L.append(f"| {name} | " + " | ".join(ci(gp[f"{name}|{m}"]["cell"]) for m in ("v4", "v4_mult", "v4_chartzero")) + " |")
    L += ["", "v4 per week and position:", ""]
    for name in dict.fromkeys("|".join(k.split("|")[:2]) for k in gp):
        for w, d in gp[f"{name}|v4"]["by_week"].items():
            L.append(f"- {name} wk {w}: mean {ci(d['mean_RB_WR_TE'])}; RB {ci(d['RB'])}, WR {ci(d['WR'])}, TE {ci(d['TE'])}")
    L += ["", "### 3. T8 realized ROS points (2026 weeks w..9, >= 2 games), within-position Spearman", "",
          "| Test | list values (RB/WR/TE mean) | diffs |", "| --- | --- | --- |"]
    for k, d in RV["t8_realized"].items():
        if "undefined" in d:
            L.append(f"| {k} | undefined: {d['undefined']} (n by week {d['n_by_week']}) | |")
            continue
        vals = ", ".join(f"{m} {d[m]['all']['est']:.3f}" for m in d if m not in ("diffs", "n_by_week", "weeks_used"))
        diffs = "; ".join(f"{dk} {ci(dv['all'])}" for dk, dv in d["diffs"].items())
        L.append(f"| {k} | {vals} | {diffs} |")
    o = RV["overshoot"]
    L += ["", f"### 4. Overshoot: {o['n_v4_beyond_both']} of {o['n_same_side']} same-side cells have v4 beyond both "
          f"publishers ({o['n_items']} cells in all)", ""]
    for it in o["same_side_items"]:
        L.append(f"- {it['kind']} wk {it['week']} {it['subject']} {it['measure']}: CBS {it['cbs']:.3f}, USAT "
                 f"{it['usatoday']:.3f}, v4 {it['v4']:.3f}{' BEYOND' if it['beyond_both'] else ''}")
    L += ["", "### 5. Week-to-week SD of the publishers' own level moves", ""]
    for k, d in RV["publisher_move_sd"].items():
        L.append(f"- {k}: sd {d['sd']:.4f}" + (f" (moves {', '.join(f'{x:+.3f}' for x in d['moves'])})" if "moves" in d else ""))
    L += ["", "### 6. Value per point, ratio of Adjusted-on-ppg slopes Full / Standard, mean over weeks and sources", "",
          "| Source | QB | RB | WR | TE |", "| --- | --- | --- | --- | --- |"]
    vp = RV["value_per_point"]["mean_ratio_full_over_std"]
    for key in ("projections", "v4_charts"):
        L.append(f"| {key} | " + " | ".join(f"{vp[f'{key}|{p}']:.3f}" if vp[f'{key}|{p}'] else "n/a" for p in v4.POSITIONS) + " |")
    L.append("| publishers (quoted) | | CBS 0.88, USAT 0.88 | 0.73, 0.70 | 0.69, 0.65 |")
    L += ["", "### 7. Calibration: realized ROS ppg at s0 on chart-implied P_i(s0) vs on the projections' mean ppg", "",
          "| Chart, s0, pos | n | P0 slope | P0 intercept | P0 R^2 | P0 Spearman | proj slope | proj intercept | proj R^2 | proj Spearman | mean P0 / proj / realized |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    g = lambda x, f=".3f": "n/a" if x is None else format(x, f)
    for k, d in RV["calibration"].items():
        c, q = d["chart_P0"], d["projections_mean_ppg"]
        L.append(f"| {k} | {d['n']} | {g(c['slope'])} | {g(c['intercept'], '+.2f')} | {g(c['r2'])} | "
                 f"{g(c['spearman_mean_over_weeks'])} | {g(q['slope'])} | {g(q['intercept'], '+.2f')} | {g(q['r2'])} | "
                 f"{g(q['spearman_mean_over_weeks'])} | {g(c['mean_x'], '.2f')} / {g(q['mean_x'], '.2f')} / "
                 f"{g(d['mean_realized'], '.2f')} |")
    L.append("")
    return L


# ---------------------------------------------------------------------------

def _int_weeks(d):
    return {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in d.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", nargs="+", default=["5,6,7"])
    ap.add_argument("--only", default=None, choices=("g1", "g2", "g3", "cov", "review"))
    ap.add_argument("--out", default=None, help="output directory (default out/v4 or out/v4/weeks_<list>)")
    a = ap.parse_args(argv)
    W = tuple(int(x) for x in ",".join(a.weeks).split(",") if x)
    out = HERE / "out" / "v4"
    if a.out:
        out = Path(a.out)
    elif W != DEV_WEEKS:
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
    RV = None
    if a.only in (None, "review"):
        if G1 is None:
            G1 = json.loads((out / "g1.json").read_text(encoding="utf-8"), object_hook=_int_weeks)
        if G2 is None:
            G2 = json.loads((out / "g2.json").read_text(encoding="utf-8"), object_hook=_int_weeks)
        RV = review1(ctx, weeks, W, G1, G2)
        (out / "review1.json").write_text(json.dumps(rnd(RV), indent=1), encoding="utf-8")
    if a.only is None:
        (out / "summary.md").write_text(summary_md(W, G1, G2, G3, COV, EXT) + "\n" +
                                        "\n".join(summary_review1(W, RV)), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
