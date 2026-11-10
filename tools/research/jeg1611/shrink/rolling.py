"""JEG-1611 rolling-origin (forward-only) check of run_shrink.py.

For each test season T in 2018-2025 everything is fitted on seasons < T only:
half-life, decay, k, the B vs C_linear form choice (inner leave-one-season-out
inside seasons < T, same rule as run_shrink: C wins pooled MSE and >= 7/11 of
seasons, scaled to the inner count), the share model, and the E regression
coefficients (whose rec_hat / share_hat features on train rows come from the
same < T fit). Features: a decision row at (S, w) uses games of seasons < S and
weeks < w of S only, so restricting training rows to S < T keeps every
training feature and target inside seasons < T; test rows use weeks 1..w-1 of T.

Run: /usr/bin/python3 tools/research/jeg1611/shrink/rolling.py
Writes out/shrink/rolling.json and appends a section to out/shrink/results.md.
"""
from __future__ import annotations

import json
import math
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_shrink as S  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
TEST = tuple(range(2018, 2026))
T975 = {7: 2.365}
POS = S.POS


def t_int(v):
    v = np.asarray([x for x in v if np.isfinite(x)])
    m = v.mean()
    h = T975.get(len(v) - 1, 2.365) * v.std(ddof=1) / math.sqrt(len(v))
    return m, m - h, m + h


def fit_form(N, STD, REC, y, rows, form):
    return S.fit_B(N, REC, y, rows) if form == "B" else S.fit_C(N, REC, STD, y, rows, "linear_std")


def pred_form(f, N, STD, REC, idx):
    return (S.pred_B if f["form"] == "mean" else S.pred_C)(f, N, REC, STD, idx)[0]


def inner_choice(cols, N, STD, REC, y, elig, p, T):
    """B vs C_linear chosen by leave-one-season-out inside seasons < T."""
    seasons = [s for s in range(2015, T)]
    mse = {"B": {}, "C_linear": {}}
    for V in seasons:
        tr = np.where(elig & (cols["pos"] == p) & (cols["season"] < T) & (cols["season"] != V))[0]
        te = np.where(elig & (cols["pos"] == p) & (cols["season"] == V))[0]
        for form in mse:
            f = fit_form(N, STD, REC, y, tr, form)
            mse[form][V] = (np.sum((pred_form(f, N, STD, REC, te) - y[te]) ** 2), len(te))
    pooled = {f: sum(a for a, _ in v.values()) / sum(b for _, b in v.values()) for f, v in mse.items()}
    wins = sum(mse["C_linear"][V][0] < mse["B"][V][0] for V in seasons)
    need = math.ceil(7 / 11 * len(seasons))
    return ("C_linear" if pooled["C_linear"] < pooled["B"] and wins >= need else "B"), wins, len(seasons)


def main():
    games, pos, last_week = S.load_games()
    cols, N, STD, REC, HALF = S.build_rows(games, pos, last_week)
    y = cols["ros_rec"]
    elig = (cols["ros_games"] >= 3) & (cols["raw_n"] >= 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(cols["ros_std"] >= 2.0, np.log1p(cols["ros_rec"] / cols["ros_std"]), np.nan)
    group = np.array([f"{s}|{w}|{p}" for s, w, p in zip(cols["season"], cols["week"], cols["pos"])])
    final = json.loads((S.OUT / "model.json").read_text(encoding="utf-8"))
    skill = np.isin(cols["pos"], POS) & (cols["raw_n"] >= 1)

    folds = {}
    A_rows = defaultdict(lambda: {"model": {}, "raw_all": {}, "B": {}, "C_linear": {}})
    D_parts = defaultdict(list)
    E_parts = {"primary": defaultdict(dict), "replication": defaultdict(dict)}
    for T in TEST:
        fold = {}
        # rec_hat / share_hat on every skill row of seasons <= T from the < T fit
        rec_hat = np.full(len(y), np.nan)
        share_hat = np.full(len(y), np.nan)
        combo = np.full(len(y), -1)
        for p in POS:
            tr = np.where(elig & (cols["pos"] == p) & (cols["season"] < T))[0]
            app = np.where(skill & (cols["pos"] == p) & (cols["season"] <= T))[0]
            form, wins, nin = inner_choice(cols, N, STD, REC, y, elig, p, T)
            fits = {fm: fit_form(N, STD, REC, y, tr, fm) for fm in ("B", "C_linear")}
            f = fits[form]
            rec_hat[app] = pred_form(f, N, STD, REC, app)
            combo[app] = f["combo"]
            fR = S.fit_R(N, REC, STD, z, tr[np.isfinite(z[tr])])
            share_hat[app] = S.pred_R(fR, N, REC, STD, app)
            h, d = S.COMBOS[f["combo"]]
            hR, dR = S.COMBOS[fR["combo"]]
            fold[p] = {"form": form, "inner_C_wins": f"{wins}/{nin}",
                       "half_life": None if math.isinf(h) else h, "decay": d, "k": f["k"],
                       "share": {"half_life": None if math.isinf(hR) else hR, "decay": dR, "k": fR["k"]}}
            te = np.where(elig & (cols["pos"] == p) & (cols["season"] == T))[0]
            A_rows[p]["model"][T] = (rec_hat[te], y[te], group[te])
            A_rows[p]["raw_all"][T] = (cols["raw_rec"][te], y[te], group[te])
            for fm in ("B", "C_linear"):
                A_rows[p][fm][T] = (pred_form(fits[fm], N, STD, REC, te), y[te], group[te])
        folds[T] = fold

        # D: chart_top_n pool, P_forecast
        rows = np.arange(len(y))
        fc_std = np.where(combo >= 0, STD[np.maximum(combo, 0), rows], np.nan)
        fc_ppr = fc_std + np.where(combo >= 0, REC[np.maximum(combo, 0), rows], np.nan)
        test_el = elig & (cols["season"] == T) & np.isin(cols["pos"], POS)
        for g in np.unique(group[test_el]):
            m = np.where(test_el & (group == g))[0]
            p = g.split("|")[2]
            top = m[np.argsort(-fc_ppr[m], kind="mergesort")][:S.TOP_N[p]]
            top = top[(cols["ros_std"][top] >= 2.0) & (fc_std[top] >= 2.0)]
            P_or, P_fc = cols["ros_std"][top], fc_std[top]
            D_parts[p].append(dict(
                season=np.full(len(top), T), group=group[top],
                oracle=np.log((P_or + y[top]) / P_or),
                raw_all=np.log((P_fc + cols["raw_rec"][top]) / P_fc),
                model=np.log((P_fc + rec_hat[top]) / P_fc),
                ratio_model=share_hat[top]))

        # E
        for key, weeks, target, ros3 in (("primary", S.WEEKS, "ppg", True), ("replication", (5, 6, 7, 8), "total", False)):
            cand = (cols["cur_n"] >= 2) & np.isin(cols["week"], weeks) & skill & (cols["season"] <= T)
            pool = np.zeros(len(y), bool)
            for g in np.unique(group[cand]):
                m = np.where(cand & (group == g))[0]
                pool[m[np.argsort(-cols["cur_half"][m], kind="mergesort")][:S.TOP_N[g.split("|")[2]]]] = True
            if ros3:
                pool &= cols["ros_games"] >= 3
            pool &= np.isfinite(rec_hat) & np.isfinite(share_hat)
            ys = cols["ros_std"] if target == "ppg" else cols["ros_std_total"]
            yf = cols["ros_ppr"] if target == "ppg" else cols["ros_ppr_total"]
            scale = np.ones(len(y)) if target == "ppg" else (np.where(cols["season"] >= 2021, 18, 17) - cols["week"] + 1.0)
            for p in POS:
                tr = pool & (cols["pos"] == p) & (cols["season"] < T)
                te = pool & (cols["pos"] == p) & (cols["season"] == T)
                X = lambda ix: np.column_stack([cols["cur_std"][ix], cols["cur_rec"][ix], rec_hat[ix]])
                b = S.ols(X(tr), yf[tr])
                fc = b[0] + X(te) @ b[1:]
                preds = {"i_trailing_full": cols["cur_std"][te] + cols["cur_rec"][te],
                         "iii_full_minus_rec_hat": cols["cur_std"][te] + cols["cur_rec"][te] - rec_hat[te],
                         "vi_full_forecast": fc, "vii_minus_rec_hat": fc - rec_hat[te] * scale[te],
                         "viii_over_share": fc / np.exp(share_hat[te])}
                for m, pr in preds.items():
                    E_parts[key][m].setdefault(T, []).extend(
                        [S.spearman(pr[group[te] == g], ys[te][group[te] == g]) for g in np.unique(group[te])])

    # ---- aggregate
    out = {"test_seasons": list(TEST), "folds": {str(T): v for T, v in folds.items()}}
    A = {}
    for p in POS:
        per = {}
        for m, d in A_rows[p].items():
            per[m] = {T: (np.mean((pr - yy) ** 2), S.group_spearman(pr, yy, gg)) for T, (pr, yy, gg) in d.items()}
        pooled = {m: float(np.sum([np.sum((d[T][0] - d[T][1]) ** 2) for T in TEST]) /
                           np.sum([len(d[T][1]) for T in TEST])) for m, d in A_rows[p].items()}
        A[p] = {m: {"mse": S.r3(pooled[m]), "spearman": S.r3(np.mean([per[m][T][1] for T in TEST])),
                    "seasons_beating_raw_all": int(sum(per[m][T][0] < per["raw_all"][T][0] for T in TEST))}
                for m in per}
        A[p]["n_rows"] = int(sum(len(A_rows[p]["model"][T][1]) for T in TEST))
    out["A"] = A
    rng = np.random.default_rng(S.SEED)
    D = {}
    for p in POS:
        cat = {k: np.concatenate([x[k] for x in D_parts[p]]) for k in D_parts[p][0]}
        od = S.demean(cat["oracle"], cat["group"])
        D[p] = {"n_rows": int(len(od))}
        for m in ("raw_all", "model", "ratio_model"):
            md = S.demean(cat[m], cat["group"])
            lo, hi = S.season_boot(lambda ix: S.slope(od[ix], md[ix]), cat["season"], list(TEST), rng)
            sp = t_int([S.group_spearman(cat[m][cat["season"] == T], cat["oracle"][cat["season"] == T],
                                         cat["group"][cat["season"] == T]) for T in TEST])
            D[p][m] = {"slope": S.r3(S.slope(od, md)), "slope_ci95": [S.r3(lo), S.r3(hi)],
                       "spearman": S.r3(sp[0]), "spearman_ci95": [S.r3(sp[1]), S.r3(sp[2])]}
    out["D_chart_top_n_P_forecast"] = D
    E = {}
    for key, parts in E_parts.items():
        sm = {m: {T: np.nanmean(v) for T, v in d.items()} for m, d in parts.items()}
        E[key] = {"spearman": {m: S.r3(np.mean(list(v.values()))) for m, v in sm.items()}}
        for a, b in (("viii_over_share", "vi_full_forecast"), ("vii_minus_rec_hat", "vi_full_forecast"),
                     ("iii_full_minus_rec_hat", "i_trailing_full"), ("vi_full_forecast", "i_trailing_full")):
            d = [sm[a][T] - sm[b][T] for T in TEST]
            mm, lo, hi = t_int(d)
            E[key][f"{a}_minus_{b}"] = {"diff": S.r3(mm), "ci95": [S.r3(lo), S.r3(hi)],
                                         "seasons_won": f"{sum(x > 0 for x in d)} of {len(d)}"}
    out["E"] = E
    # final (all-season) model.json vs forward-only folds
    cmp = {}
    for p in POS:
        fp, rp = final["positions"][p], final["ratio_model"][p]
        fin = (fp["prior_form"], fp["half_life_games"], fp["season_decay"], fp["k"])
        fin_r = (rp["half_life_games"], rp["season_decay"], rp["k"])
        fw = [(("linear_std" if folds[T][p]["form"] == "C_linear" else "mean"), folds[T][p]["half_life"],
               folds[T][p]["decay"], folds[T][p]["k"]) for T in TEST]
        fw_r = [(folds[T][p]["share"]["half_life"], folds[T][p]["share"]["decay"], folds[T][p]["share"]["k"]) for T in TEST]
        cmp[p] = {"final_rec": list(fin), "folds_matching_rec": f"{sum(x == fin for x in fw)} of {len(TEST)}",
                  "final_share": list(fin_r), "folds_matching_share": f"{sum(x == fin_r for x in fw_r)} of {len(TEST)}",
                  "fold_forms": [x[0] for x in fw]}
    out["model_json_vs_forward_folds"] = cmp
    (S.OUT / "rolling.json").write_text(json.dumps(S.clean(out), indent=1), encoding="utf-8")
    append_md(out)
    print(json.dumps(S.clean({k: out[k] for k in ("A", "D_chart_top_n_P_forecast", "E", "model_json_vs_forward_folds")}), indent=0)[:7000])


def append_md(o):
    md = (S.OUT / "results.md").read_text(encoding="utf-8")
    head = "## Rolling-origin check"
    if head in md:
        md = md[:md.index(head)].rstrip() + "\n\n"
    L = [head, "",
         "Generated by `rolling.py` (results above unchanged). Test seasons 2018-2025; for each test season T every "
         "hyperparameter, the B vs C form choice (inner leave-one-season-out within seasons < T), the share model and "
         "the E regressions use seasons < T only; test rows use weeks 1..w-1 of T as features. Intervals: t across the "
         "8 seasons (E, Spearman) or season-block bootstrap (D slopes).", "",
         "| pos | rows | raw history MSE | model MSE | model seasons beating raw | raw Spearman | model Spearman | B MSE | C_linear MSE |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in POS:
        a = o["A"][p]
        L.append(f"| {p} | {a['n_rows']} | {a['raw_all']['mse']} | {a['model']['mse']} | "
                 f"{a['model']['seasons_beating_raw_all']} of 8 | {a['raw_all']['spearman']} | {a['model']['spearman']} | "
                 f"{a['B']['mse']} | {a['C_linear']['mse']} |")
    L += ["", "D (chart top-N, P_forecast): slope of the oracle move on each move.", "",
          "| pos | n | raw_all slope | model slope | ratio_model slope | raw Spearman | model Spearman | ratio Spearman |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in POS:
        d = o["D_chart_top_n_P_forecast"][p]
        L.append(f"| {p} | {d['n_rows']} | {d['raw_all']['slope']} {d['raw_all']['slope_ci95']} | "
                 f"{d['model']['slope']} {d['model']['slope_ci95']} | {d['ratio_model']['slope']} {d['ratio_model']['slope_ci95']} | "
                 f"{d['raw_all']['spearman']} | {d['model']['spearman']} | {d['ratio_model']['spearman']} |")
    L += ["", "E: within-position Spearman differences (forward-only).", "",
          "| target | comparison | diff | 95% | seasons won |", "| --- | --- | --- | --- | --- |"]
    for key in ("primary", "replication"):
        for k, v in o["E"][key].items():
            if k == "spearman":
                continue
            L.append(f"| {key} | {k} | {v['diff']} | {v['ci95']} | {v['seasons_won']} |")
    L += ["", "model.json (all seasons) vs forward-only folds:", ""]
    for p, v in o["model_json_vs_forward_folds"].items():
        L.append(f"- {p}: rec model final {v['final_rec']}, matched in {v['folds_matching_rec']} folds "
                 f"(fold forms {v['fold_forms']}); share model final {v['final_share']}, matched in {v['folds_matching_share']}.")
    L.append("")
    (S.OUT / "results.md").write_text(md + "\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
