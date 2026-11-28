#!/usr/bin/env python3
"""JEG-1735: candidate ranker lists for the EDDF registry, and the same study run on them.

Candidates only (Jeremy, 2026-11-28): none is enabled, none goes live; the study decides which
add independent information. Reads the seven files the consensus study session saved
(args.dir; default the notes folder ros-anchor/), resolves names offline
(tools/research/ros_rank_keys.py), writes
  docs/research/data/jeg1735/candidates.json   {id: {scoring: {vintage, ranks, kind, note}}}
  docs/research/data/jeg1735/candidate_study.json
Parsing rules (as the lead session stated them): drop Wolf's ECR column; Rotoballer's two lists
by scoring; projection-model files ranked by their points and flagged `model`; Razzball QBs
exist for standard only; STM has no overall rank so its 120 players are ranked by ROS points;
FanDuel scoring is inferred half PPR; Footballguys is QBs only (QBs are excluded from EDDF by
default, so it prices nothing).
"""
import csv
import json
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eddf_evidence as E  # noqa: E402
import ros_rank_keys as K  # noqa: E402

eddf, vr = E.eddf, E.vr
OUT = E.OUT
DEFAULT_DIR = Path("/Users/botcomp/Library/Application Support/Claude/side-session-notes/"
                   "local_c3e6ad02-da22-4b1e-8561-dfcafd32021f/ros-anchor")
POS = {"QB", "RB", "WR", "TE"}
ALL = ["ppr", "half_ppr", "standard"]


def rank_by_points(rows):
    """[(key, pts)] -> {key: rank}, higher first, ties share the average rank."""
    rows = sorted(rows, key=lambda x: -x[1])
    out, i = {}, 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1][1] == rows[i][1]:
            j += 1
        for k, _ in rows[i:j + 1]:
            out[k] = (i + j) / 2 + 1
        i = j + 1
    return out


def put(lists, cid, scoring, vintage, kind, note, ranks):
    lists.setdefault(cid, {})[scoring] = {"vintage": vintage, "kind": kind, "note": note,
                                           "ranks": {str(k): v for k, v in ranks.items()}}


def build(d: Path) -> dict:
    L: dict = {}
    # 1. Wolf, Roto Street Journal (the same analyst as the FantasyPros-feed list fp-wolf-of-roto-street)
    rk = {}
    for r in csv.DictReader(open(d / "rsj_wolf_2026-11-24.psv"), delimiter="|"):
        name = r["player_team"].rsplit(" (", 1)[0]
        if r["pos"] in POS:
            pk = K.pk(name, r["pos"], "cand-rsj-wolf")
            if pk is not None and pk not in rk:
                rk[pk] = float(r["rank"])
    for sc in ALL:
        put(L, "cand-rsj-wolf", sc, "2026-11-24", "analyst", "scoring not stated, used for all three; same analyst and date as fp-wolf-of-roto-street", rk)
    # 2. Rotoballer, Nick Mariano
    by = {}
    for r in csv.DictReader(open(d / "rotoballer_ros_2026-11-27.csv")):
        sc = {"half_ppr": "half_ppr", "full_ppr": "ppr"}.get(r["scoring"])
        if sc and r["pos"] in POS:
            pk = K.pk(r["player"], r["pos"], f"cand-rotoballer:{sc}")
            if pk is not None:
                by.setdefault(sc, {}).setdefault(pk, float(r["rank"]))
    for sc, rk in by.items():
        put(L, "cand-rotoballer", sc, "2026-11-25", "analyst", "Nick Mariano, top 200", rk)
    # 3. GWTTKB, PPR
    rk = {}
    for r in csv.DictReader(open(d / "gwttkb_ros_ppr_2026-11-27.csv")):
        if r["pos"] in POS:
            pk = K.pk(r["player"], r["pos"], "cand-gwttkb")
            if pk is not None:
                rk.setdefault(pk, float(r["rank"]))
    put(L, "cand-gwttkb", "ppr", "2026-11-23", "model", "model-based board, independence unconfirmed", rk)
    # 4. Razzball ROS points, ranked per scoring (QBs standard only)
    pts = {"standard": [], "half_ppr": [], "ppr": []}
    for r in csv.DictReader(open(d / "razzball_ros_2026-11-27.csv")):
        if r["pos"] not in POS:
            continue
        pk = K.pk(r["name"], r["pos"], "cand-razzball")
        if pk is None:
            continue
        for sc, col in (("standard", "std_pts"), ("half_ppr", "half_pts"), ("ppr", "ppr_pts")):
            if r[col] not in ("", None):
                pts[sc].append((pk, float(r[col])))
    for sc, rows in pts.items():
        put(L, "cand-razzball", sc, "2026-11-26", "model", "projection points, ranked by points", rank_by_points(rows))
    # 5. FanDuel Research projections, scoring inferred half PPR
    rk = {}
    for r in csv.DictReader(open(d / "fanduel_ros_proj_2026-11-27.csv")):
        if r["pos"] in POS and r["overall_rank"]:
            pk = K.pk(r["player"], r["pos"], "cand-fanduel")
            if pk is not None:
                rk.setdefault(pk, float(r["overall_rank"]))
    put(L, "cand-fanduel", "half_ppr", "2026-11-27", "model", "projection model; half PPR inferred; no update date on the page (read date used)", rk)
    # 6. StickToTheModel, PPR, 120 players ranked by ROS points
    rows = []
    for r in csv.DictReader(open(d / "stm_ros_2026-11-27.csv")):
        pk = K.pk(r["player"], r["pos"], "cand-stm")
        if pk is not None and r["pos"] in POS:
            rows.append((pk, float(r["ros_pts"])))
    put(L, "cand-stm", "ppr", "2026-11-24", "model", "projection points, top 30 per position, ranked by points", rank_by_points(rows))
    # 7. Footballguys, QBs only
    rk = {}
    for r in csv.DictReader(open(d / "footballguys_ros_2026-11-24_qb.csv")):
        pk = K.pk(r["player"], "QB", "cand-footballguys-qb")
        if pk is not None:
            rk.setdefault(pk, float(r["pos_rank"].replace("QB", "")))
    for sc in ALL:
        put(L, "cand-footballguys-qb", sc, "2026-11-24", "analyst", "QBs only; QBs are excluded from EDDF by default so this prices nothing", rk)
    return L


def main():
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    cands = build(d)
    (OUT / "candidates.json").write_text(json.dumps(cands, separators=(",", ":"), sort_keys=True))
    cfg = eddf.load_config()
    base_lists = json.loads((OUT / "lists.json").read_text())
    as_of = date(2026, 11, 27)
    study = {"as_of": as_of.isoformat(), "join_not_ok": {k: len(v["not_joined"]) for k, v in K.join_report().items()}, "scorings": {}}
    inp = vr.Inputs.load(vr.FIXTURE, vr.PLAYERS)
    hist = vr.History(vr.REPO / "data/history")
    for scoring in ALL:
        weeks = [12, 11, 10]
        wm, charts, pos_of, _, _ = E.adjusted_by_week(inp, hist, scoring, weeks)
        lists = {r: {int(pk): v for pk, v in dd[scoring]["ranks"].items()} for r, dd in base_lists.items() if scoring in dd}
        vint = {r: dd[scoring]["vintage"] for r, dd in base_lists.items() if scoring in dd}
        clists = {r: {int(pk): v for pk, v in dd[scoring]["ranks"].items()} for r, dd in cands.items() if scoring in dd}
        cvint = {r: dd[scoring]["vintage"] for r, dd in cands.items() if scoring in dd}
        fresh = [r["id"] for r in cfg["rankers"] if r["id"] in vint and eddf.ranker_status(
            r, vint[r["id"]], as_of, cfg["stale_days"], scoring, cfg.get("stale_weekday"))["in"]]
        fp_mean = {}
        anchors = eddf.stable_anchors([E.chart_mean({k: wm[w][k] for k in charts}) for w in weeks], cfg["anchor_stability"], cfg["anchor_floor_frac"])
        impl0 = {r: eddf.implied_values(lists[r], anchors, pos_of, cfg) for r in fresh}
        for pk in pos_of:
            vs = [impl0[r][pk] for r in fresh if pk in impl0[r]]
            if vs:
                fp_mean[pk] = st.mean(vs)
        sec = {}
        for cid, ranks in clists.items():
            cfg1 = {**cfg, "rankers": [{"id": cid, "scoring": [scoring], "group": cid}]}
            iv = eddf.implied_values(ranks, anchors, pos_of, cfg1)
            n = len(iv)
            entry = {"kind": cands[cid][scoring]["kind"], "vintage": cvint[cid], "listed": len(ranks), "priced_non_qb": n,
                     "age_days": (as_of - date.fromisoformat(cvint[cid])).days}
            if n >= cfg["min_anchors"]:
                # independence: agreement of its implied values with the fresh FantasyPros-feed mean and with the charts
                common = [p for p in iv if p in fp_mean]
                cm = E.chart_mean({c: wm[12][c] for c in charts})
                cc = [p for p in iv if p in cm]
                entry["rho_vs_feed_mean"] = E.spearman([iv[p] for p in common], [fp_mean[p] for p in common]) if len(common) > 3 else None
                entry["rho_vs_charts"] = E.spearman([iv[p] for p in cc], [cm[p] for p in cc]) if len(cc) > 3 else None
                # leave-one-chart-out, charts plus this one source alone
                rows = []
                for h in charts:
                    others = [c for c in charts if c != h]
                    res = eddf.eddf({c: wm[12][c] for c in others}, {cid: ranks}, {cid: cvint[cid]},
                                    [E.chart_mean({c: wm[w][c] for c in others}) for w in weeks], pos_of, cfg1, as_of, scoring)
                    dd = eddf.chart_only({c: wm[12][c] for c in others}, pos_of)
                    P = [p for p in wm[12][h] if p in dd and p in res["values"] and p in ranks and pos_of.get(p) != "QB"]
                    y = [wm[12][h][p] for p in P]
                    rows.append((E.spearman([dd[p] for p in P], y), E.spearman([res["values"][p]["value"] for p in P], y),
                                 E.mae([dd[p] for p in P], y), E.mae([res["values"][p]["value"] for p in P], y)))
                entry["loo_ranked"] = {"rho_charts_only": st.mean(r[0] for r in rows), "rho_with_source": st.mean(r[1] for r in rows),
                                       "mae_charts_only": st.mean(r[2] for r in rows), "mae_with_source": st.mean(r[3] for r in rows)}
            else:
                entry["note"] = "prices too few non-QB players to fit a curve" if n else "prices no non-QB players"
            entry["note_source"] = cands[cid][scoring]["note"]
            sec[cid] = entry
        # one reference row: a fresh FantasyPros-feed list on the same footing
        study["scorings"][scoring] = sec
    (OUT / "candidate_study.json").write_text(json.dumps(study, indent=1))
    print(json.dumps({sc: {c: (v.get("priced_non_qb"), v.get("rho_vs_feed_mean") and round(v["rho_vs_feed_mean"], 3), v.get("loo_ranked") and round(v["loo_ranked"]["rho_with_source"], 3)) for c, v in s.items()} for sc, s in study["scorings"].items()}, indent=0))
    print("unjoined", study["join_not_ok"])


if __name__ == "__main__":
    main()
