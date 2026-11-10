"""JEG-1611 diagnostic follow-up (items 6-7), appended to publisher_moves.json/.md
under 'followup'. Dev weeks 5-7 only; saved snapshots only.

6. G2 'closer' ceiling: response_test's within-position percentile move
   (pct(ppr) - pct(standard)), corr / slope / closer of one publisher's own move
   against the other's, and against the mean reference.
7. Scale convention per column: top-N mean ratio Full/Standard, OLS slope of
   chart value on mean projected ppg per column, and the projected top-N ratio.

Run (after publisher_moves.py):  /usr/bin/python3 tools/research/jeg1611/diag/publisher_moves_followup.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import publisher_moves as pm  # noqa: E402

lg, s4, rt = pm.lg, pm.s4, pm.lg.rt
POS, PUBS, DEV = pm.POS, pm.PUBS, pm.DEV_WEEKS
TOPN = {"RB": 12, "WR": 12, "TE": 6}


def pct(vals):
    x = np.asarray(vals, float)
    return s4.weighted_ranks(x, np.ones(len(x)))[0] / len(x)


def move_stats(m, r, w):
    """response_test.move_stats: corr, slope (m on r), closer = mean(r^2) - mean((m-r)^2)."""
    wm = lambda x: (w * x).sum(1) / w.sum(1)  # noqa: E731
    corr = s4.weighted_pearson(m, r, w)
    mr, mm = wm(r)[:, None], wm(m)[:, None]
    slope = (w * (m - mm) * (r - mr)).sum(1) / (w * (r - mr) ** 2).sum(1)
    closer = wm(r ** 2) - wm((m - r) ** 2)
    return corr, slope, closer


# ---------------------------------------------------------------------------
# Item 6
# ---------------------------------------------------------------------------

def item6(rows, rng):
    W = pm.boot_W([r["k"] for r in rows], rng)          # player-clustered across weeks
    pmove = {}                                           # (pub, row index) -> percentile move
    for q in PUBS:
        mv = np.zeros(len(rows))
        for w in DEV:
            for p in POS:
                ix = [i for i, r in enumerate(rows) if r["w"] == w and r["pos"] == p]
                mv[ix] = pct([rows[i][q]["F"] for i in ix]) - pct([rows[i][q]["S"] for i in ix])
        pmove[q] = mv
    refs = {"cbs": pmove["cbs"], "usatoday": pmove["usatoday"], "mean": 0.5 * (pmove["cbs"] + pmove["usatoday"])}
    cells = {"ref=cbs,method=usatoday": ("cbs", "usatoday"), "ref=usatoday,method=cbs": ("usatoday", "cbs"),
             "ref=mean,method=cbs": ("mean", "cbs"), "ref=mean,method=usatoday": ("mean", "usatoday")}
    out = {}
    for name, (ref, meth) in cells.items():
        out[name] = {}
        for p in POS + ("ALL",):
            per = {"corr": [], "slope": [], "closer": []}
            byweek = {}
            for w in DEV:
                ix = np.array([i for i, r in enumerate(rows) if r["w"] == w and (p == "ALL" or r["pos"] == p)])
                c, s, cl = move_stats(pmove[meth][ix], refs[ref][ix], W[:, ix])
                for k, v in (("corr", c), ("slope", s), ("closer", cl)):
                    per[k].append(v)
                byweek[str(w)] = {"corr": pm.r4(c[0]), "slope": pm.r4(s[0]), "closer": pm.r4(cl[0])}
            out[name][p] = {k: pm.summ(np.mean(v, 0)) for k, v in per.items()} | {"by_week": byweek}
    out["ref_scale"] = {q: {p: {"mean_r2": pm.r4(np.mean([np.mean(pmove[q][[i for i, r in enumerate(rows)
                                                                         if r["w"] == w and r["pos"] == p]] ** 2)
                                                         for w in DEV])),
                                "zero_move_share": pm.r4(np.mean([np.mean(pmove[q][[i for i, r in enumerate(rows)
                                                                              if r["w"] == w and r["pos"] == p]] == 0)
                                                                  for w in DEV]))}
                            for p in POS} for q in PUBS}
    out["note"] = ("pooled = mean of weekly statistics (as response_test.summarize); percentiles within position "
                   "on the common set (l_gate scored set, all four columns > 0), not response_test's top-N set. "
                   "Against ref=mean the method is half of the reference, which inflates corr and closer.")
    return out


# ---------------------------------------------------------------------------
# Item 7
# ---------------------------------------------------------------------------

def ols_slope(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(np.polyfit(x, y, 1)[0]) if len(x) >= 3 else None


def item7(ctx, weeks):
    pos_of = ctx["pos_of"]
    out = {}
    for q in PUBS:
        out[q] = {}
        for p in POS:
            out[q][p] = {}
            for w in DEV:
                wk = weeks[w]
                nat, lines = wk["natives"][q], wk["lines"]
                n = TOPN[p]
                listed = [k for k in nat["standard"] if pos_of.get(k) == p
                          and nat["standard"].get(k, 0) > 0 and nat["ppr"].get(k, 0) > 0]
                topS = sorted((nat["standard"][k] for k in listed), reverse=True)[:n]
                topF = sorted((nat["ppr"][k] for k in listed), reverse=True)[:n]
                d = {"n_listed": len(listed),
                     "top_mean_ratio_F_over_S": pm.r4(np.mean(topF) / np.mean(topS)),
                     "all_mean_ratio_F_over_S": pm.r4(np.mean([nat["ppr"][k] for k in listed])
                                                      / np.mean([nat["standard"][k] for k in listed]))}
                ppg = {s: {k: rt.projected_ppg(lines[k], s, p) for k in listed if k in lines} for s in ("standard", "ppr")}
                sl = {}
                for s in ("standard", "ppr"):
                    ks = [k for k in listed if ppg[s].get(k) is not None]
                    sl[s] = ols_slope([ppg[s][k] for k in ks], [nat[s][k] for k in ks])
                    d[f"n_slope_{s}"] = len(ks)
                d["slope_value_on_ppg_standard"] = pm.r4(sl["standard"])
                d["slope_value_on_ppg_full"] = pm.r4(sl["ppr"])
                d["slope_ratio_F_over_S"] = pm.r4(sl["ppr"] / sl["standard"]) if sl["standard"] else None
                # projected ppg ratio Full/Standard, top-N by the publisher's Standard value
                both = [k for k in listed if ppg["standard"].get(k) and ppg["ppr"].get(k)]
                topk = sorted(both, key=lambda k: (-nat["standard"][k], k))[:n]
                d["proj_top_ratio_F_over_S_pub_top"] = pm.r4(np.mean([ppg["ppr"][k] for k in topk])
                                                             / np.mean([ppg["standard"][k] for k in topk]))
                # projections' own top-N at each scoring (all projected players at the position)
                allp = {s: sorted((v for k, v in ((k, rt.projected_ppg(lines[k], s, p)) for k in lines
                                                  if pos_of.get(k) == p) if v is not None), reverse=True)[:n]
                        for s in ("standard", "ppr")}
                d["proj_top_ratio_F_over_S_proj_own_top"] = pm.r4(np.mean(allp["ppr"]) / np.mean(allp["standard"]))
                out[q][p][str(w)] = d
            keys = [k for k in out[q][p]["5"] if not k.startswith("n_")]
            out[q][p]["mean_weeks"] = {k: pm.r4(np.mean([out[q][p][str(w)][k] for w in DEV])) for k in keys}
    return out


# ---------------------------------------------------------------------------
# Item 8: test-retest (own move next week) vs cross-publisher (same week)
# ---------------------------------------------------------------------------

def item8(rows, rng):
    """Players in the common set in both week w and w + 1 (pairs 5->6, 6->7).
    Moves are de-meaned within (pair, position) on that paired set."""
    by = {(r["w"], r["k"]): r for r in rows}
    pairs = []
    for w in DEV[:-1]:
        for (wk, k), a in by.items():
            b = by.get((w + 1, k))
            if wk == w and b is not None:
                pairs.append({"w": w, "k": k, "pos": a["pos"], "g": f"{w}|{a['pos']}", "a": a, "b": b})
    out = {"n_pairs": len(pairs), "cells": {}}
    specs = {
        "self_cbs_w_vs_w+1": (lambda r: r["a"]["cbs"]["m"], lambda r: r["b"]["cbs"]["m"]),
        "self_usatoday_w_vs_w+1": (lambda r: r["a"]["usatoday"]["m"], lambda r: r["b"]["usatoday"]["m"]),
        "cross_week_w_cbs_vs_usatoday": (lambda r: r["a"]["usatoday"]["m"], lambda r: r["a"]["cbs"]["m"]),
        "cross_week_w+1_cbs_vs_usatoday": (lambda r: r["b"]["usatoday"]["m"], lambda r: r["b"]["cbs"]["m"]),
    }
    labs = [f"{w}->{w + 1}" for w in DEV[:-1]] + ["pooled"]
    for name, (xf, yf) in specs.items():
        out["cells"][name] = {}
        for lab in labs:
            rs = pairs if lab == "pooled" else [r for r in pairs if r["w"] == int(lab.split("->")[0])]
            out["cells"][name][lab] = pm.corr_block(rs, xf, yf, rng, slope=False)
    # robustness: drop players whose S and F are both carried over unchanged by that publisher
    for q in PUBS:
        keep = [r for r in pairs if not (r["a"][q]["S"] == r["b"][q]["S"] and r["a"][q]["F"] == r["b"][q]["F"])]
        out["cells"][f"self_{q}_w_vs_w+1_excl_carried_over"] = {
            "pooled": pm.corr_block(keep, lambda r, q=q: r["a"][q]["m"], lambda r, q=q: r["b"][q]["m"], rng, slope=False)}
    ident = {}
    for q in PUBS:
        ident[q] = {}
        for p in POS + ("ALL",):
            rs = [r for r in pairs if p == "ALL" or r["pos"] == p]
            ident[q][p] = {"n": len(rs),
                           "share_identical_move": pm.r4(np.mean([abs(r["a"][q]["m"] - r["b"][q]["m"]) < 1e-9 for r in rs])),
                           "share_identical_S_and_F": pm.r4(np.mean([r["a"][q]["S"] == r["b"][q]["S"]
                                                                    and r["a"][q]["F"] == r["b"][q]["F"] for r in rs]))}
    out["identical_consecutive"] = ident
    out["note"] = ("common set (l_gate scored set, all four columns > 0) in both weeks; de-meaned within position on "
                   "the paired set; pooled stacks both pairs, player-clustered bootstrap.")
    return out


def item8_md(F8):
    L = ["", "## 8. Test-retest vs cross-publisher (de-meaned move, common set in both weeks)", "", F8["note"],
         f"Pairs: {F8['n_pairs']} player-week pairs.", "",
         "| Cell | Weeks | Pos | n | Spearman | Pearson |", "| --- | --- | --- | --- | --- | --- |"]
    for name, by in F8["cells"].items():
        for lab, d in by.items():
            for p in POS + ("ALL",):
                L.append(f"| {name} | {lab} | {p} | {d[p]['n']} | {pm.fmt(d[p].get('spearman'))} | "
                         f"{pm.fmt(d[p].get('pearson'))} |")
    L += ["", "| Pub | Pos | n | share identical move | share identical S and F |", "| --- | --- | --- | --- | --- |"]
    for q, by in F8["identical_consecutive"].items():
        for p, d in by.items():
            L.append(f"| {q} | {p} | {d['n']} | {d['share_identical_move']} | {d['share_identical_S_and_F']} |")
    return "\n".join(L) + "\n"


def to_md(F):
    L = ["", "# Follow-up (items 6-7)", "", "## 6. G2 'closer' ceiling (percentile move, common set)", "",
         F["item6"]["note"], "",
         "Unchanged (m = 0) has closer = 0 exactly."]
    L += ["", "Scale: mean r^2 of each publisher's own percentile move (the upper bound of closer) and share of "
          "players whose percentile move is exactly 0:", ""]
    for q in PUBS:
        L.append(f"- {q}: " + ", ".join(f"{p} {d['mean_r2']} (zero {d['zero_move_share']})"
                                         for p, d in F["item6"]["ref_scale"][q].items()))
    L += ["", "| Cell | Pos | corr | slope | closer |", "| --- | --- | --- | --- | --- |"]
    for name in [k for k in F["item6"] if k not in ("note", "ref_scale")]:
        for p in POS + ("ALL",):
            d = F["item6"][name][p]
            L.append(f"| {name} | {p} | {pm.fmt(d['corr'])} | {pm.fmt(d['slope'])} | {pm.fmt(d['closer'])} |")
    L += ["", "## 7. Scale convention per column (mean of weeks 5-7; weekly values in the JSON)", "",
          "| Pub | Pos | top-N value ratio F/S | all-listed value ratio | slope Std | slope Full | slope ratio F/S | "
          "proj ppg top-N ratio (pub top) | proj ppg top-N ratio (proj top) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for q in PUBS:
        for p in POS:
            d = F["item7"][q][p]["mean_weeks"]
            L.append(f"| {q} | {p} | {d['top_mean_ratio_F_over_S']} | {d['all_mean_ratio_F_over_S']} | "
                     f"{d['slope_value_on_ppg_standard']} | {d['slope_value_on_ppg_full']} | {d['slope_ratio_F_over_S']} | "
                     f"{d['proj_top_ratio_F_over_S_pub_top']} | {d['proj_top_ratio_F_over_S_proj_own_top']} |")
    L.append("\nTop-N: 12 for RB and WR, 6 for TE. Slopes: OLS of chart value on mean projected ppg at that "
             "scoring (projection lines as l_gate loads them), players listed > 0 in both columns.")
    out = "\n".join(L) + "\n"
    return out + (item8_md(F["item8"]) if "item8" in F else "")


def main():
    ctx, weeks, hist, ros, _ = pm.load()
    rng = np.random.default_rng(pm.SEED)
    common = pm.build_rows(ctx, weeks, hist, ros, "common")
    F = {"item6": item6(common, rng), "item7": item7(ctx, weeks)}
    F["item8"] = item8(common, rng)
    jp, mp = pm.OUT / "publisher_moves.json", pm.OUT / "publisher_moves.md"
    J = json.loads(jp.read_text())
    J["followup"] = F
    jp.write_text(json.dumps(J, indent=1, default=str))
    md = mp.read_text()
    md = md.split("\n# Follow-up (items 6-7)")[0].rstrip("\n") + "\n"
    mp.write_text(md + to_md(F))
    print("followup written")


if __name__ == "__main__":
    main()
