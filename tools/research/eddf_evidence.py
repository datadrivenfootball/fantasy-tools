#!/usr/bin/env python3
"""JEG-1735: evidence for EDDF on real Adjusted values, three scorings, 12 teams, one QB.

Research only. Reads the committed fixture and history (the same inputs value_reference.py
computes DDF Value from), config/eddf_sources.json and docs/research/data/jeg1735/lists.json
(rankers' lists, built by tools/research/eddf_prepare.py). Writes
docs/research/data/jeg1735/evidence.json and before_after_<scoring>.csv. Nothing else changes.

Tests, each per scoring:
  loo         leave one chart out: predict the held-out chart's Adjusted value from the others
              (anchors fitted from the other charts only, so nothing of the held-out chart leaks)
  coverage    players priced and by how many sources
  robustness  drop one chart, scramble one chart: how far EDDF moves versus DDF
  stability   week-over-week change with the rankers' lists fixed at the read date; only the
              chart weeks vary (one list date exists, so this is not a test of rankers over time)
  weights     chart weight share and EDDF vs DDF as the ranker count grows; pooled-1/5 compared
Usage: eddf_evidence.py [--as-of 2026-11-27]
"""
import argparse
import csv
import json
import random
import statistics as st
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
import eddf  # noqa: E402
import value_reference as vr  # noqa: E402

OUT = REPO / "docs/research/data/jeg1735"
SCORINGS = ["ppr", "half_ppr", "standard"]
WEEKS_BACK = 3


def load_lists(scoring):
    """({ranker_id: {player_key: rank}}, {ranker_id: vintage}) at one scoring: the FantasyPros-feed
    lists and the candidate files (candidates.json). A ranker with no list at this scoring is simply
    absent here, never given another scoring's list; the registry decides who is enabled."""
    out, vint = {}, {}
    for fname in ("lists.json", "candidates.json"):
        for rid, d in json.loads((OUT / fname).read_text()).items():
            if scoring in d:
                out[rid] = {int(k): v for k, v in d[scoring]["ranks"].items()}
                vint[rid] = d[scoring]["vintage"]
    return out, vint


def ranks_of(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = ranks_of(a), ranks_of(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else None


def mae(a, b):
    return st.mean(abs(x - y) for x, y in zip(a, b))


def adjusted_by_week(inp, hist, scoring, weeks):
    """{week: {chart: {pk: Adjusted}}} on the saved natives of each week, with the same
    pipeline, hold and settings the current week uses (the way prior_result runs the prior week)."""
    s = vr.Setting(inp, scoring, 12, 0, hist=hist)
    state = s.state()
    charts = [k for k in state["included"] if vr.FAMILY[k] == "chart" and k not in state["hidden"]]
    out = {}
    for w in weeks:
        if w == state["current_week"]:
            res = s.result()
        else:
            natives = {}
            for k in vr.SOURCES:
                entry, _ = vr.history_entry(hist, k, w)
                nat = vr.snapshot_natives(inp, k, entry, scoring) if entry else {}
                if nat:
                    natives[k] = nat
            res = vr.run_pipeline(s.league, s._sources(natives), s.pos_of, [k for k in state["included"] if k in natives],
                                  s.selection, lineup=s.lineup, hidden=state.get("hidden"),
                                  promotion_model=s.promotion_model, flex_bench_seats=s.flex_bench_seats, basis=s.basis)
        out[w] = {c: {pk: r["adjusted"][c] for pk, r in res["rows"].items() if r["adjusted"].get(c) is not None}
                  for c in charts}
    return out, charts, s.pos_of, state["current_week"], dict(state["excluded"])


def chart_mean(chart_maps):
    ks = {pk for m in chart_maps.values() for pk in m}
    out = {}
    for pk in ks:
        vs = [m[pk] for m in chart_maps.values() if pk in m]
        out[pk] = sum(vs) / len(vs)
    return out


def run_eddf(cfg, charts, week_maps, lists, vint, pos_of, as_of, scoring, weeks, keep=None, variant="per_expert"):
    """EDDF with `charts` (names) and only the rankers in `keep` (None = all)."""
    c = dict(cfg)
    if keep is not None:
        c = {**cfg, "rankers": [r for r in cfg["rankers"] if r["id"] in keep]}
    hist = [chart_mean({k: week_maps[w][k] for k in charts}) for w in weeks]
    return eddf.eddf({k: week_maps[weeks[0]][k] for k in charts}, lists, vint, hist, pos_of, c, as_of, scoring, variant)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-11-27")
    args = ap.parse_args(argv)
    as_of = date.fromisoformat(args.as_of)
    cfg = eddf.load_config()
    raw = json.loads((OUT / "lists.json").read_text())
    inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
    hist = vr.History(vr.REPO / "data/history")
    rng = random.Random(7)
    report = {"as_of": args.as_of, "config": {k: v for k, v in cfg.items() if k != "rankers"}, "scorings": {}}
    for scoring in SCORINGS:
        lists, vint = load_lists(scoring)
        cw = vr.freshness(inp)["current_week"]
        weeks = [cw - i for i in range(WEEKS_BACK)]
        wm, charts, pos_of, _, excluded = adjusted_by_week(inp, hist, scoring, weeks)
        base = run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks)
        fresh = [s["id"] for s in base["report"]["rankers"] if s["in"]]
        ddf = eddf.chart_only({c: wm[weeks[0]][c] for c in charts}, pos_of)
        e = {pk: v["value"] for pk, v in base["values"].items()}
        sec = {"charts": charts, "charts_excluded": excluded, "weeks": weeks, "report": base["report"]}

        # coverage
        cnt_d = {pk: sum(1 for c in charts if pk in wm[weeks[0]][c]) for pk in pos_of}
        cnt_e = {pk: v["count"] for pk, v in base["values"].items()}
        def tally(cn):
            return {"priced": sum(1 for v in cn.values() if v >= 1), "one_source": sum(1 for v in cn.values() if v == 1),
                    "three_plus": sum(1 for v in cn.values() if v >= 3)}
        sec["coverage"] = {"ddf": tally(cnt_d), "eddf": tally(cnt_e),
                           "eddf_only_priced_by_rankers": sum(1 for pk, v in cnt_e.items() if v and not cnt_d.get(pk))}

        ranked = {pk for rid in fresh for pk in lists[rid]}
        # leave one chart out
        loo = {}
        for variant, exclude in (("QB excluded (default)", ["QB"]), ("QB included", [])):
            c2 = {**cfg, "exclude_positions": exclude}
            rows = []
            for h in charts:
                others = [c for c in charts if c != h]
                if not others:
                    continue
                res = run_eddf(c2, others, wm, lists, vint, pos_of, as_of, scoring, weeks)
                dd = eddf.chart_only({c: wm[weeks[0]][c] for c in others}, pos_of)
                P = [pk for pk in wm[weeks[0]][h] if pk in dd and pk in res["values"]]
                y = [wm[weeks[0]][h][pk] for pk in P]
                a = [dd[pk] for pk in P]
                b = [res["values"][pk]["value"] for pk in P]
                top = [i for i, v in enumerate(y) if v >= 0.25 * max(y)]
                # the research stand-in test scored only players the rankers list: report that too
                rk = [i for i, pk in enumerate(P) if pk in ranked and pos_of.get(pk) != "QB"]
                rows.append({"held_out": h, "n": len(P),
                             "rho_ddf": spearman(a, y), "rho_eddf": spearman(b, y),
                             "mae_ddf": mae(a, y), "mae_eddf": mae(b, y),
                             "ranked_n": len(rk),
                             "ranked_rho_ddf": spearman([a[i] for i in rk], [y[i] for i in rk]),
                             "ranked_rho_eddf": spearman([b[i] for i in rk], [y[i] for i in rk]),
                             "ranked_mae_ddf": mae([a[i] for i in rk], [y[i] for i in rk]),
                             "ranked_mae_eddf": mae([b[i] for i in rk], [y[i] for i in rk]),
                             "top_n": len(top),
                             "top_rho_ddf": spearman([a[i] for i in top], [y[i] for i in top]),
                             "top_rho_eddf": spearman([b[i] for i in top], [y[i] for i in top]),
                             "top_mae_ddf": mae([a[i] for i in top], [y[i] for i in top]) if top else None,
                             "top_mae_eddf": mae([b[i] for i in top], [y[i] for i in top]) if top else None})
            loo[variant] = rows
        sec["loo"] = loo

        # robustness: drop one chart, scramble one chart
        def moved(full, other, keys):
            P = [pk for pk in keys if pk in full and pk in other]
            f, o = [full[pk] for pk in P], [other[pk] for pk in P]
            return {"n": len(P), "mae": mae(f, o), "rho": spearman(f, o)}
        rob = {"drop": [], "scramble": []}
        keys = list(pos_of)
        for h in charts:
            rest = [c for c in charts if c != h]
            d_drop = eddf.chart_only({c: wm[weeks[0]][c] for c in rest}, pos_of)
            e_drop = {pk: v["value"] for pk, v in run_eddf(cfg, rest, wm, lists, vint, pos_of, as_of, scoring, weeks)["values"].items()}
            rob["drop"].append({"chart": h, "ddf": moved(ddf, d_drop, keys), "eddf": moved(e, e_drop, keys)})
            ms = []
            for k in range(15):  # one permutation is too noisy; average 15, same for DDF and EDDF
                shuf = dict(wm[weeks[0]][h])
                pks, vals = list(shuf), list(shuf.values())
                random.Random(f"{scoring}:{h}:{k}").shuffle(vals)
                wm2 = {w: ({**m, h: dict(zip(pks, vals))} if w == weeks[0] else m) for w, m in wm.items()}
                d_s = eddf.chart_only({c: wm2[weeks[0]][c] for c in charts}, pos_of)
                e_s = {pk: v["value"] for pk, v in run_eddf(cfg, charts, wm2, lists, vint, pos_of, as_of, scoring, weeks)["values"].items()}
                ms.append((moved(ddf, d_s, keys), moved(e, e_s, keys)))
            rob["scramble"].append({"chart": h,
                                    "ddf": {"mae": st.mean(a["mae"] for a, _ in ms), "rho": st.mean(a["rho"] for a, _ in ms), "n": ms[0][0]["n"]},
                                    "eddf": {"mae": st.mean(b["mae"] for _, b in ms), "rho": st.mean(b["rho"] for _, b in ms), "n": ms[0][1]["n"]}})
        sec["robustness"] = rob

        # stability: chart weeks 12 vs 11 and 11 vs 10, rankers fixed
        stab = []
        for a_w, b_w, wl_a, wl_b in ((weeks[0], weeks[1], weeks, weeks[1:] + [weeks[-1] - 1]),):
            pass
        d_now = eddf.chart_only({c: wm[weeks[0]][c] for c in charts}, pos_of)
        d_prev = eddf.chart_only({c: wm[weeks[1]][c] for c in charts}, pos_of)
        wk_prev = [weeks[1], weeks[2]]
        e_prev = {pk: v["value"] for pk, v in eddf.eddf(
            {c: wm[weeks[1]][c] for c in charts}, lists, vint,
            [chart_mean({c: wm[w][c] for c in charts}) for w in wk_prev], pos_of, cfg, as_of, scoring)["values"].items()} \
            if len(wk_prev) == 2 else {}
        P = [pk for pk in e if pk in e_prev and pk in d_now and pk in d_prev]
        sec["stability"] = {"n": len(P), "ddf_mae_week_change": mae([d_now[p] for p in P], [d_prev[p] for p in P]),
                            "eddf_mae_week_change": mae([e[p] for p in P], [e_prev[p] for p in P]),
                            "note": "anchor history for the prior week uses only two pulls (weeks 11 and 10)"}

        # weights
        n_c = len(charts)
        wt = []
        for k in sorted({0, 1, 3, 5, 8, 10, len(fresh)} & set(range(len(fresh) + 1))):
            maes, rhos = [], []
            for _ in range(20 if 0 < k < len(fresh) else 1):
                keep = set(rng.sample(fresh, k)) if k else set()
                if k == 0:
                    ev = ddf
                else:
                    ev = {pk: v["value"] for pk, v in run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks, keep=keep)["values"].items()}
                P = [pk for pk in ddf if pk in ev]
                maes.append(mae([ddf[p] for p in P], [ev[p] for p in P]))
                rhos.append(spearman([ddf[p] for p in P], [ev[p] for p in P]))
            wt.append({"rankers": k, "chart_weight_share": n_c / (n_c + k), "mae_vs_ddf": st.mean(maes), "rho_vs_ddf": st.mean(rhos)})
        # pooled alternative: all rankers averaged into one source, then equal weight with the charts
        full_run = run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks)
        ranker_part = {}
        for pk, v in full_run["values"].items():
            pass
        impl = {}
        anchors = eddf.stable_anchors([chart_mean({k: wm[w][k] for k in charts}) for w in weeks], cfg["anchor_stability"], cfg["anchor_floor_frac"])
        for rid in fresh:
            impl[rid] = eddf.implied_values(lists[rid], anchors, pos_of, cfg)
        pooled = {}
        for pk in pos_of:
            cs = [wm[weeks[0]][c][pk] for c in charts if pk in wm[weeks[0]][c]]
            rs = [m[pk] for m in impl.values() if pk in m]
            parts = cs + ([sum(rs) / len(rs)] if rs else [])
            if parts:
                pooled[pk] = sum(parts) / len(parts)
        P = [pk for pk in pooled if pk in e]
        sec["weights"] = {"by_ranker_count": wt, "charts": n_c, "fresh_rankers": len(fresh),
                          "pooled_vs_separate": {"mae": mae([pooled[p] for p in P], [e[p] for p in P]),
                                                 "rho": spearman([pooled[p] for p in P], [e[p] for p in P]),
                                                 "pooled_chart_weight_share": n_c / (n_c + 1)}}

        # before and after
        order_d = sorted(ddf, key=lambda p: -ddf[p])
        order_e = sorted(e, key=lambda p: -e[p])
        rd = {p: i + 1 for i, p in enumerate(order_d)}
        re_ = {p: i + 1 for i, p in enumerate(order_e)}
        names = {pk: (inp.players[pk].get("name") if isinstance(inp.players.get(pk), dict) else str(inp.players.get(pk))) for pk in pos_of}
        with open(OUT / f"before_after_{scoring}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["player_key", "name", "pos", "ddf_value", "eddf_value", "diff", "ddf_rank", "eddf_rank", "sources_ddf", "sources_eddf"])
            for p in order_e:
                if p in ddf or e[p] > 0:
                    w.writerow([p, names.get(p), pos_of[p], round(ddf.get(p, float("nan")), 3), round(e[p], 3),
                                round(e[p] - ddf.get(p, 0), 3), rd.get(p, ""), re_[p], cnt_d.get(p, 0), cnt_e[p]])
        both = [p for p in ddf if p in e]
        sec["before_after"] = {"n": len(both), "rho": spearman([ddf[p] for p in both], [e[p] for p in both]),
                               "mae": mae([ddf[p] for p in both], [e[p] for p in both]),
                               "max_abs_diff": max(abs(ddf[p] - e[p]) for p in both),
                               "top24_overlap": len(set(order_d[:24]) & set(order_e[:24]))}
        report["scorings"][scoring] = sec
        print(scoring, "ok", len(fresh), "fresh rankers", len(charts), "charts")
    (OUT / "evidence.json").write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
