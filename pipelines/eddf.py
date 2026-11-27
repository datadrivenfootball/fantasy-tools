#!/usr/bin/env python3
"""EDDF: the enhanced DDF Value, an alternate version beside DDF Value (JEG-1735, part of JEG-1733).

Off by default. DDF Value never reads this module. EDDF is the equal-weight mean of
  - the Adjusted values of the trade charts DDF Value already averages, and
  - one rank-implied value per fresh ranker in config/eddf_sources.json,
over the sources that have the player (Jeremy, 2026-11-27: every stable source is a
separate equal-weight source, not pooled; stale sources are excluded; each FantasyPros staff
ranker is its own source; more rankers are added over time).

Rank-implied value of one ranker, in one scoring:
  1. Anchors: players whose chart value moved under `anchor_stability` of its mean over the
     last `anchor_weeks` weekly chart pulls. Chart values only, never a curve value, so the
     curve is never fitted to itself.
  2. Curve: non-increasing isotonic regression of anchor value on the ranker's overall rank,
     pooled across positions, clipped outside the anchors' rank range.
  3. Every ranked player of a non-excluded position gets curve(rank). Positions in
     `exclude_positions` (default QB: a pooled curve made QBs worse) get no implied value.

The ranker lists are rest-of-season lists and the charts are rest-of-season values; no
weekly list is used (Jeremy, 2026-10-29: "do not blend weekly data with ROS data, ever").
Pure functions, no I/O except `load_config`. The JS twin is
app/trade-value-chart/assets/eddf-model.js; tests/fixtures/eddf_parity.json pins both.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "eddf_sources.json"
SUPPORTED_TEAMS = 12  # fit and tested against DDF values at 12 teams, one QB, only


def load_config(path: Path = CONFIG) -> dict:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [r["id"] for r in cfg["rankers"]]
    if len(ids) != len(set(ids)):
        raise ValueError("eddf_sources.json: duplicate ranker id")
    return cfg


def available(setting: dict) -> tuple[bool, str | None]:
    """EDDF is fit and tested at 12 teams with one QB only (JEG-1735)."""
    if setting.get("superflex"):
        return False, "superflex: EDDF not fit against DDF values at this setting"
    if setting.get("teams") != SUPPORTED_TEAMS:
        return False, f"{setting.get('teams')} teams: EDDF not fit against DDF values at this setting"
    return True, None


# --- isotonic curve -------------------------------------------------------------------

def isotonic_nonincreasing(xs: list[float], ys: list[float]):
    """Pool-adjacent-violators fit of y on x, non-increasing. Returns f(x), linear between
    block end points and clipped outside the data (sklearn out_of_bounds='clip')."""
    if not xs:
        raise ValueError("no anchors")
    groups: list[list[float]] = []  # [x, y_sum, n] one per distinct x
    for x, y in sorted(zip(xs, ys)):
        if groups and groups[-1][0] == x:
            groups[-1][1] += y
            groups[-1][2] += 1
        else:
            groups.append([x, y, 1])
    # blocks: [first_x, last_x, y_sum, n]; pool while a block's mean rises above its left neighbour
    blocks: list[list[float]] = []
    for x, ysum, n in groups:
        blocks.append([x, x, ysum, n])
        while len(blocks) > 1 and blocks[-2][2] / blocks[-2][3] < blocks[-1][2] / blocks[-1][3]:
            x1, _, y1, n1 = blocks[-2]
            _, x2, y2, n2 = blocks[-1]
            blocks[-2:] = [[x1, x2, y1 + y2, n1 + n2]]
    knots: list[tuple[float, float]] = []
    for first, last, ysum, n in blocks:
        m = ysum / n
        knots.append((first, m))
        if last != first:
            knots.append((last, m))

    def f(x: float) -> float:
        if x <= knots[0][0]:
            return knots[0][1]
        if x >= knots[-1][0]:
            return knots[-1][1]
        for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
            if x0 <= x <= x1:
                return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return knots[-1][1]

    return f


# --- anchors and implied values -------------------------------------------------------

def stable_anchors(history: list[dict], stability: float, floor_frac: float) -> dict:
    """{player_key: newest chart value} for players priced in every pull of `history`
    (newest first, each {player_key: chart value}) whose spread is within `stability` of
    their mean. The mean is floored at `floor_frac` of the top value so a near-zero value
    does not read as unstable noise."""
    if not history:
        return {}
    top = max((v for h in history for v in h.values()), default=0.0)
    floor = floor_frac * top
    out = {}
    for pk in history[0]:
        vs = [h.get(pk) for h in history]
        if any(v is None for v in vs):
            continue
        mean = sum(vs) / len(vs)
        if max(vs) - min(vs) <= stability * max(mean, floor):
            out[pk] = vs[0]
    return out


def implied_values(ranks: dict, anchors: dict, pos_of: dict, cfg: dict) -> dict:
    """{player_key: implied value} for one ranker, one scoring. `ranks` is
    {player_key: overall rank}. Empty when fewer than `min_anchors` anchors are ranked."""
    excl = set(cfg["exclude_positions"])
    fit = [(ranks[pk], v) for pk, v in anchors.items() if pk in ranks and pos_of.get(pk) not in excl]
    if len(fit) < cfg["min_anchors"]:
        return {}
    f = isotonic_nonincreasing([r for r, _ in fit], [v for _, v in fit])
    return {pk: f(r) for pk, r in ranks.items() if pos_of.get(pk) not in excl}


def ranker_status(ranker: dict, vintage: str | None, as_of: date, stale_days: int,
                  scoring: str) -> dict:
    """Why a ranker is in or out: {id, in, reason}."""
    if not ranker.get("enabled", True):
        return {"id": ranker["id"], "in": False, "reason": "disabled in the registry"}
    if scoring not in ranker["scoring"]:
        return {"id": ranker["id"], "in": False, "reason": f"no {scoring} list in the registry"}
    if vintage is None:
        return {"id": ranker["id"], "in": False, "reason": "no list read"}
    age = (as_of - date.fromisoformat(vintage)).days
    if age > stale_days:
        return {"id": ranker["id"], "in": False, "reason": f"stale: list updated {vintage}, {age} days old (limit {stale_days})"}
    return {"id": ranker["id"], "in": True, "reason": f"fresh: updated {vintage}, {age} days old"}


VARIANTS = ("per_expert", "site_once", "grouped")


def source_weights(parts: dict, groups: dict, variant: str) -> dict:
    """Weight of each source present for one player. `parts` is {source id: value}; ids in
    `groups` are rankers, the rest are charts (weight 1 each).
    per_expert: every ranker one vote (Jeremy, 2026-11-28, the primary variant).
    site_once:  rankers of one group share one vote (a site's lists count once between them).
    grouped:    all rankers together are one source; the charts keep one vote each."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown EDDF variant {variant!r}")
    w = {k: 1.0 for k in parts}
    ranked = [k for k in parts if k in groups]
    if variant == "site_once":
        size: dict = {}
        for k in ranked:
            size[groups[k]] = size.get(groups[k], 0) + 1
        for k in ranked:
            w[k] = 1.0 / size[groups[k]]
    elif variant == "grouped":
        for k in ranked:
            w[k] = 1.0 / len(ranked)
    return w


def eddf(chart_adjusted: dict, lists: dict, vintages: dict, anchor_history: list[dict],
         pos_of: dict, cfg: dict, as_of: date, scoring: str, variant: str = "per_expert") -> dict:
    """EDDF for one setting.

    chart_adjusted: {chart: {player_key: Adjusted value}} for the charts DDF Value averages
                    (held charts already removed, as DDF Value does).
    lists:          {ranker_id: {player_key: overall rank}} in `scoring`.
    vintages:       {ranker_id: 'YYYY-MM-DD'} each list's own source_vintage.
    anchor_history: chart-mean values from the last weekly pulls, newest first.
    Returns {"values": {pk: {value, count, sources}}, "report": {...}}.
    """
    anchors = stable_anchors(anchor_history, cfg["anchor_stability"], cfg["anchor_floor_frac"])
    status, implied = [], {}
    for r in cfg["rankers"]:
        st = ranker_status(r, vintages.get(r["id"]), as_of, cfg["stale_days"], scoring)
        if st["in"]:
            vals = implied_values(lists.get(r["id"], {}), anchors, pos_of, cfg)
            if not vals:
                st = {"id": r["id"], "in": False, "reason": f"fewer than {cfg['min_anchors']} anchors ranked"}
            else:
                implied[r["id"]] = vals
        status.append(st)
    universe = set(pos_of)
    groups = {r["id"]: r.get("group", r["id"]) for r in cfg["rankers"]}
    values = {}
    for pk in universe:
        parts = {c: m[pk] for c, m in chart_adjusted.items() if m.get(pk) is not None}
        parts.update({rid: v[pk] for rid, v in implied.items() if pk in v})
        if parts:
            w = source_weights(parts, groups, variant)
            values[pk] = {"value": sum(w[k] * parts[k] for k in parts) / sum(w.values()),
                          "count": len(parts), "sources": sorted(parts)}
    n_c, n_r = len(chart_adjusted), len(implied)
    if variant == "per_expert":
        chart_share = (n_c / (n_c + n_r)) if n_c + n_r else None
    else:
        w_all = source_weights({**{c: 0 for c in chart_adjusted}, **{r: 0 for r in implied}}, groups, variant)
        tot = sum(w_all.values())
        chart_share = (n_c / tot) if tot else None
    return {"values": values,
            "report": {"scoring": scoring, "as_of": as_of.isoformat(), "anchors": len(anchors),
                       "rankers": status, "charts": sorted(chart_adjusted),
                       "variant": variant, "chart_weight_share": chart_share,
                       "exclude_positions": list(cfg["exclude_positions"])}}


def chart_only(chart_adjusted: dict, pos_of: Iterable) -> dict:
    """DDF Value as the reference computes it (equal-weight chart mean), for comparison."""
    out = {}
    for pk in pos_of:
        vs = [m[pk] for m in chart_adjusted.values() if m.get(pk) is not None]
        if vs:
            out[pk] = sum(vs) / len(vs)
    return out
