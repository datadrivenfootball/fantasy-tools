#!/usr/bin/env python3
"""JEG-1735: the consensus study on the candidate sources (Jeremy, 2026-11-28).

Enables candidate rows only inside this harness (registry rows stay disabled). Source sets per
scoring, each run through every weighting variant (none = DDF Value, per_expert, site_once,
grouped, chart_floor) on the same consensus metrics as eddf_variants.py:
  feed          the fresh FantasyPros-feed expert lists (Tuesday rule, 9 on 27 Nov in Half PPR)
  +analyst      feed + the named-analyst candidates that are usable
  +models       feed + the projection-model candidates that are usable
  +all usable   both
A candidate is usable when it is fresh under the stale rule, prices at least `min_anchors` non-QB
players at that scoring, and is not a duplicate. Wolf (duplicate of the feed's Wolf list) and
Footballguys (QBs only, QBs excluded) never enter a set; GWTTKB is stale on the Tuesday rule.
One list date exists (Supabase ros_rankings was not readable, the puller reads only the current
pages), so nothing here tests rankers over time; a bootstrap over players puts an interval on each
leave-one-chart-out difference instead. Writes docs/research/data/jeg1735/study.json.
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

eddf, vr, OUT = E.eddf, E.vr, E.OUT
VARIANTS = ["none", "per_expert", "site_once", "grouped", "chart_floor"]
PERMS = 15
BOOT = 200
ANALYST = ["cand-rotoballer"]
MODELS = ["cand-razzball", "cand-fanduel", "cand-stm", "cand-gwttkb"]
NEVER = {"cand-rsj-wolf": "duplicates the Wolf list already in the feed (same analyst, same date)",
         "cand-footballguys-qb": "QBs only; QBs are excluded from EDDF, so it prices nothing"}


def boot_ci(a, b, y, rng):
    """95% interval of rho(b, y) - rho(a, y) over player resamples."""
    n, diffs = len(y), []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(E.spearman([b[i] for i in idx], [y[i] for i in idx]) - E.spearman([a[i] for i in idx], [y[i] for i in idx]))
    diffs.sort()
    return diffs[int(.025 * BOOT)], diffs[int(.975 * BOOT) - 1]


def main():
    as_of = date(2026, 11, 27)
    cfg0 = eddf.load_config()
    feed = {r["id"]: r for r in cfg0["rankers"] if not r.get("candidate")}
    cand = {r["id"]: r for r in cfg0["rankers"] if r.get("candidate")}
    raw = json.loads((OUT / "lists.json").read_text())
    craw = json.loads((OUT / "candidates.json").read_text())
    inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
    hist = vr.History(vr.REPO / "data/history")
    report = {"as_of": as_of.isoformat(), "variants": VARIANTS, "scorings": {}}
    for scoring in E.SCORINGS:
        weeks = [12, 11, 10]
        wm, charts, pos_of, _, _ = E.adjusted_by_week(inp, hist, scoring, weeks)
        lists = {r: {int(k): v for k, v in d[scoring]["ranks"].items()} for r, d in raw.items() if scoring in d}
        vint = {r: d[scoring]["vintage"] for r, d in raw.items() if scoring in d}
        for r, d in craw.items():
            if scoring in d:
                lists[r] = {int(k): v for k, v in d[scoring]["ranks"].items()}
                vint[r] = d[scoring]["vintage"]
        anchors = eddf.stable_anchors([E.chart_mean({k: wm[w][k] for k in charts}) for w in weeks], cfg0["anchor_stability"], cfg0["anchor_floor_frac"])
        # usability of every candidate at this scoring
        usable, notes = [], {}
        for cid, row in cand.items():
            if cid in NEVER:
                notes[cid] = NEVER[cid]
                continue
            row1 = {**row, "enabled": True}
            stt = eddf.ranker_status(row1, vint.get(cid), as_of, cfg0["stale_days"], scoring, cfg0.get("stale_weekday"))
            if not stt["in"]:
                notes[cid] = stt["reason"]
                continue
            iv = eddf.implied_values(lists[cid], anchors, pos_of, {**cfg0, "rankers": [row1]})
            if not iv:
                notes[cid] = "prices too few non-QB players to fit a curve"
                continue
            usable.append(cid)
            notes[cid] = f"usable: {len(iv)} non-QB players priced, {row['kind'] if 'kind' in row else ''}".rstrip(", ")
        sets = {"feed": [], "+analyst": [c for c in ANALYST if c in usable],
                "+models": [c for c in MODELS if c in usable],
                "+all usable": [c for c in ANALYST + MODELS if c in usable]}
        sec = {"charts": charts, "candidate_notes": notes, "usable": usable, "sets": {}}
        for sname, extra in sets.items():
            if sname != "feed" and not extra:
                continue
            ids = list(feed) + extra
            rows = [{**(feed.get(i) or cand[i]), "enabled": True} for i in ids]
            cfg = {**cfg0, "rankers": rows}
            groups = {r["id"]: r.get("group", r["id"]) for r in rows}
            fresh = [r["id"] for r in rows if eddf.ranker_status(r, vint.get(r["id"]), as_of, cfg0["stale_days"], scoring, cfg0.get("stale_weekday"))["in"]
                     and eddf.implied_values(lists.get(r["id"], {}), anchors, pos_of, cfg)]
            ranked = {pk for rid in fresh for pk in lists[rid] if pos_of.get(pk) != "QB"}

            def vals(variant, chart_set, wm_=wm, hist_weeks=weeks):
                if variant == "none":
                    return eddf.chart_only({c: wm_[hist_weeks[0]][c] for c in chart_set}, pos_of)
                r = E.run_eddf(cfg, chart_set, wm_, lists, vint, pos_of, as_of, scoring, hist_weeks, variant=variant)
                return {pk: v["value"] for pk, v in r["values"].items()}
            full = {v: vals(v, charts) for v in VARIANTS}
            none_prev = eddf.chart_only({c: wm[11][c] for c in charts}, pos_of)
            ssec = {"fresh": len(fresh), "fresh_ids": fresh, "extra": extra, "variants": {}}
            # independence among the fresh lists' implied values and ranks
            impl = {r: eddf.implied_values(lists[r], anchors, pos_of, cfg) for r in fresh}
            common = [pk for pk in pos_of if pos_of[pk] != "QB" and all(pk in lists[r] for r in fresh)]
            if len(common) > 20 and len(fresh) > 1:
                rr = [E.spearman([lists[a][p] for p in common], [lists[b][p] for p in common]) for a, b in itertools.combinations(fresh, 2)]
                rbar = st.mean(rr)
                ssec["independence"] = {"n_common": len(common), "pair_rank_rho": rbar, "effective_views": len(fresh) / (1 + (len(fresh) - 1) * rbar)}
                cm = E.chart_mean({c: wm[12][c] for c in charts})
                sd_c, sd_r = [], []
                for p in common:
                    cs = [wm[12][c][p] for c in charts if p in wm[12][c]]
                    rs = [impl[r][p] for r in fresh if p in impl[r]]
                    if len(cs) >= 2 and len(rs) >= 2:
                        sd_c.append(st.pstdev(cs)); sd_r.append(st.pstdev(rs))
                ssec["dispersion"] = {"sd_charts": st.mean(sd_c), "sd_lists": st.mean(sd_r)}
            for v in VARIANTS:
                row = {}
                loo, ci = [], None
                ys, As, Bs = [], [], []
                for h in charts:
                    others = [c for c in charts if c != h]
                    d = vals(v, others)
                    dn = eddf.chart_only({c: wm[12][c] for c in others}, pos_of)
                    P = [pk for pk in wm[12][h] if pk in d and any(pk in wm[12][o] for o in others)]
                    R = [pk for pk in P if pk in ranked]
                    y = [wm[12][h][pk] for pk in P]
                    loo.append((E.spearman([d[p] for p in P], y), E.mae([d[p] for p in P], y),
                                E.spearman([d[p] for p in R], [wm[12][h][p] for p in R]), E.mae([d[p] for p in R], [wm[12][h][p] for p in R])))
                    if v != "none":
                        ys += y; As += [dn[p] for p in P]; Bs += [d[p] for p in P]
                row["loo"] = {"rho": st.mean(x[0] for x in loo), "mae": st.mean(x[1] for x in loo),
                              "ranked_rho": st.mean(x[2] for x in loo), "ranked_mae": st.mean(x[3] for x in loo)}
                if v != "none":
                    lo, hi = boot_ci(As, Bs, ys, random.Random(f"{scoring}:{sname}:{v}"))
                    row["loo"]["rho_diff_vs_ddf_ci95"] = [lo, hi]
                drops, scr = [], []
                for h in charts:
                    rest = [c for c in charts if c != h]
                    dd = vals(v, rest)
                    P = [pk for pk in full[v] if pk in dd]
                    drops.append((E.mae([full[v][p] for p in P], [dd[p] for p in P]), E.spearman([full[v][p] for p in P], [dd[p] for p in P])))
                    for k in range(PERMS):
                        shuf = dict(wm[12][h]); pks, vs = list(shuf), list(shuf.values())
                        random.Random(f"{scoring}:{h}:{k}").shuffle(vs)
                        wm2 = {w: ({**m, h: dict(zip(pks, vs))} if w == 12 else m) for w, m in wm.items()}
                        sv = vals(v, charts, wm2)
                        P = [pk for pk in full[v] if pk in sv]
                        scr.append((E.mae([full[v][p] for p in P], [sv[p] for p in P]), E.spearman([full[v][p] for p in P], [sv[p] for p in P])))
                row["drop_one"] = {"mae": st.mean(x[0] for x in drops), "rho": st.mean(x[1] for x in drops)}
                row["scramble_one"] = {"mae": st.mean(x[0] for x in scr), "rho": st.mean(x[1] for x in scr)}
                if v == "none":
                    prev = none_prev
                else:
                    prev = {pk: x["value"] for pk, x in eddf.eddf({c: wm[11][c] for c in charts}, lists, vint,
                            [E.chart_mean({c: wm[w][c] for c in charts}) for w in (11, 10)], pos_of, cfg, as_of, scoring, v)["values"].items()}
                P = [pk for pk in full[v] if pk in prev and pk in full["none"] and pk in none_prev]
                row["week_change_mae"] = E.mae([full[v][p] for p in P], [prev[p] for p in P])
                row["priced"] = len(full[v])
                if v == "none":
                    row["chart_weight"] = 1.0
                else:
                    row["chart_weight"] = E.run_eddf(cfg, charts, wm, lists, vint, pos_of, as_of, scoring, weeks, variant=v)["report"]["chart_weight_share"]
                ssec["variants"][v] = row
            sec["sets"][sname] = ssec
            print(scoring, sname, len(fresh), "fresh")
        report["scorings"][scoring] = sec
    (OUT / "study.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
