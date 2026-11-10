#!/usr/bin/env python3
"""Evidence for the trade value source audit (JEG-1565, private draft article).

Reads only files in this repo and writes one JSON the article page loads
(app/next/research/trade-value-audit-data.json). Every number on the page comes
from this output; tests/test_research_trade_value_audit.py re-runs it and checks
the page's JSON and the numbers quoted in its text equal the output.

Inputs (week 9, 2026 snapshot):
  data/fixtures/current/comparison-sources-data.json  published chart values
  data/fixtures/current/players.json                   projections, names, positions
  data/history/week-5.json .. week-9.json              one frozen snapshot per week
  pipelines/value_reference.py                         our value model (the yardstick)

Run:  python3 pipelines/research_trade_value_audit.py [--out PATH] [--check]
--check exits 1 when PATH differs from a fresh run (the page data is stale).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from itertools import combinations
from pathlib import Path

import os

REPO = Path(__file__).resolve().parents[1]
# AUDIT_ENGINE_DIR: run the article on another checkout's value model (e.g. one with the
# charts-only position split, DDF_VALUE_SPLIT=charts) while reading this branch's week 9 inputs.
ENGINE_DIR = Path(os.environ.get("AUDIT_ENGINE_DIR") or (REPO / "pipelines"))
sys.path.insert(0, str(ENGINE_DIR))
import value_reference as vr  # noqa: E402
from lib.canonical_players import norm_player_name  # noqa: E402  (the one name rule, JEG-438)

OUT = REPO / "app" / "next" / "research" / "trade-value-audit-data.json"
HISTORY_DIR = REPO / "data" / "history"
SNAPSHOT_DAY = date(2026, 11, 7)  # pins value_reference's week logic so reruns match
WEEKS = (5, 6, 7, 8, 9)
POS = vr.POSITIONS
FLEX = ("RB", "WR", "TE")
CHARTS = ("cbs", "usatoday", "fantasypros", "fantasycalc")
PROJ = ("espn", "cbsros", "razzball")
NAMES = {"cbs": "CBS Sports", "usatoday": "USA Today", "fantasypros": "FantasyPros",
         "fantasycalc": "FantasyCalc", "espn": "ESPN", "cbsros": "CBS rest-of-season projections",
         "razzball": "Razzball"}
SCORING_LABEL = {"standard": "Standard", "half_ppr": "Half PPR", "ppr": "Full PPR"}
HIST_INDEX = vr.HISTORY_SCORING_INDEX
BASE = {"scoring": "half_ppr", "teams": 12, "superflex": 0}
TOP_N = 50          # model-free position mix: the source's own top 50
CURVE_N = 120       # overall curve length drawn on the page
TRADE_POOL = 150    # players offered in the trade-it-yourself box
SCORING_TOP = 36    # players per position compared across scoring formats
WEEKLY_TOP = 24     # players per position followed week to week
OUTLIER_DEPTH = 36  # an outlier must be a top-36 player at his position on that chart or by the others


def r(x, nd=1):
    return None if x is None else round(float(x), nd)


def spearman(a: list, b: list) -> float | None:
    """Spearman rank correlation (average ranks for ties)."""
    n = len(a)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va and vb else None


WEEK9_FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
WEEK9_PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"


def load():
    return vr.Inputs.load(WEEK9_FIXTURE, WEEK9_PLAYERS, today=SNAPSHOT_DAY)


def setting(inp, scoring="half_ppr", teams=12, superflex=0):
    return vr.Setting(inp, scoring, teams, superflex)


def pos_shares(diag_src: dict) -> dict:
    w = diag_src["weights"] or {}
    return {p: w.get(f"{p}|starter", 0.0) + w.get(f"{p}|bench", 0.0) for p in POS}


def mean_shares(list_of: list) -> dict:
    return {p: sum(s[p] for s in list_of) / len(list_of) for p in POS}


def pct(d: dict) -> dict:
    return {p: r(100 * d[p], 1) for p in POS}


def l1_points(a: dict, b: dict) -> float:
    """Half the sum of absolute share differences, in percentage points:
    the share of value that would have to move between positions to match."""
    return 50 * sum(abs(a[p] - b[p]) for p in POS)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def source_meta(inp, base_diag) -> dict:
    out = {}
    for k in CHARTS:
        sec = inp.section(k) or {}
        hold = sec.get("validationHold") or sec.get("promotionHold")
        d = base_diag["sources"].get(k, {})
        positions = d.get("positions", {})
        out[k] = {
            "name": NAMES[k], "family": vr.FAMILY[k],
            "kind": sec.get("kind"), "fetched_at": sec.get("fetched_at"),
            "content_vintage": sec.get("content_vintage") or sec.get("vintage"),
            "claimed_settings": sec.get("claimed_settings"),
            "held_this_week": bool(hold),
            "hold_reason": (hold or {}).get("reason") if isinstance(hold, dict) else None,
            "hold_level": (hold or {}).get("hold_level") if isinstance(hold, dict) else None,
            "listed": {p: positions.get(p, {}).get("listed") for p in POS},
            "rostered": {p: positions.get(p, {}).get("rostered") for p in POS},
            "filled_in": {p: positions.get(p, {}).get("nEstimated") for p in POS},
        }
    return out


def position_weighting(inp) -> dict:
    cases = {
        "half_ppr/12/1qb": ("half_ppr", 12, 0), "half_ppr/12/sf": ("half_ppr", 12, 1),
        "standard/12/1qb": ("standard", 12, 0), "ppr/12/1qb": ("ppr", 12, 0),
    }
    out = {}
    for cid, (sc, t, sf) in cases.items():
        diag = setting(inp, sc, t, sf).diagnostics()
        shares = {k: pos_shares(diag["sources"][k]) for k in CHARTS}
        w = diag["ddfWeights"]
        ddf = {p: w[f"{p}|starter"] + w[f"{p}|bench"] for p in POS}  # DDF Value's position budget (VP-4)
        out[cid] = {
            "sources": {k: pct(v) for k, v in shares.items()},
            "ddf_value": pct(ddf),
            "analyst_charts_mean": pct(mean_shares([shares[k] for k in ("cbs", "usatoday", "fantasypros")])),
            "gap_vs_ddf": {k: r(l1_points(shares[k], ddf), 1) for k in CHARTS},
        }
    return out


def overall_order(values: dict, pos_of: dict) -> list:
    return sorted((i for i in values if pos_of.get(i) in POS), key=lambda i: (-values[i], i))


def top_mix(inp, s) -> dict:
    pos_of = s.pos_of
    out = {}
    for k in CHARTS:
        order = overall_order(s.natives(k), pos_of)[:TOP_N]
        out[k] = {p: sum(1 for i in order if pos_of[i] == p) for p in POS}
    return out


def scoring_awareness(inp) -> dict:
    """Does a source change between Standard and Full PPR? For each position,
    the top SCORING_TOP players by Full PPR value that both lists carry: the
    share whose number changes, and the share whose place in the order changes."""
    std, full = setting(inp, "standard"), setting(inp, "ppr")
    pos_of = std.pos_of
    out = {}
    for k in CHARTS:
        a, b = std.natives(k), full.natives(k)
        row = {}
        for p in POS:
            common = [i for i in a if i in b and pos_of.get(i) == p]
            common = sorted(common, key=lambda i: (-b[i], i))[:SCORING_TOP]
            changed = sum(1 for i in common if abs(a[i] - b[i]) > 1e-9)
            order_a = sorted(common, key=lambda i: (-a[i], i))
            order_b = sorted(common, key=lambda i: (-b[i], i))
            moved = sum(1 for x, y in zip(order_a, order_b) if x != y)
            row[p] = {"n": len(common), "changed_pct": r(100 * changed / len(common), 0) if common else None,
                      "order_changed_pct": r(100 * moved / len(common), 0) if common else None,
                      "rank_corr": r(spearman([a[i] for i in common], [b[i] for i in common]), 3)}
        out[k] = row
    return out


def superflex(inp, pw) -> dict:
    base, sf = setting(inp, "half_ppr", 12, 0), setting(inp, "half_ppr", 12, 1)
    pos_of = base.pos_of
    out = {}
    for k in CHARTS:
        one, two = base.natives(k), sf.natives(k)
        cell = inp.cell(k, "half_ppr", 12, "native_superflex")
        sf_qbs = sum(1 for i in (cell or {}).get("values", {}) if pos_of.get(i) == "QB")
        top_q1 = max((v for i, v in one.items() if pos_of[i] == "QB"), default=None)
        top_q2 = max((v for i, v in two.items() if pos_of[i] == "QB"), default=None)
        top_nonqb = max((v for i, v in one.items() if pos_of[i] != "QB"), default=None)
        out[k] = {
            "superflex_qbs_listed": sf_qbs,
            "qb_share_1qb": pw["half_ppr/12/1qb"]["sources"][k]["QB"],
            "qb_share_sf": pw["half_ppr/12/sf"]["sources"][k]["QB"],
            "top_qb_vs_top_player_1qb_pct": r(100 * top_q1 / top_nonqb, 0) if top_q1 and top_nonqb else None,
            "top_qb_vs_top_player_sf_pct": r(100 * top_q2 / top_nonqb, 0) if top_q2 and top_nonqb else None,
        }
    out["ddf_value"] = {"qb_share_1qb": pw["half_ppr/12/1qb"]["ddf_value"]["QB"], "qb_share_sf": pw["half_ppr/12/sf"]["ddf_value"]["QB"]}
    return out


def ddf_values(s) -> dict:
    """Our DDF Value (the model's mean of the four charts' Adjusted values)."""
    idx = s.rows("indexed")
    return {i: v["ddf_value"] for i, v in idx.items() if v.get("ddf_value") is not None}


def curves(inp) -> dict:
    """Each chart's overall value curve, #1 = 100, ranks 1..CURVE_N, per scoring;
    plus curve statistics at half PPR."""
    out = {"curves": {}, "stats": {}, "curve_players": {}}
    for sc in vr.SCORINGS:
        s = setting(inp, sc)
        out["curves"][sc] = {}
        for k in CHARTS:
            nat = s.natives(k)
            order = overall_order(nat, s.pos_of)
            top = nat[order[0]]
            out["curves"][sc][k] = [r(100 * nat[i] / top, 1) for i in order[:CURVE_N]]
            out["curve_players"].setdefault(sc, {})[k] = [[inp.players[i]["name"], s.pos_of[i]] for i in order[:CURVE_N]]
        ddf = ddf_values(s)
        order = overall_order(ddf, s.pos_of)
        out["curves"][sc]["ddf"] = [r(100 * ddf[i] / ddf[order[0]], 1) for i in order[:CURVE_N]]
        out["curve_players"][sc]["ddf"] = [[inp.players[i]["name"], s.pos_of[i]] for i in order[:CURVE_N]]
    s = setting(inp)
    diag = s.diagnostics()
    for k in CHARTS:
        nat = s.natives(k)
        order = overall_order(nat, s.pos_of)
        top = nat[order[0]]
        pos_top = {p: max(v for i, v in nat.items() if s.pos_of[i] == p) for p in POS}
        waiver = {p: diag["sources"][k]["positions"][p]["waiver"] for p in POS}
        at = lambda n: r(100 * nat[order[n - 1]] / top, 0) if len(order) >= n else None  # noqa: E731
        out["stats"][k] = {
            "listed_total": len(order),
            "rank12_pct": at(12), "rank24_pct": at(24), "rank50_pct": at(50), "rank100_pct": at(100),
            "waiver_pct_of_position_top": {p: r(100 * waiver[p] / pos_top[p], 1) for p in POS},
            "waiver_pct_of_overall_top": {p: r(100 * waiver[p] / top, 1) for p in POS},
        }
    for k in CHARTS:
        nat = s.natives(k)
        top = max(nat.values())
        out["stats"][k]["position_top_pct"] = {
            p: r(100 * max(v for i, v in nat.items() if s.pos_of[i] == p) / top, 0) for p in POS}
    ddf = ddf_values(s)
    order = overall_order(ddf, s.pos_of)
    out["stats"]["ddf"] = {"position_top_pct": {
        p: r(100 * max(v for i, v in ddf.items() if s.pos_of[i] == p) / ddf[order[0]], 0) for p in POS},"listed_total": len(order),
                           **{f"rank{n}_pct": r(100 * ddf[order[n - 1]] / ddf[order[0]], 0) for n in (12, 24, 50, 100)}}
    return out


def consolidation(inp) -> dict:
    """2-for-1 test at half PPR: of all pairs of players ranked 25-60 on a
    chart, the share whose summed chart value is strictly greater than each top-12 player's, raw
    and after each piece's own waiver-line value is subtracted (the receiving
    team cuts a waiver-level player to make room)."""
    s = setting(inp)
    diag = s.diagnostics()
    out = {}
    for k in CHARTS:
        nat = s.natives(k)
        order = overall_order(nat, s.pos_of)
        waiver = {p: diag["sources"][k]["positions"][p]["waiver"] for p in POS}
        vaw = {i: max(0.0, nat[i] - waiver[s.pos_of[i]]) for i in order}
        stars, mids = order[:12], order[24:60]
        pairs = list(combinations(mids, 2))
        raw_hits = vaw_hits = 0
        for st in stars:
            raw_hits += sum(1 for a, b in pairs if nat[a] + nat[b] > nat[st])
            vaw_hits += sum(1 for a, b in pairs if vaw[a] + vaw[b] > vaw[st])
        total = len(stars) * len(pairs)
        out[k] = {"pairs_tested": total, "raw_beats_star_pct": r(100 * raw_hits / total, 0),
                  "after_waiver_beats_star_pct": r(100 * vaw_hits / total, 0)}
    ddf = ddf_values(s)  # already value above waivers: nothing to subtract
    order = overall_order(ddf, s.pos_of)
    stars, pairs = order[:12], list(combinations(order[24:60], 2))
    hits = sum(1 for st in stars for a, b in pairs if ddf[a] + ddf[b] > ddf[st])
    out["ddf"] = {"pairs_tested": len(stars) * len(pairs),
                  "after_waiver_beats_star_pct": r(100 * hits / (len(stars) * len(pairs)), 0)}
    return out


def agreement(inp) -> dict:
    s = setting(inp)
    pos_of = s.pos_of
    nat = {k: s.natives(k) for k in CHARTS}
    common = [i for i in nat["cbs"] if all(i in nat[k] for k in CHARTS)]
    matrix = {}
    for a, b in combinations(CHARTS, 2):
        matrix[f"{a}|{b}"] = r(spearman([nat[a][i] for i in common], [nat[b][i] for i in common]), 3)
    by_pos = {}
    for p in POS:
        cp = [i for i in common if pos_of[i] == p]
        by_pos[p] = {f"{a}|{b}": r(spearman([nat[a][i] for i in cp], [nat[b][i] for i in cp]), 3)
                     for a, b in combinations(CHARTS, 2)}
        by_pos[p]["n"] = len(cp)
    return {"n_common": len(common), "overall": matrix, "by_position": by_pos}


def avg_pos_ranks(values: dict, pos_of: dict) -> dict:
    """Rank at his position, 1 = best, with tied values sharing their average rank."""
    out = {}
    for p in POS:
        order = sorted((i for i in values if pos_of.get(i) == p), key=lambda i: (-values[i], i))
        n = 0
        while n < len(order):
            m = n
            while m + 1 < len(order) and values[order[m + 1]] == values[order[n]]:
                m += 1
            for j in range(n, m + 1):
                out[order[j]] = (n + m) / 2 + 1
            n = m + 1
    return out


def player_rows(inp) -> tuple[list, dict]:
    """Top TRADE_POOL players by DDF Value at half PPR / 12 teams, with each
    chart's number as a percent of that chart's own #1 player (the article
    publishes derived measures, not the charts' tables) and his rank at his
    position on each chart (ties share their average rank)."""
    s = setting(inp)
    diag = s.diagnostics()
    pos_of = s.pos_of
    nat = {k: s.natives(k) for k in CHARTS}
    top = {k: max(nat[k].values()) for k in CHARTS}
    pos_rank = {k: avg_pos_ranks(nat[k], pos_of) for k in CHARTS}
    waiver = {k: {p: diag["sources"][k]["positions"][p]["waiver"] for p in POS} for k in CHARTS}
    ddf = ddf_values(s)
    ranked = sorted(ddf, key=lambda i: (-ddf[i], i))[:TRADE_POOL]
    rows = []
    for i in ranked:
        rows.append({"key": i, "name": inp.players[i]["name"], "pos": pos_of[i], "ddf": r(ddf[i], 1),
                     "pct_of_top": {k: (r(100 * nat[k][i] / top[k], 4) if i in nat[k] else None) for k in CHARTS},
                     "pos_rank": {k: pos_rank[k].get(i) for k in CHARTS}})
    return rows, {k: {p: r(100 * waiver[k][p] / top[k], 4) for p in POS} for k in CHARTS}


def outliers(rows: list) -> list:
    """Largest gap between one chart's rank for a player at his position and
    the median rank the other three charts give him (all four must list him,
    and either rank must be inside the top OUTLIER_DEPTH).
    Ranks, not values, so a flat or steep curve cannot fake a disagreement."""
    out = []
    for row in rows:
        rk = row["pos_rank"]
        if any(rk[k] is None for k in CHARTS):
            continue
        for k in CHARTS:
            med = sorted(rk[o] for o in CHARTS if o != k)[1]
            if min(rk[k], med) > OUTLIER_DEPTH:
                continue
            out.append({"name": row["name"], "pos": row["pos"], "source": k, "rank": rk[k],
                        "others_median_rank": med, "gap": r(rk[k] - med, 1)})
    out.sort(key=lambda x: (-abs(x["gap"]), x["name"], x["source"]))
    return out


def fantasycalc_scoring_factors(inp) -> dict:
    """FantasyCalc Full PPR / Standard, per position, over the top SCORING_TOP:
    median ratio and the spread (max - min) of the ratio."""
    std, full = setting(inp, "standard"), setting(inp, "ppr")
    a, b = std.natives("fantasycalc"), full.natives("fantasycalc")
    out = {}
    for p in POS:
        common = sorted((i for i in a if i in b and std.pos_of.get(i) == p and a[i] > 0),
                        key=lambda i: (-b[i], i))[:SCORING_TOP]
        ratios = sorted(b[i] / a[i] for i in common)
        out[p] = {"n": len(ratios), "median_ratio": r(ratios[len(ratios) // 2], 3),
                  "spread": r(ratios[-1] - ratios[0], 3)}
    return out


def weekly(inp) -> dict:
    """Week-over-week change of each source's own numbers (half PPR), weeks 5-9.
    rank_move: mean absolute change in position rank of last week's top
    WEEKLY_TOP players at each position that are listed both weeks (scale-free).
    unchanged_pct: share of those players whose number is exactly the same."""
    docs = {w: json.loads((HISTORY_DIR / f"week-{w}.json").read_text(encoding="utf-8")) for w in WEEKS}
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    out = {}
    for k in CHARTS:
        dates, moves, unchanged = [], [], []
        prev = None
        for w in WEEKS:
            sec = docs[w]["sources"][k]
            dates.append(str(sec["_sort"][0])[:10])
            if vr.FAMILY[k] == "chart":
                cur = {int(x): v for x, v in sec["natives"]["half_ppr"].items()}
            else:
                cur = {int(x): v[HIST_INDEX["half_ppr"]] for x, v in sec["ppg"].items()
                       if v and v[HIST_INDEX["half_ppr"]]}
            cur = {i: v for i, v in cur.items() if pos_of.get(i) in POS}
            if prev is not None:
                deltas, same = [], 0
                for p in POS:
                    both = [i for i in prev if i in cur and pos_of[i] == p]
                    rank_prev = {i: n for n, i in enumerate(sorted(both, key=lambda i: (-prev[i], i)))}
                    rank_cur = {i: n for n, i in enumerate(sorted(both, key=lambda i: (-cur[i], i)))}
                    top = sorted(both, key=lambda i: (-prev[i], i))[:WEEKLY_TOP]
                    deltas += [abs(rank_cur[i] - rank_prev[i]) for i in top]
                    same += sum(1 for i in top if cur[i] == prev[i])
                moves.append(r(sum(deltas) / len(deltas), 2) if deltas else None)
                unchanged.append(r(100 * same / len(deltas), 0) if deltas else None)
            prev = cur
        out[k] = {"weeks": list(WEEKS), "snapshot_dates": dates,
                  "rank_move": moves, "unchanged_pct": unchanged}
    return out


# ---------------------------------------------------------------------------
# Scorecard (rules printed on the page)
# ---------------------------------------------------------------------------

RULES = {
    "balance": "Position mix vs DDF Value: share of value that would have to move between positions to match DDF Value's position budget, Half PPR, 12 teams. Close up to 5 points, OK up to 10, Far above 10. Distance from the reference describes a chart; it does not prove it right or wrong.",
    "scoring": "Scoring formats: compare Standard with Full PPR for the top 36 at RB, WR and TE. Strong when at least 20% of those players change places on average; OK when the numbers change but fewer change places; Weak when the numbers do not change. For scale: rankings by realized rest-of-season points (2015-2025, snapshot weeks 5-8) reorder about {realized}% of the same top 36 between the two formats.",
    "qb_sf": "QB share in superflex vs DDF Value: distance, in percentage points, between the chart's quarterback share of all value in a 12-team Half PPR superflex league and DDF Value's. Close up to 5, OK up to 10, Far above 10. Distance describes a chart; it does not prove it right or wrong.",
    "superflex": "Superflex coverage: Strong with superflex values for 24 or more QBs (two per team); OK with fewer; Weak with none.",
    "league_size": "League size: does the chart change its numbers when the number of teams changes (10, 12, 14)? Strong when it offers its numbers by team count; Weak with one table for every league size.",
    "depth": "Depth: how far down the chart's list goes compared with how many players a 12-team league rosters. None of the four charts states a roster size, so each is measured against the waiver line of a 12-team league with our lineup. For each position, the gap between players listed and players rostered, as a share of players rostered, counting stopping short and reaching past alike; averaged over the four positions. Strong up to 10%, OK up to 30%, Weak above 30%.",
    "curve": "Curve shape: average distance, in percentage points of each chart's own #1 player, between the chart's value curve and DDF Value's over overall ranks 1 to 100 (Half PPR). Close up to 5, OK up to 10, Far above 10. Distance from the reference describes a chart; it does not prove it right or wrong.",
    "freshness": "Weekly change: Strong when each of the four week-to-week changes in our saved weekly snapshots (weeks 5 to 9) is a distinct capture and moves last week's top 24 per position by at least a quarter of a rank on average; OK when one week did not; Weak otherwise.",
    "consolidation": "2-for-1 sense: the share of mid-tier pairs (ranks 25-60) that the raw chart says beat a top-12 player, minus the share once each player's waiver-level value is subtracted. Strong up to 10 points of difference, OK up to 25, Weak above 25.",
}
LEVEL = {3: "Strong", 2: "OK", 1: "Weak", None: "Not measured"}


def grade(x, strong, ok, higher_is_better=False):
    if x is None:
        return None
    if higher_is_better:
        return 3 if x >= strong else 2 if x >= ok else 1
    return 3 if x <= strong else 2 if x <= ok else 1


def scoring_level(sc_k):
    moved = [sc_k[p]["order_changed_pct"] or 0 for p in FLEX]
    changed = [sc_k[p]["changed_pct"] or 0 for p in FLEX]
    if sum(moved) / len(moved) >= 20:
        return 3
    return 2 if sum(changed) / len(changed) >= 50 else 1


def fresh_level(wk_k):
    moves = wk_k["rank_move"]
    weeks_ok = sum(1 for m in moves if m is not None and m >= 0.25)
    new_dates = len(set(wk_k["snapshot_dates"])) == len(WEEKS)
    if weeks_ok == len(moves) and new_dates:
        return 3, weeks_ok
    return (2 if weeks_ok >= len(moves) - 1 else 1), weeks_ok


def scorecard(meta, pw, sc, sfx, wk, cons, curves_half) -> dict:
    out = {}
    league_size_offered = {"fantasycalc"}  # its public values API takes numTeams (pipelines/pull_fantasycalc_12team.py)
    for k in CHARTS:
        gap = pw["half_ppr/12/1qb"]["gap_vs_ddf"][k]
        n_sf = sfx[k]["superflex_qbs_listed"]
        qb_gap = r(abs(sfx["ddf_value"]["qb_share_sf"] - sfx[k]["qb_share_sf"]), 1)
        depth = sum(abs(meta[k]["listed"][p] - meta[k]["rostered"][p]) / meta[k]["rostered"][p] for p in POS) / len(POS)
        cv, ref = curves_half[k], curves_half["ddf"]
        n = min(100, len(cv), len(ref))
        cdist = sum(abs(cv[i] - ref[i]) for i in range(n)) / n
        fl, fw = fresh_level(wk[k])
        cgap = cons[k]["raw_beats_star_pct"] - cons[k]["after_waiver_beats_star_pct"]
        out[k] = {
            "balance": {"level": grade(gap, 5, 10), "value": gap},
            "scoring": {"level": scoring_level(sc[k])},
            "superflex": {"level": 3 if n_sf >= 24 else 2 if n_sf > 0 else 1, "value": n_sf},
            "qb_sf": {"level": grade(qb_gap, 5, 10), "value": qb_gap},
            "league_size": {"level": 3 if k in league_size_offered else 1},
            "depth": {"level": grade(100 * depth, 10, 30), "value": r(100 * depth, 0)},
            "curve": {"level": grade(cdist, 5, 10), "value": r(cdist, 1)},
            "freshness": {"level": fl, "value": fw},
            "consolidation": {"level": grade(cgap, 10, 25), "value": r(cgap, 0)},
        }
    for k in out:
        for dim in out[k].values():
            dim["label"] = LEVEL[dim["level"]]
    return out





FC_DIR = REPO / "data" / "research" / "jeg1565" / "fantasycalc"
FC_RAW_WEEK4 = REPO / "data" / "raw" / "sources" / "fantasycalc" / "week-4" / "snapshot.json"


def _reorder(a: dict, b: dict, pos_of: dict) -> dict:
    """Top SCORING_TOP by Full PPR value at RB, WR and TE: how many change places
    between Standard (a) and Full PPR (b), and the spread of the Full/Standard ratio."""
    out = {}
    for p in FLEX:
        top = sorted((k for k in a if k in b and pos_of.get(k) == p and a[k] > 0), key=lambda k: (-b[k], k))[:SCORING_TOP]
        ratios = [b[k] / a[k] for k in top]
        oa, ob = sorted(top, key=lambda k: (-a[k], k)), sorted(top, key=lambda k: (-b[k], k))
        out[p] = {"n": len(top), "reordered": sum(1 for x, y in zip(oa, ob) if x != y),
                  "ratio_spread": r(max(ratios) - min(ratios), 3) if ratios else None}
    return out


def scoring_provenance(inp) -> dict:
    """Is a chart's Standard-vs-Full difference in the publisher's own output?
    FantasyCalc: one request per format (ppr=0 / ppr=1); every capture we hold.
    Charts: share of players whose Standard and Full PPR numbers are identical,
    per weekly snapshot (the as-published natives)."""
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    fc = []
    caps = json.loads((FC_DIR / "captures.json").read_text(encoding="utf-8"))
    for label in ("week 4 cache", "live pull"):
        side = {c["scoring"]: c for c in caps if c["label"] == label}
        a = {x["name"]: x["value"] for x in side["standard"]["rows"]}
        b = {x["name"]: x["value"] for x in side["full"]["rows"]}
        names = {x["name"]: x["pos"] for x in side["standard"]["rows"]}
        fc.append({"capture": label, "fetched_at": side["full"]["fetched_at"],
                   "urls": [side["standard"]["source_url"], side["full"]["source_url"]], **_reorder(a, b, names)})
    raw = json.loads(FC_RAW_WEEK4.read_text(encoding="utf-8"))
    a = {x["player_name"]: x["native_value"] for x in raw["rows"] if x["scoring"] == "standard"}
    b = {x["player_name"]: x["native_value"] for x in raw["rows"] if x["scoring"] == "ppr"}
    names = {x["player_name"]: x["pos"] for x in raw["rows"]}
    fc.append({"capture": "week 4 raw snapshot", "fetched_at": raw["fetched_at"], **_reorder(a, b, names)})
    identical = {}
    for w in WEEKS:
        doc = json.loads((HISTORY_DIR / f"week-{w}.json").read_text(encoding="utf-8"))
        for k in CHARTS:
            n = doc["sources"][k]["natives"]
            a = {int(x): v for x, v in n["standard"].items()}
            b = {int(x): v for x, v in n["ppr"].items()}
            common = [x for x in a if x in b]
            identical.setdefault(k, []).append(r(100 * sum(1 for x in common if a[x] == b[x]) / len(common), 0))
            if k == "fantasycalc":
                fc.append({"capture": f"week {w} snapshot", "fetched_at": str(doc["sources"][k]["_sort"][0]),
                           **_reorder(a, b, pos_of)})
    order = {"week 4 cache": 0, "week 4 raw snapshot": 1, "live pull": 99}
    fc.sort(key=lambda x: (order.get(x["capture"], 50), x["capture"]))
    reordered = [sum(x[p]["reordered"] for p in FLEX) for x in fc]
    return {"fantasycalc_captures": fc, "identical_std_vs_ppr_pct_by_week": identical,
            "fantasycalc_captures_with_reorder": sum(1 for v in reordered if v > 0),
            "fantasycalc_captures_total": len(fc)}


DEPTH_TEAMS = (10, 12, 14)
DEPTH_CURVE_MAX = 130   # position ranks drawn in the depth chart


def depth_class(listed: int, rostered: int) -> str:
    """Where a list ends against the waiver line (the first player past the
    league's rostered count): within max(2, 10% of rostered) is near."""
    tol = max(2, round(0.1 * rostered))
    if listed < rostered - tol:
        return "short"
    if listed > rostered + tol:
        return "past"
    return "near"


def depth_vs_waiver(inp, data: dict) -> dict:
    """Each source's list against the waiver line, per position, at 10/12/14
    teams (Half PPR, our default lineup). The waiver line at a position is the
    value of the first player past the number the league rosters there (VP-2)."""
    out = {"teams": list(DEPTH_TEAMS), "rostered": {}, "sources": {}}
    keys = CHARTS
    for t in DEPTH_TEAMS:
        s = setting(inp, "half_ppr", t)
        diag = s.diagnostics()
        pos_of = s.pos_of
        out["rostered"][t] = {p: diag["sources"]["cbs"]["positions"][p]["rostered"] for p in POS}
        # The pie for under-allocation: DDF Value of the players the league rosters (top N at each
        # position by DDF Value, N = rostered count). A chart's unpriced value = DDF Value of those
        # rostered players it does not list.
        ddf = ddf_values(s)
        ros_set = {p: sorted((i for i in ddf if pos_of.get(i) == p), key=lambda i: (-ddf[i], i))[:out["rostered"][t][p]]
                   for p in POS}
        ddf_pie = sum(max(0.0, ddf[i]) for p in POS for i in ros_set[p])
        out.setdefault("ddf_pie", {})[t] = r(ddf_pie, 1)
        for k in keys:
            nat = s.natives(k)
            row = out["sources"].setdefault(k, {}).setdefault(t, {})
            total = sum(nat.values())
            past_value = 0.0
            miss_value, miss_n = 0.0, 0
            for p in POS:
                order = sorted((i for i in nat if pos_of.get(i) == p), key=lambda i: (-nat[i], i))
                ros = out["rostered"][t][p]
                waiver = diag["sources"][k]["positions"][p]["waiver"]
                top = nat[order[0]]
                last = order[-1]
                beyond = order[ros:]
                past_value += sum(nat[i] for i in beyond)
                missing = [i for i in ros_set[p] if i not in nat]
                mv = sum(max(0.0, ddf[i]) for i in missing)
                miss_value += mv
                miss_n += len(missing)
                row[p] = {"listed": len(order), "rostered": ros, "gap": len(order) - ros,
                          "unpriced": max(0, ros - len(order)), "beyond": max(0, len(order) - ros),
                          "class": depth_class(len(order), ros),
                          "last_name": inp.players[last]["name"],
                          "last_pct_of_top": r(100 * nat[last] / top, 1),
                          "waiver_pct_of_top": r(100 * waiver / top, 1),
                          "unpriced_players_pct": r(100 * len(missing) / ros, 0),
                          "unpriced_value_pct": r(100 * mv / ddf_pie, 1),
                          "past_value_pct": r(100 * sum(nat[i] for i in beyond) / total, 1)}
                if t == 12:
                    row[p]["curve"] = [r(100 * nat[i] / top, 1) for i in order[:DEPTH_CURVE_MAX]]
            row["value_past_line_pct"] = r(100 * past_value / total, 1)
            row["unpriced_value_pct"] = r(100 * miss_value / ddf_pie, 1)
            row["unpriced_players_pct"] = r(100 * miss_n / sum(out["rostered"][t].values()), 0)
    out["filled_in_12"] = {k: sum(data["sources"][k]["filled_in"].values()) for k in CHARTS}
    return out


def ddf_reference(inp, data: dict) -> dict:
    """DDF Value as the reference line: how far its order moves with scoring.
    It is the charts' weighted, adjusted average, so it is never graded."""
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    a, b = ddf_values(setting(inp, "standard")), ddf_values(setting(inp, "ppr"))
    reo = _reorder(a, b, pos_of)
    moved = sum(reo[p]["reordered"] / reo[p]["n"] for p in FLEX) / 3 * 100
    return {"reorder_avg_pct": r(moved, 0)}

def should_be(inp, data: dict) -> dict:
    """Reference numbers for the five headline findings. Where a number is DDF Value,
    it is the league-aware consensus of the same charts, not an independent truth."""
    h, sfx = data["headline"], data["superflex"]
    return {
        "scoring_columns_reorder_min": min(h["reorder_avg_pct"]["cbs"], h["reorder_avg_pct"]["usatoday"]),
        "scoring_columns_reorder_max": max(h["reorder_avg_pct"]["cbs"], h["reorder_avg_pct"]["usatoday"]),
        "scoring_ddf_reorder": data["ddf_reference"]["reorder_avg_pct"],
        "pairs_ddf": h["pairs_after_waiver"]["ddf"],
        "pairs_gap_fantasypros": r(h["pairs_after_waiver"]["fantasypros"] - h["pairs_after_waiver"]["ddf"], 0),
        "pairs_gap_usatoday": r(h["pairs_after_waiver"]["usatoday"] - h["pairs_after_waiver"]["ddf"], 0),
        "superflex_ddf_qb": sfx["ddf_value"]["qb_share_sf"],
        "superflex_gap": {k: r(sfx["ddf_value"]["qb_share_sf"] - sfx[k]["qb_share_sf"], 1) for k in CHARTS},
        "te_ddf_pct": h["top_te_pct"]["ddf"],
        "te_gap": h["top_te_gap_vs_ddf"],
    }

# Public pages a reader can open to check the article (JEG-1565). Checked by
# pipelines/check_trade_value_audit_links.py; results in data/research/jeg1565/link-check.json.
LINKS_READ = "2026-11-07"
SOURCE_LINKS = [
    {"source": "CBS Sports", "label": "CBS Sports week 9 trade chart (Dave Richard)", "kind": "chart",
     "url": "https://www.cbssports.com/fantasy/football/news/dave-richards-week-9-fantasy-football-trade-chart-rest-of-season-rankings/"},
    {"source": "USA Today", "label": "USA Today week 9 trade value charts", "kind": "chart",
     "url": "https://www.usatoday.com/story/sports/fantasy/football/2026/11/03/fantasy-trade-value-charts-week-9-ros-rankings/92593100007/"},
    {"source": "FantasyPros", "label": "FantasyPros trade value chart, week 9", "kind": "chart",
     "url": "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-9-2026/"},
    {"source": "FantasyPros", "label": "FantasyPros legal terms", "kind": "terms",
     "url": "https://www.fantasypros.com/about/legal/"},
    {"source": "FantasyCalc", "label": "FantasyCalc trade value chart", "kind": "chart",
     "url": "https://fantasycalc.com/trade-value-chart"},
    {"source": "FantasyCalc", "label": "FantasyCalc values, Standard (raw data: ppr=0)", "kind": "endpoint",
     "url": "https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1&numTeams=12&ppr=0"},
    {"source": "FantasyCalc", "label": "FantasyCalc values, Full PPR (raw data: ppr=1)", "kind": "endpoint",
     "url": "https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1&numTeams=12&ppr=1"},
    {"source": "KeepTradeCut", "label": "KeepTradeCut: how player values work", "kind": "method",
     "url": "https://keeptradecut.com/about/player-values"},
    {"source": "KeepTradeCut", "label": "KeepTradeCut terms and conditions", "kind": "terms",
     "url": "https://keeptradecut.com/terms-and-conditions"},
    {"source": "Footballguys", "label": "Footballguys dynasty trade value chart (June 2026)", "kind": "chart",
     "url": "https://www.footballguys.com/article/2026-dynasty-trade-value-chart-june"},
    {"source": "Footballguys", "label": "Footballguys terms of service", "kind": "terms",
     "url": "https://www.footballguys.com/terms"},
    {"source": "Draft Sharks", "label": "Draft Sharks dynasty trade value charts", "kind": "chart",
     "url": "https://www.draftsharks.com/article/dynasty-trade-value-charts"},
    {"source": "Dynasty Nerds", "label": "Dynasty Nerds home page (no method or data terms found)", "kind": "home",
     "url": "https://dynastynerds.com/"},
]


def replacement_qb(inp) -> dict:
    """The first quarterback past the league's rostered count, by projected Half PPR
    points per game (players.json blend_ppg, the model's projection input), in a
    one-QB and a superflex 12-team league."""
    players = json.loads((REPO / "data" / "fixtures" / "current" / "players.json").read_text(encoding="utf-8"))["players"]
    qbs = sorted((p for p in players if p.get("pos") == "QB" and (p.get("blend_ppg") or {}).get("half_ppr")),
                 key=lambda p: (-p["blend_ppg"]["half_ppr"], p["player_key"]))
    out = {}
    for label, sf in (("one_qb", 0), ("superflex", 1)):
        diag = setting(inp, "half_ppr", 12, sf).diagnostics()
        ros = diag["sources"]["cbs"]["positions"]["QB"]["rostered"]
        rep = qbs[ros]
        out[label] = {"rostered": ros, "rank": ros + 1, "name": rep["name"], "ppg": r(rep["blend_ppg"]["half_ppr"], 1),
                      "nfl_depth": rep.get("depth_chart_order")}
    return out


ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
BENCH_WEEKS = (5, 6, 7, 8)


def realized_scoring_benchmark() -> dict:
    """How much a ranking by realized rest-of-season fantasy points reorders between
    Standard and Full PPR: for each season 2015-2025 and snapshot week w in 5-8, sum
    each player's points from week w to the season's last regular week, take the top
    SCORING_TOP RB/WR/TE by Full PPR points, and count how many change places within
    their position when the same players are ranked by Standard points (the page's
    reorder rule); average over the three positions."""
    import csv
    import gzip
    pts = {}
    last = {}
    with gzip.open(ACTUALS, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["pos"] not in FLEX:
                continue
            season, week = int(row["season"]), int(row["week"])
            last[season] = max(last.get(season, 0), week)
            key = (season, row["player_id"], row["pos"])
            pts.setdefault(key, []).append((week, float(row["std"] or 0), float(row["ppr"] or 0)))
    cells = []
    by_season = {}
    for season in sorted(last):
        for w in BENCH_WEEKS:
            moved = []
            for p in FLEX:
                tot = {}
                for (s_, pid, pos), weeks in pts.items():
                    if s_ != season or pos != p:
                        continue
                    std = sum(x[1] for x in weeks if x[0] >= w)
                    ppr = sum(x[2] for x in weeks if x[0] >= w)
                    if ppr > 0:
                        tot[pid] = (std, ppr)
                top = sorted(tot, key=lambda i: (-tot[i][1], i))[:SCORING_TOP]
                oa = sorted(top, key=lambda i: (-tot[i][0], i))
                ob = sorted(top, key=lambda i: (-tot[i][1], i))
                moved.append(100 * sum(1 for x, y in zip(oa, ob) if x != y) / len(top))
            cell = sum(moved) / len(moved)
            cells.append(cell)
            by_season.setdefault(season, []).append(cell)
    seasons = {s_: r(sum(v) / len(v), 0) for s_, v in by_season.items()}
    return {"seasons": seasons, "pooled": r(sum(cells) / len(cells), 0),
            "min": r(min(cells), 0), "max": r(max(cells), 0),
            "season_min": min(seasons.values()), "season_max": max(seasons.values()),
            "first_season": min(seasons), "last_season": max(seasons), "weeks": list(BENCH_WEEKS)}


def headline(d: dict) -> dict:
    """The numbers the article quotes in its text, gathered in one place.
    The yardstick everywhere is DDF Value (the reference), never a participant."""
    sc, pw, sfx, cons, cs = d["scoring"], d["position_weighting"], d["superflex"], d["consolidation"], d["curve_stats"]
    reorder = {k: r(sum(sc[k][p]["order_changed_pct"] for p in FLEX) / 3, 0) for k in sc}
    sf_chart_qb = [sfx[k]["qb_share_sf"] for k in CHARTS]
    base = pw["half_ppr/12/1qb"]
    wr_tilt = {k: r(base["sources"][k]["WR"] - base["ddf_value"]["WR"], 1) for k in CHARTS}
    rb_tilt = {k: r(base["sources"][k]["RB"] - base["ddf_value"]["RB"], 1) for k in CHARTS}
    return {
        "reorder_avg_pct": reorder,
        "fantasypros_numbers_changed_pct": max(sc["fantasypros"][p]["changed_pct"] for p in POS),
        "fantasycalc_top_flex_reordered": sum(round(sc["fantasycalc"][p]["order_changed_pct"] * sc["fantasycalc"][p]["n"] / 100)
                                              for p in FLEX),
        "fantasycalc_top_flex_compared": sum(sc["fantasycalc"][p]["n"] for p in FLEX),
        "superflex_chart_qb_min": min(sf_chart_qb), "superflex_chart_qb_max": max(sf_chart_qb),
        "superflex_ddf_qb": sfx["ddf_value"]["qb_share_sf"],
        "superflex_chart_mean_qb": r(sum(sf_chart_qb) / len(sf_chart_qb), 1),
        "superflex_chart_spread": r(max(sf_chart_qb) - min(sf_chart_qb), 1),
        "superflex_chart_mean_1qb": r(sum(sfx[k]["qb_share_1qb"] for k in CHARTS) / len(CHARTS), 1),
        "unpriced_cbs_12": sum(d["depth_vs_waiver"]["sources"]["cbs"][12][p]["unpriced"] for p in POS),
        "superflex_cbs_gap": r(sfx["ddf_value"]["qb_share_sf"] - sfx["cbs"]["qb_share_sf"], 1),
        "wr_tilt_vs_ddf": wr_tilt, "rb_tilt_vs_ddf": rb_tilt,
        "pairs_raw": {k: cons[k]["raw_beats_star_pct"] for k in CHARTS},
        "pairs_after_waiver": {k: cons[k]["after_waiver_beats_star_pct"] for k in (*CHARTS, "ddf")},
        "top_te_pct": {k: cs[k]["position_top_pct"]["TE"] for k in (*CHARTS, "ddf")},
        "top_te_gap_vs_ddf": {k: r(cs[k]["position_top_pct"]["TE"] - cs["ddf"]["position_top_pct"]["TE"], 0) for k in CHARTS},
        "rank24_pct": {k: cs[k]["rank24_pct"] for k in (*CHARTS, "ddf")},
        "agreement_min": min(d["agreement"]["overall"].values()),
        "agreement_max": max(d["agreement"]["overall"].values()),
        "superflex_qbs_min": min(sfx[k]["superflex_qbs_listed"] for k in CHARTS),
        "superflex_qbs_max": max(sfx[k]["superflex_qbs_listed"] for k in CHARTS),
        "filled_in_total": {k: sum(d["sources"][k]["filled_in"].values()) for k in CHARTS},
        "usatoday_hold": d["sources"]["usatoday"]["hold_level"],
        "reorder_chart_spread": max(reorder[k] for k in CHARTS) - min(reorder[k] for k in CHARTS),
        "reorder_cbs_usatoday_gap": abs(reorder["usatoday"] - reorder["cbs"]),
        "reorder_half_gap": abs(reorder["usatoday"] - reorder["cbs"]) / 2,
    }


def build() -> dict:
    inp = load()
    base = setting(inp)
    base_diag = base.diagnostics()
    meta = source_meta(inp, base_diag)
    pw = position_weighting(inp)
    sc = scoring_awareness(inp)
    sfx = superflex(inp, pw)
    cv = curves(inp)
    cons = consolidation(inp)
    rows, waiver = player_rows(inp)
    outl = outliers(rows)
    wk = weekly(inp)
    data = {
        "generated_by": "pipelines/research_trade_value_audit.py",
        "ticket": "JEG-1565",
        "fixture_built_at": inp.fixture.get("built_at"),
        "content_week": vr.freshness(inp)["current_week"],
        "base_setting": {**BASE, "roster": vr.roster(0)},
        "pie": base_diag["pie"],
        "ddf_value_inputs": [k for k in base.state()["included"]
                             if vr.FAMILY[k] == "chart" and k not in (base.state().get("hidden") or set())],
        "sources": meta,
        "position_weighting": pw,
        "top50_mix": top_mix(inp, base),
        "scoring": sc,
        "superflex": sfx,
        "curves": cv["curves"],
        "curve_players": cv["curve_players"],
        "curve_stats": cv["stats"],
        "consolidation": cons,
        "agreement": agreement(inp),
        "players": rows,
        "waiver_line": waiver,
        "outliers": outl[:24],
        "fantasycalc_scoring_factors": fantasycalc_scoring_factors(inp),
        "weekly": wk,
        "scorecard": scorecard(meta, pw, sc, sfx, wk, cons, cv["curves"]["half_ppr"]),
        "rules": RULES,
    }
    lineup = json.loads((REPO / "config" / "lineup_parameters.json").read_text(encoding="utf-8"))
    data["model_missed_game_rate_pct"] = {p: r(100 * lineup["positions"][p]["m"]["all"], 1) for p in POS}
    data["scoring_provenance"] = scoring_provenance(inp)
    data["depth_vs_waiver"] = depth_vs_waiver(inp, data)
    data["ddf_reference"] = ddf_reference(inp, data)
    data["headline"] = headline(data)
    cbs_top = max(setting(inp).natives("cbs").values())
    data["cbs_four_points_pct"] = r(100 * 4 / cbs_top, 1)
    data["source_links"] = {"read": LINKS_READ, "links": SOURCE_LINKS}
    data["should_be"] = should_be(inp, data)
    data["replacement_qb"] = replacement_qb(inp)
    data["realized_scoring"] = realized_scoring_benchmark()
    data["rules"] = {**data["rules"], "scoring": data["rules"]["scoring"].format(realized=int(data["realized_scoring"]["pooled"]))}
    data["cbs_waiver_rb_pct"] = r(data["waiver_line"]["cbs"]["RB"], 1)
    data["bench_weight"] = bench_weight(inp)
    data["ddf_mix_vs_chart_mean"] = ddf_mix_vs_chart_mean(data)
    return data


def bench_weight(inp) -> dict:
    """How much of each chart's value above the waiver line goes to players who would sit on a
    12-team bench (ranks past the starters, up to the rostered count; default lineup, Half PPR),
    taken at face value, against the share those same players deliver once each player's value
    is weighted by his expected starts (ES-5 parts: missed-game rates 2015-2025, byes and
    projection spread from config/lineup_parameters.json; methodology ES-1, ES-5, ES-14)."""
    res = setting(inp).result()
    out = {}
    for k in CHARTS:
        rows = [row for row in res["sources"][k]["players"].values() if row["role"] != "waiver"]
        face = sum(row["vorp"] for row in rows)
        face_bench = sum(row["vorp"] for row in rows if row["role"] == "bench")
        lineup = sum(row["bench_slice"] + row["starter_slice"] for row in rows)
        lineup_bench = sum(row["bench_slice"] + row["starter_slice"] for row in rows if row["role"] == "bench")
        face_pct, es_pct = 100 * face_bench / face, 100 * lineup_bench / lineup
        out[k] = {"face_pct": r(face_pct, 1), "expected_starts_pct": r(es_pct, 1),
                  "ratio": r(face_pct / es_pct, 1),
                  "filled_in_players": sum(1 for row in rows if row["imputed"])}
    ratios = [out[k]["ratio"] for k in CHARTS]
    out["ratio_min"], out["ratio_max"] = min(ratios), max(ratios)
    out["all_over"] = all(out[k]["face_pct"] > out[k]["expected_starts_pct"] for k in CHARTS)
    out["ddf_readout_pct"] = r(100 * res["bench_share_readout"]["overall"], 1)
    return out


def ddf_mix_vs_chart_mean(data: dict) -> dict:
    """VP-4: DDF Value's position mix is the mean of the included charts' own position mixes
    (value above the waiver line). The largest gap, in percentage points, between DDF Value's
    share and the plain mean of the four charts' shares, over the figure's four settings."""
    gaps = []
    for case in data["position_weighting"].values():
        for p in POS:
            mean4 = sum(case["sources"][k][p] for k in CHARTS) / len(CHARTS)
            gaps.append(abs(case["ddf_value"][p] - mean4))
    return {"max_gap_pts": r(max(gaps), 2)}


def dump(data: dict) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = dump(build())
    if args.check:
        same = args.out.exists() and args.out.read_text(encoding="utf-8") == text
        print("up to date" if same else f"stale: {args.out}")
        return 0 if same else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
