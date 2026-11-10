"""JEG-1610: scoring-aware DDF v3 (unwind Adjusted to points, history mix,
rebuild), gates G1-G3, coverage, robustness and the secondary realized check.

Spec: docs/research/jeg1610/preregistration.md (binding) and its dated
implementation readings. Research only: value_reference.run_pipeline is used
as an unmodified library; saved snapshots only (no live requests).

Run:  /usr/bin/python3 tools/research/jeg1610/run_v3.py
Out:  tools/research/jeg1610/out/{g1,g2,g3,coverage,secondary,extremes}.json, unwind_rows.csv
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
REPO = HERE.parents[2]
OUT = HERE / "out"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "research" / "jeg1605"))

import history as hs  # noqa: E402
import unwind as uw  # noqa: E402
import l_gate as lg  # noqa: E402
import response_test as rtest  # noqa: E402

rt, rb, dc, s4, vr = lg.rt, lg.rb, lg.dc, lg.s4, lg.vr
WEEKS = (5, 6, 7, 8, 9)
SCORINGS = ("standard", "half_ppr", "ppr")
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
ANCHOR = {"fantasycalc": "ppr", "fantasypros": "half_ppr"}
G1_CHARTS = ("cbs", "usatoday")
G1_DIRECTIONS = (("standard", "ppr"), ("ppr", "standard"))
G1_MEASURES = ("within", "levels", "xpos")
G3_REFS = ("cbs", "usatoday")
G3_SETS = ("fantasycalc", "fantasypros")


def r4(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), 4)


def rnd(d):
    if isinstance(d, dict):
        return {str(k): rnd(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [rnd(v) for v in d]
    if isinstance(d, (np.floating, np.integer)):
        d = d.item()
    return r4(d) if isinstance(d, float) else d


# ---------------------------------------------------------------------------
# World and pipeline runs
# ---------------------------------------------------------------------------

def load_world():
    ctx = lg.load_ctx()
    rows = hs.load_rows()
    idmap = hs.load_idmap()
    old, unmapped = hs.load_nflverse_rows(idmap)
    ctx.update(hist_rows=rows, hist_old=old, hist_unmapped=unmapped, cats=hs.load_categories())
    st = {s: ctx["live"][s].state() for s in SCORINGS}
    ctx["inc_list"] = {s: list(st[s]["included"]) for s in SCORINGS}
    ctx["hidden"] = {s: set(st[s]["hidden"]) for s in SCORINGS}
    return ctx


def run_at(ctx, natives_by_src: dict, s: str, drop=()):
    """The unmodified pipeline at s (live league, lineup, included, hidden),
    with the sources in `drop` removed from I and from the inputs."""
    nat = {k: v for k, v in natives_by_src.items() if k not in drop}
    inc = [k for k in ctx["inc_list"][s] if k not in drop]
    return rb.run(ctx["live"][s].league, ctx["live"][s].lineup, nat, ctx["pos_of"], inc, ctx["hidden"][s])


def digest(ctx, res, s):
    """The parts of a pipeline result v3 reads."""
    pos_of = ctx["pos_of"]
    chart_keys = [k for k in res["included"] if vr.FAMILY[k] == "chart" and k not in ctx["hidden"][s]]
    return {"charts": {c: uw.listed_records(res, c, pos_of) for c in CHARTS if c in res["sources"]},
            "pairs": uw.projection_pairs(res, [j for j in uw.PROJ if j in res["included"]], pos_of),
            "adj": {k: dict(r["adjusted"]) for k, r in res["rows"].items()},
            "ddf": {k: r["ddf"]["blended"]["value"] for k, r in res["rows"].items()},
            "chart_keys": chart_keys, "weights": dict(res["ddf_weights"]), "pie": res["pie"]}


def current_natives(natives, s):
    return {src: dict(natives[src][s]) for src in vr.SOURCES}


# ---------------------------------------------------------------------------
# Mixes
# ---------------------------------------------------------------------------

def history_mixes(ctx, w, keys, s0, window="primary"):
    rows = hs.window_rows(ctx["hist_rows"], w, window, ctx["hist_old"])
    stats = hs.player_stats(rows)
    r0 = uw.R_OF[s0]
    return {k: hs.history_mix(stats, k, r0) for k in keys}


def projected_mixes(lines, keys, s0):
    """v2's all-source projected mix in place of history (G1 comparison run)."""
    r0 = uw.R_OF[s0]
    out = {}
    for k in keys:
        m = rt.player_mix(lines.get(k) or {})
        if m is None:
            out[k] = hs.Mix(None, None, 0, "fallback", "rookie_no_rows")
        elif m["std"] + r0 * m["rec"] <= 0:
            out[k] = hs.Mix(m["std"], m["rec"], 0, "fallback", "nonpositive_anchor_points")
        else:
            out[k] = hs.Mix(m["std"], m["rec"], 0, "history", None)
    return out


def unwind_chart(ctx, dg, chart, s0, w, mixes=None, window="primary"):
    recs = dg["charts"][chart]
    if mixes is None:
        mixes = history_mixes(ctx, w, recs.keys(), s0, window)
    return uw.unwind(recs, uw.maps_by_position(dg["pairs"]), mixes, s0)


# ---------------------------------------------------------------------------
# Week container
# ---------------------------------------------------------------------------

class Week:
    """Anchor and target runs of one snapshot week, cached by tag."""

    def __init__(self, ctx, w):
        self.ctx, self.w = ctx, w
        self.natives, self.lines = rb.week_inputs(ctx["inp"], ctx["hist"], w)
        self._runs = {}

    def run(self, tag, natives_by_src, s, drop=()):
        key = (tag, s, tuple(sorted(drop)))
        if key not in self._runs:
            self._runs[key] = digest(self.ctx, run_at(self.ctx, natives_by_src, s, drop), s)
        return self._runs[key]

    def current(self, s, drop=()):
        return self.run("current", current_natives(self.natives, s), s, drop)

    def fc_half_anchor(self, drop=()):
        nat = current_natives(self.natives, "half_ppr")
        nat["fantasycalc"] = dict(self.natives["fantasycalc"]["ppr"])
        return self.run("fc_half_anchor", nat, "half_ppr", drop)

    def anchor(self, chart, variant="primary", drop=()):
        """(digest, s0, x) of the anchor run for a rescaled chart."""
        if chart == "fantasycalc" and variant == "fchalf":
            return self.fc_half_anchor(drop), "half_ppr", dict(self.natives["fantasycalc"]["ppr"])
        s0 = ANCHOR[chart]
        return self.current(s0, drop), s0, dict(self.natives[chart][s0])

    def v3_list(self, chart, s, variant="primary", drop=()):
        dg, s0, x = self.anchor(chart, variant, drop)
        u = unwind_chart(self.ctx, dg, chart, s0, self.w)
        return uw.rebuild(u, s, x), u


def v3_natives(wk: Week, s, fc_variant="primary", drop=()):
    nat = current_natives(wk.natives, s)
    for c in ("fantasycalc", "fantasypros"):
        if c in drop:
            continue
        nat[c] = wk.v3_list(c, s, fc_variant if c == "fantasycalc" else "primary", drop)[0]
    return nat


# ---------------------------------------------------------------------------
# G1
# ---------------------------------------------------------------------------

def hist_share(m):
    if m is None or m.basis != "history" or (m.std + m.rec) == 0:
        return None
    return m.rec / (m.std + m.rec)


def mixed_pairs_hist(ctx, keys, mixes, pos):
    sh = {k: hist_share(mixes.get(k)) for k in keys if ctx["pos_of"][k] == pos}
    sh = {k: v for k, v in sh.items() if v is not None}
    order = sorted(sh, key=lambda k: (sh[k], k))
    t = len(order) // 3
    return [(i, j) for i in order[-t:] for j in order[:t]] if t else []


def g1_measures(ctx, wkl, keys, vals, inp, tgt, rank_only=False):
    m = lg.metrics(ctx, wkl, keys, vals, inp, tgt) if not rank_only else None
    if rank_only:
        pos_of = ctx["pos_of"]
        per = [float(s4.spearman([vals[k] for k in keys if pos_of[k] == p], [tgt[k] for k in keys if pos_of[k] == p])[0])
               for p in lg.M1_POS]
        return {"within": statistics.fmean(per), "xpos": float(s4.spearman([vals[k] for k in keys],
                                                                            [tgt[k] for k in keys])[0]),
                "levels": None}
    return {"within": m["within"], "levels": m["male"], "xpos": m["whole_set"], "within_by_pos": m["within_by_pos"],
            "median_ratio_to_input": m["median_ratio_to_input"], "WR_over_RB_level": m["WR_over_RB_level"],
            "n_levels": m["n_male"]}


def better(measure, a, b):
    if a is None or b is None:
        return None
    return a < b if measure == "levels" else a > b


def g1(ctx, weeks, wkls):
    cells, variants = {}, {}
    neg = 0
    for chart in G1_CHARTS:
        for s0, s in G1_DIRECTIONS:
            name = f"{chart}|{s0}->{s}"
            cell = {}
            for w in WEEKS:
                wk, wkl = weeks[w], wkls[w]
                inp, tgt = wk.natives[chart][s0], wk.natives[chart][s]
                keys = [k for k in wkl["keys"] if inp.get(k, 0) > 0 and tgt.get(k, 0) > 0]
                dg = wk.current(s0)
                x = dict(inp)
                row = {"n": len(keys), "unchanged": g1_measures(ctx, wkl, keys, inp, inp, tgt)}
                mixes = history_mixes(ctx, w, dg["charts"][chart].keys(), s0)
                u = unwind_chart(ctx, dg, chart, s0, w, mixes)
                vals = uw.rebuild(u, s, x)
                neg += sum(vals[k] <= 0 for k in keys)
                row["v3"] = g1_measures(ctx, wkl, keys, vals, inp, tgt)
                row["counts"] = uw.counts(u)
                row["scored_on_fallback"] = sum(u.records[k]["basis"] == "fallback" for k in keys if k in u.records)
                row["scored_not_invertible"] = sum(u.records[k]["label"] != "invertible" for k in keys
                                                   if k in u.records)
                # companions (reported, no verdict)
                comp = {}
                for vname, mx in (("projected_mix", projected_mixes(wk.lines, dg["charts"][chart].keys(), s0)),
                                  ("window_2026_only", history_mixes(ctx, w, dg["charts"][chart].keys(), s0, "2026_only")),
                                  ("window_2015_2026", history_mixes(ctx, w, dg["charts"][chart].keys(), s0, "2015_2026"))):
                    uv = unwind_chart(ctx, dg, chart, s0, w, mx)
                    comp[vname] = g1_measures(ctx, wkl, keys, uw.rebuild(uv, s, x), inp, tgt)
                cur_s = wk.current(s)
                proj = uw.rebuild_proj(u, s, uw.maps_by_position(cur_s["pairs"]))
                pv = {k: proj.get(k, 0.0) for k in keys}
                comp["v3_proj"] = g1_measures(ctx, wkl, keys, pv, inp, tgt, rank_only=True)
                comp["v3_proj_unpriced_in_set"] = sum(k not in proj for k in keys)
                # L-mix extreme pairs by history reception share
                mp = {}
                allp = []
                for p in lg.MIX_POS:
                    pr = mixed_pairs_hist(ctx, keys, mixes, p)
                    allp += pr
                    mp[p] = {"v3": lg.concordance(pr, vals, tgt), "unchanged": lg.concordance(pr, inp, tgt),
                             "n_pairs": len(pr)}
                mp["RB+TE"] = {"v3": lg.concordance(allp, vals, tgt), "unchanged": lg.concordance(allp, inp, tgt),
                               "n_pairs": len(allp)}
                comp["mixed_pairs_history_share"] = mp
                row["companions"] = comp
                cell[w] = row
            cells[name] = cell
    table, gate = {}, True
    for name, cell in cells.items():
        for meas in G1_MEASURES:
            won = sum(bool(better(meas, cell[w]["v3"][meas], cell[w]["unchanged"][meas])) for w in WEEKS)
            gate &= won >= 3
            table[f"{name}|{meas}"] = {"weeks_won": won,
                                       "v3": {w: cell[w]["v3"][meas] for w in WEEKS},
                                       "unchanged": {w: cell[w]["unchanged"][meas] for w in WEEKS}}
            for v in ("projected_mix", "window_2026_only", "window_2015_2026", "v3_proj"):
                a = [better(meas, cell[w]["companions"][v][meas], cell[w]["unchanged"][meas]) for w in WEEKS]
                variants.setdefault(v, {})[f"{name}|{meas}"] = None if any(x is None for x in a) else sum(a)
        mp = [(cell[w]["companions"]["mixed_pairs_history_share"]["RB+TE"]) for w in WEEKS]
        variants.setdefault("mixed_pairs_RB+TE_weeks_won", {})[name] = sum(
            (m["v3"] or 0) > (m["unchanged"] or 0) for m in mp)
    return {"verdict": "PASS" if gate else "FAIL", "rule": "v3 strictly beats unchanged in >= 3 of 5 weeks in all 12 cells",
            "table": table, "variants_weeks_won": variants, "rebuilt_nonpositive_in_scored_sets": neg, "cells": cells}


# ---------------------------------------------------------------------------
# G2 (response test with v3 added)
# ---------------------------------------------------------------------------

def add_v3(lists, wk: Week, drop=()):
    for subj in rtest.SUBJECTS:
        base = lists[subj]["base"]["standard"]
        variants = (("v3", "primary"),) + ((("v3_fchalf", "fchalf"),) if subj == "fantasycalc" else ())
        for name, var in variants:
            lists[subj][name] = {s: {k: wk.v3_list(subj, s, var, drop)[0].get(k, 0.0) for k in base}
                                 for s in rtest.TARGETS}
    return lists


def code_check(ctx, weeks):
    """Largest change in any v3 list when CBS Sports' and USA Today's natives at
    s0 are shuffled within position in the anchor run."""
    worst, worst_rel = 0.0, 0.0
    rng = random.Random(16101)
    for w in WEEKS:
        wk = weeks[w]
        for chart in ("fantasycalc", "fantasypros"):
            s0 = ANCHOR[chart]
            nat = current_natives(wk.natives, s0)
            for ref in ("cbs", "usatoday"):
                d = nat[ref]
                for p in uw.POSITIONS:
                    ks = [k for k in d if ctx["pos_of"].get(k) == p]
                    vals = [d[k] for k in ks]
                    rng.shuffle(vals)
                    d.update(zip(ks, vals))
            dg = digest(ctx, run_at(ctx, nat, s0), s0)
            x = dict(wk.natives[chart][s0])
            u = unwind_chart(ctx, dg, chart, s0, w)
            for s in rtest.TARGETS:
                a = uw.rebuild(u, s, x)
                b = wk.v3_list(chart, s)[0]
                for k in b:
                    dlt = abs(a[k] - b[k])
                    worst = max(worst, dlt)
                    if b[k] > 0:
                        worst_rel = max(worst_rel, dlt / b[k])
    return {"max_abs_change": worst, "max_rel_change": worst_rel,
            "note": "CBS Sports and USA Today natives at s0 enter W and fill-in peers of the anchor run"}


def g2(ctx, weeks):
    worlds = {w: rtest.week_world(ctx, w) for w in WEEKS}
    lists = {w: add_v3(rtest.adjusted_lists(ctx, worlds[w]), weeks[w]) for w in WEEKS}
    print("g2 lists", flush=True)
    main = rtest.run_cells(ctx, worlds, lists, WEEKS)
    worlds_loo = {w: rtest.week_world(ctx, w, loo=True) for w in WEEKS}
    lists_loo = {w: add_v3(rtest.adjusted_lists(ctx, worlds_loo[w]), weeks[w], drop=("cbsros", "cbs"))
                 for w in WEEKS}
    loo = rtest.run_cells(ctx, worlds_loo, lists_loo, WEEKS, refs=("mean", "cbs"))
    print("g2 loo", flush=True)
    plc = {f"{subj}|{ref}|v3": rtest.placebo(ctx, worlds, lists, WEEKS, subj, ref, "v3")
           for subj in rtest.SUBJECTS for ref in rtest.REFS}
    lv = rtest.levels(ctx, worlds, lists, WEEKS)
    ver = {"ranking": rtest.verdict(main, loo, plc, "v3"), "levels": rtest.level_verdict(lv, "v3")}
    # same statistics for v1 / v2 from this rerun, for comparison
    ref_v = {m: {"ranking": rtest.verdict(main, loo, {**plc, **{f"{s}|mean|{m}": rtest.placebo(
        ctx, worlds, lists, WEEKS, s, "mean", m) for s in rtest.SUBJECTS}}, m),
                 "levels": rtest.level_verdict(lv, m)} for m in ("v1", "v2")}
    pick = ("base", "today", "v1", "v2", "v3", "v3_fchalf")
    short = {k: {m: v["methods"][m] for m in pick if m in v["methods"]} | {"info": v["info"]}
             for k, v in main.items()}
    short_loo = {k: {m: v["methods"][m] for m in ("v3",) if m in v["methods"]} for k, v in loo.items()}
    return {"verdict_v3": ver, "verdict_v1_v2_rerun": ref_v, "main": short, "loo": short_loo, "placebo": plc,
            "levels_summary": {k: v for k, v in lv["summary"].items() if k.split("|")[1] in pick},
            "levels_by_week": lv["by_week"], "code_check": code_check(ctx, weeks)}


# ---------------------------------------------------------------------------
# G3 (DDF Value v3 vs current DDF Value)
# ---------------------------------------------------------------------------

def ddf_minus(dg, ref, override=None):
    """{key: mean Adjusted over the run's DDF charts other than ref} (as _ddf)."""
    keys = [k for k in dg["chart_keys"] if k != ref]
    out = {}
    for i, adj in dg["adj"].items():
        vals = []
        for k in keys:
            v = (override or {}).get(k, {}).get(i, adj.get(k))
            if v is not None:
                vals.append(v)
        if vals:
            out[i] = sum(vals) / len(vals)
    return out


def g3_runs(ctx, wk: Week, s):
    """{method: digest} at s, plus v3_proj overrides."""
    out = {"current": wk.current(s), "v3": wk.run("v3", v3_natives(wk, s), s),
           "v3_fchalf": wk.run("v3_fchalf", v3_natives(wk, s, "fchalf"), s),
           "current_noFC": wk.current(s, drop=("fantasycalc",)),
           "v3_noFC": wk.run("v3_noFC", v3_natives(wk, s, drop=("fantasycalc",)), s, drop=("fantasycalc",))}
    maps_s = uw.maps_by_position(out["current"]["pairs"])
    ov = {c: uw.rebuild_proj(wk.v3_list(c, s)[1], s, maps_s) for c in ("fantasycalc", "fantasypros")}
    return out, ov


def g3_lists(ctx, weeks, scorings=("standard", "ppr")):
    lists, ddf_full = {}, {}
    for w in WEEKS:
        wk = weeks[w]
        per_s = {s: g3_runs(ctx, wk, s) for s in scorings}
        for R in G3_REFS:
            d = {}
            for meth in ("current", "v3", "v3_fchalf", "current_noFC", "v3_noFC", "v3_proj"):
                d[meth] = {}
                for s in scorings:
                    runs, ov = per_s[s]
                    if meth == "v3_proj":
                        d[meth][s] = ddf_minus(runs["current"], R, ov)
                    else:
                        d[meth][s] = ddf_minus(runs[meth], R)
            lists[(w, R)] = d
        ddf_full[w] = {s: {"current": per_s[s][0]["current"]["ddf"], "v3": per_s[s][0]["v3"]["ddf"]} for s in scorings}
    return lists, ddf_full


G3_PAIRS = {"primary": ("v3", "current"), "fchalf": ("v3_fchalf", "current"), "noFC": ("v3_noFC", "current_noFC"),
            "v3_proj": ("v3_proj", "current")}


def g3(ctx, weeks):
    worlds = {w: rtest.week_world(ctx, w) for w in WEEKS}
    lists, ddf_full = g3_lists(ctx, weeks)
    res = {}
    for setsubj in G3_SETS:
        for R in G3_REFS:
            sets_w = {w: rtest.player_set(ctx, worlds[w], setsubj, R) for w in WEEKS}
            units = sorted({k for w in WEEKS for p in rtest.POS for k in sets_w[w][p]})
            unit = {k: i for i, k in enumerate(units)}
            W = np.vstack([np.ones(len(units)), s4.bootstrap_counts(len(units), rtest.N_BOOT, rtest.SEED_BOOT)])
            per_week = []
            for w in WEEKS:
                L = {m: {s: {k: v.get(k, 0.0) for p in rtest.POS for k in sets_w[w][p]} for s, v in by.items()}
                     for m, by in lists[(w, R)].items()}
                L["base"] = L["current"]
                L["today"] = L["current"]
                cell, _info, _ = rtest.week_cell(ctx, worlds[w], {setsubj: L}, setsubj, R, W, unit)
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
            # levels: DDF^-R vs R
            lv = {}
            for label, (a, b) in G3_PAIRS.items():
                lower = higher = 0
                for w in WEEKS:
                    nat = worlds[w]["natives"]
                    ref = {s: rtest.level(nat[R][s], ctx["pos_of"]) for s in rtest.TARGETS}
                    err = {}
                    for m in (a, b):
                        mv = {s: rtest.level(lists[(w, R)][m][s], ctx["pos_of"]) for s in rtest.TARGETS}
                        err[m] = sum(abs(math.log(mv[s][q]) - math.log(ref[s][q])) for s in rtest.TARGETS
                                     for q in ("WR/RB", "TE/RB"))
                    lower += err[a] < err[b] - 1e-12
                    higher += err[a] > err[b] + 1e-12
                lv[label] = {"weeks_lower_error": lower, "weeks_higher_error": higher,
                             "verdict": "moves toward" if lower >= 4 else "moves away" if higher >= 4 else "mixed"}
            row["levels"] = lv
            res[f"{setsubj}_set|{R}"] = row
    verdicts = {}
    for label in G3_PAIRS:
        by_set = {}
        for setsubj in G3_SETS:
            rows = [res[f"{setsubj}_set|{R}"][label] for R in G3_REFS]
            good = all(r["a_standard_diff"]["est"] > 0 and rtest.above(r["a_standard_diff"]["ci"])
                       and not rtest.below(r["a_ppr_diff"]["ci"]) and not rtest.below(r["closer_diff"]["ci"])
                       for r in rows)
            bad = any(rtest.below(r["a_standard_diff"]["ci"]) or rtest.below(r["a_ppr_diff"]["ci"])
                      or rtest.below(r["closer_diff"]["ci"]) for r in rows)
            by_set[setsubj] = "better" if good else "worse" if bad else "not shown"
        vs = set(by_set.values())
        overall = "worse" if "worse" in vs else "better" if vs == {"better"} else "not shown"
        verdicts[label] = {"by_set": by_set, "overall": overall}
    hinge = {}
    for label in ("fchalf", "noFC"):
        for key, row in res.items():
            p, q = row["primary"]["a_standard_diff"]["est"], row[label]["a_standard_diff"]["est"]
            hinge[f"{label}|{key}"] = bool(p is not None and q is not None and (p > 0) != (q > 0))
    return {"verdicts": verdicts, "hinges_on_sign_flip_a_standard": hinge, "cells": res}, ddf_full


# ---------------------------------------------------------------------------
# Secondary: realized points (JEG-1601 M1 / M2)
# ---------------------------------------------------------------------------

def secondary(ctx, weeks):
    values = {}
    for w in s4.SNAP_WEEKS:
        wk = weeks[w]
        for s in s4.SCORINGS:
            cur = wk.current(s)["ddf"]
            v3 = wk.run("v3", v3_natives(wk, s), s)["ddf"]
            for m, d in (("DDF_cur", cur), ("DDF_v3", v3)):
                for k, v in d.items():
                    if v:
                        values[(w, s, m, k)] = v
    world = s4.load_world()
    actuals = s4.load_actuals_2026()
    cells = s4.build_cells(world, values, ["DDF_cur", "DDF_v3"], actuals)
    units = sorted({k for c in cells.values() for k in c["keys"]})
    unit_index = {k: i for i, k in enumerate(units)}
    W = s4.bootstrap_counts(len(units))
    ms = s4.metric_samples(cells, ["DDF_cur", "DDF_v3"], unit_index, W)
    return {s: [s4.diff(ms, s, "DDF_v3", "DDF_cur", k) for k in ("M1", "M2", "M1_QB")] for s in ("standard", "ppr")}


# ---------------------------------------------------------------------------
# Coverage, lost in the unwind, extremes
# ---------------------------------------------------------------------------

PRIMARY_UNWINDS = (("fantasycalc", "ppr"), ("fantasypros", "half_ppr"), ("cbs", "standard"), ("cbs", "ppr"),
                   ("usatoday", "standard"), ("usatoday", "ppr"))


def coverage(ctx, weeks, wkls, g2_sets):
    out = {"per_chart_week": {}, "scored_sets_on_fallback": {}, "lost": {}}
    csv_rows = []
    for w in WEEKS:
        wk = weeks[w]
        for chart, s0 in PRIMARY_UNWINDS:
            dg = wk.current(s0)
            u = unwind_chart(ctx, dg, chart, s0, w)
            out["per_chart_week"][f"{chart}|{s0}|{w}"] = uw.counts(u)
            recs = dg["charts"][chart]
            # lost: chart's own cross-position level vs Adjusted share; V vs A
            tot = sum(r["A"] for r in u.records.values())
            adj_share = {p: sum(r["A"] for r in u.records.values() if r["pos"] == p) / tot for p in uw.POSITIONS}
            wts = dg["weights"]
            w_share = {p: wts[f"{p}|starter"] + wts[f"{p}|bench"] for p in uw.POSITIONS}
            nat_share = {}
            ntot = sum(r["x"] for r in u.records.values())
            for p in uw.POSITIONS:
                nat_share[p] = sum(r["x"] for r in u.records.values() if r["pos"] == p) / ntot
            ks = [k for k, r in u.records.items() if r["A"] > 0]
            out["lost"][f"{chart}|{s0}|{w}"] = {
                "below_waiver": sum(r["label"] == "below_waiver" for r in u.records.values()),
                "no_inverse": sum(r["label"] == "no_inverse" for r in u.records.values()),
                "adjusted_share_by_pos": adj_share, "W_share_by_pos": w_share, "native_share_by_pos": nat_share,
                "monotone_violations_A_in_x": uw.monotone_violations(recs),
                "spearman_V_vs_A": float(s4.spearman([u.records[k]["V"] for k in ks], [u.records[k]["A"] for k in ks])[0])
                if len(ks) > 2 else None}
            for k, r in u.records.items():
                csv_rows.append([w, chart, s0, k, ctx["name_of"].get(k), r["pos"], r4(r["x"]), r4(r["A"]), r4(r["V"]),
                                 r["label"], r4(r["P0"]), r["n_proj"], r["basis"], r["reason"] or "", r["games"],
                                 r4(r["std_h"]), r4(r["rec_h"]), r4(r["k"])])
        # scored sets on the fallback
        for chart, s0 in (("cbs", "standard"), ("cbs", "ppr"), ("usatoday", "standard"), ("usatoday", "ppr")):
            u = unwind_chart(ctx, wk.current(s0), chart, s0, w)
            other = "ppr" if s0 == "standard" else "standard"
            keys = [k for k in wkls[w]["keys"] if wk.natives[chart][s0].get(k, 0) > 0
                    and wk.natives[chart][other].get(k, 0) > 0]
            out["scored_sets_on_fallback"][f"G1|{chart}|{s0}|{w}"] = {
                "n": len(keys), "fallback": sum(u.records[k]["basis"] == "fallback" for k in keys)}
        for subj in rtest.SUBJECTS:
            u = wk.v3_list(subj, rtest.TARGETS[0])[1]
            keys = [k for p in rtest.POS for k in g2_sets[w][subj][p]]
            out["scored_sets_on_fallback"][f"G2|{subj}|{w}"] = {
                "n": len(keys), "fallback": sum(u.records[k]["basis"] == "fallback" for k in keys if k in u.records)}
    cats = ctx["cats"]
    out["category_table"] = {"week_rows": cats["week_rows"],
                             "rec_match_vs_actuals": hs.rec_match_report(ctx["hist_rows"], cats),
                             "nflverse_unmapped_2015_2023": ctx["hist_unmapped"]}
    # pooled summary
    agg = {}
    for key, byp in out["per_chart_week"].items():
        chart, s0, _w = key.split("|")
        a = agg.setdefault(f"{chart}|{s0}", {"priced": 0, "history": 0, "below_waiver": 0, "no_inverse": 0,
                                             **{"fallback_" + r: 0 for r in hs.REASONS}})
        for c in byp.values():
            for f in a:
                a[f] += c[f]
    for a in agg.values():
        a["history_share"] = a["history"] / a["priced"] if a["priced"] else None
    out["pooled"] = agg
    return out, csv_rows


def rush_share(cats, k):
    c = hs.per_game_categories(cats, k)
    if not c:
        return None
    tot = hs.category_std_points(c)
    return (0.1 * c["rush_yds"] + 6 * c["rush_td"]) / tot if tot > 0 else None


def extremes(ctx, weeks, g2_sets, ddf_full):
    """Pass-catching backs, receiving tight ends, rushing quarterbacks: v3 move
    (log Full / Standard) beside the references' and current DDF's."""
    out = {}
    cats = ctx["cats"]
    for w in WEEKS:
        wk = weeks[w]
        nat = wk.natives
        rows = {}
        lists = {c: {s: wk.v3_list(c, s)[0] for s in ("standard", "ppr")} for c in ("fantasycalc", "fantasypros")}
        mixes = history_mixes(ctx, w, set(nat["fantasycalc"]["ppr"]) | set(nat["fantasypros"]["half_ppr"]), "ppr")
        pool = {p: sorted({k for subj in rtest.SUBJECTS for k in g2_sets[w][subj].get(p, [])}) for p in ("RB", "TE")}
        qbs = sorted((k for k, v in nat["fantasycalc"]["ppr"].items() if ctx["pos_of"].get(k) == "QB" and v > 0),
                     key=lambda k: -nat["fantasycalc"]["ppr"][k])[:24]

        def lg_move(d_std, d_ppr, k):
            a, b = d_std.get(k), d_ppr.get(k)
            return math.log(b / a) if a and b and a > 0 and b > 0 else None

        def describe(k):
            m = mixes.get(k)
            d = {"player": ctx["name_of"].get(k), "pos": ctx["pos_of"].get(k), "hist_rec_share": hist_share(m),
                 "basis": m.basis if m else None, "rush_share": rush_share(cats, k)}
            for c in ("fantasycalc", "fantasypros"):
                d[f"{c}_v3"] = lg_move(lists[c]["standard"], lists[c]["ppr"], k)
            for c in ("cbs", "usatoday"):
                d[c] = lg_move(nat[c]["standard"], nat[c]["ppr"], k)
            d["ddf_current"] = lg_move(ddf_full[w]["standard"]["current"], ddf_full[w]["ppr"]["current"], k)
            d["ddf_v3"] = lg_move(ddf_full[w]["standard"]["v3"], ddf_full[w]["ppr"]["v3"], k)
            pg = hs.per_game_categories(cats, k)
            if pg:
                d["per_game_categories_2024_2026"] = {c: pg[c] for c in ("rec", "targets", "rec_yds", "rush_yds",
                                                                         "rush_td", "pass_yds", "games")}
            return d
        for p, label in (("RB", "pass_catching_backs"), ("TE", "receiving_tight_ends")):
            ks = [k for k in pool[p] if hist_share(mixes.get(k)) is not None]
            ks.sort(key=lambda k: -hist_share(mixes[k]))
            rows[label] = [describe(k) for k in ks[:6]]
            rows[label.replace("pass_catching", "least_pass_catching").replace("receiving", "least_receiving")] = \
                [describe(k) for k in ks[-6:]]
        qs = [k for k in qbs if rush_share(cats, k) is not None]
        qs.sort(key=lambda k: -rush_share(cats, k))
        rows["rushing_quarterbacks"] = [describe(k) for k in qs[:6]]
        # group means of the move, and the references' for the same players
        summ = {}
        for label, lst in rows.items():
            summ[label] = {f: statistics.fmean(v[f] for v in lst if v.get(f) is not None)
                           if any(v.get(f) is not None for v in lst) else None
                           for f in ("fantasycalc_v3", "fantasypros_v3", "cbs", "usatoday", "ddf_current", "ddf_v3")}
        out[w] = {"players": rows, "group_mean_log_move": summ}
    return out


# ---------------------------------------------------------------------------

def main(only=None):
    OUT.mkdir(exist_ok=True)
    ctx = load_world()
    weeks = {w: Week(ctx, w) for w in WEEKS}
    wkls = {w: lg.load_week(ctx, w) for w in WEEKS}
    if only in (None, "g1"):
        G1 = g1(ctx, weeks, wkls)
        (OUT / "g1.json").write_text(json.dumps(rnd(G1), indent=1), encoding="utf-8")
        print("G1", G1["verdict"])
        for name, row in G1["table"].items():
            print(f"  {name:32s} won {row['weeks_won']}/5")
        if only == "g1":
            return
    G2 = g2(ctx, weeks)
    (OUT / "g2.json").write_text(json.dumps(rnd(G2), indent=1, sort_keys=True), encoding="utf-8")
    print("G2", json.dumps(rnd(G2["verdict_v3"])))
    G3, ddf_full = g3(ctx, weeks)
    (OUT / "g3.json").write_text(json.dumps(rnd(G3), indent=1), encoding="utf-8")
    print("G3", json.dumps(G3["verdicts"]))
    worlds = {w: rtest.week_world(ctx, w) for w in WEEKS}
    g2_sets = {w: {subj: rtest.player_set(ctx, worlds[w], subj, "mean") for subj in rtest.SUBJECTS} for w in WEEKS}
    cov, csv_rows = coverage(ctx, weeks, wkls, g2_sets)
    (OUT / "coverage.json").write_text(json.dumps(rnd(cov), indent=1), encoding="utf-8")
    with (OUT / "unwind_rows.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["week", "chart", "anchor", "player_key", "name", "pos", "x", "adjusted", "vorp_display", "label",
                     "P0_ppg", "n_proj", "mix_basis", "fallback_reason", "games", "std_h", "rec_h", "k"])
        wr.writerows(csv_rows)
    ext = extremes(ctx, weeks, g2_sets, ddf_full)
    (OUT / "extremes.json").write_text(json.dumps(rnd(ext), indent=1), encoding="utf-8")
    sec = secondary(ctx, weeks)
    (OUT / "secondary.json").write_text(json.dumps(rnd(sec), indent=1), encoding="utf-8")
    print("secondary", json.dumps(rnd({s: [(d["metric"], d["diff"], d["ci95"]) for d in v] for s, v in sec.items()})))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
