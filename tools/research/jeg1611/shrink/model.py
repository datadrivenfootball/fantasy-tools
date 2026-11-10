"""JEG-1611 steps 5-6: shrunk expected receptions per game for the rest of season.

rec_hat = (n_eff * rec_h + k_p * prior_p) / (n_eff + k_p)

- rec_h: recency-weighted mean of (ppr - std) over the player's prior games
  (game weight 0.5 ** (age_in_games / half_life), times season_decay for each
  season boundary between the game and the decision point).
- n_eff: sum of those weights.
- prior_p: position mean, or (role-aware form) a + b * std_h, std_h being the
  same recency-weighted mean of Standard points; clamped at >= 0.

Parameters are fitted by leave-one-season-out CV in run_shrink.py and stored
in tools/research/jeg1611/out/shrink/model.json. Research only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_JSON = HERE.parent / "out" / "shrink" / "model.json"
SKILL_POS = ("RB", "WR", "TE")


def _row(r):
    """(season, week, std, rec) from a dict or a (season, week, std, ppr) tuple."""
    if isinstance(r, dict):
        std = float(r.get("std") or 0)
        rec = float(r["rec"]) if "rec" in r else float(r.get("ppr") or 0) - std
        return int(r["season"]), int(r["week"]), std, rec
    s, w, std, ppr = r
    return int(s), int(w), float(std), float(ppr) - float(std)


def recency_sums(history_rows, season, week, half_life, season_decay):
    """(n_eff, sum_w_std, sum_w_rec, n_raw) over games strictly before (season, week).

    half_life is in games (None or inf = no game decay)."""
    games = sorted(g for g in map(_row, history_rows) if (g[0], g[1]) < (season, week))
    lam = 1.0 if half_life is None or math.isinf(half_life) else 0.5 ** (1.0 / half_life)
    n_eff = s_std = s_rec = 0.0
    last = None
    for s, _w, std, rec in games:
        if last is not None and s > last:
            f = season_decay ** (s - last)
            n_eff, s_std, s_rec = n_eff * f, s_std * f, s_rec * f
        n_eff, s_std, s_rec = n_eff * lam + 1.0, s_std * lam + std, s_rec * lam + rec
        last = s
    if last is not None and season > last:
        f = season_decay ** (season - last)
        n_eff, s_std, s_rec = n_eff * f, s_std * f, s_rec * f
    return n_eff, s_std, s_rec, len(games)


def shrink(rec_h, n_eff, k, prior):
    """(rec_hat, w) with w = n_eff / (n_eff + k)."""
    if n_eff <= 0:
        return prior, 0.0
    w = n_eff / (n_eff + k) if (n_eff + k) > 0 else 1.0
    return w * rec_h + (1.0 - w) * prior, w


def prior_for(params, std_h):
    """Position prior: constant mean, or role-aware a + b * std_h (>= 0)."""
    if params["prior_form"] == "linear_std" and std_h is not None:
        return max(0.0, params["a"] + params["b"] * std_h)
    return params["mean"]


def load_model(path=MODEL_JSON):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expected_receptions(history_rows, pos, week, season, model=None):
    """(rec_hat, n_eff, w) for the rest of `season` from decision week `week`.

    history_rows: the player's game rows, dicts with season/week/std and rec or
    ppr, or (season, week, std, ppr) tuples; rows at or after (season, week)
    are ignored. QB (and any non-skill position) is left alone: the position
    mean with w = 0.
    """
    model = model or load_model()
    pm = model["positions"].get(pos)
    if pm is None or pos not in SKILL_POS:
        qb = model.get("qb", {}).get("mean_rec_pg", 0.0)
        n_eff = recency_sums(history_rows, season, week, model["half_life_games"], model["season_decay"])[0]
        return qb, n_eff, 0.0
    n_eff, s_std, s_rec, _ = recency_sums(history_rows, season, week, pm["half_life_games"], pm["season_decay"])
    if n_eff <= 0:
        return prior_for(pm, None), 0.0, 0.0
    std_h, rec_h = s_std / n_eff, s_rec / n_eff
    rec_hat, w = shrink(rec_h, n_eff, pm["k"], prior_for(pm, std_h))
    return rec_hat, n_eff, w


def expected_reception_share(history_rows, pos, week, season, model=None):
    """(share_hat, n_eff, w): shrunk rest-of-season receptions per Standard point,
    rec / std, so Full = Standard * (1 + share_hat) and a scoring with r points
    per reception moves by log(1 + r * share_hat) (approximately, r in [0, 1]).

    Fitted on z = log(1 + rec/std) (ratio_model in model.json); the player's
    history z_h needs a recency-weighted Standard ppg >= min_std_h, else the
    position prior with w = 0. QB / non-skill: 0.0 with w = 0.
    """
    model = model or load_model()
    pm = model.get("ratio_model", {}).get(pos)
    if pm is None or pos not in SKILL_POS:
        return 0.0, 0.0, 0.0
    n_eff, s_std, s_rec, _ = recency_sums(history_rows, season, week, pm["half_life_games"], pm["season_decay"])
    if n_eff <= 0 or s_std / n_eff < pm["min_std_h"]:
        return math.expm1(pm["mean"]), 0.0, 0.0
    z_h = math.log1p((s_rec / n_eff) / (s_std / n_eff))
    z_hat, w = shrink(z_h, n_eff, pm["k"], pm["mean"])
    return math.expm1(z_hat), n_eff, w
