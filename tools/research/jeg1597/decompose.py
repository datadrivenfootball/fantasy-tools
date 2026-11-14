"""JEG-1599 (step 2 of JEG-1597): decompose a trade chart into points, rescore, rebuild.

Research prototype. Pure functions only: no file or network I/O, no change to
the value model. docs/research/jeg1597/step2-decomposition.md has the model.

Model, per chart c, position p, week w, anchor scoring s0:

1. Fit. A monotone map between the chart's native value and projected
   rest-of-season points at s0. The fit is a power law, log native = a +
   b log points, estimated on *rank-matched* pairs (the chart's k-th highest
   native against the k-th highest projected total among the same players),
   over the chart's top N at p. Rank matching converts units without the
   attenuation an ordinary regression would get from the chart and the
   projections disagreeing about *who* is better; the chart keeps its own
   order because the map is monotone (b > 0).
2. Implied points at s0: points_c(i, s0) = fit^-1(native_i). The chart's own
   "total yield" in points units.
3. Rescore: points_c(i, s) = points_c(i, s0) * ratio_i ** lam, ratio_i =
   proj_ppg(i, s) / proj_ppg(i, s0) from the projection stat line (games are
   the same at every scoring, so they cancel in the ratio).
4. Map back: native_c(i, s) = fit(points_c(i, s)). With the power law this is
   native_i * ratio_i ** (b * lam), so games and the fit's level `a` cancel;
   only the chart's elasticity b and the stat mix matter.

lam = 0 returns the natives unchanged (today's behaviour for that column).
"""
from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO / "pipelines") not in sys.path:
    sys.path.insert(0, str(REPO / "pipelines"))

from lib.scoring import SCORING  # noqa: E402  (read-only import)

SCORINGS = ("standard", "half_ppr", "ppr")
TRIPLET_INDEX = {"standard": 0, "half_ppr": 1, "ppr": 2}
RECEPTION_WEIGHT = {s: SCORING[s]["receptions"] for s in SCORINGS}
POSITIONS = ("QB", "RB", "WR", "TE")
# VP-2.2d missed-game rates, the fallback availability when CBS has no gp.
MISS_P = {"QB": 0.12, "RB": 0.14, "WR": 0.11, "TE": 0.15}
FIT_TOP_N = {"QB": 24, "RB": 36, "WR": 36, "TE": 24}
MIN_FIT_N = 8
LAMBDAS = (0.0, 0.5, 1.0)
# Stat-mix source preference (brief): Razzball pg_* line, cross-checked with
# CBS ROS; ESPN only where both are missing.
PRIMARY_SOURCES = ("razzball", "cbsros")
FALLBACK_SOURCES = ("espn",)


# ---------------------------------------------------------------------------
# Stat mix: points at any scoring from a per-game line
# ---------------------------------------------------------------------------

def points_from_triplet(triplet, scoring: str) -> float | None:
    """Per-game points at `scoring` from a [std, half, ppr] triplet. Scorings
    differ only in the receptions weight (lib/scoring.py), so the triplet is
    std + r * receptions and any scoring is read from std and ppr - std."""
    if not isinstance(triplet, (list, tuple)) or len(triplet) < 3:
        return None
    std, ppr = triplet[0], triplet[2]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (std, ppr)):
        return None
    return float(std) + RECEPTION_WEIGHT[scoring] * (float(ppr) - float(std))


def source_ratio(triplet, s0: str, s: str) -> float | None:
    """proj_ppg(s) / proj_ppg(s0) for one source's line; None when the s0
    points are not positive (no usable line)."""
    p0, p1 = points_from_triplet(triplet, s0), points_from_triplet(triplet, s)
    if p0 is None or p1 is None or p0 <= 0:
        return None
    return max(p1, 0.0) / p0


@dataclass
class Ratio:
    value: float
    basis: str            # "primary" | "fallback" | "median"
    spread: tuple         # (min, max) of the per-source ratios (all sources that have a line)
    n_sources: int


def player_ratio(lines: dict, s0: str, s: str,
                 primary=PRIMARY_SOURCES, fallback=FALLBACK_SOURCES) -> Ratio | None:
    """lines: {source: [std, half, ppr] per-game}. Ratio of the mean per-game
    points of the primary sources that have a line at s0 > 0; else the
    fallback sources'. Spread over every source with a line."""
    every = {k: source_ratio(t, s0, s) for k, t in lines.items()}
    every = {k: v for k, v in every.items() if v is not None}
    for basis, group in (("primary", primary), ("fallback", fallback)):
        used = [k for k in group if k in every]
        if used:
            p0 = statistics.fmean(points_from_triplet(lines[k], s0) for k in used)
            p1 = statistics.fmean(points_from_triplet(lines[k], s) for k in used)
            vals = list(every.values())
            return Ratio(max(p1, 0.0) / p0, basis, (min(vals), max(vals)), len(vals))
    return None


# ---------------------------------------------------------------------------
# Expected games (a prior: the chart gives one number per player)
# ---------------------------------------------------------------------------

def schedule_games(week: int, bye_week: int | None, last_week: int = 18) -> int:
    """Team games from `week` through `last_week` (CBS's gp convention counts
    the regular season through week 18), minus the bye if still ahead."""
    n = last_week - week + 1
    if bye_week is not None and week <= bye_week <= last_week:
        n -= 1
    return max(n, 0)


def expected_games(pos: str, week: int, bye_week: int | None, cbs_gp: float | None) -> tuple[float, str]:
    """(games, basis). CBS's own gp where it has one, else schedule games
    times (1 - miss_p) from VP-2.2d."""
    if cbs_gp is not None and cbs_gp > 0:
        return float(cbs_gp), "cbs_gp"
    return schedule_games(week, bye_week) * (1.0 - MISS_P[pos]), "schedule"


# ---------------------------------------------------------------------------
# Fit, inverse, rescale
# ---------------------------------------------------------------------------

@dataclass
class Fit:
    a: float              # log native intercept
    b: float              # elasticity of native in points
    n: int
    r2: float
    b_ols: float | None = None   # plain regression slope on the same players (diagnostic)
    identifiable: bool = True
    reason: str = ""

    def to_native(self, points: float) -> float:
        if points <= 0:
            return 0.0
        return math.exp(self.a + self.b * math.log(points))

    def to_points(self, native: float) -> float:
        if native <= 0:
            return 0.0
        return math.exp((math.log(native) - self.a) / self.b)


def _ols(xs, ys):
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None, None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    return a, b, (1 - sse / sst) if sst > 0 else 1.0


def fit_chart(pairs: list, top_n: int | None = None, min_n: int = MIN_FIT_N) -> Fit:
    """pairs: [(native, points_total)] for players the chart and the
    projections both list. Uses the chart's top `top_n` by native with both
    values > 0. Rank-matched power law; not identifiable (b = 1, flagged) when
    fewer than `min_n` players or the slope is not positive."""
    use = sorted(((n, p) for n, p in pairs if n > 0 and p > 0), key=lambda t: -t[0])
    if top_n:
        use = use[:top_n]
    if len(use) < min_n:
        return Fit(0.0, 1.0, len(use), 0.0, None, False, f"fewer than {min_n} shared players")
    natives = sorted((n for n, _ in use), reverse=True)
    points = sorted((p for _, p in use), reverse=True)
    lx = [math.log(p) for p in points]
    ly = [math.log(n) for n in natives]
    a, b, r2 = _ols(lx, ly)
    _a2, b_ols, _r = _ols([math.log(p) for _, p in use], [math.log(n) for n, _ in use])
    if a is None or b is None or b <= 0:
        return Fit(0.0, 1.0, len(use), 0.0, b_ols, False, "non-positive or undefined slope")
    return Fit(a, b, len(use), r2, b_ols)


def implied_points(native: float, fit: Fit, ratio: float = 1.0, lam: float = 1.0) -> float:
    """The chart's implied rest-of-season points at the target scoring."""
    return fit.to_points(native) * ratio ** lam


def rescale_native(native: float, fit: Fit, ratio: float, lam: float = 1.0,
                   position_ratio: float = 1.0) -> float:
    """Map implied points at the target scoring back to native units.

    position_ratio = 1 is the literal "same fit" inverse: fit(fit^-1(native)
    * ratio ** lam) = native * ratio ** (b * lam). With b > 1 (every chart is
    convex in points) a position-wide points change is amplified b times, so
    a Full -> Standard WR list (ratio ~0.64) would fall to 0.64 ** 2.9 ~ 0.27.

    position_ratio = k_p (the position's typical ratio) re-expresses the fit
    in the target scoring's points scale, g_s(x) = K * g(x / K) with K =
    k_p ** lam: the chart's value curve stretches with its position's points
    and its value units move in proportion (degree-1 homogeneous, like value
    above replacement). Result: native * K * (ratio / k_p) ** (b * lam). The
    position level then moves exactly as projected points (times lam) and
    only the player's deviation from his position's ratio goes through the
    chart's curve.

    lam = 0, a non-identifiable fit or native <= 0 return the native unchanged."""
    if lam == 0 or not fit.identifiable or native <= 0:
        return native
    if ratio == 1.0 and position_ratio == 1.0:
        return native
    scale = position_ratio ** lam
    return scale * fit.to_native(implied_points(native, fit, ratio, lam) / scale)


@dataclass
class ChartRescale:
    natives: dict                         # player_key -> rescaled native
    fits: dict                            # pos -> Fit
    ratio: dict                           # player_key -> ratio used
    median_ratio_keys: list = field(default_factory=list)   # no stat line: position median used
    not_identifiable: list = field(default_factory=list)    # positions left at lam 0
    position_ratio: dict = field(default_factory=dict)      # pos -> k_p used


MODES = ("position_scaled", "same_fit")


def rescale_chart(natives: dict, pos_of: dict, ratios: dict, points_s0: dict, lam: float,
                  top_n: dict = FIT_TOP_N, min_n: int = MIN_FIT_N,
                  mode: str = "position_scaled") -> ChartRescale:
    """One chart-week from the anchor scoring s0 to a target scoring.

    natives: {key: native at s0}; ratios: {key: Ratio | float} (s / s0);
    points_s0: {key: projected ROS points at s0} (mean ppg x expected games).
    A player without a ratio takes the median ratio of the chart's players at
    his position that have one (flagged). A position whose fit is not
    identifiable keeps its natives (lam 0, flagged). mode: "position_scaled"
    (k_p = median ratio of the chart's top-N fit players at the position, see
    rescale_native) or "same_fit" (k_p = 1, the literal inverse)."""
    if mode not in MODES:
        raise ValueError(mode)
    out, fits, used, kp = {}, {}, {}, {}
    median_keys, not_ident = [], []
    for pos in POSITIONS:
        keys = [k for k in natives if pos_of.get(k) == pos]
        if not keys:
            continue
        fit = fit_chart([(natives[k], points_s0[k]) for k in keys if k in points_s0],
                        top_n.get(pos), min_n)
        fits[pos] = fit
        have = {k: (ratios[k].value if isinstance(ratios[k], Ratio) else float(ratios[k]))
                for k in keys if ratios.get(k) is not None}
        med = statistics.median(have.values()) if have else 1.0
        top = sorted(keys, key=lambda k: -natives[k])[:top_n.get(pos) or len(keys)]
        top_r = [have[k] for k in top if k in have]
        kp[pos] = (statistics.median(top_r) if top_r else med) if mode == "position_scaled" else 1.0
        if not fit.identifiable:
            not_ident.append(pos)
        for k in keys:
            r = have.get(k)
            if r is None:
                r = med
                median_keys.append(k)
            used[k] = r
            out[k] = rescale_native(natives[k], fit, r, lam, kp[pos]) if fit.identifiable else natives[k]
    return ChartRescale(out, fits, used, median_keys, not_ident, kp)


def pair_flips(before: dict, after: dict, keys: list) -> int:
    """Within-set pairs whose order differs between two value maps."""
    n = 0
    for x in range(len(keys)):
        for y in range(x + 1, len(keys)):
            i, j = keys[x], keys[y]
            d0, d1 = before[i] - before[j], after[i] - after[j]
            if d0 * d1 < 0:
                n += 1
    return n
