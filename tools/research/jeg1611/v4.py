"""JEG-1611 v4: the exact unwind and the clean delta (iteration 3 of
docs/research/jeg1611/iteration-log.md; readings in its Iteration 3a).

Per rescaled chart c, week w, anchor s0, target s:
1-2. natives x_i > 0 and Adjusted A_i from the unmodified pipeline at s0;
3-4. P_i(s0) = inverse of the projections' pricing at A_i (v3 `expected_points`);
     A_i = 0 -> below_waiver, no inverse -> no_inverse (both keep x_i);
     R_p(s) = mean over the projections in I of their waiver_value (ppg) at p,
     from a pipeline run at s with the allocation mix held at the anchor run's;
5-6. sh_i = expected_reception_share (shrink model, 2024-2026 rows before w),
     P_i(s) = P_i(s0) (1 + r_s sh_i) / (1 + r_s0 sh_i); QB sh = 0;
7.   V_i = P_i - R_p; b_p = OLS slope of x on V(s0) over the invertible players;
     x_i(s) = max(0, x_i + b_p (V_i(s) - V_i(s0))).

Research only: value_reference.run_pipeline is an unmodified library. Pure
functions first; the world-dependent Week4 container last. Games never enter.
"""
from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "research" / "jeg1610"))
sys.path.insert(0, str(REPO / "tools" / "research" / "jeg1605"))
sys.path.insert(0, str(HERE / "shrink"))

import history as hs  # noqa: E402
import unwind as uw  # noqa: E402
import run_v3 as R3  # noqa: E402
import model as sm  # noqa: E402

vr = R3.vr
R_OF = uw.R_OF
POSITIONS = uw.POSITIONS
SKILL = ("RB", "WR", "TE")
SEASON = 2026
MIN_B_NODES = 4
MIX_MODELS = ("share", "raw", "recg", "assumed")
FORMS = ("delta", "mult", "tail", "chartzero", "ddfrate")


# ---------------------------------------------------------------------------
# Pure numerics
# ---------------------------------------------------------------------------

def ols(xs, ys):
    """(slope, intercept, r2) of y on x; None slope when x has no spread."""
    n = len(xs)
    if n < 2:
        return None, None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None, None, None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else None
    return b, a, r2


@dataclass(frozen=True)
class Mix4:
    """How a player's points change with the reception weight.
    kind: share (P0 (1 + r sh)/(1 + r0 sh)), hist (v3 own history ratio),
    q (v3 position-level fallback ratio), rec (P0 + (r - r0) rec_hat)."""
    kind: str
    sh: float = 0.0
    std: float | None = None
    rec: float | None = None
    q: float | None = None
    rec_hat: float = 0.0
    label: str = "own"          # own | fallback_prior | qb | assumed | fallback (raw)
    n_eff: float = 0.0
    w: float = 0.0


QB_MIX = Mix4("share", 0.0, label="qb")


def points_at(P0: float, mix: Mix4, s: str, s0: str) -> float:
    """P_i(s). At s == s0 the ratio is exactly 1.0 (a / a) and the additive
    term exactly 0.0, so P_i(s0) comes back bit for bit."""
    r, r0 = R_OF[s], R_OF[s0]
    if mix.kind == "share":
        return P0 * ((1.0 + r * mix.sh) / (1.0 + r0 * mix.sh))
    if mix.kind == "hist":
        return P0 * ((mix.std + r * mix.rec) / (mix.std + r0 * mix.rec))
    if mix.kind == "q":
        return P0 * hs.fallback_ratio(mix.q, r, r0)
    if mix.kind == "rec":
        return P0 + (r - r0) * mix.rec_hat
    raise ValueError(mix.kind)


def replacement(waiver: dict, projections) -> dict:
    """R_p = mean over the projections of their waiver_value (ppg) at p."""
    out = {}
    for p in POSITIONS:
        vals = [waiver[j][p] for j in projections if j in waiver and waiver[j].get(p) is not None
                and math.isfinite(waiver[j][p])]
        out[p] = sum(vals) / len(vals) if vals else None
    return out


# ---------------------------------------------------------------------------
# Steps 3-7 on one chart-week (pure)
# ---------------------------------------------------------------------------

@dataclass
class U4:
    s0: str
    records: dict                 # key -> {pos, x, A, label, P0, n_proj, mix}
    R0: dict                      # pos -> R_p(s0)
    b: dict                       # pos -> {b, intercept, r2, n, method}
    extra: dict = field(default_factory=dict)


def fit_b(recs: dict, R0: dict) -> dict:
    out = {}
    for p in POSITIONS:
        inv = [r for r in recs.values() if r["pos"] == p and r["label"] == "invertible" and R0.get(p) is not None]
        xs = [r["P0"] - R0[p] for r in inv]
        ys = [r["x"] for r in inv]
        if len(inv) >= MIN_B_NODES:
            b, a, r2 = ols(xs, ys)
            out[p] = {"b": b, "intercept": a, "r2": r2, "n": len(inv), "method": "ols"}
        elif inv:
            top = max(inv, key=lambda r: (r["x"], r["P0"]))
            v = top["P0"] - R0[p]
            out[p] = {"b": top["x"] / v if v > 0 else None, "intercept": None, "r2": None, "n": len(inv),
                      "method": "top_player"}
        else:
            out[p] = {"b": None, "intercept": None, "r2": None, "n": 0, "method": "none"}
    return out


def unwind4(chart_recs: dict, maps0: dict, mixes: dict, R0: dict, s0: str) -> U4:
    """chart_recs: uw.listed_records of the chart in the anchor run; maps0:
    uw.maps_by_position of the projections in that run; mixes: {key: Mix4};
    R0: replacement(...) of the anchor run."""
    recs = {}
    for i, (p, x, a, _v) in chart_recs.items():
        if not x > 0:
            continue
        rec = {"pos": p, "x": x, "A": a}
        if a <= 0:
            rec.update(label="below_waiver", P0=None, n_proj=0)
        else:
            P0, n = uw.expected_points(a, maps0.get(p, {}))
            rec.update(label="invertible" if P0 is not None else "no_inverse", P0=P0, n_proj=n)
        rec["mix"] = QB_MIX if p == "QB" else mixes[i]
        recs[i] = rec
    return U4(s0, recs, dict(R0), fit_b(recs, R0))


def chart_zero(u: U4) -> dict:
    """Iteration 4 (H-d): the chart's own zero in points per position from the
    fit x = a_p + b_p V(s0): Z_p(s0) = R_p(s0) - a_p / b_p. Falls back to R_p(s0)
    (counted) when a_p >= 0, b_p is missing or not positive, or Z_p < R_p."""
    out = {}
    for p in POSITIONS:
        b, a, R0 = u.b[p]["b"], u.b[p]["intercept"], u.R0[p]
        if R0 is None:
            out[p] = {"zero": None, "fallback": True}
        elif b is None or a is None or b <= 0 or a >= 0 or R0 - a / b < R0:
            out[p] = {"zero": R0, "fallback": True}
        else:
            out[p] = {"zero": R0 - a / b, "fallback": False}
    return out


def rebuild4(u: U4, s: str, natives0: dict, Rs: dict, form: str = "delta", rate_ratio: dict | None = None) -> dict:
    """Chart natives at s. natives0 = the chart's whole input list; every
    non-invertible player keeps x_i (form 'tail': moved by the position's
    median invertible ratio of the delta form)."""
    out = dict(natives0)
    ratios = {p: [] for p in POSITIONS}
    if form == "chartzero":
        # the zero moves with scoring by the position prior share (QB 0)
        prior = u.extra.get("prior_sh", {})
        r, r0 = R_OF[s], R_OF[u.s0]
        z = chart_zero(u)
        Z0 = {p: z[p]["zero"] for p in POSITIONS}
        Rs = {p: (None if Z0[p] is None else
                  Z0[p] * ((1.0 + r * prior.get(p, 0.0)) / (1.0 + r0 * prior.get(p, 0.0)))) for p in POSITIONS}
    else:
        Z0 = u.R0
    for i, rec in u.records.items():
        if rec["label"] != "invertible":
            continue
        p = rec["pos"]
        bp = u.b[p]["b"]
        if bp is None or Z0[p] is None or Rs.get(p) is None:
            continue
        P0 = rec["P0"]
        Ps = points_at(P0, rec["mix"], s, u.s0)
        V0, Vs = P0 - Z0[p], Ps - Rs[p]
        x = rec["x"]
        delta = max(0.0, x + bp * (Vs - V0))
        if form == "ddfrate":
            # Iteration 7: the slope at the target is b_p(s0) x rate_p(s) / rate_p(s0)
            rr = (rate_ratio or {}).get(p)
            out[i] = max(0.0, x + ((bp * rr) * Vs - bp * V0)) if rr is not None else x
        elif form == "mult":
            out[i] = x * (max(0.0, Vs) / V0) if V0 > 0 else x
        else:
            out[i] = delta
        ratios[p].append(delta / x)
    if form == "tail":
        med = {p: statistics.median(v) for p, v in ratios.items() if v}
        for i, rec in u.records.items():
            if rec["label"] != "invertible" and rec["pos"] in med:
                out[i] = rec["x"] * med[rec["pos"]]
    return out


def counts4(u: U4) -> dict:
    out = {}
    for p in POSITIONS:
        rs = [r for r in u.records.values() if r["pos"] == p]
        out[p] = {"priced": len(rs), "invertible": sum(r["label"] == "invertible" for r in rs),
                  "below_waiver": sum(r["label"] == "below_waiver" for r in rs),
                  "no_inverse": sum(r["label"] == "no_inverse" for r in rs),
                  "fallback_prior": sum(r["mix"].label == "fallback_prior" for r in rs),
                  "fallback_raw": sum(r["mix"].label == "fallback" for r in rs),
                  "b": u.b[p]["b"], "b_r2": u.b[p]["r2"], "b_n": u.b[p]["n"], "b_method": u.b[p]["method"]}
    return out


# ---------------------------------------------------------------------------
# Steps 5-6: mixes (history rows before week w)
# ---------------------------------------------------------------------------

def rows_by_key(hist_rows: list, w: int) -> dict:
    """{key: [{season, week, std, rec}]}: 2024, 2025 all weeks, 2026 weeks 1..w-1."""
    out = {}
    for s, wk, k, std, rec in hs.window_rows(hist_rows, w, "primary"):
        out.setdefault(k, []).append({"season": s, "week": wk, "std": std, "rec": rec})
    return out


def share_mix(rows, pos, w, model) -> Mix4:
    if pos not in SKILL:
        return QB_MIX
    sh, n_eff, wt = sm.expected_reception_share(rows or [], pos, w, SEASON, model)
    return Mix4("share", sh, label="fallback_prior" if wt == 0 else "own", n_eff=n_eff, w=wt)


def recg_mix(rows, pos, w, model) -> Mix4:
    if pos not in SKILL:
        return Mix4("rec", rec_hat=0.0, label="qb")
    rh, n_eff, wt = sm.expected_receptions(rows or [], pos, w, SEASON, model)
    return Mix4("rec", rec_hat=rh, label="fallback_prior" if wt == 0 else "own", n_eff=n_eff, w=wt)


def assumed_mix(pos, model) -> Mix4:
    if pos not in SKILL:
        return QB_MIX
    return Mix4("share", math.expm1(model["ratio_model"][pos]["mean"]), label="assumed")


def raw_mixes(stats: dict, keys, pos_of: dict, r0: float) -> dict:
    """v3's mix: own history (6+ games) else the chart-week's position-level q_p."""
    hm = {k: hs.history_mix(stats, k, r0) for k in keys}
    q = {p: hs.position_share(hm, keys, pos_of, p) for p in POSITIONS}
    out = {}
    for k in keys:
        m = hm[k]
        if m.basis == "history":
            out[k] = Mix4("hist", std=m.std, rec=m.rec, label="own")
        else:
            out[k] = Mix4("q", q=q.get(pos_of.get(k)), label="fallback")
    return out


# ---------------------------------------------------------------------------
# Pipeline with the allocation mix held fixed
# ---------------------------------------------------------------------------

def result_mix(res: dict) -> list:
    """[(weight, allocation)] of a run_pipeline result (one vertex or the blend)."""
    if res.get("allocation_mix"):
        return [(d["weight"], d["allocation"]) for d in res["allocation_mix"]]
    return [(1.0, res["allocation"])]


def run_fixed(ctx, natives_by_src: dict, s: str, mix: list, drop=()) -> dict:
    """The unmodified pipeline at s with the allocation mix held at `mix`: each
    vertex run with run_pipeline(allocation=a) and blended with the same
    weights by value_reference._blend_runs, i.e. exactly what run_pipeline does
    internally once it has built its mix, minus building it."""
    nat = {k: v for k, v in natives_by_src.items() if k not in drop}
    inc_all = [k for k in ctx["inc_list"][s] if k not in drop]
    live = ctx["live"][s]
    pos_of = ctx["pos_of"]

    def sources():
        return {k: vr.SourceInput(k, vr.FAMILY[k], dict(nat[k])) for k in vr.SOURCES if k in nat}

    def one(a):
        src = sources()
        inc = [k for k in inc_all if k in src]
        return vr.run_pipeline(live.league, src, pos_of, inc, None, lineup=live.lineup,
                               hidden=set(ctx["hidden"][s]) & set(inc), flex_bench_seats=True, allocation=a)
    if len(mix) == 1:
        return one(mix[0][1])
    runs = [one(a) for _w, a in mix]
    src = sources()
    pos4 = {i: p for i, p in pos_of.items() if p in vr.POSITIONS}
    for x in src.values():
        x.values = {i: float(v) for i, v in x.values.items() if vr._finite(v) and i in pos4}
    m = vr.mean_ppg(src, [k for k in inc_all if k in src])
    return vr._blend_runs(mix, runs, m)


def ddf_rate(dg: dict) -> dict:
    """DDF's own value per point at a run's scoring: per position, the mean over
    the projections in I of the OLS slope of Adjusted on ppg (Adjusted > 0)."""
    out = {}
    for p in POSITIONS:
        sl = []
        for j, by in dg["pairs"].items():
            pr = [(x, a) for x, a in by.get(p, []) if a > 0]
            b = uw.ols_slope([x for x, _ in pr], [a for _, a in pr])
            if b is not None:
                sl.append(b)
        out[p] = sum(sl) / len(sl) if sl else None
    return out


def digest4(ctx, res: dict, s: str) -> dict:
    d = R3.digest(ctx, res, s)
    projs = [j for j in uw.PROJ if j in res["included"]]
    d["mix"] = result_mix(res)
    d["projections"] = projs
    d["waiver"] = {j: {p: res["sources"][j]["positions"][p].get("waiver_value") for p in POSITIONS}
                   for j in projs}
    d["R"] = replacement(d["waiver"], projs)
    return d


# ---------------------------------------------------------------------------
# Week container
# ---------------------------------------------------------------------------

class Week4(R3.Week):
    """Anchor, fixed-allocation and target runs of one snapshot week."""

    def __init__(self, ctx, w, model=None):
        super().__init__(ctx, w)
        self.model = model or sm.load_model()
        self._hist = rows_by_key(ctx["hist_rows"], w)
        self._mix_cache = {}
        self._u = {}

    def run(self, tag, natives_by_src, s, drop=(), mix=None, mix_tag=None):
        key = (tag, s, tuple(sorted(drop)), mix_tag)
        if key not in self._runs:
            if mix is None:
                res = R3.run_at(self.ctx, natives_by_src, s, drop)
            else:
                res = run_fixed(self.ctx, natives_by_src, s, mix, drop)
            self._runs[key] = digest4(self.ctx, res, s)
        return self._runs[key]

    def anchor4(self, chart, variant="primary", drop=()):
        """(digest, s0, x, anchor_tag) for a rescaled chart or a G1 chart at s0."""
        if chart == "fantasycalc" and variant == "fchalf":
            return self.fc_half_anchor(drop), "half_ppr", dict(self.natives["fantasycalc"]["ppr"]), "fc_half_anchor"
        s0 = R3.ANCHOR[chart]
        return self.current(s0, drop), s0, dict(self.natives[chart][s0]), f"current_{s0}"

    def anchor_at(self, chart, s0, drop=()):
        """G1: the chart's own column at s0 in today's run at s0."""
        return self.current(s0, drop), s0, dict(self.natives[chart][s0]), f"current_{s0}"

    def fixed(self, anchor_dg, anchor_tag, s, drop=()):
        """Today's inputs at s, allocation mix held at the anchor run's."""
        return self.run("fixed", R3.current_natives(self.natives, s), s, drop,
                        mix=anchor_dg["mix"], mix_tag=(anchor_tag, tuple(sorted(drop))))

    def mixes(self, kind, keys, s0=None, chart_keys=None):
        pos_of = self.ctx["pos_of"]
        if kind == "raw":
            ck = tuple(sorted(chart_keys))
            key = ("raw", s0, ck)
            if key not in self._mix_cache:
                stats = hs.player_stats(hs.window_rows(self.ctx["hist_rows"], self.w, "primary"))
                self._mix_cache[key] = raw_mixes(stats, list(ck), pos_of, R_OF[s0])
            return self._mix_cache[key]
        out = {}
        for k in keys:
            ck = (kind, k)
            if ck not in self._mix_cache:
                p = pos_of.get(k)
                if kind == "share":
                    self._mix_cache[ck] = share_mix(self._hist.get(k), p, self.w, self.model)
                elif kind == "recg":
                    self._mix_cache[ck] = recg_mix(self._hist.get(k), p, self.w, self.model)
                elif kind == "assumed":
                    self._mix_cache[ck] = assumed_mix(p, self.model)
                else:
                    raise ValueError(kind)
            out[k] = self._mix_cache[ck]
        return out

    def unwound(self, chart, s0=None, variant="primary", drop=(), mixkind="share"):
        """(U4, x, anchor digest, anchor tag). s0=None: the chart's rescale anchor."""
        key = (chart, s0, variant, tuple(sorted(drop)), mixkind)
        if key not in self._u:
            if s0 is None:
                dg, s00, x, tag = self.anchor4(chart, variant, drop)
            else:
                dg, s00, x, tag = self.anchor_at(chart, s0, drop)
            recs = dg["charts"][chart]
            priced = [k for k, r in recs.items() if r[1] > 0]
            mx = self.mixes(mixkind, priced, s00, priced)
            u = unwind4(recs, uw.maps_by_position(dg["pairs"]), mx, dg["R"], s00)
            u.extra["prior_sh"] = {p: math.expm1(self.model["ratio_model"][p]["mean"]) for p in SKILL}
            self._u[key] = (u, x, dg, tag)
        return self._u[key]

    def v4_list(self, chart, s, s0=None, variant="primary", drop=(), mixkind="share", form="delta"):
        u, x, dg, tag = self.unwound(chart, s0, variant, drop, mixkind)
        fx = self.fixed(dg, tag, s, drop)
        Rs = fx["R"]
        rr = None
        if form == "ddfrate":
            r0, rs = ddf_rate(self.fixed(dg, tag, u.s0, drop)), ddf_rate(fx)
            rr = {p: (rs[p] / r0[p] if rs[p] is not None and r0[p] else None) for p in POSITIONS}
        return rebuild4(u, s, x, Rs, form, rr), u, Rs


def v4_natives(wk: Week4, s, fc_variant="primary", drop=(), mixkind="share", form="delta"):
    nat = R3.current_natives(wk.natives, s)
    for c in ("fantasycalc", "fantasypros"):
        if c in drop:
            continue
        nat[c] = wk.v4_list(c, s, variant=fc_variant if c == "fantasycalc" else "primary", drop=drop,
                            mixkind=mixkind, form=form)[0]
    return nat


def v4_run(wk: Week4, s, fc_variant="primary", drop=(), alloc="rederived", form="delta"):
    """DDF Value v4 at s: the pipeline at s with FantasyCalc and FantasyPros
    replaced by their v4 lists. alloc='half_fixed': mix held at today's Half run's."""
    nat = v4_natives(wk, s, fc_variant, drop, form=form)
    tag = f"v4|{fc_variant}|{alloc}|{form}"
    if alloc == "rederived":
        return wk.run(tag, nat, s, drop)
    half = wk.current("half_ppr", drop)
    return wk.run(tag, nat, s, drop, mix=half["mix"], mix_tag=("current_half_ppr", tuple(sorted(drop))))
