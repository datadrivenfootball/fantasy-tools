#!/usr/bin/env python3
"""JEG-1735: pooled vs per-position curves (Jeremy, 2026-11-27: fit per-position curves).

Position bias = mean (EDDF - DDF) by position over the 100 players with the highest DDF Value, and
over every player both price, as enabled, one vote per expert, rescaled to the DDF total. Also the
leave-one-chart-out numbers of both curve modes (the same harness as eddf_variants.py). Writes
docs/research/data/jeg1735/curve_compare.json. Research only.
"""
import json
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eddf_evidence as E  # noqa: E402

eddf, vr, OUT = E.eddf, E.vr, E.OUT
TOP = 100


def main():
    as_of = date(2026, 11, 27)
    base = eddf.load_config()
    inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
    hist = vr.History(vr.REPO / "data/history")
    out = {"as_of": as_of.isoformat(), "top_n": TOP, "scorings": {}}
    for scoring in E.SCORINGS:
        weeks = [12, 11, 10]
        wm, charts, pos_of, _, _ = E.adjusted_by_week(inp, hist, scoring, weeks)
        lists, vint = E.load_lists(scoring)
        ddf = eddf.chart_only({c: wm[12][c] for c in charts}, pos_of)
        top = sorted(ddf, key=lambda p: -ddf[p])[:TOP]
        sec = {}
        for mode in ("pooled", "per_position"):
            cfg = {**base, "curve_mode": mode}
            res = E.run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks)
            e = {pk: v["value"] for pk, v in res["values"].items()}
            bias = {}
            for pos in ("RB", "WR", "TE", "QB"):
                for label, keys in (("top", [p for p in top if pos_of.get(p) == pos]),
                                    ("all", [p for p in ddf if pos_of.get(p) == pos and p in e])):
                    d = [e[p] - ddf[p] for p in keys if p in e]
                    bias[f"{pos}_{label}"] = {"n": len(d), "mean_diff": st.mean(d) if d else None}
            loo = []
            for h in charts:
                others = [c for c in charts if c != h]
                r2 = E.run_eddf(cfg, others, wm, lists, vint, pos_of, as_of, scoring, weeks)
                dd = eddf.chart_only({c: wm[12][c] for c in others}, pos_of)
                P = [pk for pk in wm[12][h] if pk in dd and pk in r2["values"]]
                y = [wm[12][h][p] for p in P]
                loo.append((E.spearman([r2["values"][p]["value"] for p in P], y), E.mae([r2["values"][p]["value"] for p in P], y)))
            sec[mode] = {"bias": bias, "loo_rho": st.mean(x[0] for x in loo), "loo_mae": st.mean(x[1] for x in loo),
                         "rho_vs_ddf": E.spearman([e[p] for p in ddf if p in e], [ddf[p] for p in ddf if p in e])}
        out["scorings"][scoring] = sec
    (OUT / "curve_compare.json").write_text(json.dumps(out, indent=1))
    for sc, s in out["scorings"].items():
        for m, v in s.items():
            b = v["bias"]
            print(sc, m, {k: round(x["mean_diff"], 2) for k, x in b.items() if x["mean_diff"] is not None and k.endswith("top") or k.endswith("all") and k.startswith(("TE", "RB", "WR"))}, round(v["loo_rho"], 3), round(v["loo_mae"], 2), round(v["rho_vs_ddf"], 3))


if __name__ == "__main__":
    main()
