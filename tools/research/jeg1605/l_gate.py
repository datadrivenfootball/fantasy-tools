"""JEG-1605: the L gate and its companions, the anchor estimator, and the
descriptive FantasyCalc / FantasyPros runs (preregistration sections 2-3).

Research only. Spec: docs/research/jeg1605/preregistration.md. H and M are not
built here (stop rule: the lead decides after L).

Run:  /usr/bin/python3 tools/research/jeg1605/l_gate.py
Out:  tools/research/jeg1605/out/l_gate.json
"""
from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V1 = REPO / "tools" / "research" / "jeg1597"
OUT = HERE / "out"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(V1))
sys.path.insert(0, str(REPO / "pipelines"))

import roundtrip as rt  # noqa: E402
import rebuild_ddf as rb  # noqa: E402  (v1 loaders, read-only)
import step4_tests as s4  # noqa: E402  (player_set, spearman)

_spec = importlib.util.spec_from_file_location("jeg1597_fantasycalc_scoring", V1 / "fantasycalc_scoring.py")
fcs = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = fcs
_spec.loader.exec_module(fcs)

vr, dc = rb.vr, rb.dc
WEEKS = (5, 6, 7, 8, 9)
SCORINGS = rt.ANCHOR_SCORINGS
L_CHARTS = ("cbs", "usatoday")
DIRECTIONS = (("standard", "ppr"), ("ppr", "standard"))
M1_POS = ("RB", "WR", "TE")
MIX_POS = ("RB", "TE")
FC_VARIANTS = {"full": {"ppr": 1.0}, "half": {"half_ppr": 1.0}, "half_full": {"half_ppr": 0.5, "ppr": 0.5}}
FP_VARIANTS = {"half": {"half_ppr": 1.0}, "standard": {"standard": 1.0}, "full": {"ppr": 1.0},
               "thirds": {s: 1.0 for s in SCORINGS}}
CAPTURES = {"2026-09-29": 4, "2026-11-07": 9, "2026-11-09": 9}   # capture -> history week used for projections


def r4(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), 4)


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------

def load_ctx():
    inp, hist, team, byes, gp = rb.load_world()
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    live = {s: vr.Setting(inp, s, rb.TEAMS, hist=hist) for s in SCORINGS}
    included = {s: set(live[s].state()["included"]) for s in SCORINGS}
    return {"inp": inp, "hist": hist, "team": team, "byes": byes, "gp": gp, "pos_of": pos_of,
            "name_of": {k: p["name"] for k, p in inp.players.items()}, "live": live, "included": included}


def allocation(ctx, natives, s):
    """N_p(s): value_reference.allocate on the week's mean ppg (as step4_tests.load_world)."""
    pos_of = ctx["pos_of"]
    sources = {k: vr.SourceInput(k, vr.FAMILY[k], {i: float(x) for i, x in natives[k][s].items() if i in pos_of})
               for k in vr.SOURCES}
    inc = [k for k in sources if k in ctx["included"][s]]
    m = vr.mean_ppg(sources, inc)
    order = {p: sorted((i for i in m if pos_of.get(i) == p), key=lambda i: (-m[i], i)) for p in rt.POSITIONS}
    a = vr.allocate(ctx["live"][s].league, order, m, flex_bench_seats=True)
    return {p: int(a[p].get("replacement", a[p]["rostered"])) for p in rt.POSITIONS}


def load_week(ctx, w):
    pos_of = ctx["pos_of"]
    natives, lines = rb.week_inputs(ctx["inp"], ctx["hist"], w)
    games = {k: dc.expected_games(p, w, ctx["byes"].get(ctx["team"].get(k)), ctx["gp"].get(w, {}).get(k))[0]
             for k, p in pos_of.items() if p in rt.POSITIONS}
    # the general projected-points code reproduces v1's at the three scorings
    for s in SCORINGS:
        mine = rt.projected_points(lines, pos_of, games, s)
        v1 = rb.projected_points(lines, pos_of, w, ctx["team"], ctx["byes"], ctx["gp"], s)[0]
        assert mine.keys() == v1.keys() and max(abs(mine[k] - v1[k]) for k in v1) < 1e-9, (w, s)
    ppg_half = {k: v for k in lines if pos_of.get(k) in rt.POSITIONS
                for v in [rt.projected_ppg(lines[k], "half_ppr", pos_of[k])] if v is not None}
    return {"natives": natives, "lines": lines, "games": games, "alloc": {s: allocation(ctx, natives, s) for s in SCORINGS},
            "keys": s4.player_set(ppg_half, pos_of)}


def run_chain(ctx, wk, values, s0, s, **kw):
    return rt.chain(values, ctx["pos_of"], wk["lines"], wk["games"], wk["alloc"][s0], wk["alloc"][s], s0, s, **kw)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def rec_share(lines_k):
    m = rt.player_mix(lines_k or {})
    return None if m is None else m["rec"] / (m["std"] + m["rec"])


def mixed_pairs(ctx, wk, keys, pos):
    sh = {k: rec_share(wk["lines"].get(k)) for k in keys if ctx["pos_of"][k] == pos}
    sh = {k: v for k, v in sh.items() if v is not None}
    order = sorted(sh, key=lambda k: (sh[k], k))
    t = len(order) // 3
    return [(i, j) for i in order[-t:] for j in order[:t]] if t else []


def concordance(pairs, vals, tgt):
    num = den = 0.0
    for i, j in pairs:
        st = tgt[i] - tgt[j]
        if st == 0:
            continue
        sv = vals[i] - vals[j]
        den += 1
        num += 0.5 if sv == 0 else float((sv > 0) == (st > 0))
    return num / den if den else None


def metrics(ctx, wk, keys, vals, inp, tgt):
    pos_of = ctx["pos_of"]
    per = {}
    for p in M1_POS + ("QB",):
        ks = [k for k in keys if pos_of[k] == p]
        per[p] = float(s4.spearman([vals[k] for k in ks], [tgt[k] for k in ks])[0]) if len(ks) >= 3 else None
    within = statistics.fmean(per[p] for p in M1_POS if per[p] is not None)
    whole = float(s4.spearman([vals[k] for k in keys], [tgt[k] for k in keys])[0])
    pos_l = [k for k in keys if vals[k] > 0 and tgt[k] > 0]
    male = statistics.fmean(abs(math.log(vals[k]) - math.log(tgt[k])) for k in pos_l)
    ratio = {p: statistics.median(vals[k] / inp[k] for k in keys if pos_of[k] == p) for p in rt.POSITIONS}
    mix = {}
    allp = []
    for p in MIX_POS:
        pr = mixed_pairs(ctx, wk, keys, p)
        allp += pr
        mix[p] = concordance(pr, vals, tgt)
    mix["RB+TE"] = concordance(allp, vals, tgt)
    mix["n_pairs"] = len(allp)
    return {"within": within, "within_by_pos": per, "whole_set": whole, "male": male, "n_male": len(pos_l),
            "median_ratio_to_input": ratio, "WR_over_RB_level": ratio["WR"] / ratio["RB"], "mixed_pairs": mix}


def rnd(d):
    if isinstance(d, dict):
        return {k: rnd(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [rnd(v) for v in d]
    return r4(d) if isinstance(d, float) else d


# ---------------------------------------------------------------------------
# L and companions
# ---------------------------------------------------------------------------

L_VARIANTS = {
    "chain": {},
    "additive": {"split": "additive"},
    "per_position_curves": {"curve_mode": "per_position"},
    "source_espn": {"mix_sources": ("espn",)},
    "source_cbsros": {"mix_sources": ("cbsros",)},
    "source_razzball": {"mix_sources": ("razzball",)},
}


def chain_info(res):
    return {"b": res.curve.b, "a": res.curve.a, "n_fit": res.curve.n, "resid_sd": res.curve.resid_sd,
            "n_priced": res.n_priced, "fallback": len(res.fallback), "zero_anchor_line": len(res.zero_anchor_line),
            "per_position_b": {p: c.b for p, c in res.curves.items()}, "per_position_on_pooled": res.curve_fallback}


def l_cells(ctx, weeks):
    pos_of = ctx["pos_of"]
    cells = {}
    for chart in L_CHARTS:
        for s0, s in DIRECTIONS:
            cell = {}
            for w in WEEKS:
                wk = weeks[w]
                inp, tgt = wk["natives"][chart][s0], wk["natives"][chart][s]
                keys = [k for k in wk["keys"] if inp.get(k, 0) > 0 and tgt.get(k, 0) > 0]
                row = {"n": len(keys), "unchanged": metrics(ctx, wk, keys, inp, inp, tgt),
                       "published_ratio_target_over_input": {
                           p: statistics.median(tgt[k] / inp[k] for k in keys if pos_of[k] == p) for p in rt.POSITIONS}}
                row["published_WR_over_RB_level"] = (row["published_ratio_target_over_input"]["WR"]
                                                     / row["published_ratio_target_over_input"]["RB"])
                for name, kw in L_VARIANTS.items():
                    res = run_chain(ctx, wk, inp, s0, s, **kw)
                    row[name] = metrics(ctx, wk, keys, res.values, inp, tgt) | {"chain": chain_info(res)}
                # source spread of ratio_i carried as each player's interval
                widths = {p: [] for p in rt.POSITIONS}
                for k in keys:
                    sr = rt.source_ratios(wk["lines"].get(k, {}), s0, s, pos_of[k])
                    if len(sr) >= 2:
                        widths[pos_of[k]].append(max(sr.values()) - min(sr.values()))
                row["source_ratio_interval_width"] = {p: {"median": statistics.median(v) if v else None,
                                                          "max": max(v) if v else None, "n": len(v)}
                                                      for p, v in widths.items()}
                cell[w] = row
            cells[f"{chart}|{s0}->{s}"] = cell
    return cells


def summarize_l(cells):
    out = {"cells": {}, "companions": {}}
    gate = True
    for name, cell in cells.items():
        d = {w: cell[w]["chain"]["within"] - cell[w]["unchanged"]["within"] for w in WEEKS}
        won = sum(v > 0 for v in d.values())
        gate &= won >= 3
        out["cells"][name] = {"weeks_won": won, "diff_by_week": d,
                              "chain_within": {w: cell[w]["chain"]["within"] for w in WEEKS},
                              "unchanged_within": {w: cell[w]["unchanged"]["within"] for w in WEEKS}}
    out["verdict"] = "PASS" if gate else "FAIL"
    # companions
    comp = {}
    for v in L_VARIANTS:
        comp[v] = {}
        for name, cell in cells.items():
            comp[v][name] = {
                "within_diff_vs_unchanged": {w: cell[w][v]["within"] - cell[w]["unchanged"]["within"] for w in WEEKS},
                "weeks_within_won": sum(cell[w][v]["within"] > cell[w]["unchanged"]["within"] for w in WEEKS),
                "xpos_diff_vs_unchanged": {w: cell[w][v]["whole_set"] - cell[w]["unchanged"]["whole_set"] for w in WEEKS},
                "weeks_xpos_won": sum(cell[w][v]["whole_set"] > cell[w]["unchanged"]["whole_set"] for w in WEEKS),
                "male": {w: cell[w][v]["male"] for w in WEEKS},
                "male_unchanged": {w: cell[w]["unchanged"]["male"] for w in WEEKS},
                "weeks_male_better": sum(cell[w][v]["male"] < cell[w]["unchanged"]["male"] for w in WEEKS),
                "median_ratio_chain": {p: statistics.median(cell[w][v]["median_ratio_to_input"][p] for w in WEEKS)
                                       for p in rt.POSITIONS},
                "median_ratio_published": {p: statistics.median(cell[w]["published_ratio_target_over_input"][p]
                                                                for w in WEEKS) for p in rt.POSITIONS},
                "WR_over_RB_chain_by_week": {w: cell[w][v]["WR_over_RB_level"] for w in WEEKS},
                "WR_over_RB_published_by_week": {w: cell[w]["published_WR_over_RB_level"] for w in WEEKS},
                "mixed_pairs_diff_RB+TE": {w: _sub(cell[w][v]["mixed_pairs"]["RB+TE"],
                                                   cell[w]["unchanged"]["mixed_pairs"]["RB+TE"]) for w in WEEKS},
                "mixed_pairs_diff_RB": {w: _sub(cell[w][v]["mixed_pairs"]["RB"], cell[w]["unchanged"]["mixed_pairs"]["RB"])
                                        for w in WEEKS},
                "mixed_pairs_diff_TE": {w: _sub(cell[w][v]["mixed_pairs"]["TE"], cell[w]["unchanged"]["mixed_pairs"]["TE"])
                                        for w in WEEKS},
                "weeks_mixed_won": sum((_sub(cell[w][v]["mixed_pairs"]["RB+TE"],
                                             cell[w]["unchanged"]["mixed_pairs"]["RB+TE"]) or 0) > 0 for w in WEEKS),
            }
    out["companions"] = comp
    out["L_mix_label"] = ("mix-aware helps" if all(comp["chain"][c]["weeks_mixed_won"] >= 3 for c in cells)
                          else "mix-aware does not help (not in >= 3 of 5 weeks in all 4 cells)")
    return out


def _sub(a, b):
    return None if a is None or b is None else a - b


def l_anchor(ctx, weeks):
    """Standard column run as if anchored at Half (a one-step wrong anchor)."""
    out = {}
    for chart in L_CHARTS:
        for s in ("ppr", "standard"):
            rows = {}
            for w in WEEKS:
                wk = weeks[w]
                inp, tgt = wk["natives"][chart]["standard"], wk["natives"][chart][s]
                keys = [k for k in wk["keys"] if inp.get(k, 0) > 0 and tgt.get(k, 0) > 0]
                wrong = run_chain(ctx, wk, inp, "half_ppr", s)
                right = run_chain(ctx, wk, inp, "standard", s)
                mw, mr = metrics(ctx, wk, keys, wrong.values, inp, tgt), metrics(ctx, wk, keys, right.values, inp, tgt)
                rows[w] = {"wrong_within": mw["within"], "right_within": mr["within"], "wrong_whole": mw["whole_set"],
                           "right_whole": mr["whole_set"], "wrong_male": mw["male"], "right_male": mr["male"],
                           "wrong_WR_over_RB": mw["WR_over_RB_level"], "right_WR_over_RB": mr["WR_over_RB_level"]}
            out[f"{chart}|standard col as half->{s}"] = rows
    return out


# ---------------------------------------------------------------------------
# Anchor estimator, identity, descriptive runs
# ---------------------------------------------------------------------------

def estimator_row(ctx, wk, values):
    curves = rt.anchor_residuals(values, ctx["pos_of"], wk["lines"], wk["games"], wk["alloc"])
    return {"winner": rt.estimate_anchor(curves),
            "resid_sd": {s0: c.resid_sd for s0, c in curves.items()},
            "b": {s0: c.b for s0, c in curves.items()},
            "position_level_vs_curve": {s0: {p: math.exp(v) for p, v in c.pos_log_resid.items()}
                                        for s0, c in curves.items()}}


def calibration(ctx, weeks):
    rows, correct, cross = {}, 0, 0
    for chart in L_CHARTS:
        for col in ("standard", "ppr"):
            for w in WEEKS:
                r = estimator_row(ctx, weeks[w], weeks[w]["natives"][chart][col])
                rows[f"{chart}|{col}|{w}"] = r
                correct += r["winner"] == col
                cross += {r["winner"], col} == {"standard", "ppr"}
    info_half = {f"{c}|half_ppr|{w}": estimator_row(ctx, weeks[w], weeks[w]["natives"][c]["half_ppr"])["winner"]
                 for c in L_CHARTS for w in WEEKS}
    passed = correct >= 16 and cross == 0
    return {"correct_of_20": correct, "cross_errors": cross, "pass": passed, "rows": rows,
            "info_half_columns_winner_not_scored": info_half}


def identity(ctx, weeks):
    worst, n = 0.0, 0
    lists = [(c, col) for c in L_CHARTS for col in SCORINGS] + [("fantasycalc", "ppr"), ("fantasypros", "half_ppr")]
    for w in WEEKS:
        wk = weeks[w]
        for c, col in lists:
            for s0 in SCORINGS:
                for kw in ({}, {"split": "additive"}, {"curve_mode": "per_position"}):
                    vals = wk["natives"][c][col]
                    res = run_chain(ctx, wk, vals, s0, s0, **kw)
                    worst = max(worst, max(abs(res.values[k] - vals[k]) for k in res.values))
                    n += 1
    return {"runs": n, "max_abs_diff": worst, "pass": worst < 1e-9}


def describe(ctx, wk, values, variants, primary, published=None):
    """Chain from one list under each anchor variant to every target scoring."""
    pos_of = ctx["pos_of"]
    keys = [k for k in wk["keys"] if values.get(k, 0) > 0]
    out = {}
    prim = {}
    for name, weights in variants.items():
        out[name] = {}
        for s in SCORINGS:
            m = rt.chain_mix(values, weights, pos_of, wk["lines"], wk["games"], wk["alloc"], s)
            vals, iv = m["values"], m["interval"]
            if name == primary:
                prim[s] = vals
            row = {"median_ratio_to_input": {p: statistics.median(vals[k] / values[k] for k in keys if pos_of[k] == p)
                                             for p in rt.POSITIONS},
                   "runs": {s0: chain_info(r) for s0, r in m["runs"].items()},
                   "median_interval_rel_width": statistics.median(
                       (iv[k][1] - iv[k][0]) / vals[k] for k in keys if vals[k] > 0)}
            if published is not None and s in published:
                tgt = published[s]
                ks = [k for k in keys if tgt.get(k, 0) > 0]
                row["vs_own_column"] = {
                    "within_chain": statistics.fmean(float(s4.spearman([vals[k] for k in ks if pos_of[k] == p],
                                                                       [tgt[k] for k in ks if pos_of[k] == p])[0])
                                                     for p in M1_POS),
                    "within_input": statistics.fmean(float(s4.spearman([values[k] for k in ks if pos_of[k] == p],
                                                                       [tgt[k] for k in ks if pos_of[k] == p])[0])
                                                     for p in M1_POS),
                    "own_column_median_ratio_to_input": {p: statistics.median(tgt[k] / values[k] for k in ks
                                                                              if pos_of[k] == p) for p in rt.POSITIONS}}
            out[name][s] = row
    # agreement of each variant with the primary, within position, at each target
    for name in variants:
        if name == primary:
            continue
        for s in SCORINGS:
            m = rt.chain_mix(values, variants[name], pos_of, wk["lines"], wk["games"], wk["alloc"], s)["values"]
            out[name][s]["within_spearman_vs_primary"] = statistics.fmean(
                float(s4.spearman([m[k] for k in keys if pos_of[k] == p], [prim[s][k] for k in keys if pos_of[k] == p])[0])
                for p in M1_POS)
            out[name][s]["median_value_ratio_vs_primary"] = {
                p: statistics.median(m[k] / prim[s][k] for k in keys if pos_of[k] == p and prim[s][k] > 0)
                for p in rt.POSITIONS}
    return out


def te_premium_example(ctx, wk, values):
    res = rt.chain_mix(values, {"ppr": 1.0}, ctx["pos_of"], wk["lines"], wk["games"], wk["alloc"], "ppr_te_premium",
                       n_p_target=wk["alloc"]["ppr"])
    tes = sorted((k for k in values if ctx["pos_of"].get(k) == "TE" and values[k] > 0), key=lambda k: -values[k])[:8]
    return [{"player": ctx["name_of"][k], "full": values[k], "te_premium": res["values"][k]} for k in tes]


def load_captures():
    keys = fcs.name_keys()
    caps = json.loads(fcs.CAPTURES.read_text())
    out = {}
    for c in caps:
        date = c["fetched_at"][:10]
        col = "standard" if c["scoring"] == "standard" else "ppr"
        out.setdefault(date, {})[col] = {keys[fcs.norm(r["name"])]: float(r["value"]) for r in c["rows"]
                                         if fcs.norm(r["name"]) in keys}
    for ppr, col in (("0", "standard"), ("0.5", "half_ppr"), ("1", "ppr")):
        rows = json.loads((fcs.LIVE / f"ppr{ppr}_qb1_t12.json").read_text())
        out.setdefault("2026-11-09", {})[col] = {keys[fcs.norm(r["player"]["name"])]: float(r["value"]) for r in rows
                                                if fcs.norm(r["player"]["name"]) in keys}
    return out


def main():
    OUT.mkdir(exist_ok=True)
    ctx = load_ctx()
    weeks = {w: load_week(ctx, w) for w in sorted(set(WEEKS) | set(CAPTURES.values()))}

    ident = identity(ctx, weeks)
    assert ident["pass"], ident
    cells = l_cells(ctx, weeks)
    L = summarize_l(cells)
    anchor_cost = l_anchor(ctx, weeks)
    calib = calibration(ctx, weeks)

    # FantasyCalc (ppr column) and FantasyPros (half column) through the estimator, weeks 5-9
    est = {}
    for chart, col in (("fantasycalc", "ppr"), ("fantasypros", "half_ppr")):
        rows = {w: estimator_row(ctx, weeks[w], weeks[w]["natives"][chart][col]) for w in WEEKS}
        share = {s0: sum(r["winner"] == s0 for r in rows.values()) / len(WEEKS) for s0 in SCORINGS}
        est[chart] = {"rows": rows, "winner_share": share,
                      "estimated_mix": share if calib["pass"] else "not identified (calibration failed)"}
    caps = load_captures()
    est["fantasycalc_captures"] = {f"{d}|{col}": estimator_row(ctx, weeks[CAPTURES[d]], v)
                                   for d, cols in caps.items() for col, v in cols.items()}

    # descriptive chain runs
    fc_var, fp_var = dict(FC_VARIANTS), dict(FP_VARIANTS)
    if calib["pass"]:
        fc_var["estimated_mix"] = {s: x for s, x in est["fantasycalc"]["winner_share"].items() if x > 0}
        fp_var["estimated_mix"] = {s: x for s, x in est["fantasypros"]["winner_share"].items() if x > 0}
    desc = {"fantasycalc": {}, "fantasypros": {}, "fantasycalc_captures": {}}
    for w in WEEKS:
        wk = weeks[w]
        desc["fantasycalc"][w] = describe(ctx, wk, wk["natives"]["fantasycalc"]["ppr"], fc_var, "full",
                                          published=wk["natives"]["fantasycalc"])
        desc["fantasypros"][w] = describe(ctx, wk, wk["natives"]["fantasypros"]["half_ppr"], fp_var, "half")
    for d, cols in caps.items():
        desc["fantasycalc_captures"][d] = describe(ctx, weeks[CAPTURES[d]], cols["ppr"], fc_var, "full", published=cols)
    te = te_premium_example(ctx, weeks[9], weeks[9]["natives"]["fantasycalc"]["ppr"])

    # fitted b and fallback counts per chart-week (primary anchors)
    b_table, fb_table = {}, {}
    for w in WEEKS:
        wk = weeks[w]
        for chart, col, s0 in [(c, col, col) for c in L_CHARTS for col in ("standard", "ppr")] + [
                ("fantasycalc", "ppr", "ppr"), ("fantasycalc", "ppr", "half_ppr"),
                ("fantasypros", "half_ppr", "half_ppr"), ("fantasypros", "half_ppr", "standard"),
                ("fantasypros", "half_ppr", "ppr")]:
            res = run_chain(ctx, wk, wk["natives"][chart][col], s0, "standard" if s0 != "standard" else "ppr")
            name = f"{chart}|{col} col|anchor {s0}"
            b_table.setdefault(name, {})[w] = {"b": res.curve.b, "n_fit": res.curve.n, "resid_sd": res.curve.resid_sd,
                                               "per_position_b": {p: c.b for p, c in
                                                                  run_chain(ctx, wk, wk["natives"][chart][col], s0, s0,
                                                                            curve_mode="per_position").curves.items()}}
            fb_table.setdefault(name, {})[w] = {"n_priced": res.n_priced, "fallback": len(res.fallback),
                                                "zero_anchor_line": len(res.zero_anchor_line)}
    bs = [v["b"] for t in b_table.values() for v in t.values()]

    out = {
        "spec": "docs/research/jeg1605/preregistration.md",
        "weeks": WEEKS, "n_p": {w: weeks[w]["alloc"] for w in weeks},
        "identity": ident,
        "L": L, "L_cells": cells, "L_anchor": anchor_cost,
        "anchor_estimator": {"calibration": calib, "charts": est},
        "descriptive": desc, "te_premium_example_week9_fantasycalc": te,
        "fitted_b": {"range": [min(bs), max(bs)], "by_chart_week": b_table},
        "fallback_counts": fb_table,
    }
    (OUT / "l_gate.json").write_text(json.dumps(rnd(out), indent=1, default=str), encoding="utf-8")
    print("identity", ident)
    print("L", L["verdict"], {c: (v["weeks_won"], [r4(x) for x in v["diff_by_week"].values()])
                               for c, v in L["cells"].items()})
    print("calibration", calib["correct_of_20"], "cross", calib["cross_errors"], calib["pass"])
    print("b range", r4(min(bs)), r4(max(bs)))


if __name__ == "__main__":
    main()
