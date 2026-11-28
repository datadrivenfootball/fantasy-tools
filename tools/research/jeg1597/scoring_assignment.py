"""JEG-1598 (step 1 of JEG-1597): which scoring does each trade chart's list resemble?

Research only: reads saved inputs, writes out/scoring_assignment.json. Method and
pre-stated pass bars: docs/research/jeg1597/step1-scoring-assignment.md.

Inputs
  data/history/week-5.json .. week-9.json     chart natives per scoring, projection ppg triplets
  data/fixtures/current/comparison-sources-data.json + players.json   the current week

Run: python3 tools/research/jeg1597/scoring_assignment.py [--boot 500]
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

REPO = Path(__file__).resolve().parents[3]
HISTORY = REPO / "data" / "history"
CURRENT = REPO / "data" / "fixtures" / "current"
OUT = Path(__file__).resolve().parent / "out" / "scoring_assignment.json"

WEEKS = (5, 6, 7, 8, 9)
CHARTS = ("cbs", "usatoday", "fantasypros", "fantasycalc")
PROJ = ("espn", "cbsros", "razzball")
PROJ_FIELD = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
COLUMNS = ("standard", "half_ppr", "ppr")
COMBO = {"standard": "standard", "half_ppr": "half", "ppr": "full"}
LABEL_R = {"standard": 0.0, "half_ppr": 0.5, "ppr": 1.0}
POS = ("QB", "RB", "WR", "TE")
POOLED = ("RB", "WR", "TE")
TOP_N = {"QB": 24, "RB": 36, "WR": 36, "TE": 24}
GRID = np.round(np.arange(-0.5, 2.0001, 0.05), 2)
IDENT_MIN_DISCORDANT = 0.05
SEED = 1597
LABELLED = ("cbs", "usatoday")


# ---------------------------------------------------------------- loading

def positions() -> dict:
    rows = json.loads((CURRENT / "players.json").read_text())["players"]
    return {int(r["player_key"]): r["pos"] for r in rows}


def reference(triplets_by_source: list[dict]) -> dict:
    """key -> (std, rec): mean over projections listing the player with ppg_full > 0."""
    acc: dict = {}
    for src in triplets_by_source:
        for k, t in src.items():
            if not t or t[2] is None or t[0] is None or not t[2] > 0:
                continue
            acc.setdefault(k, []).append((float(t[0]), float(t[2])))
    return {k: (sum(a for a, _ in v) / len(v), sum(b - a for a, b in v) / len(v)) for k, v in acc.items()}


def load_week(w: int) -> dict:
    src = json.loads((HISTORY / f"week-{w}.json").read_text())["sources"]
    charts = {c: {s: {int(k): float(x) for k, x in src[c]["natives"][s].items() if x is not None}
                  for s in COLUMNS} for c in CHARTS}
    ref = reference([{int(k): v for k, v in src[p]["ppg"].items()} for p in PROJ])
    return {"label": f"week-{w}", "charts": charts, "ref": ref}


def load_current() -> dict:
    data = json.loads((CURRENT / "comparison-sources-data.json").read_text())
    keys = data["player_keys"]
    charts = {}
    for c in CHARTS:
        suffix = "_12_qb1" if c == "fantasycalc" else "_12"
        charts[c] = {s: {int(keys[n]): float(x) for n, x in data["sources"][c]["combos"][COMBO[s] + suffix]["native"].items()
                         if n in keys and x is not None} for s in COLUMNS}
    rows = json.loads((CURRENT / "players.json").read_text())["players"]
    per_src = []
    for p in PROJ:
        f = PROJ_FIELD[p]
        per_src.append({int(r["player_key"]): [r[f].get(s) for s in COLUMNS]
                        for r in rows if isinstance(r.get(f), dict)})
    vintage = data["sources"]["cbs"].get("content_vintage")
    return {"label": "current", "vintage": vintage, "charts": charts, "ref": reference(per_src)}


# ---------------------------------------------------------------- method

def select(values: dict, ref: dict, pos_of: dict, p: str, n: int) -> list:
    keys = [k for k, v in values.items() if v > 0 and k in ref and pos_of.get(k) == p and ref[k][0] + ref[k][1] > 0]
    return sorted(keys, key=lambda k: (-values[k], k))[:n]


def _corr_rows(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a - a.mean(axis=-1, keepdims=True)
    b = b - b.mean(axis=-1, keepdims=True)
    den = np.sqrt((a * a).sum(-1) * (b * b).sum(-1))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (a * b).sum(-1) / den
    return np.nan_to_num(out, nan=0.0)


def rho_grid(v: np.ndarray, std: np.ndarray, rec: np.ndarray, idx: np.ndarray | None = None) -> np.ndarray:
    """Spearman(v, std + r*rec) for each r in GRID. idx (B, n) -> shape (len(GRID), B)."""
    if idx is None:
        idx = np.arange(len(v))[None, :]
    rv = rankdata(v[idx], axis=1)
    out = np.empty((len(GRID), idx.shape[0]))
    for j, r in enumerate(GRID):
        out[j] = _corr_rows(rv, rankdata((std + r * rec)[idx], axis=1))
    return out


def partial_spearman(v, rec, m_half) -> float | None:
    if min(np.ptp(v), np.ptp(rec), np.ptp(m_half)) == 0:
        return None
    rv, ry, rz = (rankdata(x) for x in (v, rec, m_half))
    c = np.corrcoef(np.vstack([rv, ry, rz]))
    a, b, z = c[0, 1], c[0, 2], c[1, 2]
    den = np.sqrt(max(1e-12, (1 - b * b) * (1 - z * z)))
    return float((a - b * z) / den)


def discordant_share(x: np.ndarray, y: np.ndarray) -> float:
    pairs = list(combinations(range(len(x)), 2))
    if not pairs:
        return 0.0
    bad = sum(1 for i, j in pairs if (x[i] - x[j]) * (y[i] - y[j]) < 0)
    return bad / len(pairs)


GRID_IDX = {s: int(np.argmin(np.abs(GRID - r))) for s, r in LABEL_R.items()}
TE15 = int(np.argmin(np.abs(GRID - 1.5)))


def support(argmax_labels: np.ndarray) -> dict:
    counts = {s: int((argmax_labels == j).sum()) for j, s in enumerate(COLUMNS)}
    tot = sum(counts.values()) + len(COLUMNS)
    return {s: round((counts[s] + 1) / tot, 3) for s in COLUMNS}


def _gi(r: float) -> int:
    return int(np.argmin(np.abs(GRID - r)))


def assess(values: dict, ref: dict, pos_of: dict, boot: int, rng: np.random.Generator,
           ident_min: float = IDENT_MIN_DISCORDANT, bias: dict | None = None) -> dict:
    """Per-position and pooled evidence for one chart column.

    bias (post-hoc variant only): per-position offset b_p, so label s is scored at
    rho_p(r_s + b_p) instead of rho_p(r_s)."""
    bias = bias or {}
    out = {"positions": {}}
    pooled_z = None
    boot_rhat = {}
    for p in POS:
        keys = select(values, ref, pos_of, p, TOP_N[p])
        n = len(keys)
        if n < 8:
            out["positions"][p] = {"n": n, "identifiable": False, "reason": "fewer than 8 players"}
            continue
        v = np.array([values[k] for k in keys])
        std = np.array([ref[k][0] for k in keys])
        rec = np.array([ref[k][1] for k in keys])
        point = rho_grid(v, std, rec)[:, 0]
        idx = rng.integers(0, n, size=(boot, n))
        bs = rho_grid(v, std, rec, idx)
        rhat_b = GRID[bs.argmax(axis=0)]
        boot_rhat[p] = rhat_b
        disc = discordant_share(std, std + rec)
        ident = disc >= ident_min
        gi = {s: _gi(LABEL_R[s] + bias.get(p, 0.0)) for s in COLUMNS}
        lab = np.stack([bs[gi[s]] for s in COLUMNS]).argmax(axis=0)
        out["positions"][p] = {
            "n": n,
            "identifiable": bool(ident),
            "ref_discordant_pairs_std_vs_full": round(disc, 3),
            "rho": {s: round(float(point[GRID_IDX[s]]), 4) for s in COLUMNS} | {"te_premium_1.5": round(float(point[TE15]), 4)},
            "r_hat": float(GRID[point.argmax()]),
            "r_hat_ci80": [float(np.quantile(rhat_b, 0.1)), float(np.quantile(rhat_b, 0.9))],
            "partial_rec_given_half": (None if (pc := partial_spearman(v, rec, std + 0.5 * rec)) is None else round(pc, 4)),
            "dist": support(lab) if ident else None,
            "top": COLUMNS[int(np.argmax([point[gi[s]] for s in COLUMNS]))] if ident else None,
        }
        if p in POOLED and ident:
            z = (n - 3) * np.arctanh(np.clip(bs, -0.999999, 0.999999))
            zp = (n - 3) * np.arctanh(np.clip(point, -0.999999, 0.999999))
            # labels scored at the (bias-shifted) grid points; r_hat uses the unshifted grid
            zl = np.stack([z[gi[s]] for s in COLUMNS])
            zpl = np.array([zp[gi[s]] for s in COLUMNS])
            pooled_z = (z, zp, zl, zpl) if pooled_z is None else tuple(a + b for a, b in zip(pooled_z, (z, zp, zl, zpl)))
    if pooled_z is None:
        out["pooled"] = {"identifiable": False}
    else:
        z, zp, zl, zpl = pooled_z
        lab = zl.argmax(axis=0)
        rb = GRID[z.argmax(axis=0)]
        dist = support(lab)
        out["pooled"] = {
            "identifiable": True,
            "positions": [p for p in POOLED if out["positions"].get(p, {}).get("identifiable")],
            "r_hat": float(GRID[zp.argmax()]),
            "r_hat_ci80": [float(np.quantile(rb, 0.1)), float(np.quantile(rb, 0.9))],
            "dist": dist,
            "top": COLUMNS[int(np.argmax(zpl))],
        }
    if "TE" in boot_rhat and "WR" in boot_rhat and out["positions"]["TE"].get("identifiable"):
        d = boot_rhat["TE"] - boot_rhat["WR"]
        lo, hi = float(np.quantile(d, 0.1)), float(np.quantile(d, 0.9))
        te = out["positions"]["TE"]["r_hat"]
        out["te_premium_probe"] = {
            "r_hat_te_minus_wr": round(te - out["positions"]["WR"]["r_hat"], 2),
            "ci80": [round(lo, 2), round(hi, 2)],
            "flag": bool(te >= 1.25 and lo > 0),
        }
    return out


# ---------------------------------------------------------------- cost of a wrong assignment

def m_at(ref, k, s):
    std, rec = ref[k]
    return std + LABEL_R[s] * rec


def cost_of_half(values: dict, ref: dict, pos_of: dict, true_col: str) -> dict:
    out = {}
    for p in POOLED:
        keys = [k for k in select(values, ref, pos_of, p, TOP_N[p]) if m_at(ref, k, "standard") > 0]
        if len(keys) < 8:
            continue
        err = {k: m_at(ref, k, true_col) / m_at(ref, k, "half_ppr") - 1 for k in keys}
        row = {"n": len(keys), "pairs": len(keys) * (len(keys) - 1) // 2,
               "median_abs_value_error_pct": round(100 * float(np.median([abs(e) for e in err.values()])), 1)}
        for target in ("standard", "ppr"):
            a = {k: np.log(values[k] * m_at(ref, k, target) / m_at(ref, k, true_col)) for k in keys}
            b = {k: np.log(values[k] * m_at(ref, k, target) / m_at(ref, k, "half_ppr")) for k in keys}
            flips = sum(1 for i, j in combinations(keys, 2) if (a[i] - a[j]) * (b[i] - b[j]) < 0)
            row[f"pair_flips_target_{target}"] = flips
        if p == "RB":
            share = sorted(keys, key=lambda k: -ref[k][1] / m_at(ref, k, "half_ppr"))
            pc = share[: max(1, len(keys) // 3)]
            errs = [100 * err[k] for k in pc]
            pos_med = float(np.median([err[k] for k in keys]))
            rel = [100 * ((1 + err[k]) / (1 + pos_med) - 1) for k in pc]
            row["pass_catching_backs"] = {"n": len(pc), "median_value_error_pct": round(float(np.median(errs)), 1),
                                          "max_abs_value_error_pct": round(float(max(abs(e) for e in errs)), 1),
                                          "median_error_vs_rb_median_pct": round(float(np.median(rel)), 1),
                                          "max_abs_error_vs_rb_median_pct": round(float(max(abs(e) for e in rel)), 1)}
        row["median_value_error_pct"] = round(100 * float(np.median(list(err.values()))), 1)
        out[p] = row
    if "RB" in out and "WR" in out:
        out["wr_level_vs_rb_pct"] = round(100 * ((1 + out["WR"]["median_value_error_pct"] / 100)
                                                 / (1 + out["RB"]["median_value_error_pct"] / 100) - 1), 1)
    return out


# ---------------------------------------------------------------- FantasyCalc multipliers

def fc_multipliers(charts: dict, ref: dict, pos_of: dict) -> dict:
    a, b = charts["fantasycalc"]["standard"], charts["fantasycalc"]["ppr"]
    out = {}
    for p in POS:
        keys = [k for k in select(b, ref, pos_of, p, TOP_N[p]) if a.get(k, 0) > 0 and m_at(ref, k, "standard") > 0]
        if len(keys) < 8:
            continue
        chart_ratio = float(np.median([b[k] / a[k] for k in keys]))
        proj_ratio = float(np.median([m_at(ref, k, "ppr") / m_at(ref, k, "standard") for k in keys]))
        same_order = [k for k in sorted(keys, key=lambda k: (-a[k], k))] == [k for k in sorted(keys, key=lambda k: (-b[k], k))]
        out[p] = {"n": len(keys), "fc_full_over_std": round(chart_ratio, 3),
                  "projection_full_over_std": round(proj_ratio, 3), "same_within_position_order": same_order}
    if "RB" in out and "WR" in out:
        out["wr_vs_rb"] = {"fc": round(out["WR"]["fc_full_over_std"] / out["RB"]["fc_full_over_std"], 3),
                           "projections": round(out["WR"]["projection_full_over_std"] / out["RB"]["projection_full_over_std"], 3)}
    return out


# ---------------------------------------------------------------- two-column check

def column_ratio_tracks_receptions(charts: dict, ref: dict, pos_of: dict) -> dict:
    """For charts with their own Standard and Full columns: Spearman between the chart's
    Full/Standard ratio and the projections' reception share rec / m(0.5), top N by Full."""
    out = {}
    for chart in CHARTS:
        a, b = charts[chart]["standard"], charts[chart]["ppr"]
        row = {}
        for p in POOLED:
            keys = [k for k in select(b, ref, pos_of, p, TOP_N[p]) if a.get(k, 0) > 0 and m_at(ref, k, "half_ppr") > 0]
            if len(keys) < 8:
                continue
            ratio = np.array([b[k] / a[k] for k in keys])
            share = np.array([ref[k][1] / m_at(ref, k, "half_ppr") for k in keys])
            rho = None if np.ptp(ratio) == 0 else round(float(_corr_rows(rankdata(ratio), rankdata(share))), 3)
            row[p] = {"n": len(keys), "spearman_ratio_vs_rec_share": rho}
        out[chart] = row
    return out


# ---------------------------------------------------------------- validation

def validate(cases: list) -> dict:
    """Labelled test on CBS and USA Today, weeks 5-9 (pass bars pre-stated in the note)."""
    by = {(c["chart"], c["week"], c["column"]): c["result"]["pooled"] for c in cases}
    rows, correct, cross, sep_ok, sep_n, true_support = [], 0, 0, 0, 0, []
    half_top, half_between = 0, 0
    for chart in LABELLED:
        for w in WEEKS:
            wk = f"week-{w}"
            r = {col: by[(chart, wk, col)] for col in COLUMNS}
            for col in ("standard", "ppr"):
                pooled = r[col]
                top = pooled.get("top")
                p_true = pooled["dist"][col] if pooled.get("identifiable") else 1 / 3
                correct += top == col
                cross += top == ("ppr" if col == "standard" else "standard")
                true_support.append(p_true)
                rows.append({"chart": chart, "week": wk, "column": col, "top": top,
                             "r_hat": pooled.get("r_hat"), "p_true": round(p_true, 3)})
            sep_n += 1
            rs, rh, rf = (r[c].get("r_hat") for c in COLUMNS)
            if None not in (rs, rf):
                sep_ok += rf > rs
            half_top += r["half_ppr"].get("top") == "half_ppr"
            if None not in (rs, rh, rf):
                half_between += rs <= rh <= rf
    n = len(rows)
    p1 = correct >= 0.8 * n
    p2 = sep_ok == sep_n and cross == 0
    return {"cases": rows, "n": n, "correct": correct, "cross_errors": cross,
            "separated_chart_weeks": f"{sep_ok}/{sep_n}", "mean_support_on_true": round(float(np.mean(true_support)), 3),
            "half_top_correct": f"{half_top}/{sep_n}", "half_r_hat_between": f"{half_between}/{sep_n}",
            "P1_pass": bool(p1), "P2_pass": bool(p2), "pass": bool(p1 and p2)}


def position_bias(cases: list, charts: tuple) -> dict:
    """Mean (r_hat_p - true r) over the labelled Standard and Full columns of `charts`, weeks 5-9."""
    acc: dict = {}
    for c in cases:
        if c["chart"] in charts and c["week"] != "current" and c["column"] in ("standard", "ppr"):
            for p in POOLED:
                pr = c["result"]["positions"].get(p, {})
                if "r_hat" in pr:
                    acc.setdefault(p, []).append(pr["r_hat"] - LABEL_R[c["column"]])
    return {p: round(float(np.mean(v)), 2) for p, v in acc.items()}


def summarize(cases: list) -> dict:
    """Per chart and week: the pooled answer on each column (compact)."""
    out: dict = {}
    for c in cases:
        pl = c["result"]["pooled"]
        out.setdefault(c["chart"], {}).setdefault(c["week"], {})[c["column"]] = (
            {"top": pl["top"], "r_hat": pl["r_hat"], "ci80": pl["r_hat_ci80"], "dist": pl["dist"]}
            if pl.get("identifiable") else {"top": None, "identifiable": False})
    return out


def run_variant(weeks, pos_of, boot, ident_min, bias_for=None) -> list:
    cases = []
    for wi, wk in enumerate(weeks):
        for ci, chart in enumerate(CHARTS):
            bias = bias_for(chart) if bias_for else None
            for col in COLUMNS:
                # same seed for a chart-week's three columns: paired resamples, so columns with
                # the same within-position order (FantasyCalc, FantasyPros) get identical answers
                rng = np.random.default_rng([SEED, wi, ci])
                res = assess(wk["charts"][chart][col], wk["ref"], pos_of, boot, rng, ident_min, bias)
                cases.append({"chart": chart, "week": wk["label"], "column": col, "bias": bias, "result": res})
    return cases


def pseudo_chart_check(pos_of: dict, boot: int) -> dict:
    """Sanity check with known labels and no chart opinion: one projection's ppg at each
    scoring is the 'chart', the mean of the other two is the reference (weeks 5-9)."""
    rng = np.random.default_rng(SEED)
    rows, correct, cross, n = [], 0, 0, 0
    for w in WEEKS:
        src = json.loads((HISTORY / f"week-{w}.json").read_text())["sources"]
        raw = {p: {int(k): v for k, v in src[p]["ppg"].items()} for p in PROJ}
        for held in PROJ:
            ref = reference([raw[p] for p in PROJ if p != held])
            for col in ("standard", "ppr"):
                j = COLUMNS.index(col)
                values = {k: float(t[j]) for k, t in raw[held].items() if t and t[j] is not None}
                pl = assess(values, ref, pos_of, boot, rng, 0.0)["pooled"]
                n += 1
                correct += pl.get("top") == col
                cross += pl.get("top") == ("ppr" if col == "standard" else "standard")
                rows.append({"week": w, "chart": held, "column": col, "top": pl.get("top"),
                             "r_hat": pl.get("r_hat"), "p_true": pl["dist"][col] if pl.get("dist") else None})
    return {"n": n, "correct": correct, "cross_errors": cross, "rows": rows}


def run(boot: int = 500) -> dict:
    pos_of = positions()
    weeks = [load_week(w) for w in WEEKS] + [load_current()]
    variants = {}
    pre = run_variant(weeks, pos_of, boot, IDENT_MIN_DISCORDANT)
    variants["prestated"] = pre
    allpos = run_variant(weeks, pos_of, boot, 0.0)
    variants["posthoc_all_positions"] = allpos
    bias_by_chart = {"cbs": position_bias(allpos, ("usatoday",)), "usatoday": position_bias(allpos, ("cbs",))}
    bias_pooled = position_bias(allpos, LABELLED)
    variants["posthoc_loco_bias"] = run_variant(weeks, pos_of, boot, 0.0,
                                                lambda c: bias_by_chart.get(c, bias_pooled))
    costs, fc, two_col = [], {}, {}
    for wk in weeks:
        for chart in LABELLED:
            for col in ("standard", "ppr"):
                costs.append({"chart": chart, "week": wk["label"], "true_column": col, "assigned": "half_ppr",
                              "by_position": cost_of_half(wk["charts"][chart][col], wk["ref"], pos_of, col)})
        fc[wk["label"]] = fc_multipliers(wk["charts"], wk["ref"], pos_of)
        two_col[wk["label"]] = column_ratio_tracks_receptions(wk["charts"], wk["ref"], pos_of)
    return {
        "meta": {"ticket": "JEG-1598", "parent": "JEG-1597", "boot": boot, "seed": SEED, "top_n": TOP_N,
                 "grid": [float(GRID[0]), float(GRID[-1]), 0.05], "pooled_positions": list(POOLED),
                 "ident_min_discordant_prestated": IDENT_MIN_DISCORDANT,
                 "current_vintage": weeks[-1].get("vintage"),
                 "variants": {"prestated": "method as pre-stated",
                              "posthoc_all_positions": "post hoc: identifiability floor 0, every RB/WR/TE pooled",
                              "posthoc_loco_bias": "post hoc: floor 0 plus a per-position r offset learned on the other labelled chart (fantasypros/fantasycalc: both)"},
                 "loco_bias": {"by_chart": bias_by_chart, "pooled": bias_pooled},
                 "note": "docs/research/jeg1597/step1-scoring-assignment.md"},
        "validation": {k: validate(v) for k, v in variants.items()},
        "sanity_projection_pseudo_charts": pseudo_chart_check(pos_of, boot),
        "summary": {k: summarize(v) for k, v in variants.items()},
        "cases": {k: v for k, v in variants.items()},
        "fantasycalc_multipliers": fc,
        "two_column_ratio_vs_reception_share": two_col,
        "cost_of_half_assignment": costs,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=500)
    args = ap.parse_args()
    out = run(args.boot)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    for name, v in out["validation"].items():
        print(f"{name:22s} labelled {v['correct']}/{v['n']} correct, cross {v['cross_errors']}, separated "
              f"{v['separated_chart_weeks']}, mean p_true {v['mean_support_on_true']}, half top {v['half_top_correct']}, "
              f"half between {v['half_r_hat_between']}, P1 {v['P1_pass']} P2 {v['P2_pass']}")
    print("loco bias", out["meta"]["loco_bias"])
    sc = out["sanity_projection_pseudo_charts"]
    print(f"pseudo-charts (projections): {sc['correct']}/{sc['n']} correct, cross {sc['cross_errors']}")


if __name__ == "__main__":
    main()
