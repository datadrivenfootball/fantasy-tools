#!/usr/bin/env python3
"""Freshness and size check for the weekly projection warehouse (JEG-1641).

Reads only public.source_projection_runs (the newest as_of per source) and
public.source_weekly_warehouse_size(); fetches no source.

Stale = a source's newest run row is older than its cadence (RULES), or it has
none. Each source runs daily (ESPN 12:40 UTC via espn-weekly-store, the rest
13:30 UTC via weekly-projection-warehouse, plus Sunday copies), so 26 hours
is one missed day plus the scheduler's grace. FantasyPros only warns: its
anonymous page can lag a week and it is the least complete source.
Outside the regular season (after SEASON_END) nothing is due.

Size: problem when the database passes DB_ALERT_BYTES (75% of the Pro plan's
8 GB included disk) or the warehouse tables pass WAREHOUSE_ALERT_BYTES (the
point Jeremy said to revisit retention; projection in
docs/weekly-projection-warehouse.md).

Two ways to run:
  (default)  exit 1 when anything is stale or over size: the step in
             weekly-projection-warehouse.yml, so the monitored run goes red.
  --alert    open, update or close one GitHub issue (label warehouse-stale),
             the source-lateness pattern; exit 1 only if the check or the
             alert cannot complete. Runs hourly in source-lateness.yml, which
             has its own schedule, so a dead pg_cron still alerts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from lib.timestamps import parse_iso_timestamp  # noqa: E402

from projection_warehouse import SEASON_END  # noqa: E402  (the Tuesday after 2026 week 18)
DB_ALERT_BYTES = 6 * 1024 ** 3
WAREHOUSE_ALERT_BYTES = 1024 ** 3
LABEL = "warehouse-stale"
TITLE = "Weekly projection warehouse is stale"
COMMENT_HOURS = 6


@dataclass(frozen=True)
class Rule:
    max_age_hours: float
    alert: bool  # False = warning only, never stale for the exit code / issue


RULES = {
    "espn": Rule(26, True),
    "sleeper": Rule(26, True),
    "cbs": Rule(26, True),
    "nflverse_schedule": Rule(26, True),
    "nflverse_injuries": Rule(26, True),
    "fantasypros": Rule(26, False),
}


def _ts(v):
    if not v:
        return None
    return parse_iso_timestamp(str(v))


def judge(latest: dict[str, dict | None], sizes: dict[str, int], now: datetime) -> dict:
    """latest: source -> newest run row ({as_of, rows_written}) or None."""
    in_season = now.date() < SEASON_END
    out = {"checked_at": now.isoformat(timespec="seconds"), "in_season": in_season,
           "sources": {}, "stale": [], "warnings": [], "size": {}, "over_size": []}
    for source, rule in RULES.items():
        row = latest.get(source)
        at = _ts((row or {}).get("as_of"))
        age = (now - at).total_seconds() / 3600 if at else None
        late = in_season and (age is None or age > rule.max_age_hours)
        out["sources"][source] = {"as_of": at.isoformat() if at else None,
                                  "age_hours": round(age, 1) if age is not None else None,
                                  "max_age_hours": rule.max_age_hours,
                                  "rows_written": (row or {}).get("rows_written"), "late": late}
        if late:
            (out["stale"] if rule.alert else out["warnings"]).append(source)
    db = sizes.get("database")
    wh = sum(v for k, v in sizes.items() if k != "database")
    out["size"] = {"database_bytes": db, "warehouse_bytes": wh,
                   "database_alert_bytes": DB_ALERT_BYTES, "warehouse_alert_bytes": WAREHOUSE_ALERT_BYTES}
    if db is not None and db > DB_ALERT_BYTES:
        out["over_size"].append(f"database {db / 1e9:.2f} GB > {DB_ALERT_BYTES / 1e9:.2f} GB")
    if wh > WAREHOUSE_ALERT_BYTES:
        out["over_size"].append(f"warehouse tables {wh / 1e9:.2f} GB > {WAREHOUSE_ALERT_BYTES / 1e9:.2f} GB")
    return out


def problem(rep: dict) -> bool:
    return bool(rep["stale"] or rep["over_size"])


def body(rep: dict) -> str:
    lines = ["The weekly projection warehouse (JEG-1641) has a source past its cadence or is over its size line.",
             "", "| Source | Newest as_of | Age (h) | Max (h) | Late |", "|---|---|---|---|---|"]
    for s, r in rep["sources"].items():
        lines.append(f"| {s} | {r['as_of'] or 'none'} | {r['age_hours']} | {r['max_age_hours']} | "
                     f"{'yes' if r['late'] else 'no'} |")
    if rep["over_size"]:
        lines += ["", "Size: " + "; ".join(rep["over_size"])]
    lines += ["", "What to do: docs/weekly-projection-warehouse.md (Freshness and size).",
              "This issue closes itself when every source is fresh and size is under the line."]
    return "\n".join(lines)


def _marker(rep: dict) -> str:
    return "<!-- warehouse-stale: " + ",".join(sorted(rep["stale"]) + sorted(rep["over_size"])) + " -->"


def alert(rep: dict, repo: str | None, token: str | None, now: datetime, call=None) -> str:
    from source_lateness import _call, _open_issues  # noqa: PLC0415 -- same GitHub path
    bad = problem(rep)
    if not token or not repo:
        return "dry run: would open or update the issue" if bad else "dry run: nothing stale"
    call = call or _call
    issues = [i for i in _open_issues(repo, token, call) if "pull_request" not in i and (
        i.get("title") == TITLE or LABEL in {(lb or {}).get("name") for lb in i.get("labels") or []})]
    issue = issues[0] if issues else None
    if not bad:
        if not issue:
            return "fresh; no open issue"
        call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token,
             {"body": "Every warehouse source is fresh again, so this is resolved."})
        call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token,
             {"state": "closed", "state_reason": "completed"})
        return f"closed #{issue['number']}"
    text = body(rep) + "\n" + _marker(rep)
    if issue is None:
        made = call("POST", f"/repos/{repo}/issues", token, {"title": TITLE, "body": text, "labels": [LABEL]})
        return f"opened #{made['number']}"
    since = _ts(issue.get("updated_at"))
    changed = _marker(rep) not in (issue.get("body") or "")
    if not changed and since is not None and now - since < timedelta(hours=COMMENT_HOURS):
        return f"#{issue['number']} already open"
    call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token, {"body": text})
    call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token, {"body": body(rep)})
    return f"updated #{issue['number']}"


def load(sb) -> tuple[dict, dict]:
    latest = {}
    for source in RULES:
        rows = sb.get("source_projection_runs",
                      f"?select=as_of,rows_written&source=eq.{source}&order=as_of.desc&limit=1")
        latest[source] = rows[0] if rows else None
    sizes = {r["relation"]: int(r["bytes"]) for r in (sb.rpc("source_weekly_warehouse_size", {}) or [])}
    return latest, sizes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--alert", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        try:
            import sbclient as sb  # noqa: PLC0415
        except ImportError:
            import gh_sbclient as sb  # noqa: PLC0415
        rep = judge(*load(sb), now)
    except Exception as exc:  # noqa: BLE001 -- a check that cannot run must show red
        print(f"::error title=projection warehouse::not checked ({type(exc).__name__}: {exc})")
        return 1
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, indent=1) + "\n")
    for s in rep["stale"]:
        print(f"::warning title=warehouse stale::{s} newest as_of {rep['sources'][s]['as_of']}")
    for s in rep["warnings"]:
        print(f"::notice title=warehouse warn-only::{s} newest as_of {rep['sources'][s]['as_of']}")
    for msg in rep["over_size"]:
        print(f"::warning title=warehouse size::{msg}")
    print(json.dumps({s: (r["as_of"], r["age_hours"]) for s, r in rep["sources"].items()}, indent=1))
    if a.alert:
        try:
            print("warehouse alert: " + alert(rep, os.environ.get("GITHUB_REPOSITORY"),
                                              os.environ.get("GITHUB_TOKEN"), now))
        except Exception as exc:  # noqa: BLE001
            print(f"::error title=projection warehouse alert::alert failed ({type(exc).__name__}: {exc})")
            return 1
        return 0
    return 1 if problem(rep) else 0


if __name__ == "__main__":
    sys.exit(main())
