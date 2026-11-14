"""JEG-1598 sub-question 1 (part of JEG-1597): is FantasyCalc pegged to one scoring, or a blend?

Research only: reads saved inputs, writes out/fantasycalc_scoring.json. Method, pre-stated
decision rules and results: docs/research/jeg1597/fantasycalc-pegged-or-blend.md.

Inputs
  data/research/jeg1597/fantasycalc/2026-11-09/*.json   live public values, 24 settings (SOURCE.md)
  data/history/week-5..9.json, data/fixtures/current/   chart natives + projection ppg (step-1 loaders)
  data/inputs/weekly_actuals_2024_2026.csv               realized points (small-sample reference)
  ../fantasy-tools-jeg1565/data/research/jeg1565/fantasycalc/captures.json   2026-09-29 / 11-07 pairs

Run: python3 tools/research/jeg1597/fantasycalc_scoring.py [--boot 300]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
_spec = importlib.util.spec_from_file_location("jeg1597_scoring_assignment", HERE / "scoring_assignment.py")
sa = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sa
_spec.loader.exec_module(sa)

LIVE = REPO / "data" / "research" / "jeg1597" / "fantasycalc" / "2026-11-09"
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
CAPTURES = Path("/Users/botcomp/code/fantasy-tools-jeg1565/data/research/jeg1565/fantasycalc/captures.json")
OUT = HERE / "out" / "fantasycalc_scoring.json"

SEED = 1598
# Estimation grid is wider than the [0, 1.5] reporting range so a Standard column is not
# pushed onto the grid edge (edge pile-up would flatter the calibration).
GRID = np.round(np.arange(-0.5, 2.0001, 0.05), 2)
WITHIN_POS = ("RB", "WR", "TE")
# Cross-position: chart's k-th player vs projection's k-th player above replacement (12 teams).
CROSS = {"primary": {"K": {"RB": 24, "WR": 24, "TE": 12}, "R": {"RB": 30, "WR": 36, "TE": 15}},
         "alt": {"K": {"RB": 18, "WR": 18, "TE": 9}, "R": {"RB": 24, "WR": 30, "TE": 12}}}
PASS_TOL, PASS_SHARE = 0.25, 0.80
GRID_PTS = (0.0, 0.5, 1.0)
REALIZED_WEEKS = {5: (5, 8), 6: (6, 8)}   # capture week -> realized weeks (>= 3 games of data)
LIVE_PPR = ("0", "0.5", "1")
LIVE_QBS = (1, 2)
LIVE_TEAMS = (8, 10, 12, 14)


# ---------------------------------------------------------------- profiles

def _z(x):
    return np.arctanh(np.clip(x, -0.999999, 0.999999))


def _corr(a, b):
    a = a - a.mean(-1, keepdims=True)
    b = b - b.mean(-1, keepdims=True)
    den = np.sqrt((a * a).sum(-1) * (b * b).sum(-1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nan_to_num((a * b).sum(-1) / den)


def within_profile(values, ref, pos_of, boot, rng, positions=WITHIN_POS):
    """Fisher-z of order (Spearman) and spacing (Pearson of log v vs log m(r)) per position,
    summed over positions. Returns r_hat, CI80 and per-position r_hat."""
    total_pt = np.zeros(len(GRID))
    total_bs = np.zeros((len(GRID), boot))
    per = {}
    for p in positions:
        keys = sa.select(values, ref, pos_of, p, sa.TOP_N[p])
        n = len(keys)
        if n < 8:
            continue
        v = np.array([values[k] for k in keys])
        std = np.array([ref[k][0] for k in keys])
        rec = np.array([ref[k][1] for k in keys])
        idx = np.vstack([np.arange(n), rng.integers(0, n, size=(boot, n))])
        lv, rv = np.log(v[idx]), rankdata(v[idx], axis=1)
        z = np.empty((len(GRID), boot + 1))
        for j, r in enumerate(GRID):
            m = np.clip((std + r * rec)[idx], 0.1, None)
            z[j] = (n - 3) * 0.5 * (_z(_corr(rv, rankdata(m, axis=1))) + _z(_corr(lv, np.log(m))))
        per[p] = {"n": n, "r_hat": float(GRID[z[:, 0].argmax()]),
                  "ci80": [float(np.quantile(GRID[z[:, 1:].argmax(0)], q)) for q in (0.1, 0.9)]}
        total_pt += z[:, 0]
        total_bs += z[:, 1:]
    if not per:
        return {"identifiable": False}
    rb = GRID[total_bs.argmax(0)]
    return {"r_hat": float(GRID[total_pt.argmax()]), "ci80": [float(np.quantile(rb, 0.1)), float(np.quantile(rb, 0.9))],
            "positions": per}


def cross_profile(values, ref, pos_of, boot, rng, spec=CROSS["primary"]):
    """Chart's k-th RB/WR/TE value vs projection's k-th points above replacement at r.
    One log-log line for all three positions; r_hat minimises its squared error."""
    K, R = spec["K"], spec["R"]
    chart = {}
    for p in WITHIN_POS:
        vs = sorted((x for k, x in values.items() if x > 0 and pos_of.get(k) == p), reverse=True)[: K[p]]
        if len(vs) < K[p]:
            return {"identifiable": False, "reason": f"chart lists fewer than {K[p]} {p}"}
        chart[p] = np.log(np.array(vs))
    pool = {p: np.array([ref[k] for k in ref if pos_of.get(k) == p]) for p in WITHIN_POS}
    if any(len(pool[p]) < R[p] for p in WITHIN_POS):
        return {"identifiable": False, "reason": "reference too short"}
    y_rows = np.concatenate([chart[p] for p in WITHIN_POS])
    pos_rows = np.concatenate([[i] * K[p] for i, p in enumerate(WITHIN_POS)])
    # bootstrap: resample rank slots within position (same rows used for every r)
    idx = [np.arange(len(y_rows))]
    for _ in range(boot):
        parts, off = [], 0
        for p in WITHIN_POS:
            parts.append(off + rng.integers(0, K[p], size=K[p]))
            off += K[p]
        idx.append(np.concatenate(parts))
    idx = np.array(idx)
    sse = np.empty((len(GRID), boot + 1))
    ratio = {}
    for j, r in enumerate(GRID):
        xs = []
        for p in WITHIN_POS:
            m = np.sort(pool[p][:, 0] + r * pool[p][:, 1])[::-1]
            xs.append(m[: K[p]] - m[R[p] - 1])
        x = np.log(np.clip(np.concatenate(xs), 0.05, None))
        X, Y = x[idx], y_rows[idx]
        xm, ym = X.mean(1, keepdims=True), Y.mean(1, keepdims=True)
        b = ((X - xm) * (Y - ym)).sum(1) / np.maximum(((X - xm) ** 2).sum(1), 1e-12)
        resid = (Y - ym) - b[:, None] * (X - xm)
        sse[j] = (resid ** 2).sum(1)
        if r in GRID_PTS:
            # mean residual by position at the point fit: + means chart prices it above the line
            ratio[str(r)] = {p: round(float(resid[0][pos_rows == i].mean()), 3) for i, p in enumerate(WITHIN_POS)}
    rb = GRID[sse[:, 1:].argmin(0)]
    return {"r_hat": float(GRID[sse[:, 0].argmin()]), "ci80": [float(np.quantile(rb, 0.1)), float(np.quantile(rb, 0.9))],
            "sse_at": {str(r): round(float(sse[GRID == r, 0][0]), 3) for r in GRID_PTS},
            "mean_log_resid_by_pos": ratio}


# ---------------------------------------------------------------- decision rules (pre-stated)

def calibration(cases):
    """cases: list of (truth_r, r_hat). Pass when |r_hat - truth| < 0.25 on >= 80%."""
    ok = [abs(rh - t) < PASS_TOL for t, rh in cases if rh is not None]
    n = len(ok)
    return {"n": n, "within_tol": int(sum(ok)), "share": round(sum(ok) / n, 3) if n else None,
            "pass": bool(n and sum(ok) >= PASS_SHARE * n)}


def classify(estimates, calibrated):
    """estimates: list of {'r_hat', 'ci80'} over weeks. Pre-stated rule (doc section 1.4)."""
    if not calibrated:
        return {"verdict": "not identifiable", "reason": "method failed calibration"}
    est = [e for e in estimates if e.get("r_hat") is not None]
    if len(est) < 3:
        return {"verdict": "not identifiable", "reason": "fewer than 3 weeks"}
    pegged = []
    for e in est:
        lo, hi = e["ci80"]
        g = [g for g in GRID_PTS if g - PASS_TOL < lo and hi < g + PASS_TOL]
        pegged.append(g[0] if g else None)
    for g in GRID_PTS:
        if sum(x == g for x in pegged) >= 0.8 * len(est):
            return {"verdict": f"pegged at r={g}", "weeks": len(est)}
    rh = np.array([e["r_hat"] for e in est])
    widths = np.array([e["ci80"][1] - e["ci80"][0] for e in est])
    interior = all(min(abs(x - g) for g in GRID_PTS) >= 0.15 for x in rh)
    if interior and widths.max() <= 0.5 and np.ptp(rh) <= 0.3:
        return {"verdict": "stable blend", "r_mean": round(float(rh.mean()), 2),
                "r_range": [float(rh.min()), float(rh.max())]}
    return {"verdict": "not identifiable", "reason": "CI too wide or r_hat unstable",
            "r_range": [float(rh.min()), float(rh.max())], "max_ci80_width": round(float(widths.max()), 2)}


def switch_test(v0, v1, ref, pos_of, positions=("QB", "RB", "WR", "TE"), min_value=300.0):
    """Does a setting switch v0 -> v1 act as a per-position multiplier, or carry a
    player-level (per-scoring) term? Residual = log(v1/v0) minus a smooth fit on log v0."""
    out = {}
    for p in positions:
        keys = sorted((k for k in v0 if pos_of.get(k) == p and v0[k] >= min_value and v1.get(k, 0) > 0),
                      key=lambda k: -v0[k])[:36]
        if len(keys) < 8:
            continue
        a = np.array([v0[k] for k in keys])
        b = np.array([v1[k] for k in keys])
        lr = np.log(b / a)
        X = np.vstack([np.ones(len(a)), np.log(a)]).T
        coef = np.linalg.lstsq(X, lr, rcond=None)[0]
        resid = lr - X @ coef
        pairs = len(keys) * (len(keys) - 1) // 2
        disc = sum(1 for i, j in combinations(range(len(keys)), 2) if (a[i] - a[j]) * (b[i] - b[j]) < 0)
        row = {"n": len(keys), "k_p": round(float(np.exp(np.median(lr))), 4),
               "sd_log_ratio": round(float(lr.std()), 5), "resid_sd": round(float(resid.std()), 5),
               "slope_on_log_value": round(float(coef[1]), 4), "reordered_pairs": disc, "pairs": pairs}
        share = [(ref[k][1] / max(ref[k][0] + 0.5 * ref[k][1], 0.1)) for k in keys if k in ref]
        if p != "QB" and len(share) == len(keys) and np.ptp(resid) > 0 and np.ptp(share) > 0:
            row["spearman_resid_vs_rec_share"] = round(float(_corr(rankdata(resid), rankdata(share))), 3)
        out[p] = row
    verdict = "multiplier only"
    for p, row in out.items():
        rho = row.get("spearman_resid_vs_rec_share")
        if row["reordered_pairs"] > 0.02 * row["pairs"] or (rho is not None and abs(rho) >= 0.3 and row["resid_sd"] > 0.005):
            verdict = "player-level term"
    return {"verdict": verdict, "positions": out,
            "within_position": "not identifiable" if verdict == "multiplier only" else "identifiable"}


# ---------------------------------------------------------------- data

def norm(n):
    n = re.sub(r"[^a-z ]", "", str(n).lower()).strip()
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", n).strip()


def name_keys():
    data = json.loads((sa.CURRENT / "comparison-sources-data.json").read_text())
    out = {}
    for n, k in data["player_keys"].items():
        out.setdefault(norm(n), int(k))
    return out


def load_live(keys_by_name):
    files, unmatched = {}, set()
    for ppr in LIVE_PPR:
        for q in LIVE_QBS:
            for t in LIVE_TEAMS:
                rows = json.loads((LIVE / f"ppr{ppr}_qb{q}_t{t}.json").read_text())
                d = {}
                for r in rows:
                    k = keys_by_name.get(norm(r["player"]["name"]))
                    if k is None:
                        unmatched.add(r["player"]["name"])
                        continue
                    d[k] = {"value": float(r["value"]), "base": float(r["redraftValue"]),
                            "tf": r.get("maybeTradeFrequency"), "pos": r["player"]["position"]}
                files[(ppr, q, t)] = d
    return files, sorted(unmatched)


def realized_ref(w0, w1):
    acc = {}
    with ACTUALS.open() as fh:
        for row in csv.DictReader(fh):
            if row["season"] == "2026" and w0 <= int(row["week"]) <= w1:
                std, ppr = float(row["std"]), float(row["ppr"])
                acc.setdefault(int(row["player_key"]), []).append((std, ppr - std))
    return {k: (float(np.mean([a for a, _ in v])), float(np.mean([b for _, b in v])))
            for k, v in acc.items() if len(v) >= 2}


# ---------------------------------------------------------------- analyses

def pools(live):
    sig = {}
    for combo, d in live.items():
        key = (tuple(sorted((k, x["base"]) for k, x in d.items())), tuple(sorted((k, x["tf"]) for k, x in d.items())))
        sig.setdefault(key, []).append(combo)
    out = []
    for (_, tfsig), combos in sig.items():
        exposed = [c for c in combos if all(x["value"] == x["base"] for x in live[c].values())]
        out.append({"combos": ["ppr%s_qb%d_t%d" % c for c in sorted(combos)],
                    "base_exposed_at": ["ppr%s_qb%d_t%d" % c for c in exposed], "tf_sig": hash(tfsig) % 10**8})
    return out


def parameter_response(live, ref, pos_of):
    val = {c: {k: x["value"] for k, x in d.items()} for c, d in live.items()}
    base = {c: {k: x["base"] for k, x in d.items()} for c, d in live.items()}
    res = {"value_over_base": {}, "ppr": {}, "teams": {}, "qbs": {}}
    for c in sorted(live):
        res["value_over_base"]["ppr%s_qb%d_t%d" % c] = switch_test(base[c], val[c], ref, pos_of)
    for q in LIVE_QBS:
        for t in LIVE_TEAMS:
            for a, b in (("0", "1"), ("0", "0.5"), ("0.5", "1")):
                res["ppr"][f"qb{q}_t{t}_ppr{a}->{b}"] = switch_test(val[(a, q, t)], val[(b, q, t)], ref, pos_of)
    for ppr in LIVE_PPR:
        for q in LIVE_QBS:
            for t in (8, 10, 14):
                res["teams"][f"ppr{ppr}_qb{q}_t12->t{t}"] = switch_test(val[(ppr, q, 12)], val[(ppr, q, t)], ref, pos_of)
        for t in LIVE_TEAMS:
            res["qbs"][f"ppr{ppr}_t{t}_qb1->qb2"] = switch_test(val[(ppr, 1, t)], val[(ppr, 2, t)], ref, pos_of)
    # the two exposed bases (12 teams, full PPR) by QB count, and the second trade pool
    res["qbs"]["base_qb1->base_qb2"] = switch_test(base[("1", 1, 12)], base[("1", 2, 12)], ref, pos_of)
    res["pool_P_vs_Q_base_qb1"] = switch_test(base[("1", 1, 12)], base[("0", 1, 14)], ref, pos_of)
    res["pool_P_vs_Q_base_qb2"] = switch_test(base[("1", 2, 12)], base[("0", 2, 14)], ref, pos_of)
    return res


def summarize_switches(block):
    """compact: verdict counts and k_p ranges per position"""
    verdicts, kp = {}, {}
    for name, r in block.items():
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        for p, row in r["positions"].items():
            kp.setdefault(p, []).append(row["k_p"])
    return {"verdicts": verdicts, "k_p_range": {p: [min(v), max(v)] for p, v in kp.items()}}


def switch_size_vs_projection(v0, v1, ref, pos_of):
    """Size of a ppr0 -> ppr1 switch relative to the projections' own Standard -> Full move:
    log(k_WR / k_RB) / log(proj_WR / proj_RB) (1.0 = a full scoring change), same for TE."""
    k, pr = {}, {}
    for p in WITHIN_POS:
        keys = [x for x in sa.select(v1, ref, pos_of, p, 24 if p != "TE" else 12) if v0.get(x, 0) > 0 and ref[x][0] > 0]
        k[p] = float(np.median([v1[x] / v0[x] for x in keys]))
        pr[p] = float(np.median([(ref[x][0] + ref[x][1]) / ref[x][0] for x in keys]))
    return {p: round(float(np.log(k[p] / k["RB"]) / np.log(pr[p] / pr["RB"])), 3) for p in ("WR", "TE")} | {
        "k": {p: round(v, 4) for p, v in k.items()}, "projection_full_over_std": {p: round(v, 3) for p, v in pr.items()}}


def capture_pairs(keys_by_name, ref, pos_of):
    caps = json.loads(CAPTURES.read_text())
    out = {}
    for label in ("week 4 cache", "live pull"):
        cols = {}
        for c in caps:
            if c["label"] == label:
                cols[c["scoring"]] = {keys_by_name[norm(r["name"])]: float(r["value"]) for r in c["rows"]
                                      if norm(r["name"]) in keys_by_name}
        out[label] = switch_test(cols["standard"], cols["full"], ref, pos_of)
    return out


def run(boot=300):
    rng = np.random.default_rng(SEED)
    pos_of = sa.positions()
    weeks = [sa.load_week(w) for w in sa.WEEKS] + [sa.load_current()]
    keys_by_name = name_keys()
    live, unmatched = load_live(keys_by_name)
    cur_ref = weeks[-1]["ref"]
    live_cols = {s: {k: x["value"] for k, x in live[(p, 1, 12)].items()}
                 for s, p in (("standard", "0"), ("half_ppr", "0.5"), ("ppr", "1"))}
    live_week = {"label": "live-2026-11-09", "charts": {"fantasycalc": live_cols}, "ref": cur_ref}
    real = {w: realized_ref(*span) for w, span in REALIZED_WEEKS.items()}

    est = {"within": {}, "cross": {}, "cross_alt": {}, "within_realized": {}, "cross_realized": {}}
    methods = {"within": lambda v, r: within_profile(v, r, pos_of, boot, rng),
               "cross": lambda v, r: cross_profile(v, r, pos_of, boot, rng, CROSS["primary"]),
               "cross_alt": lambda v, r: cross_profile(v, r, pos_of, boot, rng, CROSS["alt"])}
    for wk in weeks + [live_week]:
        for chart, cols in wk["charts"].items():
            if chart not in ("cbs", "usatoday", "fantasycalc"):
                continue
            for col, values in cols.items():
                for m, f in methods.items():
                    est[m].setdefault(chart, {}).setdefault(wk["label"], {})[col] = f(values, wk["ref"])
                wnum = int(wk["label"].split("-")[1]) if wk["label"].startswith("week-") else None
                if wnum in real:
                    est["within_realized"].setdefault(chart, {}).setdefault(wk["label"], {})[col] = methods["within"](values, real[wnum])
                    est["cross_realized"].setdefault(chart, {}).setdefault(wk["label"], {})[col] = methods["cross"](values, real[wnum])

    calib, verdicts = {}, {}
    for m, by_chart in est.items():
        cases = [(sa.LABEL_R[col], by_chart[c][wl][col].get("r_hat"))
                 for c in sa.LABELLED for wl in by_chart.get(c, {}) if wl.startswith("week-")
                 for col in ("standard", "ppr")]
        calib[m] = calibration(cases)
        fc = by_chart.get("fantasycalc", {})
        verdicts[m] = {col: classify([fc[wl][col] for wl in fc if wl.startswith("week-")], calib[m]["pass"])
                       for col in ("standard", "half_ppr", "ppr")}

    compact = {m: {c: {wl: {col: (e.get("r_hat"), e.get("ci80")) for col, e in cols.items()} for wl, cols in wls.items()}
                   for c, wls in by_chart.items()} for m, by_chart in est.items()}
    pr = parameter_response(live, cur_ref, pos_of)
    size = {c: {wk["label"]: switch_size_vs_projection(wk["charts"][c]["standard"], wk["charts"][c]["ppr"], wk["ref"], pos_of)
                for wk in weeks + [live_week] if c in wk["charts"]}
            for c in ("cbs", "usatoday", "fantasycalc")}
    return {
        "meta": {"ticket": "JEG-1598 sub-question 1", "parent": "JEG-1597", "boot": boot, "seed": SEED,
                 "grid": [float(GRID[0]), float(GRID[-1]), 0.05], "pass_bar": f"|r_hat-truth|<{PASS_TOL} on >={PASS_SHARE:.0%}",
                 "cross_specs": CROSS, "realized_weeks": REALIZED_WEEKS, "live_dir": str(LIVE.relative_to(REPO)),
                 "live_unmatched_names": unmatched, "note": "docs/research/jeg1597/fantasycalc-pegged-or-blend.md"},
        "calibration": calib,
        "fantasycalc_verdicts": verdicts,
        "r_hat_compact": compact,
        "trade_pools_live": pools(live),
        "parameter_response_summary": {k: summarize_switches(v) for k, v in pr.items() if k in ("value_over_base", "ppr", "teams", "qbs")},
        "parameter_response": pr,
        "ppr_switch_size_vs_projection": size,
        "capture_pairs_ppr0_vs_ppr1": capture_pairs(keys_by_name, weeks[0]["ref"], pos_of),
        "estimates": est,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=300)
    out = run(ap.parse_args().boot)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    for m, c in out["calibration"].items():
        print(f"calibration {m:16s} {c['within_tol']}/{c['n']} pass={c['pass']}  FC verdict ppr col: "
              f"{out['fantasycalc_verdicts'][m]['ppr']['verdict']}")
    for k, v in out["parameter_response_summary"].items():
        print(k, v["verdicts"])
    print("pools:", [(p["combos"][:3], len(p["combos"]), p["base_exposed_at"]) for p in out["trade_pools_live"]])
    print("unmatched live names:", len(out["meta"]["live_unmatched_names"]))


if __name__ == "__main__":
    main()
