"""JEG-1610 steps 2-7: unwind a chart's Adjusted value to expected points,
apply each player's history mix, and rebuild chart natives at a target scoring.

Spec: docs/research/jeg1610/preregistration.md section 1 (binding) and the
implementation readings in its "Changes after this commit" section.

Every function here is pure: inputs are plain dicts / tuples taken from one
unmodified value_reference.run_pipeline result (the anchor run), outputs are
new dicts. Games do not enter anywhere.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import history as hs

POSITIONS = ("QB", "RB", "WR", "TE")
R_OF = {"standard": 0.0, "half_ppr": 0.5, "ppr": 1.0}
PROJ = ("espn", "cbsros", "razzball")


# ---------------------------------------------------------------------------
# Small numerics
# ---------------------------------------------------------------------------

def ols_slope(xs, ys) -> float | None:
    """OLS slope of y on x; None when x has no spread."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


# ---------------------------------------------------------------------------
# Pipeline extraction (pure on the result dict)
# ---------------------------------------------------------------------------

def listed_records(result: dict, src: str, pos_of: dict) -> dict:
    """{key: (pos, native, adjusted, vorp_display)} of the source's listed
    (not imputed) players in one pipeline result."""
    out = {}
    for i, pl in result["sources"][src]["players"].items():
        if pl.get("imputed"):
            continue
        out[i] = (pos_of.get(i, pl["pos"]), float(pl["native"]), float(pl["adjusted"]), float(pl["vorp_display"]))
    return out


def projection_pairs(result: dict, projections, pos_of: dict) -> dict:
    """{j: {pos: [(ppg, adjusted)]}} of each projection's priced players (ppg > 0)."""
    out = {}
    for j in projections:
        if j not in result["sources"]:
            continue
        by = {p: [] for p in POSITIONS}
        for i, pl in result["sources"][j]["players"].items():
            if pl.get("imputed") or not pl["native"] > 0:
                continue
            p = pos_of.get(i, pl["pos"])
            if p in by:
                by[p].append((float(pl["native"]), float(pl["adjusted"])))
        out[j] = by
    return out


# ---------------------------------------------------------------------------
# Step 4: the projections' maps (ppg <-> adjusted)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjMap:
    ppg: tuple          # sorted ascending
    adj: tuple          # running max of adjusted along ppg (monotone)
    slope_top: float | None   # OLS slope of raw adjusted on ppg, top 3 by ppg


def build_map(pairs) -> ProjMap | None:
    if not pairs:
        return None
    srt = sorted(pairs)
    ppg = tuple(p for p, _ in srt)
    mono, run = [], float("-inf")
    for _, a in srt:
        run = max(run, a)
        mono.append(run)
    top = srt[-3:]
    return ProjMap(ppg, tuple(mono), ols_slope([p for p, _ in top], [a for _, a in top]))


def inverse(m: ProjMap | None, a: float) -> float | None:
    """ppg at which the map reaches adjusted a: the lowest ppg on the monotone
    curve with that value, linear between nodes, above the top node the top-3
    OLS slope from the top node; below the lowest node undefined."""
    if m is None:
        return None
    adj, ppg = m.adj, m.ppg
    if a > adj[-1]:
        if m.slope_top is None or m.slope_top <= 0:
            return None
        return ppg[-1] + (a - adj[-1]) / m.slope_top
    if a < adj[0]:
        return None
    i = bisect.bisect_left(adj, a)
    if adj[i] == a:
        return ppg[i]
    lo, hi = i - 1, i
    t = (a - adj[lo]) / (adj[hi] - adj[lo])
    return ppg[lo] + t * (ppg[hi] - ppg[lo])


def forward(m: ProjMap | None, x: float) -> float | None:
    """Adjusted at ppg x on the monotone curve (v3_proj): linear between nodes,
    the lowest node's value below it, top-3 OLS slope above the top; floor 0."""
    if m is None:
        return None
    ppg, adj = m.ppg, m.adj
    if x >= ppg[-1]:
        v = adj[-1] + (m.slope_top or 0.0) * (x - ppg[-1]) if (m.slope_top or 0.0) > 0 else adj[-1]
    elif x <= ppg[0]:
        v = adj[0]
    else:
        i = bisect.bisect_right(ppg, x)
        lo, hi = i - 1, i
        t = (x - ppg[lo]) / (ppg[hi] - ppg[lo]) if ppg[hi] > ppg[lo] else 0.0
        v = adj[lo] + t * (adj[hi] - adj[lo])
    return max(0.0, v)


def maps_by_position(pairs: dict) -> dict:
    """{pos: {j: ProjMap}} from projection_pairs output."""
    return {p: {j: build_map(by[p]) for j, by in pairs.items() if by.get(p)} for p in POSITIONS}


def expected_points(a: float, maps_p: dict) -> tuple[float | None, int]:
    """P_i(s0) = mean over projections with a defined inverse; (value, n used)."""
    vals = [v for v in (inverse(m, a) for m in maps_p.values()) if v is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def forward_points(x: float, maps_p: dict) -> float | None:
    vals = [v for v in (forward(m, x) for m in maps_p.values()) if v is not None]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# Step 7: g_p, the anchor's points -> chart units
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GMap:
    p: tuple
    x: tuple
    slope_top: float | None
    slope_low: float | None
    tied_nodes: int


def build_g(nodes) -> GMap | None:
    """nodes: [(P_i(s0), x_i)] of the invertible players at a position. Equal P
    are collapsed to the mean x (counted)."""
    if not nodes:
        return None
    by = {}
    for p, x in nodes:
        by.setdefault(p, []).append(x)
    ps = tuple(sorted(by))
    xs = tuple(sum(by[p]) / len(by[p]) for p in ps)
    tied = sum(len(v) - 1 for v in by.values())
    return GMap(ps, xs, ols_slope(ps[-3:], xs[-3:]), ols_slope(ps[:3], xs[:3]), tied)


def g_eval(g: GMap, P: float) -> float:
    ps, xs = g.p, g.x
    if P > ps[-1]:
        v = xs[-1] + (g.slope_top or 0.0) * (P - ps[-1])
    elif P < ps[0]:
        v = xs[0] + (g.slope_low or 0.0) * (P - ps[0])
    else:
        i = bisect.bisect_left(ps, P)
        if ps[i] == P:
            v = xs[i]
        else:
            lo, hi = i - 1, i
            v = xs[lo] + (P - ps[lo]) / (ps[hi] - ps[lo]) * (xs[hi] - xs[lo])
    return max(0.0, v)


# ---------------------------------------------------------------------------
# One chart-week
# ---------------------------------------------------------------------------

@dataclass
class Unwound:
    s0: str
    records: dict               # key -> dict (pos, x, A, V, label, P0, n_proj, basis, reason, ratio by s, k)
    q: dict                     # pos -> q_p
    g: dict                     # pos -> GMap
    counts: dict = field(default_factory=dict)


def unwind(chart_recs: dict, maps0: dict, mixes: dict, s0: str) -> Unwound:
    """Steps 3-6 for one chart at anchor s0.

    chart_recs: listed_records of the chart in the anchor run;
    maps0: maps_by_position of the projections in the same run;
    mixes: {key: history.Mix} (own history or fallback, per step 5)."""
    r0 = R_OF[s0]
    recs = {}
    for i, (p, x, a, v) in chart_recs.items():
        if not x > 0:
            continue                       # listed at 0: no price, no v3 value
        rec = {"pos": p, "x": x, "A": a, "V": v}
        if a <= 0:
            rec.update(label="below_waiver", P0=None, n_proj=0)
        else:
            P0, n = expected_points(a, maps0.get(p, {}))
            rec.update(label="invertible" if P0 is not None else "no_inverse", P0=P0, n_proj=n)
        m = mixes.get(i) or hs.Mix(None, None, 0, "fallback", "rookie_no_rows")
        rec.update(basis=m.basis, reason=m.reason, games=m.games, std_h=m.std, rec_h=m.rec)
        recs[i] = rec
    q = {p: hs.position_share(mixes, recs.keys(), {i: r["pos"] for i, r in recs.items()}, p) for p in POSITIONS}
    for i, rec in recs.items():
        if rec["basis"] == "history":
            rec["k"] = rec["P0"] / (rec["std_h"] + r0 * rec["rec_h"]) if rec["P0"] is not None else None
        else:
            rec["k"] = None
    g = {p: build_g([(r["P0"], r["x"]) for r in recs.values() if r["pos"] == p and r["label"] == "invertible"])
         for p in POSITIONS}
    return Unwound(s0, recs, q, g)


def ratio_for(rec: dict, q: dict, s: str, s0: str) -> float:
    """P_i(s) / P_i(s0): own history, else the position-level mix."""
    if rec["basis"] == "history":
        return hs.own_ratio(hs.Mix(rec["std_h"], rec["rec_h"], rec["games"], "history", None), R_OF[s], R_OF[s0])
    qp = q.get(rec["pos"])
    if qp is None:
        raise ValueError(f"no position-level mix at {rec['pos']}")
    return hs.fallback_ratio(qp, R_OF[s], R_OF[s0])


def rebuild(u: Unwound, s: str, natives0: dict) -> dict:
    """Step 7: chart natives at s. natives0 = the chart's input list (every
    listed player); invertible players move by the delta form, everyone else
    keeps his native."""
    out = dict(natives0)
    # No shortcut at s == s0: the ratio is then exactly 1.0, so the delta form
    # returns x_i bit for bit (the identity test exercises this path).
    for i, rec in u.records.items():
        if rec["label"] != "invertible":
            continue
        g = u.g[rec["pos"]]
        P0 = rec["P0"]
        Ps = P0 * ratio_for(rec, u.q, s, u.s0)
        out[i] = rec["x"] + g_eval(g, Ps) - g_eval(g, P0)
    return out


def rebuild_proj(u: Unwound, s: str, maps_s: dict) -> dict:
    """v3_proj: {key: Adjusted at s} for the invertible players, priced through
    the projections' forward maps at s (below_waiver -> 0)."""
    out = {}
    for i, rec in u.records.items():
        if rec["label"] == "below_waiver":
            out[i] = 0.0
            continue
        if rec["label"] != "invertible":
            continue
        Ps = rec["P0"] * ratio_for(rec, u.q, s, u.s0)
        v = forward_points(Ps, maps_s.get(rec["pos"], {}))
        if v is not None:
            out[i] = v
    return out


def counts(u: Unwound) -> dict:
    out = {}
    for p in POSITIONS:
        rs = [r for r in u.records.values() if r["pos"] == p]
        c = {"priced": len(rs), "history": sum(r["basis"] == "history" for r in rs),
             "below_waiver": sum(r["label"] == "below_waiver" for r in rs),
             "no_inverse": sum(r["label"] == "no_inverse" for r in rs),
             "invertible": sum(r["label"] == "invertible" for r in rs),
             "g_tied_nodes": u.g[p].tied_nodes if u.g[p] else 0, "q_p": u.q[p]}
        for reason in hs.REASONS:
            c["fallback_" + reason] = sum(r["reason"] == reason for r in rs)
        out[p] = c
    return out


def monotone_violations(chart_recs: dict) -> int:
    """Count of adjacent pairs (by native, within position) where Adjusted falls."""
    bad = 0
    for p in POSITIONS:
        rs = sorted((x, a) for (pp, x, a, _v) in chart_recs.values() if pp == p and x > 0)
        bad += sum(rs[j + 1][1] < rs[j][1] - 1e-9 for j in range(len(rs) - 1) if rs[j + 1][0] > rs[j][0])
    return bad
