"""Weekly projection warehouse rows (JEG-1641). Pure functions, no network.

Builds rows for the append-only tables of
supabase/migrations/jeg1641_weekly_projection_warehouse_20261114.sql:

  source_weekly_projections   one row per run x source x player x target week
  source_projection_runs      one row per run x source (written last)
  nflverse_schedule_snapshots the season's nflverse games.csv rows, every run
  nflverse_injury_snapshots   the latest report week, QB/RB/WR/TE

Storage only: nothing here prices, blends or fills anything. A number the
source does not give is None, never 0 (docs/weekly-inputs-contract.md), and
there are no ROS rows (Jeremy 2026-10-29). Identity: the source's own id is
always kept; player_key is None when unresolved and the row is still stored.
What is stored and example queries: docs/weekly-projection-warehouse.md.
"""
from __future__ import annotations

import csv
import io
from datetime import date

POSITIONS = ("QB", "RB", "WR", "TE")
LAST_REGULAR_WEEK = 18
# The Tuesday after 2026 week 18: no weekly projection is due after it.
SEASON_END = date(2027, 1, 5)

# Rows per offered target week below which a pull is treated as truncated and
# nothing is written for that source (fail closed). Measured 2026-11-14: ESPN
# about 1,800 players a week (zeros for byes/outs included), Sleeper 350-440
# with points, CBS about 350.
MIN_ROWS_PER_WEEK = {"espn": 300, "sleeper": 200, "cbs": 200}
MIN_SCHEDULE_GAMES = 256  # 272 regular-season games in 2026
MIN_INJURY_ROWS = 10

SCORING_BASIS = {
    "espn": ("source_points = ESPN appliedTotal (kona leaguedefaults/3 scoring); "
             "points_* = ESPN's projected stat line rescored with the v_player_game_actuals "
             "formula (pipelines/lib/espn_weekly.points); basis=team_week"),
    "sleeper": "points_* = Sleeper pts_std / pts_half_ppr / pts_ppr as given (provider in stats.company)",
    "cbs": ("points_std = CBS non-PPR weekly page total; points_half_ppr / points_ppr = "
            "that total plus 0.5 / 1 per projected reception (pull_cbs_ros_projections)"),
}
COVERAGE = {"espn": "every_week", "sleeper": "every_week",
            "cbs": "current_week"}


def _f(v):
    """A number or None (never 0 for missing)."""
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, 2)


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def gsis_to_sleeper(sleeper_base: dict) -> dict[str, str]:
    """gsis id -> Sleeper id from the committed identity base (unique only)."""
    seen: dict[str, set] = {}
    for sid, rec in ((sleeper_base or {}).get("by_sleeper_id") or {}).items():
        g = (rec or {}).get("gsis_id")
        if g:
            seen.setdefault(str(g), set()).add(str(sid))
    return {g: next(iter(s)) for g, s in seen.items() if len(s) == 1}


def projection_row(*, run_id, source, as_of, season, content_week, target_week,
                   source_player_id, player_key, sleeper_id, full_name, position,
                   team=None, opponent=None, points_std=None, points_half_ppr=None,
                   points_ppr=None, source_points=None, stats=None,
                   source_updated_at=None) -> dict:
    return {
        "run_id": run_id, "source": source, "coverage": COVERAGE[source],
        "as_of": as_of, "season": season, "content_week": content_week,
        "target_week": target_week, "source_player_id": str(source_player_id),
        "player_key": player_key, "sleeper_id": sleeper_id, "full_name": full_name,
        "position": position, "team": team or None, "opponent": opponent or None,
        "points_std": _f(points_std), "points_half_ppr": _f(points_half_ppr),
        "points_ppr": _f(points_ppr), "source_points": _f(source_points),
        "scoring_basis": SCORING_BASIS[source], "stats": stats or None,
        "source_updated_at": source_updated_at,
    }


def has_value(row: dict) -> bool:
    return any(row.get(k) is not None for k in
               ("points_std", "points_half_ppr", "points_ppr", "source_points", "stats"))


def _key_of(hit):
    e, _how = hit
    return e["player_key"] if e else None


# ---------------------------------------------------------------- ESPN

def espn_rows(rows, index, *, run_id, as_of, season, content_week, points_fn):
    """ESPN weekly projection blocks (pull_espn_projections --weekly-out) ->
    one row per player per target week >= content_week. points_fn is
    espn_weekly.points (passed in so this module stays import-light)."""
    out, unresolved = [], 0
    for r in rows:
        wk = r.get("week")
        if not isinstance(wk, int) or wk < content_week or wk > LAST_REGULAR_WEEK:
            continue
        if r.get("pos") not in POSITIONS:
            continue
        e, _why = index.resolve_espn(r["espn_id"], r.get("name", ""), r["pos"])
        if e is None:
            unresolved += 1
        sids = index.espn_to_sleeper.get(str(r["espn_id"])) or []
        stats = r.get("stats") or {}
        out.append(projection_row(
            run_id=run_id, source="espn", as_of=as_of, season=season,
            content_week=content_week, target_week=wk, source_player_id=r["espn_id"],
            player_key=e["player_key"] if e else None,
            sleeper_id=sids[0] if len(sids) == 1 else None, full_name=r.get("name"),
            position=r["pos"], team=r.get("team"),
            points_std=points_fn(stats, "standard"), points_half_ppr=points_fn(stats, "half_ppr"),
            points_ppr=points_fn(stats, "full_ppr"), source_points=r.get("applied_total"),
            stats=stats))
    return dedupe(out), {"unresolved_rows": unresolved}


# ---------------------------------------------------------------- Sleeper

def sleeper_rows(payloads_by_week: dict, index, *, run_id, as_of, season, content_week):
    """Sleeper projections API payloads {week: [entry, ...]} -> rows.

    Kept: QB/RB/WR/TE entries whose stats carry at least one pts_* key (Sleeper
    lists every player each week; entries without points carry only ADP).
    stats = Sleeper's full stat dict as given, with company/updated_at."""
    out, unresolved = [], 0
    for wk, entries in sorted(payloads_by_week.items()):
        wk = int(wk)
        if wk < content_week:
            continue
        for ent in entries or []:
            st = ent.get("stats") or {}
            pl = ent.get("player") or {}
            pos = (pl.get("position") or "").upper()
            if pos not in POSITIONS or not any(k in st for k in ("pts_std", "pts_half_ppr", "pts_ppr")):
                continue
            sid = str(ent.get("player_id") or "")
            if not sid:
                continue
            name = " ".join(x for x in (pl.get("first_name"), pl.get("last_name")) if x)
            e, _why = index.resolve_sleeper(sid, name, pos)
            if e is None:
                unresolved += 1
            upd = ent.get("updated_at")
            stats = dict(st)
            stats["_company"] = ent.get("company")
            out.append(projection_row(
                run_id=run_id, source="sleeper", as_of=as_of, season=season,
                content_week=content_week, target_week=wk, source_player_id=sid,
                player_key=e["player_key"] if e else None, sleeper_id=sid, full_name=name or None,
                position=pos, team=ent.get("team"), opponent=ent.get("opponent"),
                points_std=st.get("pts_std"), points_half_ppr=st.get("pts_half_ppr"),
                points_ppr=st.get("pts_ppr"), stats=stats,
                source_updated_at=_ms_iso(upd)))
    return dedupe(out), {"unresolved_rows": unresolved}


def _ms_iso(ms):
    from datetime import datetime, timezone  # noqa: PLC0415
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


# ---------------------------------------------------------------- CBS

def cbs_rows(weekly: dict, index, *, run_id, as_of, season, content_week):
    """pull_cbs_ros_projections.pull_weekly output -> rows for each week CBS
    really served (the puller drops a page whose title names another week)."""
    out, unresolved = [], 0
    for wk, rows in sorted((weekly.get("weeks") or {}).items()):
        wk = int(wk)
        if wk < content_week:
            continue
        for r in rows:
            pos = (r.get("pos") or "").upper()
            if pos not in POSITIONS:
                continue
            e, _why = index.resolve_name(r.get("player_name", ""), pos)
            if e is None:
                unresolved += 1
            out.append(projection_row(
                run_id=run_id, source="cbs", as_of=as_of, season=season,
                content_week=content_week, target_week=wk,
                # CBS publishes no id on the page: normalized name, position and
                # team, so two players with one name do not collide
                source_player_id="|".join(str(x or "") for x in (
                    r.get("player_norm") or r.get("player_name"), pos, r.get("team"))),
                player_key=e["player_key"] if e else None, sleeper_id=None,
                full_name=r.get("player_name"), position=pos, team=r.get("team"),
                points_std=r.get("points_standard"), points_half_ppr=r.get("points_half_ppr"),
                points_ppr=r.get("points_ppr")))
    return dedupe(out), {"unresolved_rows": unresolved}


# ---------------------------------------------------------------- nflverse

def schedule_rows(csv_text: str, *, run_id, as_of, season):
    out = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        if _i(r.get("season")) != season:
            continue
        out.append({
            "run_id": run_id, "as_of": as_of, "season": season, "game_id": r["game_id"],
            "game_type": r.get("game_type") or None, "week": _i(r.get("week")),
            "gameday": r.get("gameday") or None, "gametime": r.get("gametime") or None,
            "away_team": r["away_team"], "home_team": r["home_team"],
            "away_score": _i(r.get("away_score")), "home_score": _i(r.get("home_score")),
            "spread_line": _f(r.get("spread_line")), "total_line": _f(r.get("total_line")),
        })
    return out


def byes(schedule: list[dict], last_week: int = LAST_REGULAR_WEEK) -> dict[str, list[int]]:
    """team -> regular-season weeks without a game (the bye), from schedule rows."""
    teams: dict[str, set] = {}
    for g in schedule:
        if g.get("game_type") not in (None, "REG"):
            continue
        for t in (g["away_team"], g["home_team"]):
            teams.setdefault(t, set()).add(g["week"])
    return {t: [w for w in range(1, last_week + 1) if w not in wks] for t, wks in sorted(teams.items())}


def injury_rows(csv_text: str, index, gsis_sleeper: dict, *, run_id, as_of, season):
    """The latest report week in nflverse injuries_<season>.csv, QB/RB/WR/TE."""
    rows = [r for r in csv.DictReader(io.StringIO(csv_text)) if _i(r.get("season")) == season]
    if not rows:
        return [], {"report_week": None, "unresolved_rows": 0}
    week = max(_i(r.get("week")) or 0 for r in rows)
    out, unresolved, seen = [], 0, set()
    for r in rows:
        pos = (r.get("position") or "").upper()
        if _i(r.get("week")) != week or pos not in POSITIONS or not r.get("gsis_id"):
            continue
        if r["gsis_id"] in seen:
            continue
        seen.add(r["gsis_id"])
        e, _why = index.resolve_gsis(r["gsis_id"], r.get("full_name", ""), pos)
        if e is None:
            unresolved += 1
        out.append({
            "run_id": run_id, "as_of": as_of, "season": season, "week": week,
            "gsis_id": r["gsis_id"], "player_key": e["player_key"] if e else None,
            "sleeper_id": gsis_sleeper.get(r["gsis_id"]), "full_name": r.get("full_name") or None,
            "position": pos, "team": r.get("team") or None,
            "report_status": r.get("report_status") or None,
            "report_primary_injury": r.get("report_primary_injury") or None,
            "practice_status": r.get("practice_status") or None,
            "practice_primary_injury": r.get("practice_primary_injury") or None,
        })
    return out, {"report_week": week, "unresolved_rows": unresolved}


# ---------------------------------------------------------------- shared

def dedupe(rows: list[dict]) -> list[dict]:
    """One row per (source, source_player_id, target_week): the first wins
    (the table's unique key within a run)."""
    seen, out = set(), []
    for r in rows:
        k = (r["source"], r["source_player_id"], r["target_week"])
        if k in seen or not has_value(r):
            continue
        seen.add(k)
        out.append(r)
    return out


def week_counts(rows: list[dict]) -> dict[int, int]:
    c: dict[int, int] = {}
    for r in rows:
        c[r["target_week"]] = c.get(r["target_week"], 0) + 1
    return dict(sorted(c.items()))


def floor_problems(source: str, rows: list[dict]) -> list[str]:
    """Each offered target week must clear the per-week floor; an empty pull
    is the caller's call (a current-week source may serve no week yet)."""
    floor = MIN_ROWS_PER_WEEK[source]
    return [f"{source} week {w}: {n} rows (floor {floor})"
            for w, n in week_counts(rows).items() if n < floor]


def run_row(*, run_id, source, as_of, season, content_week, rows_written,
            target_weeks=(), workflow_run=None, detail=None) -> dict:
    return {"run_id": run_id, "source": source, "as_of": as_of, "season": season,
            "content_week": content_week, "target_weeks": sorted(set(target_weeks)),
            "rows_written": rows_written, "workflow_run": workflow_run,
            "detail": detail or {}}
