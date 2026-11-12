#!/usr/bin/env python3
"""Weekly rollover pre-flight (read-only). Run it Tuesday afternoon, before the
week's trade-chart articles land, so a red gate is found while there is still
time to fix it (retro of the Week 10 rollover, 2026-11-12).

    python3 pipelines/rollover_preflight.py            # human report, exit 1 on any FAIL
    python3 pipelines/rollover_preflight.py --json     # machine-readable

Checks (all reads, nothing dispatched or written):
1. Pages: the newest completed run on main whose deploy job finished deployed.
2. Chain: the newest finished rebuild-chain run on main succeeded, and the
   chain did not flap (two or more green-to-red turns in the last 12 hours).
3. Live site: the served status file names the current content week (or the
   week before on Tuesday and Wednesday) and no source serves more than a week behind.
4. Connector: get-values answers with the same week as the live site.
5. Supabase pg_cron: printed as SQL to run (the script has no database access).

`gh` must be authenticated for 1 and 2. Holds are reported, never failed:
holds are the fidelity gate's call, not a pipeline fault.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl_week  # noqa: E402

REPO = "datadrivenfootball/fantasy-tools"
SITE = "https://datadrivenfootball.github.io/fantasy-tools"
GET_VALUES = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1/get-values?scoring=ppr&teams=12&superflex=0"
CRON_SQL = """select jobname, schedule, active from cron.job
 where jobname in ('rebuild-chain-weekly-tue-evening','rebuild-chain-weekly-wed-morning',
   'rebuild-chain-bake-live','pages-deploy-live','vintage-check-live',
   'source-probe-trade-charts','source-probe-fantasycalc','source-probe-projections')
 order by jobname;  -- expect 8 rows, all active"""


def _gh_json(args: list[str]):
    proc = subprocess.run(["gh", *args, "-R", REPO], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (fixed https URLs)
        return json.loads(resp.read().decode("utf-8"))


def check_pages(runs_with_jobs: list[dict]) -> tuple[str, str]:
    """runs_with_jobs: newest first, each {databaseId, headSha, jobs:[{name, conclusion}]}.
    Decision A (JEG-1485): a run can fail on code tests and still deploy, so the
    deploy job is what counts, not the run's conclusion."""
    for run in runs_with_jobs:
        deploy = next((j for j in run.get("jobs") or [] if j.get("name") == "deploy"), None)
        if not deploy or deploy.get("conclusion") in (None, "", "skipped", "cancelled"):
            continue
        ok = deploy.get("conclusion") == "success"
        return ("PASS" if ok else "FAIL",
                f"newest finished deploy: run {run['databaseId']} at {str(run.get('headSha'))[:9]} -> {deploy['conclusion']}")
    return "FAIL", "no finished deploy job in the recent Pages runs"


def check_chain(runs: list[dict], now: datetime) -> tuple[str, str]:
    """runs: newest first, completed only, each {databaseId, conclusion, createdAt}.
    Cancelled runs are skipped. FAIL when the newest finished run failed, or
    when the chain flapped: two or more green-to-red turns in the last 12 hours
    (2026-11-12: the same commit 2ec76ac19 went green in 43148154825 and red in
    43148183220). A red streak that has since been fixed passes."""
    finished = [r for r in runs if r.get("conclusion") not in (None, "", "cancelled", "skipped")]
    if not finished:
        return "FAIL", "no finished rebuild-chain run found"
    newest = finished[0]
    since = now - timedelta(hours=12)
    window = [r for r in finished
              if datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) >= since][::-1]
    turns = sum(1 for older, newer in zip(window, window[1:])
                if older.get("conclusion") == "success" and newer.get("conclusion") == "failure")
    failed = sum(1 for r in window if r.get("conclusion") == "failure")
    msg = (f"newest run {newest['databaseId']} -> {newest.get('conclusion')}; last 12 h: "
           f"{failed} failed, {turns} green-to-red turns")
    if newest.get("conclusion") != "success" or turns >= 2:
        return "FAIL", msg
    return "PASS", msg


def check_live(status: dict, week: int, weekday: int) -> tuple[str, str, int | None]:
    """weekday: Monday 0 (New York calendar, nfl_week.today_ny). The site may
    still name the previous week on Tuesday and Wednesday, while the new week's
    charts are publishing; from Thursday it must name the current week. A source
    may serve one week behind (stale only after Thursday noon, JEG-1176)."""
    served = {k: (v or {}).get("served_week") for k, v in (status.get("source_weeks") or {}).items()}
    live_week = status.get("nfl_week")
    floor = week - 1 if weekday in (1, 2) else week
    behind = sorted(k for k, w in served.items() if not isinstance(w, int) or w < week - 1)
    held = status.get("held") or []
    msg = (f"site week {live_week} (content week now {week}, needs {floor} or later); served {served}; "
           f"held {held or 'none'}; status run_at {status.get('run_at')}")
    ok = isinstance(live_week, int) and live_week >= floor and not behind
    return ("PASS" if ok else "FAIL"), msg + (f"; more than a week behind: {behind}" if behind else ""), live_week


def check_connector(values: dict, live_week: int | None) -> tuple[str, str]:
    week = values.get("default_week", values.get("week"))
    msg = f"get-values default week {week}, weeks {values.get('weeks')}, sources {len(values.get('sources_included') or [])}"
    return ("PASS" if live_week is not None and week == live_week else "FAIL"), msg


def run(now: datetime | None = None) -> list[dict]:
    now = now or nfl_week.now_utc()
    week = nfl_week.content_week()
    results: list[dict] = []

    def add(name, fn):
        try:
            verdict, msg, *_ = fn()
        except Exception as exc:  # a check that cannot run is a FAIL, never a silent pass
            verdict, msg = "FAIL", f"could not run: {exc}"
        results.append({"check": name, "verdict": verdict, "detail": msg})

    def pages():
        runs = _gh_json(["run", "list", "-w", "pages.yml", "-b", "main", "--status", "completed",
                         "--limit", "8", "--json", "databaseId,headSha"])
        for r in runs:
            r["jobs"] = _gh_json(["run", "view", str(r["databaseId"]), "--json", "jobs"])["jobs"]
        return check_pages(runs)

    def chain():
        runs = _gh_json(["run", "list", "-w", "rebuild-chain.yml", "-b", "main", "--status", "completed",
                         "--limit", "30", "--json", "databaseId,conclusion,createdAt"])
        return check_chain(runs, now)

    live: dict = {}

    def site():
        verdict, msg, live["week"] = check_live(_get_json(f"{SITE}/modules/comparison-chain-status.json"), week,
                                                nfl_week.today_ny().weekday())
        return verdict, msg

    add("pages deploy on main", pages)
    add("rebuild chain on main", chain)
    add("live site week", site)
    add("connector (get-values)", lambda: check_connector(_get_json(GET_VALUES), live.get("week")))
    results.append({"check": "Supabase pg_cron", "verdict": "MANUAL",
                    "detail": "run via Supabase execute_sql (read-only):\n" + CRON_SQL})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    results = run()
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"[{r['verdict']}] {r['check']}: {r['detail']}")
    return 1 if any(r["verdict"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
