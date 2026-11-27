#!/usr/bin/env python3
"""JEG-1735: the variants side by side on the consensus metrics (Jeremy, 2026-11-28).

Variants: none (DDF Value, charts only), per_expert (every list one vote, Jeremy's primary),
site_once (a publisher's lists share one vote), grouped (all lists one source beside the
charts). Same inputs and helpers as eddf_evidence.py. Writes
docs/research/data/jeg1735/variants.json. Research only.
Metrics per scoring: leave-one-chart-out agreement (all players and ranked non-QB players),
scramble and drop-one robustness, week-over-week stability, coverage, dispersion,
independence (pairwise agreement of the implied values and an effective source count) and
weight dominance (the share of total weight a single publisher holds).
"""
import itertools
import json
import random
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eddf_evidence as E  # noqa: E402

eddf, vr = E.eddf, E.vr
OUT = E.OUT
PERMS = 15


def values_for(variant, cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks):
    if variant == "none":
        return E.eddf.chart_only({c: wm[weeks[0]][c] for c in charts}, pos_of)
    r = E.run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks, variant=variant)
    return {pk: v["value"] for pk, v in r["values"].items()}


def main():
    as_of = date(2026, 11, 27)
    cfg = eddf.load_config()
    raw = json.loads((OUT / "lists.json").read_text())
    inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
    hist = vr.History(vr.REPO / "data/history")
    rng = random.Random(11)
    variants = ["none", "per_expert", "site_once", "grouped"]
    report = {"as_of": as_of.isoformat(), "variants": variants, "scorings": {}}
    for scoring in E.SCORINGS:
        lists = {rid: {int(pk): r for pk, r in d[scoring]["ranks"].items()} for rid, d in raw.items() if scoring in d}
        vint = {rid: d[scoring]["vintage"] for rid, d in raw.items() if scoring in d}
        weeks = [12, 11, 10]
        wm, charts, pos_of, _, _ = E.adjusted_by_week(inp, hist, scoring, weeks)
        base = E.run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks)
        fresh = [s["id"] for s in base["report"]["rankers"] if s["in"]]
        ranked = {pk for rid in fresh for pk in lists[rid]}
        groups = {r["id"]: r.get("group", r["id"]) for r in cfg["rankers"]}
        sec = {"fresh": len(fresh), "charts": charts, "variants": {}}
        full = {v: values_for(v, cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks) for v in variants}
        for v in variants:
            row = {}
            # leave one chart out
            loo = []
            for h in charts:
                others = [c for c in charts if c != h]
                vals = values_for(v, cfg, others, wm, lists, vint, pos_of, as_of, scoring, weeks)
                P = [pk for pk in wm[weeks[0]][h] if pk in vals and any(pk in wm[weeks[0]][o] for o in others)]
                R = [pk for pk in P if pk in ranked and pos_of.get(pk) != "QB"]
                y = [wm[weeks[0]][h][pk] for pk in P]
                yr = [wm[weeks[0]][h][pk] for pk in R]
                loo.append((E.spearman([vals[p] for p in P], y), E.mae([vals[p] for p in P], y),
                            E.spearman([vals[p] for p in R], yr), E.mae([vals[p] for p in R], yr)))
            row["loo"] = {"rho": st.mean(x[0] for x in loo), "mae": st.mean(x[1] for x in loo),
                          "ranked_rho": st.mean(x[2] for x in loo), "ranked_mae": st.mean(x[3] for x in loo)}
            # robustness
            drops, scr = [], []
            for h in charts:
                rest = [c for c in charts if c != h]
                d = values_for(v, cfg, rest, wm, lists, vint, pos_of, as_of, scoring, weeks)
                P = [pk for pk in full[v] if pk in d]
                drops.append((E.mae([full[v][p] for p in P], [d[p] for p in P]), E.spearman([full[v][p] for p in P], [d[p] for p in P])))
                for k in range(PERMS):  # the same permutations for every variant; one draw is too noisy
                    shuf = dict(wm[weeks[0]][h])
                    pks, vals_ = list(shuf), list(shuf.values())
                    random.Random(f"{scoring}:{h}:{k}").shuffle(vals_)
                    wm2 = {w: ({**m, h: dict(zip(pks, vals_))} if w == weeks[0] else m) for w, m in wm.items()}
                    sv = values_for(v, cfg, charts, wm2, lists, vint, pos_of, as_of, scoring, weeks)
                    P = [pk for pk in full[v] if pk in sv]
                    scr.append((E.mae([full[v][p] for p in P], [sv[p] for p in P]), E.spearman([full[v][p] for p in P], [sv[p] for p in P])))
            row["drop_one"] = {"mae": st.mean(x[0] for x in drops), "rho": st.mean(x[1] for x in drops)}
            row["scramble_one"] = {"mae": st.mean(x[0] for x in scr), "rho": st.mean(x[1] for x in scr)}
            # stability: chart weeks 12 vs 11, lists fixed
            if v == "none":
                prev = E.eddf.chart_only({c: wm[11][c] for c in charts}, pos_of)
            else:
                wm_prev = {w: wm[w] for w in (11, 10)}
                prev = {pk: x["value"] for pk, x in E.eddf.eddf({c: wm[11][c] for c in charts}, lists, vint,
                        [E.chart_mean({c: wm[w][c] for c in charts}) for w in (11, 10)], pos_of, cfg, as_of, scoring, v)["values"].items()}
            none_prev = E.eddf.chart_only({c: wm[11][c] for c in charts}, pos_of)
            P = [pk for pk in full[v] if pk in prev and pk in full["none"] and pk in none_prev]  # the population DDF prices both weeks
            row["stability_mae_week_change"] = E.mae([full[v][p] for p in P], [prev[p] for p in P])
            # coverage and weight dominance
            row["priced"] = len(full[v])
            if v == "none":
                row["chart_weight_share"], row["top_publisher_weight_share"] = 1.0, 0.0
            else:
                rep = E.run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks, variant=v)["report"]
                row["chart_weight_share"] = rep["chart_weight_share"]
                w = eddf.source_weights({**{c: 0 for c in charts}, **{r: 0 for r in fresh}}, groups, v)
                tot = sum(w.values())
                by_group = {}
                for r in fresh:
                    by_group[groups[r]] = by_group.get(groups[r], 0) + w[r]
                top = max(by_group.items(), key=lambda kv: kv[1])
                row["top_publisher_weight_share"] = top[1] / tot
                row["top_publisher"] = top[0]
            sec["variants"][v] = row

        # independence of the views (variant-independent): implied values of fresh rankers
        anchors = eddf.stable_anchors([E.chart_mean({k: wm[w][k] for k in charts}) for w in weeks], cfg["anchor_stability"], cfg["anchor_floor_frac"])
        impl = {r: eddf.implied_values(lists[r], anchors, pos_of, cfg) for r in fresh}
        common = [pk for pk in pos_of if pos_of[pk] != "QB" and all(pk in impl[r] for r in fresh)]
        def pair(a, b):
            return E.spearman([a[p] for p in common], [b[p] for p in common])
        cm = {c: {pk: wm[weeks[0]][c][pk] for pk in common if pk in wm[weeks[0]][c]} for c in charts}
        rr = [pair(impl[a], impl[b]) for a, b in itertools.combinations(fresh, 2)]
        ranks_rr = [E.spearman([lists[a][p] for p in common if p in lists[a] and p in lists[b]], [lists[b][p] for p in common if p in lists[a] and p in lists[b]]) for a, b in itertools.combinations(fresh, 2)]
        cc = []
        for a, b in itertools.combinations(charts, 2):
            P = [p for p in common if p in cm[a] and p in cm[b]]
            cc.append(E.spearman([cm[a][p] for p in P], [cm[b][p] for p in P]))
        rc = []
        for r in fresh:
            for c in charts:
                P = [p for p in common if p in cm[c]]
                rc.append(E.spearman([impl[r][p] for p in P], [cm[c][p] for p in P]))
        n = len(fresh)
        rbar = st.mean(ranks_rr)
        fp = [r for r in fresh if groups[r] == "FantasyPros"]
        fpp = [E.spearman([lists[a][p] for p in common if p in lists[a] and p in lists[b]], [lists[b][p] for p in common if p in lists[a] and p in lists[b]]) for a, b in itertools.combinations(fp, 2)]
        sec["independence"] = {"n_common": len(common), "ranker_pair_rank_rho": rbar, "ranker_pair_implied_rho": st.mean(rr),
                               "chart_pair_rho": st.mean(cc), "ranker_vs_chart_rho": st.mean(rc),
                               "fantasypros_staff_pair_rank_rho": st.mean(fpp) if fpp else None,
                               "effective_independent_rankers": n / (1 + (n - 1) * rbar), "n_rankers": n}
        # dispersion: per-player SD among charts, among ranker implied values
        sd_c, sd_r, gap = [], [], []
        for p in common:
            cs = [cm[c][p] for c in charts if p in cm[c]]
            rs = [impl[r][p] for r in fresh]
            if len(cs) >= 2:
                sd_c.append(st.pstdev(cs))
                sd_r.append(st.pstdev(rs))
                gap.append(abs(st.mean(cs) - st.mean(rs)))
        sec["dispersion"] = {"sd_among_charts": st.mean(sd_c), "sd_among_rankers": st.mean(sd_r), "gap_chart_mean_vs_ranker_mean": st.mean(gap)}
        report["scorings"][scoring] = sec
        print(scoring, "ok")
    (OUT / "variants.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
