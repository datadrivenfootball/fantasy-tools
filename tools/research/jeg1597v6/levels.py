"""v6 EXPLORATORY: how far a typical player's value moves from Full PPR to Standard, by source.

For the top players at each position (by DDF Value at Half; RB/WR 24, TE/QB 12), the median of
value(Standard) / value(Full), per week, then averaged over weeks 5-10 (range across weeks
shown). Sources: DDF's own projection sources (ESPN, CBS ROS, Razzball, Sleeper's own list), the
publishers' own columns (CBS Sports, USA Today), today's FantasyCalc and FantasyPros, v6's
FantasyCalc and FantasyPros, DDF Value and the new metric. Also the per-player agreement
(Spearman, within position) of v6's ratio with the projection sources' mean ratio.
Out: out/levels.json.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v6  # noqa: E402
import evidence as EV  # noqa: E402
import stats5 as st  # noqa: E402

TOP = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
PROJ = ("espn", "cbsros", "razzball")


def per_week(W, ch):
    rows = {s: ch["runs"][s]["rows"] for s in ("standard", "half_ppr", "ppr")}
    new = {s: W.metric(ch, s) for s in ("standard", "half_ppr", "ppr")}
    pos_of = W.ctx["pos_of"]
    _ddf_half = new["half_ppr"][1]

    def src(name, s):
        if name in ("fantasycalc_v6", "fantasypros_v6"):
            return W.chart_list(ch, name.split("_")[0], "v5", s)
        if name == "sleeper_own":
            return ch["ps_adj"][("sleeper_own", s)]
        if name == "ddf_value":
            return new[s][1]
        if name == "scoring_aware_ddf":
            return new[s][0]
        if name == "projections_mean":
            out = {}
            for i, r in rows[s].items():
                vs = [r["adjusted"].get(j) for j in PROJ]
                if all(v is not None for v in vs):
                    out[i] = sum(float(v) for v in vs) / len(vs)
            return out
        return {i: float(r["adjusted"][name]) for i, r in rows[s].items() if r["adjusted"].get(name) is not None}

    names = ("espn", "cbsros", "razzball", "sleeper_own", "projections_mean", "cbs", "usatoday", "fantasycalc",
             "fantasypros", "fantasycalc_v6", "fantasypros_v6", "ddf_value", "scoring_aware_ddf")
    out = {}
    for p, n in TOP.items():
        top = sorted((k for k, v in _ddf_half.items() if v and pos_of.get(k) == p), key=lambda k: -_ddf_half[k])[:n]
        out[p] = {}
        lr = {}
        for name in names:
            lo, hi = src(name, "standard"), src(name, "ppr")
            vals = {k: math.log(lo[k] / hi[k]) for k in top if lo.get(k) and hi.get(k) and lo[k] > 0 and hi[k] > 0}
            lr[name] = vals
            out[p][name] = math.exp(statistics.median(vals.values())) if len(vals) >= 3 else None
        for name in ("fantasycalc_v6", "fantasypros_v6", "scoring_aware_ddf", "ddf_value"):
            ks = [k for k in lr[name] if k in lr["projections_mean"]]
            out[p][f"rho_{name}_vs_projections"] = (st.spearman([lr[name][k] for k in ks], [lr["projections_mean"][k] for k in ks])
                                                   if len(ks) >= 6 else None)
    return out


def main():
    ctx, Ws = v6.load(EV.WEEKS)
    res = {}
    for W in Ws:
        res[W.w] = per_week(W, W.chain(kinds=("v5",)))
    agg = {}
    for p in TOP:
        agg[p] = {}
        for name in res[EV.WEEKS[0]][p]:
            xs = [res[w][p][name] for w in res if res[w][p][name] is not None]
            agg[p][name] = {"mean": statistics.fmean(xs) if xs else None, "min": min(xs) if xs else None,
                            "max": max(xs) if xs else None}
    out = {"label": "EXPLORATORY; weeks 5-10 seen", "per_week": res, "summary": agg}
    (HERE / "out" / "levels.json").write_text(json.dumps(EV.jsonable(out), indent=1))
    for p in TOP:
        print(p, {k: (round(v["mean"], 3) if v["mean"] is not None else None) for k, v in agg[p].items()})


if __name__ == "__main__":
    main()
