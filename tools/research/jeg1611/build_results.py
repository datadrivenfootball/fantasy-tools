"""JEG-1611: build docs/research/jeg1611/results.md from the run JSON only.

Tier 1 verdicts by the frozen rule (docs/research/jeg1611/pass-rule.md, both
amendment sections). Reads out/v4/holdout/dev_weeks_5_6_7 (dev) and
out/v4/holdout/weeks_8_9 (confirmation run), and out/shrink/rolling.json (T1).

Run:  /usr/bin/python3 tools/research/jeg1611/build_results.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEV = HERE / "out" / "v4" / "holdout" / "dev_weeks_5_6_7"
HOLD = HERE / "out" / "v4" / "holdout" / "weeks_8_9"
ROLLING = HERE / "out" / "shrink" / "rolling.json"
OUT = REPO / "docs" / "research" / "jeg1611" / "results.md"
SUBJ = ("fantasycalc", "fantasypros")
G1_CELLS = ("cbs|standard->ppr", "cbs|ppr->standard", "usatoday|standard->ppr", "usatoday|ppr->standard")
VARIANTS = ("v4", "v4_mult", "v4_tail", "v4_raw", "v4_recg", "v4_assumed", "v4_chartzero", "v4_ddfrate")


def load(d):
    return {k: json.loads((d / f"{k}.json").read_text(encoding="utf-8")) for k in ("g1", "g2", "g3", "coverage",
                                                                                   "review1", "extremes")}


def ci(d, nd=3):
    if not d or d.get("est") is None:
        return "n/a"
    return f"{d['est']:+.{nd}f} [{d['ci'][0]:+.{nd}f}, {d['ci'][1]:+.{nd}f}]"


def no_harm(d):
    """Lower bound >= 0 PASS; interval entirely below 0 FAIL (harm); else INCONCLUSIVE."""
    lo, hi = d["ci"]
    return "PASS" if lo >= 0 else "FAIL" if hi < 0 else "INCONCLUSIVE"


def combine(vs):
    vs = list(vs)
    return "PASS" if all(v == "PASS" for v in vs) else "FAIL" if "FAIL" in vs else "INCONCLUSIVE"


def tier1(J, meth="v4"):
    g2, g3, rv = J["g2"], J["g3"], J["review1"]
    t = {}
    t["T2"] = {"value": f"{rv['exactness']['identity_combinations']} identity combinations, max diff "
                        f"{rv['exactness']['identity_max_abs_diff']}; current DDF reproduced "
                        f"{rv['exactness']['current_ddf_reproduced']}; fixed allocation reproduces anchor "
                        f"{rv['exactness']['fixed_allocation_reproduces_anchor']}",
               "verdict": "PASS" if rv["exactness"]["pass"] else "FAIL"}
    cells = {c: rv["g1_within_paired"][f"{c}|{meth}"]["cell"] for c in G1_CELLS}
    t["T3"] = {"value": "; ".join(f"{c} {ci(v, 4)} {no_harm(v)}" for c, v in cells.items()),
               "verdict": combine(no_harm(v) for v in cells.values())}
    t4 = {}
    for s in SUBJ:
        c = g2["main"][f"{s}|mean"][meth]["corr"]
        p95 = g2["placebo"][f"{s}|mean|{meth}"]["corr"]["p95"]
        t4[s] = (c, p95, c["ci"][0] > 0 and c["est"] > p95)
    t["T4"] = {"value": "; ".join(f"{s} corr {ci(c)} (placebo p95 {p:+.3f})" for s, (c, p, _) in t4.items()),
               "verdict": "PASS" if all(ok for *_x, ok in t4.values()) else "FAIL"}
    t5 = {s: rv["g2_size"][f"{s}|mean|{meth}"]["sd_ratio"] for s in SUBJ}
    t["T5"] = {"value": "; ".join(f"{s} {ci(v)}" for s, v in t5.items()),
               "verdict": "PASS" if all(0.5 <= v["est"] <= 1.5 for v in t5.values()) else "FAIL"}
    g3label = {"v4": "primary", "v4_chartzero": "chartzero", "v4_ddfrate": "ddfrate"}.get(meth)
    parts = {f"G2 {s}": g2["main"][f"{s}|mean"][meth]["a_standard_diff"] for s in SUBJ}
    if g3label:
        parts.update({f"G3 {k}": row[g3label]["a_standard_diff"] for k, row in g3["cells"].items()})
    t["T6"] = {"value": "; ".join(f"{k} {ci(v)} {no_harm(v)}" for k, v in parts.items()),
               "verdict": combine(no_harm(v) for v in parts.values())}
    t8 = rv["t8_realized"]
    t8parts = {"CBS F->S v4 - unchanged": ("G1|cbs|ppr->standard", "v4-unchanged"),
               "USA Today F->S v4 - unchanged": ("G1|usatoday|ppr->standard", "v4-unchanged"),
               "FantasyCalc Standard v4 - base": ("G2|fantasycalc|standard", "v4-base"),
               "FantasyPros Standard v4 - base": ("G2|fantasypros|standard", "v4-base")}
    vals, verd = [], []
    if meth != "v4":
        t["T8"] = {"value": "computed for v4 only", "verdict": "n/a"}
    else:
        for lab, (k, dk) in t8parts.items():
            d = t8[k]
            if "undefined" in d:
                vals.append(f"{lab} undefined ({d['undefined']}; n by week {d['n_by_week']})")
                verd.append("INCONCLUSIVE")
                continue
            x = d["diffs"][dk]["all"]
            ok = x["est"] >= 0 and x["ci"][1] >= 0
            vals.append(f"{lab} {ci(x)} (weeks used {d['weeks_used']})")
            verd.append("PASS" if ok else "FAIL")
        t["T8"] = {"value": "; ".join(vals), "verdict": combine(verd)}
    return t


def t1():
    d = json.loads(ROLLING.read_text(encoding="utf-8"))["E"]["primary"]["viii_over_share_minus_vi_full_forecast"]
    won = int(d["seasons_won"].split()[0])
    ok = won >= 6 and d["ci95"][0] > 0
    return {"value": f"{d['diff']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}], {d['seasons_won']} forward seasons",
            "verdict": "PASS" if ok else "FAIL"}


RULES = {
    "T1": "Rolling-origin share-model conversion beats not converting in >= 6 of 8 forward seasons, interval above 0",
    "T2": "Identity at s = s0 exact on every chart-week; current DDF and the fixed-allocation anchor reproduced",
    "T3": "G1 within no harm, 4 cells: paired lower bound of (v4 - unchanged) >= 0 (crossing 0 inconclusive, below 0 harm)",
    "T4": "G2 direction, both subjects, mean reference: corr interval above 0 and point above placebo p95",
    "T5": "G2 size, both subjects, mean reference: sd ratio point estimate in [0.5, 1.5]",
    "T6": "Agreement no harm: G2 (a) Standard and G3 (a) Standard, lower bound >= 0 for every subject / cell",
    "T8": "Realized points, Full to Standard: v4 - unchanged (G1) and v4 - base (G2) point >= 0, interval not entirely below 0",
}


def table_tier1(dev, hold):
    L = ["| # | Rule | Dev (weeks 5-7) | Weeks 8-9 | Verdict (8-9) |", "| --- | --- | --- | --- | --- |"]
    T1 = t1()
    L.append(f"| T1 | {RULES['T1']} | (fixed, not re-run) | {T1['value']} | **{T1['verdict']}** |")
    for k in ("T2", "T3", "T4", "T5", "T6", "T8"):
        L.append(f"| {k} | {RULES[k]} | {dev[k]['value']} ({dev[k]['verdict']}) | {hold[k]['value']} | "
                 f"**{hold[k]['verdict']}** |")
    verdicts = [T1["verdict"]] + [hold[k]["verdict"] for k in ("T2", "T3", "T4", "T5", "T6", "T8")]
    overall = "PASS" if all(v == "PASS" for v in verdicts) else "DOES NOT PASS"
    return L, overall, verdicts


def g1_won(J, meas):
    t = J["g1"]["table"]
    L = ["| Cell | " + " | ".join(VARIANTS) + " |", "| --- |" + " --- |" * len(VARIANTS)]
    for c in G1_CELLS:
        for m in meas:
            row = t[f"{c}|{m}"]
            L.append(f"| {c} {m} | " + " | ".join(str(row.get(f"weeks_won|{v}", "n/a")) for v in VARIANTS) + " |")
    return L


def level_moves(J):
    sm = J["g2"]["level_moves"]["summary"]
    any_key = next(iter(sm))
    rm = {r: [sm[any_key][f"{r}|{q}"]["mean_ref_move"] for q in ("WR/RB", "TE/RB")] for r in ("cbs", "usatoday", "mean")}
    L = [f"References (mean of weeks): WR/RB CBS {rm['cbs'][0]:+.3f}, USA Today {rm['usatoday'][0]:+.3f}; "
         f"TE/RB CBS {rm['cbs'][1]:+.3f}, USA Today {rm['usatoday'][1]:+.3f}.", "",
         "| Subject, method | WR/RB move | TE/RB move | weeks closer than unchanged vs CBS (WR/RB, TE/RB) | vs USA Today | vs mean |",
         "| --- | --- | --- | --- | --- | --- |"]
    for s in SUBJ:
        for m in ("v2",) + VARIANTS:
            d = sm.get(f"{s}|{m}")
            if not d:
                continue
            L.append(f"| {s}, {m} | {d['mean|WR/RB']['mean_move']:+.3f} | {d['mean|TE/RB']['mean_move']:+.3f} | " +
                     " | ".join(f"{d[r + '|WR/RB']['weeks_closer_than_unchanged']}, {d[r + '|TE/RB']['weeks_closer_than_unchanged']}"
                                for r in ("cbs", "usatoday", "mean")) + " |")
    return L


def size_table(J):
    gs = J["review1"]["g2_size"]
    L = ["| Subject | method | sd ratio (T5 statistic) | closer / E[r^2] | slope ref on method |", "| --- | --- | --- | --- | --- |"]
    for s in SUBJ:
        for m in ("v1", "v2") + VARIANTS + ("v4_fchalf", "pub_cbs", "pub_usatoday"):
            d = gs.get(f"{s}|mean|{m}")
            if d:
                L.append(f"| {s} | {m} | {ci(d['sd_ratio'])} | {ci(d['closer_norm'])} | {ci(d['slope_ref_on_method'])} |")
    return L


def robustness(J):
    """Tier 1 point estimates under each robustness variant, with 'hinges on' when a sign flips."""
    g2, rv = J["g2"], J["review1"]
    L = ["| Variant | G2 verdict | T4 corr FC / FP | T5 sd ratio FC / FP | T6 G2 (a) Std FC / FP | hinges on |",
         "| --- | --- | --- | --- | --- | --- |"]
    base = {s: g2["main"][f"{s}|mean"]["v4"] for s in SUBJ}
    for m in ("v4", "v4_fchalf", "v4_assumed", "v4_mult", "v4_chartzero", "v4_ddfrate", "v4_raw", "v4_recg"):
        rows = {s: g2["main"][f"{s}|mean"].get(m) for s in SUBJ}
        subj = [s for s in SUBJ if rows[s]]
        flips = []
        for s in subj:
            for stat in ("corr", "a_standard_diff"):
                a, b = base[s][stat]["est"], rows[s][stat]["est"]
                if (a > 0) != (b > 0):
                    flips.append(f"{s} {stat}")
        sd = [rv["g2_size"].get(f"{s}|mean|{m}") for s in subj]
        ver = g2["verdicts"].get(m, {}).get("ranking", {}).get("verdict", "n/a")
        L.append(f"| {m} | {ver} | " + " / ".join(f"{rows[s]['corr']['est']:+.3f}" for s in subj) + " | " +
                 " / ".join(f"{d['sd_ratio']['est']:.2f}" for d in sd if d) + " | " +
                 " / ".join(f"{rows[s]['a_standard_diff']['est']:+.3f}" for s in subj) + f" | {', '.join(flips) or 'none'} |")
    return L


def g3_table(J):
    g3 = J["g3"]
    L = ["| Pair | verdict | by set | (a) Std diff per set/ref | hinges on (sign flip of (a) Std vs primary) |",
         "| --- | --- | --- | --- | --- |"]
    for lab, v in g3["verdicts"].items():
        cells = "; ".join(f"{k} {ci(row[lab]['a_standard_diff'])}" for k, row in g3["cells"].items())
        hg = [k.split("|", 1)[1] for k, f in g3["hinges_on_sign_flip_a_standard"].items() if f and k.split("|")[0] == lab]
        L.append(f"| {lab} | {v['overall']} | {v['by_set']} | {cells} | {', '.join(hg) or 'none'} |")
    return L


def calib(J):
    L = ["| Chart, s0, pos | n | P0 slope | P0 intercept | P0 R^2 | proj slope | proj intercept | proj R^2 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    g = lambda x, f=".3f": "n/a" if x is None else format(x, f)
    for k, d in J["review1"]["calibration"].items():
        c, q = d["chart_P0"], d["projections_mean_ppg"]
        L.append(f"| {k} | {d['n']} | {g(c['slope'])} | {g(c['intercept'], '+.2f')} | {g(c['r2'])} | {g(q['slope'])} | "
                 f"{g(q['intercept'], '+.2f')} | {g(q['r2'])} |")
    return L


def coverage(J):
    L = ["| Unwind | priced | invertible | below_waiver | no_inverse | fallback_prior |", "| --- | --- | --- | --- | --- | --- |"]
    for k, a in J["coverage"]["pooled"].items():
        L.append(f"| {k} | {a['priced']} | {a['invertible']} | {a['below_waiver']} | {a['no_inverse']} | {a['fallback_prior']} |")
    return L


def ddfrate_numbers(J):
    """Headline numbers for v4_ddfrate (and v4 beside it)."""
    import statistics
    out = {}
    cells = J["g1"]["cells"]
    weeks = list(cells[G1_CELLS[0]].keys())
    for m in ("v4", "v4_ddfrate"):
        r = {}
        for c in G1_CELLS:
            r[c] = {p: (statistics.fmean(cells[c][w][m]["median_ratio_to_input"][p] for w in weeks),
                        statistics.fmean(cells[c][w]["published_median_ratio"][p] for w in weeks)) for p in ("RB", "WR", "TE")}
        sm = J["g2"]["level_moves"]["summary"]
        lm = {s: (sm[f"{s}|{m}"]["mean|WR/RB"]["mean_move"], sm[f"{s}|{m}"]["mean|TE/RB"]["mean_move"]) for s in SUBJ}
        within = {c: J["review1"]["g1_within_paired"][f"{c}|{m}"]["cell"] for c in G1_CELLS}
        ov = J["review1"]["overshoot_by_method"][m]
        out[m] = {"ratios": r, "level_moves": lm, "within": within, "overshoot": ov}
    return out


def ddfrate_lines(D, label):
    L = []
    for m in ("v4", "v4_ddfrate"):
        d = D[m]
        rat = "; ".join(f"{c} " + ", ".join(f"{p} {a:.2f}/{b:.2f}" for p, (a, b) in d["ratios"][c].items()) for c in G1_CELLS)
        L.append(f"- {label}, {m}: median rebuilt/published ratio {rat}. Level moves WR/RB, TE/RB: "
                 + "; ".join(f"{s} {a:+.3f}, {b:+.3f}" for s, (a, b) in d["level_moves"].items())
                 + ". Paired within: " + "; ".join(f"{c} {ci(v, 4)}" for c, v in d["within"].items())
                 + f". Overshoot {d['overshoot']['n_v4_beyond_both']} of {d['overshoot']['n_same_side']}.")
    return L


HEADER = """# JEG-1611: scoring-aware DDF v4, results of the weeks 8-9 confirmation run

Generated by `tools/research/jeg1611/build_results.py` from the run JSON only
(`tools/research/jeg1611/out/v4/holdout/weeks_8_9/`, dev numbers from `.../dev_weeks_5_6_7/`,
T1 from `out/shrink/rolling.json`). Research only: no change to published numbers, the value model
or the live pipeline.

**What v4 is.** Jeremy's seven steps as built in iterations 3-3a (`docs/research/jeg1611/iteration-log.md`):
Adjusted value from the unmodified pipeline at the anchor; expected points `P_i(s0)` by the inverse of the
projections' pricing; replacement in points at each scoring with the anchor's allocation mix held;
the cross-validated share model for how each player earns points (`P_i(s) = P_i(s0) (1 + r_s sh_i) /
(1 + r_s0 sh_i)`); one chart-points-per-VORP-point slope per position, additive delta; the unmodified
pipeline at the target scoring; DDF Value = the mean of the charts' Adjusted values. FantasyCalc anchored
at Full (Half as sensitivity), FantasyPros at Half, CBS Sports and USA Today as published. Code
`tools/research/jeg1611/v4.py`, runner `run_v4.py`; tests `tests/test_jeg1611_v4.py` (15 pass; exactness
re-checked on weeks 8-9 as T2). Commits: v4 cfdf78aab, iteration 4 e15b7ac19, iteration 5 fc4aae5fb, this
run {commit}.

**Status of these weeks.** Weeks 8-9 are a **confirmation run**, not a clean holdout (v3's results on weeks
5-9 were read before the rule was written; pass-rule amendment 1). **Week 10 decides**, re-run with the same
runner and the same rule. The rule is `docs/research/jeg1611/pass-rule.md` with both amendment sections,
frozen before any week 8-9 number was printed. Brackets are 95% paired player bootstrap intervals (2,000
resamples, seed 16052; placebo seed 16053)."""

LIMITS = """## Limits

- **T8 truth is three weeks at most** (2026 weeks w..9), and **week 9's actuals are nearly empty** (36
  rows in `weekly_actuals_2024_2026.csv`), so at snapshot week 8 only players with a week 9 row have 2 ROS
  games and at week 9 no player does; a week enters T8 only when every position has 3 or more players.
- **Anchors are assumed**: FantasyCalc's base list read as Full and FantasyPros as Half.
- **Weeks 8-9 were seen by v3** (JEG-1610 ran on weeks 5-9), so they confirm, they do not decide.
- Two weeks of snapshots, overlapping and not independent; CBS Sports and USA Today are references, not
  truth, and disagree with each other on the size of the cross-position move.
- `v4_ddfrate` was added after the dev numbers of item 6 were seen (Tier 2, reported only).
- The weeks 8-9 calibration table rests on 1-7 players per cell (the same thin truth as T8) and is not
  interpretable; the dev calibration (iteration 5, item 7) is the usable one.
- `pub_cbs` and `pub_usatoday` have identical `closer / E[r^2]` against the mean reference by
  construction (each publisher sits the same distance from their average)."""

DDFRATE_NOTE = """`v4_ddfrate` multiplies each position's slope at the target by DDF's own value-per-point ratio,
so the rebuilt natives hardly change level: their median rebuilt-to-input ratios are 0.92-1.06 in every
cell, against published 0.78-1.29. It therefore lands short of the publishers rather than beyond them
(overshoot 0 of 36 on weeks 8-9, 2 of 58 on dev; at CBS Standard to Full WR 1.05 and TE 1.01 are below
both CBS's 1.19 / 1.29 and USA Today's 1.06 / 1.07). Its position-share and native-level cells improve
(G1 levels_norm at CBS 2 of 2 in both directions), but within-position order and the G2 size ratio stay
v4's (sd ratio 1.52 / 1.59): a per-position rescaling cannot reorder a position. It changes no Tier 1
verdict."""


def main():
    dev, hold = load(DEV), load(HOLD)
    t_dev, t_hold = tier1(dev), tier1(hold)
    T1L, overall, _ = table_tier1(t_dev, t_hold)
    dr_dev, dr_hold = tier1(dev, "v4_ddfrate"), tier1(hold, "v4_ddfrate")
    D_dev, D_hold = ddfrate_numbers(dev), ddfrate_numbers(hold)
    import subprocess
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    hdr = HEADER.replace("{commit}", f"(after {commit})")
    L = [hdr.rstrip(), "", "## Tier 1 (frozen rule)", ""] + T1L + ["", f"**Overall verdict by the rule (weeks 8-9): v4 {overall}.**", "",
         "Per-position paired within (weeks 8-9, v4 - unchanged), TE named when below -0.01:", ""]
    for c in G1_CELLS:
        for w, d in hold["review1"]["g1_within_paired"][f"{c}|v4"]["by_week"].items():
            te = d["TE"]["est"]
            L.append(f"- {c} week {w}: RB {ci(d['RB'], 4)}, WR {ci(d['WR'], 4)}, TE {ci(d['TE'], 4)}"
                     + (" (**TE loss below -0.01**)" if te < -0.01 else ""))
    L += ["", "## Tier 2 (reported, no verdict)", "", "### G1 original measures, weeks won over unchanged (of 2, weeks 8-9)", ""]
    L += g1_won(hold, ("within", "levels", "xpos"))
    L += ["", f"Totals of {hold['g1']['weeks_won_totals_of']}: " + ", ".join(f"{k} {v}" for k, v in hold["g1"]["weeks_won_totals"].items()), ""]
    L += ["### G1 scale-free levels, weeks won (of 2)", ""] + g1_won(hold, ("levels_norm", "levels_norm_pos")) + [""]
    L += ["### Level moves vs the publishers (weeks 8-9)", ""] + level_moves(hold) + [""]
    ov = hold["review1"]["overshoot_by_method"]
    L += ["### Overshoot count (weeks 8-9; dev in brackets)", "",
          "| Method | v beyond both / same-side cells |", "| --- | --- |"]
    for m in VARIANTS:
        a, b = ov[m], dev["review1"]["overshoot_by_method"][m]
        L.append(f"| {m} | {a['n_v4_beyond_both']} / {a['n_same_side']} ({b['n_v4_beyond_both']} / {b['n_same_side']}) |")
    L += ["", "### G2 size and closer normalised by E[r^2] (weeks 8-9, mean reference)", ""] + size_table(hold) + [""]
    L += ["### G2 robustness (weeks 8-9)", ""] + robustness(hold) + [""]
    L += ["### G3 verdicts and robustness (weeks 8-9)", ""] + g3_table(hold) + [""]
    L += ["### Publishers' week-to-week level-move SD (weeks 8-9)", ""]
    for k, d in hold["review1"]["publisher_move_sd"].items():
        L.append(f"- {k}: {d['sd']:.4f}")
    vp = hold["review1"]["value_per_point"]["mean_ratio_full_over_std"]
    L += ["", "### DDF value per point, Full / Standard slope ratio (weeks 8-9)", "",
          "| Source | QB | RB | WR | TE |", "| --- | --- | --- | --- | --- |"]
    for key in ("projections", "v4_charts"):
        L.append(f"| {key} | " + " | ".join(f"{vp[f'{key}|{p}']:.3f}" if vp[f"{key}|{p}"] else "n/a" for p in ("QB", "RB", "WR", "TE")) + " |")
    L += ["", "## Calibration (weeks 8-9, realized ROS ppg on P_i(s0))", ""] + calib(hold)
    L += ["", "## Coverage (weeks 8-9 pooled)", ""] + coverage(hold)
    L += ["", "## What the variants say: v4_ddfrate", "",
          f"Tier 1 for v4_ddfrate (reported only, not the primary): dev " +
          ", ".join(f"{k} {v['verdict']}" for k, v in dr_dev.items()) + "; weeks 8-9 " +
          ", ".join(f"{k} {v['verdict']}" for k, v in dr_hold.items()) + ".", ""]
    L += [DDFRATE_NOTE, ""] + ddfrate_lines(D_dev, "dev 5-7") + ddfrate_lines(D_hold, "weeks 8-9")
    L += ["", LIMITS, ""]
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("wrote", OUT, "overall", overall)
    print(json.dumps({"dev": {k: v["verdict"] for k, v in t_dev.items()}, "hold": {k: v["verdict"] for k, v in t_hold.items()},
                      "ddfrate_dev": {k: v["verdict"] for k, v in dr_dev.items()},
                      "ddfrate_hold": {k: v["verdict"] for k, v in dr_hold.items()}}))


if __name__ == "__main__":
    main()
