"""JEG-1691 v5: fetch the per-game stat history (step 5, T1) into a read-only cache.

Reads public.player_game_stats and public.games through the project's REST API
with the publishable (anon) key, which both tables grant SELECT to. Maps the
players' uuid to player_key through public.projection_snapshots (anon-readable),
because public.players is not readable by anon. Players with no
projection_snapshots row are kept under their uuid (no player_key) and counted.

The key is read from the environment (JEG1691_SUPABASE_KEY); it is never
written to the repo. Research only: SELECTs, no writes.

Out: cache/pgs_weekly_2024_2026.json.gz
  {"meta": {...}, "cols": [...], "rows": [[season, week, player_key|null, uuid6, cat...]]}
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "cache" / "pgs_weekly_2024_2026.json.gz"
URL = "https://iskiybsimubiujwuchsl.supabase.co/rest/v1"
PAGE = 1000

# nflverse key names used by player_game_stats.stats
STAT_KEYS = ("passing_yards", "passing_tds", "interceptions", "rushing_yards", "rushing_tds",
             "receptions", "receiving_yards", "receiving_tds", "targets")


def get_all(path: str, key: str, order: str) -> list:
    out, start = [], 0
    while True:
        req = urllib.request.Request(f"{URL}/{path}&order={order}", headers={
            "apikey": key, "Authorization": f"Bearer {key}",
            "Range-Unit": "items", "Range": f"{start}-{start + PAGE - 1}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.loads(r.read())
        out.extend(page)
        if len(page) < PAGE:
            return out
        start += PAGE
        time.sleep(0.05)


def main() -> None:
    key = os.environ.get("JEG1691_SUPABASE_KEY")
    if not key:
        sys.exit("set JEG1691_SUPABASE_KEY (the project's publishable key)")
    games = {g["id"]: (g["season"], g["week"]) for g in get_all("games?select=id,season,week", key, "id")}
    pmap = {}
    for r in get_all("projection_snapshots?select=player_id,player_key", key, "id"):
        if r.get("player_id") and r.get("player_key") is not None:
            pmap.setdefault(r["player_id"], set()).add(int(r["player_key"]))
    pmap = {u: next(iter(ks)) for u, ks in pmap.items() if len(ks) == 1}
    rows, unmapped, ambiguous_games = [], set(), 0
    for r in get_all("player_game_stats?select=id,player_id,game_id,stats", key, "id"):
        sw = games.get(r["game_id"])
        if sw is None:
            ambiguous_games += 1
            continue
        st = r.get("stats") or {}
        vals = [float(st.get(k) or 0.0) for k in STAT_KEYS]
        pk = pmap.get(r["player_id"])
        if pk is None:
            unmapped.add(r["player_id"])
        rows.append([sw[0], sw[1], pk, r["player_id"][:8], *vals, st.get("source") or "nflverse"])
    rows.sort(key=lambda x: (x[0], x[1], x[2] if x[2] is not None else -1, x[3]))
    meta = {"fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project": "iskiybsimubiujwuchsl", "read_only": True,
            "tables": "player_game_stats x games (anon REST); uuid->player_key via projection_snapshots",
            "n_rows": len(rows), "n_games": len(games), "rows_without_game": ambiguous_games,
            "players_without_key": len(unmapped)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump({"meta": meta, "cols": ["season", "week", "player_key", "uuid8", *STAT_KEYS, "source"],
                   "rows": rows}, f, separators=(",", ":"))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
