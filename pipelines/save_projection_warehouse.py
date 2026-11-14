#!/usr/bin/env python3
"""Daily weekly-projection warehouse: Sleeper, CBS, FantasyPros, nflverse (JEG-1641).

Pulls public pages and APIs (no login), builds rows with
pipelines/lib/projection_warehouse.py and APPENDS them to the JEG-1641 tables
(supabase/migrations/jeg1641_weekly_projection_warehouse_20261114.sql). Every
run is new rows under a new run_id; nothing is updated or deleted (the tables
reject it). ESPN rows are written by save_espn_weekly.py from the daily ESPN
pull (one ESPN fetch a day), not here.

Per source: pull -> rows -> floor check -> insert rows -> insert one
source_projection_runs row. A source that fails writes no run row (so the
freshness check sees it stale), and the others still run; exit 1 if any
source failed. A current-week source (CBS, FantasyPros) whose page does not
yet show the content week writes a run row with 0 rows and the reason.

Politeness: Sleeper 0.5 s between requests (36 a run); CBS via the existing
puller (up to 12 pages); FantasyPros 4 pages, 5 s apart (robots.txt
Crawl-delay 5; only /ajax /api /json /xml are disallowed, none used here);
nflverse two release assets on GitHub.

What is stored and example queries: docs/weekly-projection-warehouse.md.

Usage:
    python3 pipelines/save_projection_warehouse.py [--dry-run]
        [--sources sleeper,cbs,fantasypros,nflverse_schedule,nflverse_injuries]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import projection_warehouse as pw  # noqa: E402
from nfl_week import content_week  # noqa: E402
from player_key_index import PlayerIndex  # noqa: E402

SEASON = 2026
SLEEPER_BASE = ROOT / "data" / "inputs" / "sleeper_identity_base.json"
SUMMARY = ROOT / "output" / "projection-warehouse.json"
SOURCES = ("sleeper", "cbs", "fantasypros", "nflverse_schedule", "nflverse_injuries")
FP_URL = "https://www.fantasypros.com/nfl/projections/{pos}.php?week={week}"
FP_DELAY = 5.0
SLEEPER_DELAY = 0.5
NFLVERSE_SCHEDULE = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
NFLVERSE_INJURIES = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def http_text(url: str, headers=None, timeout=60) -> str:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "data-driven-football-measurement/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def pull_sleeper(cw: int) -> dict:
    from pull_sleeper_projections import PROJ, POSITIONS, get_json  # noqa: PLC0415
    by_week: dict[int, list] = {}
    for wk in range(cw, pw.LAST_REGULAR_WEEK + 1):
        for pos in POSITIONS:
            by_week.setdefault(wk, []).extend(get_json(PROJ.format(season=SEASON, week=wk, pos=pos)) or [])
            time.sleep(SLEEPER_DELAY)
    return by_week


def pull_cbs(cw: int) -> dict:
    from pull_cbs_ros_projections import pull_weekly, utc_now  # noqa: PLC0415
    return pull_weekly(cw, utc_now())


def pull_fantasypros(cw: int) -> dict:
    pages = {}
    for i, pos in enumerate(pw.POSITIONS):
        if i:
            time.sleep(FP_DELAY)
        pages[pos] = http_text(FP_URL.format(pos=pos.lower(), week=cw), headers=BROWSER_HEADERS)
    return pages


def _sb():
    try:
        import sbclient  # noqa: PLC0415
    except ImportError:
        import gh_sbclient as sbclient  # noqa: PLC0415
    return sbclient


def insert(sb, table: str, rows: list[dict], chunk: int = 500) -> int:
    """Plain inserts: a repeated key is an error, never a merge (append-only)."""
    for i in range(0, len(rows), chunk):
        sb.post(table, rows[i:i + chunk], prefer="return=minimal")
    return len(rows)


def build(source: str, cw: int, index: PlayerIndex, gsis_sleeper: dict, run_id: str,
          as_of: str) -> tuple[str, list[dict], dict, list[str]]:
    """-> (table, rows, detail, problems). Network happens here."""
    common = {"run_id": run_id, "as_of": as_of, "season": SEASON}
    if source == "sleeper":
        rows, det = pw.sleeper_rows(pull_sleeper(cw), index, content_week=cw, **common)
        return "source_weekly_projections", rows, det, (pw.floor_problems(source, rows)
                                                         or ([] if rows else ["sleeper: no rows"]))
    if source == "cbs":
        weekly = pull_cbs(cw)
        rows, det = pw.cbs_rows(weekly, index, content_week=cw, **common)
        det |= {"not_offered_weeks": weekly.get("not_offered_weeks"), "errors": weekly.get("errors")}
        probs = pw.floor_problems(source, rows)
        if not rows and weekly.get("errors"):
            probs.append("cbs: " + "; ".join(weekly["errors"])[:500])
        return "source_weekly_projections", rows, det, probs
    if source == "fantasypros":
        rows, det = pw.fantasypros_rows(pull_fantasypros(cw), index, content_week=cw, **common)
        probs = pw.floor_problems(source, rows)
        if det["unparsed_pages"]:
            probs.append("fantasypros: no week heading or rows parsed on " + ", ".join(det["unparsed_pages"]))
        return "source_weekly_projections", rows, det, probs
    if source == "nflverse_schedule":
        rows = pw.schedule_rows(http_text(NFLVERSE_SCHEDULE), **common)
        probs = [] if len(rows) >= pw.MIN_SCHEDULE_GAMES else [
            f"nflverse_schedule: {len(rows)} games (floor {pw.MIN_SCHEDULE_GAMES})"]
        return "nflverse_schedule_snapshots", rows, {"byes": pw.byes(rows)}, probs
    if source == "nflverse_injuries":
        rows, det = pw.injury_rows(http_text(NFLVERSE_INJURIES.format(season=SEASON)), index,
                                   gsis_sleeper, **common)
        probs = [] if len(rows) >= pw.MIN_INJURY_ROWS else [
            f"nflverse_injuries: {len(rows)} rows (floor {pw.MIN_INJURY_ROWS})"]
        return "nflverse_injury_snapshots", rows, det, probs
    raise ValueError(source)


def target_weeks(table: str, rows: list[dict]) -> list[int]:
    if table == "source_weekly_projections":
        return sorted({r["target_week"] for r in rows})
    if table == "nflverse_injury_snapshots":
        return sorted({r["week"] for r in rows})
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sources", default=",".join(SOURCES))
    ap.add_argument("--summary", type=Path, default=SUMMARY)
    ap.add_argument("--no-identity", action="store_true",
                    help="dry runs without database access: player_key stays null")
    a = ap.parse_args(argv)
    sources = [s for s in a.sources.split(",") if s]
    bad = [s for s in sources if s not in SOURCES]
    if bad:
        ap.error(f"unknown source(s): {bad}")

    base = json.load(open(SLEEPER_BASE))
    sb = None
    if a.no_identity:
        if not a.dry_run:
            ap.error("--no-identity is for dry runs only")
        players = []
    else:
        sb = _sb()
        players = sb.get_all("players", "?select=id,player_key,full_name,position,active,metadata")
    index = PlayerIndex(players, base)
    gsis_sleeper = pw.gsis_to_sleeper(base)
    cw = content_week()
    run_id = str(uuid.uuid4())
    workflow_run = os.environ.get("GITHUB_RUN_ID")
    summary = {"run_id": run_id, "content_week": cw, "dry_run": a.dry_run, "sources": {}}
    failed = []
    for source in sources:
        as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rep = summary["sources"][source] = {"as_of": as_of}
        try:
            table, rows, detail, problems = build(source, cw, index, gsis_sleeper, run_id, as_of)
        except Exception as exc:  # noqa: BLE001 -- one source never stops the others
            failed.append(source)
            rep["error"] = f"{type(exc).__name__}: {exc}"[:500]
            print(f"FAILED {source}: {rep['error']}", file=sys.stderr)
            continue
        rep |= {"table": table, "rows": len(rows), "detail": detail}
        if table == "source_weekly_projections":
            rep["rows_by_week"] = pw.week_counts(rows)
        if problems:
            failed.append(source)
            rep["problems"] = problems
            print(f"FAILED {source}: {'; '.join(problems)}; nothing written", file=sys.stderr)
            continue
        if not a.dry_run:
            try:
                insert(sb, table, rows)
                insert(sb, "source_projection_runs", [pw.run_row(
                    run_id=run_id, source=source, as_of=as_of, season=SEASON, content_week=cw,
                    rows_written=len(rows), target_weeks=target_weeks(table, rows),
                    workflow_run=workflow_run, detail=detail)])
                rep["written"] = len(rows)
            except Exception as exc:  # noqa: BLE001
                failed.append(source)
                rep["error"] = f"write: {type(exc).__name__}: {exc}"[:500]
                print(f"FAILED {source} write: {rep['error']}", file=sys.stderr)
    summary["failed"] = failed
    a.summary.parent.mkdir(parents=True, exist_ok=True)
    a.summary.write_text(json.dumps(summary, indent=1, default=str) + "\n")
    for s, rep in summary["sources"].items():
        print(f"{s}: rows={rep.get('rows')} by_week={rep.get('rows_by_week', '')} "
              f"written={rep.get('written', 0 if not a.dry_run else 'dry')} "
              f"{'problems=' + str(rep['problems']) if rep.get('problems') else ''}"
              f"{'error=' + rep['error'] if rep.get('error') else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
