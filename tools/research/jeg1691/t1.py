"""JEG-1691 v5: step 5 selection (k, t by forward CV on actuals) and test T1 / T1b.

Spec: docs/research/jeg1691/preregistration.md 2.4 and 3.2 (T1, T1b).
- select(): selection origins only (2025 weeks 4-8). Freezes k_pc, t_p.
- t1(): the T1 / T1b verdict on the test origins. Guarded: runs only with
  decisive=True (run_v5.py --decisive <registration commit>).
Anchor for T1 = Half. No charts are read here.
"""
from __future__ import annotations

import math
import random
import statistics

import history5 as h5
import mix as mx

S0 = "half_ppr"
TRUTH_WEEKS = 4
MIN_TRUTH_GAMES = 2
SELECTION_ORIGINS = tuple((2025, w) for w in (4, 5, 6, 7, 8))
TEST_ORIGINS_2025 = tuple((2025, w) for w in (12, 13, 14))
POS_ALL = ("QB", "RB", "WR", "TE")
POOL = ("RB", "WR", "TE")
SEED = 16911
N_BOOT = 2000
N_SHUFFLE = 1000


def test_origins(nonzero: dict) -> tuple:
    q = set(h5.qualifying_2026_weeks(nonzero))
    o26 = [(2026, w) for w in range(5, 19) if all(x in q for x in range(w, w + TRUTH_WEEKS))]
    return TEST_ORIGINS_2025 + tuple(o26)


def origin_set(hist: dict, pos_of: dict, origin: tuple, t: float, cats=mx.CATS) -> dict:
    """Per origin: history aggregates, prior, and eligible players with truth."""
    season, w = origin
    hists, truth = {}, {}
    for k, rows in hist.items():
        p = pos_of.get(k)
        if p not in POS_ALL:
            continue
        hists[k] = mx.history_rates(h5.before(rows, origin), t, cats)
        tl = [ln for ln in h5.window(rows, season, w, w + TRUTH_WEEKS - 1) if mx.game_has_stats(ln)]
        if len(tl) >= MIN_TRUTH_GAMES:
            truth[k] = ({c: sum(ln.get(c, 0.0) for ln in tl) for c in cats}, len(tl))
    prior = mx.position_prior({k: v for k, v in hists.items() if v is not None}, pos_of, S0, cats)
    elig = {k: v for k, v in truth.items() if mx.F(v[0], S0, cats) > 0 and pos_of[k] in prior}
    return {"hists": hists, "prior": prior, "truth": elig}


def predict(T: float, g: int, m: dict) -> dict:
    return {c: T * v / g for c, v in m.items()}


def objective_terms(os_: dict, pos_of: dict, p: str, k: dict, cats=mx.CATS):
    """[(per-category squared errors)] and per-category truth per-game values, players at p."""
    out = []
    for key, (tot, g) in os_["truth"].items():
        if pos_of[key] != p:
            continue
        mixx = mx.shrunk_mix(os_["hists"].get(key), os_["prior"][p], k, S0, cats)
        T = mx.F(tot, S0, cats)
        pr = predict(T, g, mixx.m)
        out.append(({c: (pr[c] - tot[c] / g) ** 2 for c in cats}, {c: tot[c] / g for c in cats}))
    return out


def objective_S(sets: list, pos_of: dict, p: str, k: dict, cats=mx.CATS) -> float:
    tot, n = 0.0, 0
    for os_ in sets:
        terms = objective_terms(os_, pos_of, p, k, cats)
        if len(terms) < 2:
            continue
        var = {c: statistics.pvariance([tv[c] for _e, tv in terms]) for c in cats}
        for e, _tv in terms:
            tot += sum(e[c] / var[c] for c in cats if var[c] > 0)
            n += 1
    return tot / n if n else math.inf


def select(hist: dict, pos_of: dict, cats=mx.CATS, positions=POS_ALL) -> dict:
    """Coordinate descent over k_c (two passes, categories in CATS order, grid scanned from
    the largest k so ties keep the larger k), for each t; then the t with the lowest S."""
    out = {}
    sets_by_t = {t: [origin_set(hist, pos_of, o, t, cats) for o in SELECTION_ORIGINS] for t in mx.T_GRID}
    for p in positions:
        best = None
        for t in mx.T_GRID:
            sets = sets_by_t[t]
            k = {c: math.inf for c in cats}
            cur = objective_S(sets, pos_of, p, k, cats)
            for _pass in range(2):
                for c in cats:
                    for kc in sorted(mx.K_GRID, reverse=True):
                        trial = dict(k, **{c: kc})
                        v = objective_S(sets, pos_of, p, trial, cats)
                        if v < cur - 1e-12:
                            cur, k = v, trial
            if best is None or cur < best[0] - 1e-12:
                best = (cur, t, k)
        out[p] = {"t": best[1], "k": best[2], "S": best[0],
                  "S_position_mix": objective_S(sets_by_t[best[1]], pos_of, p, {c: math.inf for c in cats}, cats)}
    return out


# ---------------------------------------------------------------------------
# T1 / T1b (decisive; guarded by the runner)
# ---------------------------------------------------------------------------

def _errors(hist, pos_of, origins, sel, cats, scorings_fn):
    """rows [(player, pos, err_player, err_position, origin)], plus the per-origin pieces
    for the shuffle control."""
    rows, pieces = [], []
    for o in origins:
        by_t = {}
        for p in POOL:
            t = sel[p]["t"]
            if t not in by_t:
                by_t[t] = origin_set(hist, pos_of, o, t, cats)
        for p in POOL:
            os_ = by_t[sel[p]["t"]]
            inf_k = {c: math.inf for c in cats}
            plist = []
            for key, (tot, g) in os_["truth"].items():
                if pos_of[key] != p:
                    continue
                own = mx.shrunk_mix(os_["hists"].get(key), os_["prior"][p], sel[p]["k"], S0, cats)
                posm = mx.shrunk_mix(None, os_["prior"][p], inf_k, S0, cats)
                T = mx.F(tot, S0, cats)
                plist.append((key, tot, g, T, own.m, posm.m))
            for key, tot, g, T, m_own, m_pos in plist:
                rows.append((key, p, scorings_fn(tot, g, T, m_own, p), scorings_fn(tot, g, T, m_pos, p), o))
            pieces.append((p, plist))
    return rows, pieces


def preset_error(cats):
    def fn(tot, g, T, m, p):
        e = []
        for s in ("standard", "ppr"):
            pred = T / g * mx.F(m, s, cats)
            true = mx.F(tot, s, cats) / g
            e.append(abs(pred - true))
        return sum(e) / len(e)
    return fn


def custom_error(name, base, over, te_extra, cats):
    def fn(tot, g, T, m, p):
        kw = {"overrides": over, "te_extra": te_extra, "pos": p}
        return abs(T / g * mx.F(m, base, cats, **kw) - mx.F(tot, base, cats, **kw) / g)
    return fn


def pooled_mean(rows, idx):
    per = {p: [r[idx] for r in rows if r[1] == p] for p in POOL}
    return statistics.fmean(statistics.fmean(v) for v in per.values() if v)


def paired_boot(rows, seed=SEED, n=N_BOOT):
    """Cluster bootstrap by player within position of mean(err_position - err_player)."""
    rng = random.Random(seed)
    by = {p: {} for p in POOL}
    for r in rows:
        by[r[1]].setdefault(r[0], []).append(r[3] - r[2])
    point = statistics.fmean(statistics.fmean([d for ds in by[p].values() for d in ds]) for p in POOL if by[p])
    draws = []
    for _ in range(n):
        vals = []
        for p in POOL:
            ids = list(by[p])
            if not ids:
                continue
            pick = [ids[rng.randrange(len(ids))] for _ in ids]
            vals.append(statistics.fmean([d for i in pick for d in by[p][i]]))
        draws.append(statistics.fmean(vals))
    draws.sort()
    return point, (draws[int(0.025 * n)], draws[int(0.975 * n) - 1])


def shuffle_p5(pieces, fn, seed=SEED, n=N_SHUFFLE):
    """5th percentile of the pooled error when each player gets another same-position
    player's mix (within origin and position)."""
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        per = {p: [] for p in POOL}
        for p, plist in pieces:
            mixes = [x[4] for x in plist]
            rng.shuffle(mixes)
            for (key, tot, g, T, _m, _mp), m in zip(plist, mixes):
                per[p].append(fn(tot, g, T, m, p))
        vals.append(statistics.fmean(statistics.fmean(v) for v in per.values() if v))
    vals.sort()
    return vals[int(0.05 * n)]


def label(ci):
    lo, hi = ci
    return "PASS" if lo > 0 else ("FAIL" if hi < 0 else "INCONCLUSIVE")


def t1(hist, pos_of, nonzero, sel, sel_int):
    origins = test_origins(nonzero)
    fn = preset_error(mx.CATS)
    rows, pieces = _errors(hist, pos_of, origins, sel, mx.CATS, fn)
    point, ci = paired_boot(rows)
    own = pooled_mean(rows, 2)
    p5 = shuffle_p5(pieces, fn)
    verdict = label(ci)
    if verdict == "PASS" and not own < p5:
        verdict = "INCONCLUSIVE"
    out = {"origins": origins, "n_rows": len(rows), "a": {"diff": point, "ci95": ci,
           "err_player": own, "err_position": pooled_mean(rows, 3), "shuffle_p5": p5,
           "per_position": {p: statistics.fmean([r[3] - r[2] for r in rows if r[1] == p]) for p in POOL}},
           "verdict": verdict}
    out["b_objective_S"] = {}
    for p in POOL:
        sets = [origin_set(hist, pos_of, o, sel[p]["t"]) for o in origins]
        out["b_objective_S"][p] = {"player": objective_S(sets, pos_of, p, sel[p]["k"]),
                                   "position": objective_S(sets, pos_of, p, {c: math.inf for c in mx.CATS})}
    out["t1b"] = {}
    for name, base, over, te in mx.CUSTOM:
        fnc = custom_error(name, base, over, te, mx.CATS_INT)
        r2, _ = _errors(hist, pos_of, origins, sel_int, mx.CATS_INT, fnc)
        pt, c2 = paired_boot(r2)
        out["t1b"][name] = {"diff": pt, "ci95": c2, "label": label(c2)}
    return out
