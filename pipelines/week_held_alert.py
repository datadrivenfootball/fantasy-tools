#!/usr/bin/env python3
"""Escalate a held new week the same run (JEG-1512, never-late guardrail).

Why this exists (Week 9, 2026): every source had Week 9 in Supabase by
2026-11-04 00:38Z, but the rebuild chain failed every run from 2026-11-01 to
2026-11-05 17:54Z (week-history clock bug, then the JEG-1511 waiver-band
tests). The site served Week 8 for ~41 hours after Week 9 was complete. The
only owned record was the "chain failed; fixture not updated" status commit;
the JEG-1194 chain-stuck issue never opened (it read the in-run history index,
which `make sync` stamps with the unpublished candidate's built_at), and the
generic 12-hour ops-alert sat among ~20 fidelity alerts. Jeremy, 2026-11-05:
"You can not let data go late ever again."

    python3 pipelines/week_held_alert.py --mode chain --chain-outcome failure --published false
    python3 pipelines/week_held_alert.py --mode tripwire          # hourly, source-lateness.yml
    python3 pipelines/week_held_alert.py --mode drill             # end-to-end alert test

A source is *week-held* when this run's chain status shows Supabase holding a
newer content week for it than the week the committed (published) history
index serves, and the source is not held for its own fidelity problem (that is
source-late's job, docs/source-lateness.md). When any source is week-held:

- chain mode (end of rebuild-chain.yml on main): alert in the same run;
- tripwire mode (hourly, own schedule): alert when the committed chain status
  that shows the hold is TRIPWIRE_HOURS old (the chain has not cleared it, or
  the in-run alert did not fire).

The alert is one GitHub issue labelled `week-held` (GitHub emails the owner)
and one Linear sub-issue of JEG-1512 per season-week (LINEAR_API_KEY, the
secret divergence-issues.yml already uses), Urgent, labelled owner:claude,
naming the failing step and tests. When the chain publishes with nothing
week-held, the GitHub issue closes and the Linear issue gets a comment (a
person verifies and closes it). Runbook: docs/week-held-runbook.md.
Never fails the job; without tokens it prints what it would do.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
from lib.timestamps import parse_iso_timestamp  # noqa: E402

STATUS = REPO / "output" / "comparison-chain-status.json"
HISTORY_REL = "data/history/index.json"
LABEL = "week-held"
DRILL_LABEL = "week-held-drill"
TITLE_MARK = "is held: the site still shows week"
TRIPWIRE_HOURS = 2
COMMENT_HOURS = 6
LINEAR_PARENT = "JEG-1512"
LINEAR_LABEL = "owner:claude"
GH_API = "https://api.github.com"
LINEAR_API = "https://api.linear.app/graphql"


def _parse(ts) -> datetime | None:
    try:
        dt = parse_iso_timestamp(str(ts))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def week_ahead(status: dict, published: dict) -> dict[str, tuple[int, int]]:
    """{source: (week in Supabase, week the site serves)} for held new weeks."""
    def _dict(v):
        return v if isinstance(v, dict) else {}
    served, detail = _dict(published.get("served")), _dict(status.get("held_detail"))
    out = {}
    for src, info in sorted(_dict(status.get("source_vintages")).items()):
        cand = _int((info or {}).get("content_week")) if isinstance(info, dict) else None
        live = _int((served.get(src) or {}).get("week")) if isinstance(served.get(src), dict) else None
        if cand is None or live is None or cand <= live:
            continue
        reason = str((detail.get(src) or {}).get("reason") or "") if isinstance(detail.get(src), dict) else ""
        if reason.startswith("fidelity"):
            continue  # the source's own data problem: source-late owns it
        out[src] = (cand, live)
    return out


def decide(mode: str, ahead: dict, status: dict, now: datetime,
           chain_outcome: str = "", published: bool = False) -> str:
    """'open', 'close' or 'none'."""
    if mode == "chain":
        if chain_outcome not in ("success", "failure"):
            return "none"  # skipped or cancelled says nothing
        if ahead:
            return "open"
        return "close" if chain_outcome == "success" and published else "none"
    if mode == "tripwire":
        if not ahead:
            return "none"  # closing is the chain's job, on a confirmed publish
        run_at = _parse(status.get("run_at"))
        if run_at is None or (now - run_at).total_seconds() >= TRIPWIRE_HOURS * 3600:
            return "open"
        return "none"
    raise ValueError(f"unknown mode {mode}")


def failing(status: dict) -> list[str]:
    prv = status.get("post_rebuild_validation")
    prv = prv if isinstance(prv, dict) else {}
    tests = [t for t in (prv.get("failed_tests") or []) if isinstance(t, str)]
    steps = [s for s in (status.get("failed") or []) if isinstance(s, str)]
    return (["step: " + ", ".join(steps)] if steps else []) + tests[:10]


def title(ahead: dict, drill: bool = False) -> str:
    new = max(c for c, _ in ahead.values())
    old = min(s for _, s in ahead.values())
    return ("[drill] " if drill else "") + f"Week {new} {TITLE_MARK} {old}"


def body(ahead: dict, status: dict, mode: str, now: datetime) -> str:
    lines = [f"Supabase has a newer week than the site for {len(ahead)} source(s), and the chain has not published it.",
             "", "| source | week available | week on the site |", "|---|---|---|"]
    lines += [f"| {s} | {c} | {w} |" for s, (c, w) in sorted(ahead.items())]
    fail = failing(status)
    lines += ["", "Failing: " + ("; ".join(fail) if fail else (str(status.get("detail") or "see the run log")[:300]))]
    if status.get("held"):
        lines.append("Held sources: " + ", ".join(sorted(map(str, status["held"]))))
    lines.append(f"Chain status run_at: {status.get('run_at')}; detected by {mode} at {now.strftime('%Y-%m-%d %H:%M UTC')}.")
    run, repo = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_REPOSITORY")
    if run and repo:
        lines.append(f"Run: https://github.com/{repo}/actions/runs/{run}")
    lines += ["", "Owner: Claude lane (coordinator), same-hour response in waking hours; Jeremy rules on any test bar.",
              "Runbook: docs/week-held-runbook.md. The GitHub issue closes itself when the chain publishes with nothing held."]
    return "\n".join(lines)


# ---- GitHub -----------------------------------------------------------------

def _gh(method: str, path: str, token: str, payload: dict | None = None):
    req = urllib.request.Request(
        GH_API + path, method=method, data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _open_issue(repo, token, call, label):
    issues = call("GET", f"/repos/{repo}/issues?state=open&labels={label}&per_page=50", token) or []
    issues = [i for i in issues if "pull_request" not in i]
    return issues[0] if issues else None


def github(action: str, ttl: str, text: str, repo, token, now, call=None, label=LABEL) -> str:
    if action == "none":
        return "github: nothing to do"
    if not token or not repo:
        return f"github dry run: would {action} the {label} issue: {ttl if action == 'open' else ''}".rstrip()
    call = call or _gh
    issue = _open_issue(repo, token, call, label)
    if action == "close":
        if not issue:
            return "github: published; no open issue"
        call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token,
             {"body": "The chain published with no week held, so this is resolved."})
        call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token, {"state": "closed", "state_reason": "completed"})
        return f"github: closed #{issue['number']}"
    if issue is None:
        made = call("POST", f"/repos/{repo}/issues", token, {"title": ttl, "body": text, "labels": [label]})
        return f"github: opened #{made['number']}"
    if issue.get("title") != ttl:  # a newer week is now held: say so at once
        call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token, {"title": ttl})
        call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token, {"body": text})
        return f"github: retitled and commented on #{issue['number']}"
    upd = _parse(issue.get("updated_at"))
    if upd is not None and (now - upd).total_seconds() < COMMENT_HOURS * 3600:
        return f"github: #{issue['number']} already open"
    call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token, {"body": text})
    return f"github: commented on #{issue['number']}"


# ---- Linear -----------------------------------------------------------------

def _linear(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(LINEAR_API, data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(f"Linear API error: {payload['errors']}")
    return payload["data"]


def linear_key(season, week: int, drill: bool = False) -> str:
    return f"{'drill-' if drill else ''}week-held:{season}:w{week}"


def linear(action: str, key: str, ttl: str, text: str, token, gql=None, drill: bool = False) -> str:
    """One sub-issue of JEG-1512 per season-week, found again by its key."""
    if action == "none":
        return "linear: nothing to do"
    if not token:
        return f"linear dry run: would {action} [{key}]"
    gql = gql or (lambda q, v: _linear(token, q, v))
    parent = gql("""query($id:String!){issue(id:$id){id team{id}
        children(first:250, includeArchived:true){nodes{id identifier title completedAt canceledAt}}}}""",
                 {"id": LINEAR_PARENT})["issue"]
    nodes = parent["children"]["nodes"]
    mine = [n for n in nodes if f"[{key}]" in n["title"]]
    if action == "close":  # every open week-held incident, whatever week it named
        open_ = [n for n in nodes if "[week-held:" in n["title"]
                 and not n.get("completedAt") and not n.get("canceledAt")]
        for n in open_:
            gql("""mutation($i:CommentCreateInput!){commentCreate(input:$i){success}}""",
                {"i": {"issueId": n["id"], "body": "The chain published with no week held. Verify the live site "
                       "serves the new week (verify_live.py), then close this issue."}})
        return "linear: commented on " + (", ".join(n["identifier"] for n in open_) or "nothing (none open)")
    if mine:
        return f"linear: {mine[0]['identifier']} exists"
    labels = gql("""query($n:String!){issueLabels(filter:{name:{eq:$n}}){nodes{id}}}""",
                 {"n": LINEAR_LABEL})["issueLabels"]["nodes"]
    inp = {"teamId": parent["team"]["id"], "parentId": parent["id"], "priority": 1,
           "title": f"{ttl} [{key}]", "description": text}
    if labels:
        inp["labelIds"] = [labels[0]["id"]]
    made = gql("""mutation($i:IssueCreateInput!){issueCreate(input:$i){success issue{id identifier}}}""",
               {"i": inp})["issueCreate"]["issue"]
    if drill:  # the drill proves creation, then removes itself
        gql("""mutation($id:String!){issueArchive(id:$id){success}}""", {"id": made["id"]})
        return f"linear: opened and archived drill {made['identifier']}"
    return f"linear: opened {made['identifier']}"


# ---- inputs and CLI ---------------------------------------------------------

def _read(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def committed_history(rev: str = "HEAD") -> dict:
    """The history index as committed (published), never the in-run copy:
    `make sync` in the chain's validate rewrites the working-tree index from the
    unpublished candidate fixture (the reason JEG-1194's alert never fired)."""
    try:
        out = subprocess.run(["git", "show", f"{rev}:{HISTORY_REL}"], cwd=REPO, capture_output=True,
                             text=True, timeout=30, check=True).stdout
        doc = json.loads(out)
        return doc if isinstance(doc, dict) else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


DRILL_STATUS = {"run_at": "2000-01-01T00:00:00+00:00", "failed": ["post_rebuild_validation"],
                "post_rebuild_validation": {"failed_tests": ["FAIL tests.drill.DrillTest.test_simulated_failure"]},
                "source_vintages": {"drill": {"content_week": 2}}}
DRILL_HISTORY = {"season": "drill", "served": {"drill": {"week": 1}}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("chain", "tripwire", "drill"), required=True)
    ap.add_argument("--chain-outcome", default="")
    ap.add_argument("--published", default="false")
    ap.add_argument("--status", default=str(STATUS))
    ap.add_argument("--history", default="", help="history index file (default: committed HEAD copy)")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    repo, gh_token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    lin_token = os.environ.get("LINEAR_API_KEY", "").strip() or None
    drill = args.mode == "drill"
    try:
        if drill:
            status, history = DRILL_STATUS, DRILL_HISTORY
        else:
            status = _read(Path(args.status))
            history = _read(Path(args.history)) if args.history else committed_history()
        ahead = week_ahead(status, history)
        action = "open" if drill else decide(args.mode, ahead, status, now, args.chain_outcome, args.published == "true")
        ttl = title(ahead, drill) if ahead else ""
        text = body(ahead, status, args.mode, now) if ahead else ""
        label = DRILL_LABEL if drill else LABEL
        done = [github(action, ttl, text, repo, gh_token, now, label=label)]
        if (action == "open" and ahead) or action == "close":
            week = max(c for c, _ in ahead.values()) if ahead else 0
            done.append(linear(action, linear_key(history.get("season"), week, drill), ttl, text, lin_token, drill=drill))
        if drill and gh_token and repo:
            done.append(github("close", ttl, "", repo, gh_token, now, label=DRILL_LABEL))
    except Exception as e:  # noqa: BLE001 -- an alert never fails the chain job
        print(f"::error title=week-held alert::alert not delivered ({type(e).__name__}: {e})")
        return 0
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if drill:
        print("::notice title=week-held drill::" + "; ".join(done))
    elif ahead and action == "open":
        print(f"::error title={ttl}::" + "; ".join(done))
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"\n## {ttl}\n\n{text}\n\nAlert: {'; '.join(done)}\n")
    else:
        print("week-held alert: " + "; ".join(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
