"""JEG-1610 step 5: each player's own history mix (std_h, rec_h) and the
labelled position-level fallback.

Spec: docs/research/jeg1610/preregistration.md section 1 step 5 (binding).
Research only; reads data/inputs and the read-only Supabase cache in cache/.

rec_h = mean(ppr - std) over game rows, std_h = mean(std); seasons 2024, 2025
and 2026 weeks 1 .. w - 1 (w = snapshot week); minimum 6 games.
"""
from __future__ import annotations

import csv
import gzip
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
NFLVERSE = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
IDMAP = REPO / "data" / "inputs" / "sleeper_projection_idmap.csv"
PGS_CACHE = HERE / "cache" / "player_game_stats_2024_2026.json"

MIN_GAMES = 6
CURRENT_SEASON = 2026
WINDOWS = ("primary", "2026_only", "2015_2026")
REASONS = ("rookie_no_rows", "under_6_games", "no_key", "nonpositive_anchor_points")


# ---------------------------------------------------------------------------
# Game rows
# ---------------------------------------------------------------------------

def load_rows(path: Path = ACTUALS) -> list:
    """[(season, week, player_key, std, rec)] from weekly_actuals_2024_2026.csv."""
    out = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            std, ppr = float(r["std"] or 0), float(r["ppr"] or 0)
            out.append((int(r["season"]), int(r["week"]), int(r["player_key"]), std, ppr - std))
    return out


def load_idmap(path: Path = IDMAP) -> dict:
    """{gsis_id: player_key}; rows with a player_key only; a gsis_id mapped to
    two keys is dropped (ambiguous)."""
    seen = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            g, k = (r.get("gsis_id") or "").strip(), (r.get("player_key") or "").strip()
            if not g or not k.isdigit():
                continue
            seen.setdefault(g, set()).add(int(k))
    return {g: next(iter(ks)) for g, ks in seen.items() if len(ks) == 1}


def load_nflverse_rows(idmap: dict, path: Path = NFLVERSE, seasons=range(2015, 2024)) -> tuple[list, dict]:
    """Rows of seasons 2015-2023 mapped to player_key, and counts of unmapped rows."""
    out, unmapped = [], {"rows": 0, "players": set()}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = int(r["season"])
            if s not in seasons:
                continue
            k = idmap.get(r["player_id"])
            if k is None:
                unmapped["rows"] += 1
                unmapped["players"].add(r["player_id"])
                continue
            std, ppr = float(r["std"] or 0), float(r["ppr"] or 0)
            out.append((s, int(r["week"]), k, std, ppr - std))
    return out, {"rows": unmapped["rows"], "players": len(unmapped["players"])}


def window_rows(rows: list, w: int, window: str = "primary", old_rows: list | None = None) -> list:
    """Rows inside the history window of snapshot week w."""
    cur = [r for r in rows if r[0] == CURRENT_SEASON and 1 <= r[1] <= w - 1]
    if window == "2026_only":
        return cur
    prior = [r for r in rows if r[0] in (2024, 2025)]
    if window == "primary":
        return prior + cur
    if window == "2015_2026":
        return list(old_rows or []) + prior + cur
    raise ValueError(window)


# ---------------------------------------------------------------------------
# Mix
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Mix:
    std: float | None       # std_h (per game), None on fallback without rows
    rec: float | None       # rec_h
    games: int
    basis: str              # "history" or "fallback"
    reason: str | None      # fallback reason (REASONS) or None


def player_stats(rows: list) -> dict:
    """{key: (games, std_h, rec_h)} from window rows (pure)."""
    acc = {}
    for _s, _w, k, std, rec in rows:
        a = acc.setdefault(k, [0, 0.0, 0.0])
        a[0] += 1
        a[1] += std
        a[2] += rec
    return {k: (n, s / n, r / n) for k, (n, s, r) in acc.items()}


def history_mix(stats: dict, key: int, r_s0: float, has_key: bool = True) -> Mix:
    """Step 5: own mix, or a labelled fallback."""
    if not has_key:
        return Mix(None, None, 0, "fallback", "no_key")
    got = stats.get(key)
    if got is None:
        return Mix(None, None, 0, "fallback", "rookie_no_rows")
    n, std, rec = got
    if n < MIN_GAMES:
        return Mix(std, rec, n, "fallback", "under_6_games")
    if std + r_s0 * rec <= 0:
        return Mix(std, rec, n, "fallback", "nonpositive_anchor_points")
    return Mix(std, rec, n, "history", None)


def position_share(mixes: dict, keys, pos_of: dict, pos: str) -> float | None:
    """q_p: median rec_h / (std_h + rec_h) over the chart-week's priced players
    at pos with a history mix (basis == "history")."""
    sh = []
    for k in keys:
        m = mixes.get(k)
        if pos_of.get(k) != pos or m is None or m.basis != "history":
            continue
        d = m.std + m.rec
        if d != 0:
            sh.append(m.rec / d)
    return statistics.median(sh) if sh else None


def own_ratio(m: Mix, r_s: float, r_s0: float) -> float:
    """(std_h + r_s rec_h) / (std_h + r_s0 rec_h) = P_i(s) / P_i(s0)."""
    return (m.std + r_s * m.rec) / (m.std + r_s0 * m.rec)


def fallback_ratio(q: float, r_s: float, r_s0: float) -> float:
    return (1.0 - q * (1.0 - r_s)) / (1.0 - q * (1.0 - r_s0))


# ---------------------------------------------------------------------------
# Category cache (display and coverage only)
# ---------------------------------------------------------------------------

def load_categories(path: Path = PGS_CACHE) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    cols = doc["cols"]
    tot = {}
    for row in doc["totals"]:
        d = dict(zip(cols, row))
        tot[(int(d["player_key"]), int(d["season"]))] = {c: float(d[c]) for c in cols[2:]}
    return {"totals": tot, "week_rows": [tuple(r) for r in doc["week_rows"]]}


def category_std_points(c: dict) -> float:
    """Standard points from the category totals (fumbles lost -2)."""
    return (0.04 * c["pass_yds"] + 4 * c["pass_td"] - 2 * c["int"] + 0.1 * c["rush_yds"] + 6 * c["rush_td"]
            + 0.1 * c["rec_yds"] + 6 * c["rec_td"] - 2 * c["fumbles_lost"])


def rec_match_report(rows: list, cats: dict) -> dict:
    """How well player_game_stats receptions match sum(ppr - std) per player-season."""
    by = {}
    for s, _w, k, std, rec in rows:
        a = by.setdefault((k, s), [0, 0.0, 0.0])
        a[0] += 1
        a[1] += rec
        a[2] += std
    out = {}
    for season in (2024, 2025, 2026):
        keys = [ks for ks in by if ks[1] == season]
        both = [ks for ks in keys if ks in cats["totals"]]
        rec_d = [abs(cats["totals"][ks]["rec"] - by[ks][1]) for ks in both]
        std_d = [abs(category_std_points(cats["totals"][ks]) - by[ks][2]) for ks in both]
        games_eq = sum(int(cats["totals"][ks]["games"]) == by[ks][0] for ks in both)
        out[season] = {
            "player_seasons_actuals": len(keys), "in_category_table": len(both),
            "rec_exact": sum(d < 1e-6 for d in rec_d), "rec_within_1": sum(d <= 1 for d in rec_d),
            "rec_median_abs_diff": statistics.median(rec_d) if rec_d else None,
            "rec_max_abs_diff": max(rec_d) if rec_d else None,
            "std_points_within_1": sum(d <= 1 for d in std_d),
            "std_points_median_abs_diff": statistics.median(std_d) if std_d else None,
            "games_equal": games_eq,
        }
    return out


def per_game_categories(cats: dict, key: int, seasons=(2024, 2025, 2026)) -> dict | None:
    """Per-game category means over the cached seasons (display only)."""
    rows = [cats["totals"][(key, s)] for s in seasons if (key, s) in cats["totals"]]
    g = sum(r["games"] for r in rows)
    if not g:
        return None
    return {c: sum(r[c] for r in rows) / g for c in rows[0] if c != "games"} | {"games": g}
