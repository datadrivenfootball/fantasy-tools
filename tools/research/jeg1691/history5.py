"""JEG-1691 v5: per-game stat history from the read-only cache (fetch_history.py).

Rows are kept only for keyed players (player_key from projection_snapshots); the
count of unkeyed rows with stats is reported. Time order = (season, week).
"""
from __future__ import annotations

import gzip
import json
import statistics
from pathlib import Path

import mix as mx

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / "pgs_weekly_2024_2026.json.gz"
QUALIFY_FRACTION = 0.8   # amendment 2: nonzero rows >= 80% of 2026 weeks 1-4 median


def load(path: Path = CACHE) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        d = json.load(f)
    cols = d["cols"]
    ix = {c: i for i, c in enumerate(cols)}
    by_player, unkeyed, nonzero = {}, 0, {}
    for r in d["rows"]:
        line = {mx.PGS_KEY[k]: float(r[ix[k]]) for k in mx.PGS_KEY}
        line["targets"] = float(r[ix["targets"]])
        sw = (int(r[ix["season"]]), int(r[ix["week"]]))
        has = mx.game_has_stats(line)
        if has:
            nonzero[sw] = nonzero.get(sw, 0) + 1
        if r[ix["player_key"]] is None:
            unkeyed += has
            continue
        by_player.setdefault(int(r[ix["player_key"]]), []).append((sw, line))
    for v in by_player.values():
        v.sort(key=lambda x: x[0])
    return {"by_player": by_player, "meta": d["meta"], "unkeyed_rows_with_stats": unkeyed,
            "nonzero_rows": nonzero}


def qualifying_2026_weeks(nonzero: dict) -> list:
    base = statistics.median(nonzero.get((2026, w), 0) for w in (1, 2, 3, 4))
    return [w for w in range(1, 19) if nonzero.get((2026, w), 0) >= QUALIFY_FRACTION * base]


def before(rows: list, sw: tuple) -> list:
    """Game lines strictly before (season, week) sw, oldest first."""
    return [ln for t, ln in rows if t < sw]


def window(rows: list, season: int, w0: int, w1: int) -> list:
    return [ln for (s, w), ln in rows if s == season and w0 <= w <= w1]
