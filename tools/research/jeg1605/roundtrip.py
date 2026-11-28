"""JEG-1605: scoring-aware DDF v2, the round trip (stages 1-8), pure functions.

Research prototype. No file or network I/O, no change to the value model.
Spec (binding): docs/research/jeg1605/preregistration.md, section 1. The
interpretations taken where the spec was not literal enough to code are logged
in its "Changes after this commit" list.

Chain per chart c, week w, anchor s0, target s:
  1. x_i = chart value at s0 (x <= 0 or absent = no price).
  2. P_i(s0) = mean ppg_i(s0) x G_i; Rproj_p(s0) = mean P of ranks N_p..N_p+6;
     V_i = P_i - Rproj_p. One pooled power law log x = a + b log V on
     rank-matched pairs per position. Vc_i = (x_i / e^a)^(1/b).
  3. Pc_i(s0) = Vc_i + Rproj_p(s0).
  4. Mix: per-game {std, rec} line = mean of the sources that list him.
  5. Target scoring over the metric vector (uniform or additive split).
  6. Rebuilt pool at s: chart players Pc_i(s), everyone else projected P_i(s).
  7. R_p re-derived at s and at s0; Vc_i(s) = Vc_i + dPc_i - dR_p.
  8. x_i(s) = e^a max(Vc_i(s), 0)^b, computed as x_i (Vc_i(s) / Vc_i)^b
     (algebraically identical; exact at s = s0).
"""
from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO / "pipelines", REPO / "tools" / "research" / "jeg1597"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import decompose as dc  # noqa: E402  (read-only reuse of v1)

POSITIONS = dc.POSITIONS
FIT_TOP_N = dc.FIT_TOP_N
MIN_FIT_N = dc.MIN_FIT_N
BAND = 7
SOURCES = ("espn", "cbsros", "razzball")
ANCHOR_SCORINGS = ("standard", "half_ppr", "ppr")

# Scoring = weights over the metric vector {std, rec}; "by_pos" overrides per position.
SCORING_SPECS = {
    "standard": {"std": 1.0, "rec": dc.RECEPTION_WEIGHT["standard"]},
    "half_ppr": {"std": 1.0, "rec": dc.RECEPTION_WEIGHT["half_ppr"]},
    "ppr": {"std": 1.0, "rec": dc.RECEPTION_WEIGHT["ppr"]},
    "ppr_te_premium": {"std": 1.0, "rec": 1.0, "by_pos": {"TE": {"rec": 1.5}}},
}


def scoring_spec(s) -> dict:
    return SCORING_SPECS[s] if isinstance(s, str) else s


def weights_for(scoring, pos: str) -> dict:
    sp = scoring_spec(scoring)
    w = {k: v for k, v in sp.items() if k != "by_pos"}
    w.update((sp.get("by_pos") or {}).get(pos, {}))
    return w


def line_points(line: dict, scoring, pos: str) -> float:
    """Per-game points of a metric line under a scoring."""
    w = weights_for(scoring, pos)
    return sum(w.get(m, 0.0) * v for m, v in line.items())


def triplet_line(t) -> dict | None:
    """{std, rec} per game from a [std, half, ppr] triplet (rec = ppr - std)."""
    if not isinstance(t, (list, tuple)) or len(t) < 3:
        return None
    std, ppr = t[0], t[2]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (std, ppr)):
        return None
    return {"std": float(std), "rec": float(ppr) - float(std)}


# ---------------------------------------------------------------------------
# Projections, replacement
# ---------------------------------------------------------------------------

def projected_ppg(by_src: dict, scoring, pos: str) -> float | None:
    """Mean ppg at `scoring` over the sources with ppg > 0 (v1's rule)."""
    vals = []
    for t in by_src.values():
        ln = triplet_line(t)
        if ln is None:
            continue
        v = line_points(ln, scoring, pos)
        if v > 0:
            vals.append(v)
    return statistics.fmean(vals) if vals else None


def projected_points(lines: dict, pos_of: dict, games: dict, scoring) -> dict:
    """{key: mean ppg x G} for every projected player at QB/RB/WR/TE."""
    out = {}
    for k, by_src in lines.items():
        pos = pos_of.get(k)
        if pos not in POSITIONS or k not in games:
            continue
        v = projected_ppg(by_src, scoring, pos)
        if v is not None:
            out[k] = v * games[k]
    return out


def replacement(points: dict, pos_of: dict, n_p: dict, band: int = BAND) -> dict:
    """{pos: mean points of 0-based ranks N_p .. N_p + band - 1 of the points order}."""
    out = {}
    for p in POSITIONS:
        order = sorted((k for k in points if pos_of.get(k) == p), key=lambda k: (-points[k], k))
        sel = order[n_p[p]:n_p[p] + band]
        out[p] = statistics.fmean(points[k] for k in sel) if sel else 0.0
    return out


# ---------------------------------------------------------------------------
# Value-vs-VORP curve
# ---------------------------------------------------------------------------

@dataclass
class Curve:
    a: float
    b: float
    n: int
    resid_sd: float                     # sqrt(SSE / (n - 2)) in log value
    pos_log_resid: dict = field(default_factory=dict)   # pos -> mean log residual (level vs the curve)
    pos_n: dict = field(default_factory=dict)
    identifiable: bool = True
    reason: str = ""

    def vorp(self, x: float) -> float:
        return math.exp((math.log(x) - self.a) / self.b)


def rank_matched_pairs(values: dict, vorp: dict, pos_of: dict, top_n: dict = FIT_TOP_N) -> list:
    """[(pos, x, V)]: per position, the chart's top_n listed players (x > 0)
    that have a projected VORP; their k-th largest value against the k-th
    largest VORP among them; pairs with V > 0 kept."""
    out = []
    for p in POSITIONS:
        keys = [k for k, x in values.items() if pos_of.get(k) == p and x > 0 and k in vorp]
        top = sorted(keys, key=lambda k: (-values[k], k))[:top_n[p]]
        xs = sorted((values[k] for k in top), reverse=True)
        vs = sorted((vorp[k] for k in top), reverse=True)
        out += [(p, x, v) for x, v in zip(xs, vs) if v > 0]
    return out


def fit_curve(pairs: list, min_n: int = MIN_FIT_N) -> Curve:
    """OLS of log x on log V over the pairs. Not identifiable when fewer than
    min_n pairs or b <= 0."""
    if len(pairs) < min_n:
        return Curve(0.0, 1.0, len(pairs), float("nan"), identifiable=False, reason=f"fewer than {min_n} pairs")
    lx = [math.log(v) for _, _, v in pairs]
    ly = [math.log(x) for _, x, _ in pairs]
    mx, my = statistics.fmean(lx), statistics.fmean(ly)
    sxx = sum((u - mx) ** 2 for u in lx)
    if sxx <= 0:
        return Curve(0.0, 1.0, len(pairs), float("nan"), identifiable=False, reason="no spread in VORP")
    b = sum((u - mx) * (y - my) for u, y in zip(lx, ly)) / sxx
    a = my - b * mx
    res = [y - a - b * u for u, y in zip(lx, ly)]
    sd = math.sqrt(sum(r * r for r in res) / (len(res) - 2)) if len(res) > 2 else float("nan")
    by = {}
    for (p, _, _), r in zip(pairs, res):
        by.setdefault(p, []).append(r)
    c = Curve(a, b, len(pairs), sd, {p: statistics.fmean(v) for p, v in by.items()},
              {p: len(v) for p, v in by.items()})
    if b <= 0:
        c.identifiable, c.reason = False, "non-positive slope"
    return c


def fit_curves(values, vorp, pos_of, mode: str = "pooled", top_n: dict = FIT_TOP_N) -> tuple[Curve, dict, list]:
    """(pooled curve, {pos: curve used}, positions that fell back to the pooled
    curve). mode "per_position": one curve per position, pooled where a
    position's own fit is not identifiable."""
    pairs = rank_matched_pairs(values, vorp, pos_of, top_n)
    pooled = fit_curve(pairs)
    used, fell_back = {p: pooled for p in POSITIONS}, []
    if mode == "per_position":
        for p in POSITIONS:
            c = fit_curve([t for t in pairs if t[0] == p])
            if c.identifiable:
                used[p] = c
            else:
                fell_back.append(p)
    elif mode != "pooled":
        raise ValueError(mode)
    return pooled, used, fell_back


# ---------------------------------------------------------------------------
# Mix
# ---------------------------------------------------------------------------

def player_mix(by_src: dict, sources=SOURCES) -> dict | None:
    """Mean {std, rec} over the given sources that list him: a valid triplet
    with Full (ppr) points > 0. Equal weight per source."""
    ls = []
    for src in sources:
        ln = triplet_line(by_src.get(src))
        if ln is not None and ln["std"] + ln["rec"] > 0:
            ls.append(ln)
    if not ls:
        return None
    return {"std": statistics.fmean(l["std"] for l in ls), "rec": statistics.fmean(l["rec"] for l in ls)}


def source_ratios(by_src: dict, s0, s, pos: str, sources=SOURCES) -> dict:
    """{source: ppg(s) / ppg(s0)} of each listing source's own line (ppg(s0) > 0)."""
    out = {}
    for src in sources:
        ln = triplet_line(by_src.get(src))
        if ln is None or ln["std"] + ln["rec"] <= 0:
            continue
        p0 = line_points(ln, s0, pos)
        if p0 > 0:
            out[src] = line_points(ln, s, pos) / p0
    return out


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------

@dataclass
class ChainResult:
    values: dict              # key -> x_i(s), chart-priced players only
    curve: Curve              # pooled curve
    curves: dict              # pos -> curve used
    curve_fallback: list      # positions on the pooled curve under per_position
    vc0: dict                 # chart VORP at s0
    vc: dict                  # VORP at s
    pc0: dict                 # chart points at s0
    pc: dict                  # chart points at s
    ratio: dict               # Pc(s) / Pc(s0)
    line: dict                # mix line used
    fallback: list            # chart players on the position-median line (no listing source)
    zero_anchor_line: list    # uniform split: own line has ppg(s0) <= 0, position median used
    rproj0: dict
    r0: dict
    r: dict
    n_priced: int


def chain(values: dict, pos_of: dict, lines: dict, games: dict, n_p0: dict, n_p: dict, s0, s,
          split: str = "uniform", curve_mode: str = "pooled", mix_sources=SOURCES,
          top_n: dict = FIT_TOP_N) -> ChainResult:
    """One chart-week from anchor s0 to target s (stages 1-8)."""
    if split not in ("uniform", "additive"):
        raise ValueError(split)
    priced = {k: float(x) for k, x in values.items() if x is not None and x > 0 and pos_of.get(k) in POSITIONS}
    # 2. projected VORP at s0 and the curve
    p0 = projected_points(lines, pos_of, games, s0)
    rproj0 = replacement(p0, pos_of, n_p0)
    vorp = {k: v - rproj0[pos_of[k]] for k, v in p0.items()}
    pooled, curves, cfb = fit_curves(priced, vorp, pos_of, curve_mode, top_n)
    if not pooled.identifiable:
        raise ValueError(f"pooled curve not identifiable: {pooled.reason}")
    vc0 = {k: curves[pos_of[k]].vorp(x) for k, x in priced.items()}
    # 3. games plus points
    pc0 = {k: vc0[k] + rproj0[pos_of[k]] for k in priced}
    # 4. mix
    line = {k: player_mix(lines.get(k, {}), mix_sources) for k in priced}
    fallback = [k for k in priced if line[k] is None]
    med = {}
    for p in POSITIONS:
        have = [line[k] for k in priced if pos_of[k] == p and line[k] is not None]
        med[p] = ({"std": statistics.median(l["std"] for l in have), "rec": statistics.median(l["rec"] for l in have)}
                  if have else {"std": 1.0, "rec": 0.0})
    for k in fallback:
        line[k] = dict(med[pos_of[k]])
    zero = []
    if split == "uniform":
        for k in priced:
            if line_points(line[k], s0, pos_of[k]) <= 0:
                zero.append(k)
                line[k] = dict(med[pos_of[k]])
    # 5-6. target scoring, rebuilt points (delta form: exactly 0 at s = s0)
    pc, ratio = {}, {}
    for k in priced:
        pos, ln = pos_of[k], line[k]
        if split == "uniform":
            r = line_points(ln, s, pos) / line_points(ln, s0, pos)
            pc[k] = pc0[k] + pc0[k] * (r - 1.0)
        else:
            g = games[k]
            excess = pc0[k] / g - line_points(ln, s0, pos)          # chart excess, in non-reception points
            w0, w1 = weights_for(s0, pos).get("std", 0.0), weights_for(s, pos).get("std", 0.0)
            chart_line = {"std": ln["std"] + excess / w0, "rec": ln["rec"]}
            pc[k] = pc0[k] + g * (line_points(chart_line, s, pos) - line_points(chart_line, s0, pos))
        ratio[k] = pc[k] / pc0[k]
    ps = projected_points(lines, pos_of, games, s)
    rebuilt0 = {**p0, **pc0}
    rebuilt = {**ps, **pc}
    # 7. replacement re-derived at s and s0, VORP as changes
    r0 = replacement(rebuilt0, pos_of, n_p0)
    r = replacement(rebuilt, pos_of, n_p)
    vc = {k: vc0[k] + (pc[k] - pc0[k]) - (r[pos_of[k]] - r0[pos_of[k]]) for k in priced}
    # 8. back through the same curve
    out = {k: priced[k] * (max(vc[k], 0.0) / vc0[k]) ** curves[pos_of[k]].b for k in priced}
    return ChainResult(out, pooled, curves, cfb, vc0, vc, pc0, pc, ratio, line, fallback, zero,
                       rproj0, r0, r, len(priced))


def chain_mix(values: dict, weights: dict, pos_of, lines, games, n_p_by_scoring: dict, s,
              n_p_target: dict | None = None, **kw) -> dict:
    """Anchor as a weight vector over settings: the chain runs once per setting
    with positive weight. Returns {"values": weighted mean, "interval": {k:
    (min, max)}, "runs": {s0: ChainResult}}. N_p at the target is its own
    allocation unless given (a general scoring such as TE premium)."""
    n_t = n_p_target if n_p_target is not None else n_p_by_scoring[s]
    runs = {s0: chain(values, pos_of, lines, games, n_p_by_scoring[s0], n_t, s0, s, **kw)
            for s0, w in weights.items() if w > 0}
    tot = sum(w for w in weights.values() if w > 0)
    keys = next(iter(runs.values())).values.keys()
    mean = {k: sum(weights[s0] * r.values[k] for s0, r in runs.items()) / tot for k in keys}
    iv = {k: (min(r.values[k] for r in runs.values()), max(r.values[k] for r in runs.values())) for k in keys}
    return {"values": mean, "interval": iv, "runs": runs}


# ---------------------------------------------------------------------------
# Anchor estimator (section 2)
# ---------------------------------------------------------------------------

def anchor_residuals(values: dict, pos_of, lines, games, n_p_by_scoring: dict,
                     candidates=ANCHOR_SCORINGS) -> dict:
    """{s0: pooled Curve} for each candidate anchor; the estimator picks the
    lowest resid_sd."""
    priced = {k: x for k, x in values.items() if x is not None and x > 0 and pos_of.get(k) in POSITIONS}
    out = {}
    for s0 in candidates:
        p0 = projected_points(lines, pos_of, games, s0)
        rp = replacement(p0, pos_of, n_p_by_scoring[s0])
        vorp = {k: v - rp[pos_of[k]] for k, v in p0.items()}
        out[s0] = fit_curve(rank_matched_pairs(priced, vorp, pos_of))
    return out


def estimate_anchor(curves: dict) -> str:
    return min(curves, key=lambda s0: (curves[s0].resid_sd, ANCHOR_SCORINGS.index(s0)))
