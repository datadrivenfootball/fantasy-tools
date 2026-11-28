"""JEG-1600 (step 3 of JEG-1597): enhanced DDF prototype from rescaled chart natives.

Research only. Uses pipelines/value_reference.py as a read-only library (no
edit), the week history in data/history (weeks 5-9, as the reference prices a
prior week, VP-8) and tools/research/jeg1597/cache/cbs_ros_gp.json.

Run:  python3 tools/research/jeg1597/rebuild_ddf.py
Out:  tools/research/jeg1597/out/rebuild_values.csv     (week, scoring, player_key, name, pos, method, value)
      tools/research/jeg1597/out/rescaled_natives.csv   (per chart-week natives before/after, ratio, flags)
      tools/research/jeg1597/out/rebuild_summary.json

Anchors (working assumptions, disclosed): CBS and USA Today read their own
column at each scoring (no adjustment). FantasyCalc's base list (its ppr=1,
12-team column) anchored at Full PPR; sensitivity anchored at Half, and
excluded. FantasyPros (one list for every format) anchored at assumed Half.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(HERE))

import value_reference as vr  # noqa: E402  (read-only library use)
import decompose as dc  # noqa: E402

WEEKS = (5, 6, 7, 8, 9)
TEAMS = 12
HISTORY_DIR = REPO / "data" / "history"
GP_CACHE = HERE / "cache" / "cbs_ros_gp.json"
BYES = REPO / "data" / "inputs" / "nfl_byes_2026.json"
OUT = HERE / "out"
PROJ = ("espn", "cbsros", "razzball")
ANCHOR = {"fantasycalc": "ppr", "fantasypros": "half_ppr"}
BASE_COLUMN = {"fantasycalc": "ppr", "fantasypros": "half_ppr"}   # the list read as the chart's one list
RESCALED = ("fantasycalc", "fantasypros")
VARIANTS = {
    # method: (lam, fantasycalc anchor or None to drop it, decompose mode)
    "DDF_new": (1.0, "ppr", "position_scaled"),
    "DDF_new_l05": (0.5, "ppr", "position_scaled"),
    "DDF_new_fchalf": (1.0, "half_ppr", "position_scaled"),
    "DDF_new_noFC": (1.0, None, "position_scaled"),
    "DDF_new_samefit": (1.0, "ppr", "same_fit"),
}


def load_world():
    inp = vr.Inputs.load()
    hist = vr.History(HISTORY_DIR)
    # data/history has no served.json (make sync writes it into dist/assets/history
    # from data/history/superseded). Rebuild it the same way: the served version
    # is the superseded entry whose fingerprint the index names.
    served = {}
    for src, rec in (hist.index.get("served") or {}).items():
        if rec.get("version") != "superseded":
            continue
        doc = json.loads((HISTORY_DIR / "superseded" / f"week-{rec['week']}.json").read_text(encoding="utf-8"))
        for v in (doc.get("versions") or {}).get(src) or []:
            if v.get("fingerprint") == rec.get("entry_fingerprint"):
                served[src] = v
    hist.served_versions = {"sources": served}
    players = json.loads(vr.PLAYERS.read_text(encoding="utf-8"))["players"]
    team = {int(p["player_key"]): p.get("team") for p in players if str(p.get("player_key", "")).isdigit()}
    byes = json.loads(BYES.read_text(encoding="utf-8"))["byes"]
    gp_doc = json.loads(GP_CACHE.read_text(encoding="utf-8"))
    gp = {}
    for d, groups in gp_doc["gp"].items():
        w = gp_doc["week_of_date"][d]
        for g, keys in groups.items():
            for k in keys.split():
                gp.setdefault(w, {})[int(k)] = float(g)
    return inp, hist, team, byes, gp


def week_inputs(inp, hist, w):
    """{source: {scoring: natives}} and {key: {proj source: triplet}} from history week w."""
    natives, lines = {}, {}
    for src in vr.SOURCES:
        entry, why = vr.history_entry(hist, src, w)
        if not entry:
            raise SystemExit(f"week {w} {src}: {why}")
        natives[src] = {s: vr.snapshot_natives(inp, src, entry, s) for s in dc.SCORINGS}
        if src in PROJ:
            for key, t in (entry.get("ppg") or {}).items():
                k = int(key)
                if k in inp.players:
                    lines.setdefault(k, {})[src] = t
    return natives, lines


def projected_points(lines, pos_of, w, team, byes, gp, s0):
    """{key: mean projected ppg at s0 x expected games} and the games basis counts."""
    out, basis = {}, {"cbs_gp": 0, "schedule": 0}
    for k, by_src in lines.items():
        vals = [dc.points_from_triplet(t, s0) for t in by_src.values()]
        vals = [v for v in vals if v is not None and v > 0]
        if not vals or pos_of.get(k) not in dc.POSITIONS:
            continue
        g, b = dc.expected_games(pos_of[k], w, byes.get(team.get(k)), gp.get(w, {}).get(k))
        basis[b] += 1
        out[k] = statistics.fmean(vals) * g
    return out, basis


def run(league, lineup, natives_by_src, pos_of, included, hidden):
    sources = {k: vr.SourceInput(k, vr.FAMILY[k], dict(natives_by_src[k])) for k in vr.SOURCES if k in natives_by_src}
    inc = [k for k in included if k in sources]
    return vr.run_pipeline(league, sources, pos_of, inc, None, lineup=lineup, hidden=set(hidden) & set(inc),
                           flex_bench_seats=True)


def pos_share(rows, pos_of):
    tot = {p: 0.0 for p in dc.POSITIONS}
    for k, r in rows.items():
        v = r["ddf"]["blended"]["value"]
        if v:
            tot[pos_of[k]] += v
    s = sum(tot.values()) or 1.0
    return {p: round(v / s, 4) for p, v in tot.items()}


def main():
    OUT.mkdir(exist_ok=True)
    inp, hist, team, byes, gp = load_world()
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    name_of = {k: p["name"] for k, p in inp.players.items()}
    live = {s: vr.Setting(inp, s, TEAMS, hist=hist) for s in dc.SCORINGS}
    live_state = {s: live[s].state() for s in dc.SCORINGS}

    value_rows, native_rows = [], []
    summary = {"anchors": {"cbs": "own column", "usatoday": "own column", "fantasycalc": "ppr (base list)",
                           "fantasypros": "half_ppr (assumed)"},
               "included": live_state["ppr"]["included"], "hidden": sorted(live_state["ppr"]["hidden"]),
               "fits": [], "games_basis": {}, "flags": {}, "reproduction": {}, "weeks": {}}
    results = {}
    for w in WEEKS:
        natives, lines = week_inputs(inp, hist, w)
        pts = {}
        for s0 in ("standard", "half_ppr", "ppr"):
            pts[s0], basis = projected_points(lines, pos_of, w, team, byes, gp, s0)
        summary["games_basis"][w] = basis
        ratios = {(s0, s): {k: dc.player_ratio(ln, s0, s) for k, ln in lines.items()}
                  for s0 in dc.SCORINGS for s in dc.SCORINGS}
        # Rescaled natives, cached per (chart, anchor, target, lam)
        resc = {}
        jobs = [("fantasycalc", a, s, lam, md) for a in ("ppr", "half_ppr") for s in dc.SCORINGS
                for lam in (0.5, 1.0) for md in dc.MODES]
        jobs += [("fantasypros", "half_ppr", s, lam, md) for s in dc.SCORINGS for lam in (0.5, 1.0) for md in dc.MODES]
        # Labelled charts: their own Standard column rescaled to Full, for the step-4 L check only.
        jobs += [(c, "standard", s, lam, md) for c in ("cbs", "usatoday") for s in ("ppr",)
                 for lam in (0.5, 1.0) for md in dc.MODES]
        for c, a, s, lam, md in jobs:
            base = natives[c][BASE_COLUMN.get(c, a)]
            r = dc.rescale_chart(base, pos_of, ratios[(a, s)], pts[a], lam, mode=md)
            resc[(c, a, s, lam, md)] = r
            if lam == 1.0 and s == dc.SCORINGS[0] and md == "position_scaled":
                for p, f in r.fits.items():
                    summary["fits"].append({"week": w, "chart": c, "anchor": a, "pos": p, "b": round(f.b, 4),
                                            "b_ols": None if f.b_ols is None else round(f.b_ols, 4),
                                            "n": f.n, "r2": round(f.r2, 4), "identifiable": f.identifiable,
                                            "reason": f.reason})
            if s != a:
                summary["flags"].setdefault(f"{c}|{a}->{s}|lam{lam}|{md}", {})[w] = {
                    "median_ratio_players": len(r.median_ratio_keys), "not_identifiable": r.not_identifiable,
                    "position_ratio": {p: round(x, 4) for p, x in r.position_ratio.items()}}
            mk = set(r.median_ratio_keys)
            if md == "same_fit" and lam != 1.0:
                continue   # file size: the literal same-fit variant is written at lam 1 only
            for k, v in r.natives.items():
                rt = ratios[(a, s)].get(k)
                native_rows.append([w, s, c, a, lam, md, k, pos_of[k], round(base[k], 4),
                                    round(natives[c][s].get(k), 4) if natives[c][s].get(k) is not None else "",
                                    round(v, 4), round(r.ratio[k], 5), rt.basis if rt else "median",
                                    round(rt.spread[0], 5) if rt else "", round(rt.spread[1], 5) if rt else "",
                                    "median_ratio" if k in mk else ""])
        for s in dc.SCORINGS:
            st = live_state[s]
            league, lineup = live[s].league, live[s].lineup
            cur = {src: natives[src][s] for src in vr.SOURCES}
            runs = {"DDF_cur": run(league, lineup, cur, pos_of, st["included"], st["hidden"])}
            for method, (lam, fc_anchor, md) in VARIANTS.items():
                nat = dict(cur)
                nat["fantasypros"] = resc[("fantasypros", "half_ppr", s, lam, md)].natives
                inc = list(st["included"])
                if fc_anchor is None:
                    nat.pop("fantasycalc")
                    inc = [k for k in inc if k != "fantasycalc"]
                else:
                    nat["fantasycalc"] = resc[("fantasycalc", fc_anchor, s, lam, md)].natives
                runs[method] = run(league, lineup, nat, pos_of, inc, st["hidden"])
            results[(w, s)] = runs
            cols = {m: (r, "ddf") for m, r in runs.items()}
            cols.update({"FC_raw": (runs["DDF_cur"], "fantasycalc"), "FC_corr": (runs["DDF_new"], "fantasycalc"),
                         "FC_corr_l05": (runs["DDF_new_l05"], "fantasycalc"),
                         "FC_corr_half": (runs["DDF_new_fchalf"], "fantasycalc"),
                         "FC_corr_samefit": (runs["DDF_new_samefit"], "fantasycalc"),
                         "FP_raw": (runs["DDF_cur"], "fantasypros"), "FP_corr": (runs["DDF_new"], "fantasypros"),
                         "FP_corr_samefit": (runs["DDF_new_samefit"], "fantasypros")})
            for method, (res, field_) in cols.items():
                for k, row in res["rows"].items():
                    v = row["ddf"]["blended"]["value"] if field_ == "ddf" else row["adjusted"].get(field_)
                    if v is None or v == 0:   # absent row = 0 (or not priced); keeps the file small
                        continue
                    value_rows.append([w, s, k, name_of[k], pos_of[k], method, round(v, 4)])
            summary["weeks"].setdefault(w, {})[s] = {
                "pos_share": {m: pos_share(r["rows"], pos_of) for m, r in runs.items()},
                "ddf_weights": {m: {g: round(x, 4) for g, x in r["ddf_weights"].items()} for m, r in runs.items()},
            }

    # Reproduction: history-path DDF_cur vs the live reference (week 9 = current
    # fixture, week 8 = the reference's own prior-week run).
    for s in dc.SCORINGS:
        live_res, live_prior = live[s].result(), live[s].prior_result()
        for w, ref in ((9, live_res), (8, live_prior)):
            mine = results[(w, s)]["DDF_cur"]["rows"]
            diffs, missing = [], 0
            for k, r in ref["rows"].items():
                a = r["ddf"]["blended"]["value"]
                b = (mine.get(k) or {}).get("ddf", {}).get("blended", {}).get("value")
                if a is None and b is None:
                    continue
                if a is None or b is None:
                    missing += 1
                    continue
                diffs.append(abs(a - b))
            summary["reproduction"][f"week{w}_{s}"] = {
                "reference": "Setting.result() on data/fixtures/current" if w == 9 else "Setting.prior_result()",
                "n": len(diffs), "max_abs_diff": max(diffs) if diffs else None, "one_sided": missing}

    # Week 9 comparison tables
    w9 = {}
    for s in dc.SCORINGS:
        runs = results[(9, s)]
        cur, new = runs["DDF_cur"]["rows"], runs["DDF_new"]["rows"]
        moves = []
        for k in cur:
            a = cur[k]["ddf"]["blended"]["value"]
            b = (new.get(k) or {}).get("ddf", {}).get("blended", {}).get("value")
            if a is not None and b is not None:
                moves.append((b - a, k, a, b))
        moves.sort()
        fmt = lambda t: {"player": name_of[t[1]], "pos": pos_of[t[1]], "cur": round(t[2], 1), "new": round(t[3], 1),
                         "change": round(t[0], 1)}
        w9[s] = {"top_up": [fmt(t) for t in moves[::-1][:10]], "top_down": [fmt(t) for t in moves[:10]],
                 "pos_share": summary["weeks"][9][s]["pos_share"], "ddf_weights": summary["weeks"][9][s]["ddf_weights"]}
    # Top-36 reorder counts after rescale (chart natives, week 9), and DDF top-36 reorders
    nat9, lines9 = week_inputs(inp, hist, 9)
    pts9 = {a: projected_points(lines9, pos_of, 9, team, byes, gp, a)[0] for a in dc.SCORINGS}
    rat9 = {(a, s): {k: dc.player_ratio(ln, a, s) for k, ln in lines9.items()} for a in dc.SCORINGS for s in dc.SCORINGS}
    for s in dc.SCORINGS:
        reorder = {}
        for c in RESCALED:
            a = ANCHOR[c]
            base = nat9[c][BASE_COLUMN[c]]
            after = dc.rescale_chart(base, pos_of, rat9[(a, s)], pts9[a], 1.0).natives
            published = nat9[c][s]
            reorder[c] = {}
            for p in dc.POSITIONS:
                top = sorted((k for k in published if pos_of[k] == p), key=lambda k: -published[k])[:36]
                ratio_top = {k: after[k] / published[k] for k in top if published[k] > 0}
                reorder[c][p] = {"n": len(top), "pairs": len(top) * (len(top) - 1) // 2,
                                 "flips_vs_published_column": dc.pair_flips(published, after, top),
                                 "median_native_ratio_vs_published": round(statistics.median(ratio_top.values()), 4)
                                 if ratio_top else None}
        cur, new = results[(9, s)]["DDF_cur"]["rows"], results[(9, s)]["DDF_new"]["rows"]
        ddf_flips = {}
        for p in dc.POSITIONS:
            vals0 = {k: r["ddf"]["blended"]["value"] for k, r in cur.items() if pos_of[k] == p and r["ddf"]["blended"]["value"]}
            top = sorted(vals0, key=lambda k: -vals0[k])[:36]
            vals1 = {k: new[k]["ddf"]["blended"]["value"] or 0.0 for k in top}
            ddf_flips[p] = dc.pair_flips(vals0, vals1, top)
        w9[s]["top36_reorders_chart"] = reorder
        w9[s]["top36_reorders_ddf"] = ddf_flips
    # Ratio uncertainty at week 9 (spread across projection sources), top 36 by m at half
    unc = {}
    for s0, s in (("half_ppr", "standard"), ("ppr", "standard"), ("half_ppr", "ppr")):
        unc[f"{s0}->{s}"] = {}
        for p in ("RB", "WR", "TE"):
            ks = sorted((k for k in pts9["half_ppr"] if pos_of[k] == p), key=lambda k: -pts9["half_ppr"][k])[:36]
            rs = [rat9[(s0, s)][k] for k in ks if rat9[(s0, s)].get(k)]
            unc[f"{s0}->{s}"][p] = {"median_ratio": round(statistics.median(r.value for r in rs), 4),
                                    "median_spread": round(statistics.median(r.spread[1] - r.spread[0] for r in rs), 4),
                                    "max_spread": round(max(r.spread[1] - r.spread[0] for r in rs), 4),
                                    "fallback_basis": sum(r.basis != "primary" for r in rs), "n": len(rs)}
    summary["week9"] = w9
    summary["ratio_uncertainty_week9"] = unc

    with (OUT / "rebuild_values.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["week", "scoring", "player_key", "name", "pos", "method", "value"])
        wr.writerows(value_rows)
    with (OUT / "rescaled_natives.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["week", "target_scoring", "chart", "anchor", "lam", "mode", "player_key", "pos", "native_base",
                     "native_published_at_target", "native_rescaled", "ratio", "ratio_basis", "ratio_lo",
                     "ratio_hi", "flag"])
        wr.writerows(native_rows)
    (OUT / "rebuild_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print("reproduction:", json.dumps(summary["reproduction"]))
    print("rows:", len(value_rows), "native rows:", len(native_rows))


if __name__ == "__main__":
    main()
