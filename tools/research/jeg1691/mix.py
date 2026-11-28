"""JEG-1691 v5 steps 5-6: the player's stat mix from history and the assumed stat line.

Spec: docs/research/jeg1691/preregistration.md, section 1 (steps 5-6) and 2.4.
Pure functions only (no I/O). Research only.

Mix = stats per anchor point: m_c = h_c / F(h, s0), so F(m, s0) = 1.
Shrinkage: m~_c = a_c m_c + (1 - a_c) mbar_pc, a_c = n / (n + k_c); m* = m~ / F(m~, s0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# The seven categories DDF's ESPN ROS path scores (pipelines/bake_players.py ESPN_COMPS),
# with the weights of pipelines/lib/scoring.py. "int" is used only by T1b.
CATS = ("pass_yds", "pass_td", "rush_yds", "rush_td", "rec", "rec_yds", "rec_td")
CATS_INT = CATS + ("int",)
BASE_W = {"pass_yds": 0.04, "pass_td": 4.0, "rush_yds": 0.10, "rush_td": 6.0,
          "rec_yds": 0.10, "rec_td": 6.0, "int": -2.0}
REC_W = {"standard": 0.0, "half_ppr": 0.5, "ppr": 1.0}
SCORINGS = ("standard", "half_ppr", "ppr")
# player_game_stats (nflverse naming) -> mix category
PGS_KEY = {"passing_yards": "pass_yds", "passing_tds": "pass_td", "rushing_yards": "rush_yds",
           "rushing_tds": "rush_td", "receptions": "rec", "receiving_yards": "rec_yds",
           "receiving_tds": "rec_td", "interceptions": "int"}
K_GRID = (0.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, math.inf)
T_GRID = (math.inf, 8.0, 17.0)
PRIOR_MIN_GAMES = 8

# T1b custom scorings (descriptive): (name, base scoring, overrides, TE-only extra per reception)
CUSTOM = (("te_premium_full", "ppr", {}, 0.5),
          ("pass_td6_half", "half_ppr", {"pass_td": 6.0}, 0.0),
          ("int_minus1_half", "half_ppr", {"int": -1.0}, 0.0))


def weights(s: str, cats=CATS, overrides: dict | None = None, te_extra: float = 0.0,
            pos: str | None = None) -> dict:
    w = {c: (REC_W[s] if c == "rec" else BASE_W[c]) for c in cats}
    for c, v in (overrides or {}).items():
        if c in w:
            w[c] = v
    if te_extra and pos == "TE" and "rec" in w:
        w["rec"] += te_extra
    return w


def F(stats: dict, s: str, cats=CATS, **kw) -> float:
    """Points of a stat line at scoring s (no rounding, VP-0)."""
    w = weights(s, cats, **kw)
    return sum(w[c] * float(stats.get(c, 0.0)) for c in cats)


def game_has_stats(line: dict) -> bool:
    """A game counts when any scored category or targets is nonzero (amendment 2)."""
    return any(float(line.get(c, 0.0)) != 0.0 for c in CATS_INT) or float(line.get("targets", 0.0)) != 0.0


@dataclass(frozen=True)
class Hist:
    rates: dict      # per-game rates h_c (recency-weighted)
    n_eff: float     # sum of recency weights
    n_games: int


def history_rates(lines: list, t: float, cats=CATS) -> Hist | None:
    """lines: the player's game lines in time order (oldest first). Weight of a game =
    0.5 ** (age / t), age = games after it (0 = most recent); t = inf -> all 1."""
    lines = [ln for ln in lines if game_has_stats(ln)]
    if not lines:
        return None
    n = len(lines)
    ws = [1.0 if math.isinf(t) else 0.5 ** ((n - 1 - j) / t) for j in range(n)]
    tw = sum(ws)
    rates = {c: sum(w * float(ln.get(c, 0.0)) for w, ln in zip(ws, lines)) / tw for c in cats}
    return Hist(rates, tw, n)


def raw_mix(h: Hist | None, s0: str, cats=CATS) -> dict | None:
    if h is None:
        return None
    f = F(h.rates, s0, cats)
    if not f > 0:
        return None
    return {c: h.rates[c] / f for c in cats}


def position_prior(hists: dict, pos_of: dict, s0: str, cats=CATS) -> dict:
    """{pos: mbar_p}: games-weighted mean of raw mixes over players with >= 8 games."""
    acc = {}
    for k, h in hists.items():
        m = raw_mix(h, s0, cats)
        p = pos_of.get(k)
        if m is None or p is None or h.n_games < PRIOR_MIN_GAMES:
            continue
        a = acc.setdefault(p, [{c: 0.0 for c in cats}, 0.0])
        for c in cats:
            a[0][c] += h.n_games * m[c]
        a[1] += h.n_games
    return {p: {c: v[0][c] / v[1] for c in cats} for p, v in acc.items() if v[1] > 0}


@dataclass(frozen=True)
class Mix:
    m: dict          # m*: stats per anchor point, F(m, s0) = 1
    label: str       # own | fallback_position_mix
    n_games: int


def shrunk_mix(h: Hist | None, prior: dict, k: dict, s0: str, cats=CATS) -> Mix:
    """m* for one player; k: {cat: k_c}. Fallback (labelled) = the position prior."""
    m = raw_mix(h, s0, cats)
    if m is None:
        return Mix(normalise(prior, s0, cats), "fallback_position_mix", 0 if h is None else h.n_games)
    mt = {}
    for c in cats:
        kc = k[c]
        a = 0.0 if math.isinf(kc) else h.n_eff / (h.n_eff + kc)
        mt[c] = a * m[c] + (1.0 - a) * prior[c]
    return Mix(normalise(mt, s0, cats), "own", h.n_games)


def normalise(m: dict, s0: str, cats=CATS) -> dict:
    f = F(m, s0, cats)
    return {c: m[c] / f for c in cats}


def assumed_line(P0: float, mix: Mix) -> dict:
    """Step 6: shat = P_i(s0) x m*; F(shat, s0) = P_i(s0)."""
    return {c: P0 * v for c, v in mix.m.items()}


def rho(m: dict, s0: str, cats=CATS) -> float | None:
    """Receptions per non-reception point of a mix (the only quantity the presets see)."""
    nonrec = F(m, s0, cats) - REC_W[s0] * m.get("rec", 0.0)
    return m.get("rec", 0.0) / nonrec if nonrec > 0 else None


def rec_per_anchor_point(m: dict) -> float:
    return float(m.get("rec", 0.0))


def two_bucket_mix(rec: float, std_pts: float, s0: str) -> dict | None:
    """A points-only source (std points, receptions = ppr - std) as a mix: receptions and
    'other' points, per anchor point. 'other' has weight 1 at every preset."""
    f = std_pts + REC_W[s0] * rec
    if not f > 0 or std_pts < 0:
        return None
    return {"rec": rec / f, "other": std_pts / f}


def F2(m: dict, s: str) -> float:
    """F for a two-bucket mix."""
    return REC_W[s] * m.get("rec", 0.0) + m.get("other", 0.0)


def points_at(P0: float, m: dict, s: str, s0: str) -> float:
    """P_i(s) for a mix m (seven-category or two-bucket); exact at s = s0."""
    if s == s0:
        return P0
    if "other" in m:
        return P0 * F2(m, s) / F2(m, s0)
    return P0 * F(m, s) / F(m, s0)
