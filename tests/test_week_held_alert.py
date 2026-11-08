"""JEG-1512: a held new week must escalate the same run.

Week 9, 2026: every source had Week 9 in Supabase by 2026-11-04 00:38Z, the
chain failed every run until 2026-11-05 17:54Z, and nothing owned the hold.
pipelines/week_held_alert.py opens a `week-held` GitHub issue and a Linear
sub-issue of JEG-1512 in that run. GitHub and Linear calls are faked.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT))
import week_held_alert as wh  # noqa: E402
import chain_stuck_alert as stuck  # noqa: E402

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
SOURCES = ("cbs", "cbsros", "espn", "fantasycalc", "fantasypros", "razzball", "usatoday")
# The committed history all through the incident: the Oct 31 Week 8 build.
PUBLISHED = {"season": 2026, "content_week": 8, "fixture_built_at": "2026-10-31T19:47:05+00:00",
             "served": {s: {"week": 8} for s in SOURCES}}
# The chain status of the Nov 4 runs (commit 90bf7f5ea): Week 9 everywhere,
# every source held by the engine/reference disagreement, validate red.
WEEK9_STATUS = {
    "run_at": "2026-11-04T00:40:00+00:00", "success": False, "failed": ["post_rebuild_validation"],
    "held": list(SOURCES),
    "held_detail": {s: {"reason": "validation hold: engine and Python reference disagree"} for s in SOURCES},
    "source_vintages": {s: {"content_week": 9} for s in SOURCES},
    "post_rebuild_validation": {"failed_tests": [
        "FAIL tests.test_value_pipeline_engine.TestPromotionModelSwitchedOff.test_python_reference_flag_on_equals_baseline"]},
}


class FakeGitHub:
    def __init__(self, issues=()):
        self.issues, self.calls = list(issues), []

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET":
            return self.issues
        if method == "POST" and path.endswith("/issues"):
            return {"number": 91}
        return {}


class FakeLinear:
    def __init__(self, children=(), labels=({"id": "L1"},)):
        self.children, self.labels, self.calls = list(children), list(labels), []

    def __call__(self, query, variables):
        self.calls.append((query.split("(")[0].split("{")[0].strip(), variables))
        if "children" in query:
            return {"issue": {"id": "P", "team": {"id": "T"}, "children": {"nodes": self.children}}}
        if "issueLabels" in query:
            return {"issueLabels": {"nodes": self.labels}}
        if "issueCreate" in query:
            return {"issueCreate": {"success": True, "issue": {"id": "N", "identifier": "JEG-9999"}}}
        return {"x": {"success": True}}


class WeekAhead(unittest.TestCase):
    def test_week9_incident_is_week_held_for_every_source(self):
        ahead = wh.week_ahead(WEEK9_STATUS, PUBLISHED)
        self.assertEqual(ahead, {s: (9, 8) for s in SOURCES})

    def test_a_fidelity_hold_is_source_lates_job(self):
        status = dict(WEEK9_STATUS, held_detail={"cbs": {"reason": "fidelity: publisher_vs_stored"}})
        self.assertNotIn("cbs", wh.week_ahead(status, PUBLISHED))
        self.assertIn("espn", wh.week_ahead(status, PUBLISHED))

    def test_same_week_or_unknown_weeks_are_not_held(self):
        same = dict(WEEK9_STATUS, source_vintages={"cbs": {"content_week": 8}, "espn": {"content_week": None},
                                                   "odd": {"content_week": 10}, "bad": "x"})
        self.assertEqual(wh.week_ahead(same, PUBLISHED), {})

    def test_malformed_inputs_do_not_raise(self):
        self.assertEqual(wh.week_ahead({"source_vintages": 5, "held_detail": []}, {"served": []}), {})
        self.assertEqual(wh.week_ahead({"source_vintages": {"cbs": 9}}, {"served": {"cbs": 8}}), {})


class Decide(unittest.TestCase):
    ahead = {"cbs": (9, 8)}

    def test_chain_alerts_in_the_same_run_without_waiting(self):
        self.assertEqual(wh.decide("chain", self.ahead, WEEK9_STATUS, NOW, "failure"), "open")

    def test_a_successful_run_that_still_holds_a_source_week_alerts(self):
        self.assertEqual(wh.decide("chain", self.ahead, WEEK9_STATUS, NOW, "success", True), "open")

    def test_publish_with_nothing_held_closes(self):
        self.assertEqual(wh.decide("chain", {}, WEEK9_STATUS, NOW, "success", True), "close")
        self.assertEqual(wh.decide("chain", {}, WEEK9_STATUS, NOW, "success", False), "none")
        self.assertEqual(wh.decide("chain", {}, WEEK9_STATUS, NOW, "failure", True), "none")

    def test_skipped_or_cancelled_says_nothing(self):
        for outcome in ("skipped", "cancelled", ""):
            self.assertEqual(wh.decide("chain", self.ahead, WEEK9_STATUS, NOW, outcome), "none")

    def test_tripwire_waits_two_hours_from_the_status(self):
        fresh = dict(WEEK9_STATUS, run_at=(NOW - timedelta(hours=1, minutes=59)).isoformat())
        old = dict(WEEK9_STATUS, run_at=(NOW - timedelta(hours=wh.TRIPWIRE_HOURS)).isoformat())
        self.assertEqual(wh.decide("tripwire", self.ahead, fresh, NOW), "none")
        self.assertEqual(wh.decide("tripwire", self.ahead, old, NOW), "open")
        self.assertEqual(wh.decide("tripwire", {}, old, NOW), "none")
        self.assertEqual(wh.decide("tripwire", self.ahead, {}, NOW), "open")


class Text(unittest.TestCase):
    def test_title_and_body_name_the_weeks_step_and_test(self):
        ahead = wh.week_ahead(WEEK9_STATUS, PUBLISHED)
        self.assertEqual(wh.title(ahead), "Week 9 is held: the site still shows week 8")
        text = wh.body(ahead, WEEK9_STATUS, "chain", NOW)
        self.assertIn("| razzball | 9 | 8 |", text)
        self.assertIn("step: post_rebuild_validation", text)
        self.assertIn("test_python_reference_flag_on_equals_baseline", text)
        self.assertIn("docs/week-held-runbook.md", text)


class GitHubAlert(unittest.TestCase):
    def test_opens_one_labelled_issue(self):
        gh = FakeGitHub()
        self.assertEqual(wh.github("open", "Week 9 is held: x", "b", "o/r", "t", NOW, gh), "github: opened #91")
        self.assertEqual([c[2]["labels"] for c in gh.calls if c[0] == "POST"], [[wh.LABEL]])

    def test_an_open_issue_is_not_duplicated_or_spammed(self):
        gh = FakeGitHub([{"number": 5, "title": "T", "updated_at": (NOW - timedelta(hours=1)).isoformat()}])
        self.assertEqual(wh.github("open", "T", "b", "o/r", "t", NOW, gh), "github: #5 already open")
        self.assertEqual([c for c in gh.calls if c[0] != "GET"], [])

    def test_a_newer_held_week_retitles_at_once(self):
        gh = FakeGitHub([{"number": 5, "title": "Week 9 is held", "updated_at": NOW.isoformat()}])
        self.assertIn("retitled", wh.github("open", "Week 10 is held", "b", "o/r", "t", NOW, gh))

    def test_close_on_publish(self):
        gh = FakeGitHub([{"number": 5, "title": "T"}])
        self.assertEqual(wh.github("close", "", "", "o/r", "t", NOW, gh), "github: closed #5")

    def test_pull_requests_are_ignored_and_no_token_only_prints(self):
        gh = FakeGitHub([{"number": 3, "pull_request": {}}])
        self.assertEqual(wh.github("close", "", "", "o/r", "t", NOW, gh), "github: published; no open issue")
        self.assertTrue(wh.github("open", "T", "b", "o/r", None, NOW, gh).startswith("github dry run"))


class LinearAlert(unittest.TestCase):
    def test_opens_an_urgent_owned_sub_issue_of_jeg_1512(self):
        lin = FakeLinear()
        out = wh.linear("open", wh.linear_key(2026, 9), "Week 9 is held", "b", "k", gql=lin)
        self.assertEqual(out, "linear: opened JEG-9999")
        create = [v for q, v in lin.calls if q == "mutation" and "teamId" in v.get("i", {})][0]["i"]
        self.assertEqual((create["parentId"], create["priority"], create["labelIds"]), ("P", 1, ["L1"]))
        self.assertIn("[week-held:2026:w9]", create["title"])

    def test_one_per_week_even_after_it_was_closed(self):
        lin = FakeLinear([{"id": "a", "identifier": "JEG-1", "title": "x [week-held:2026:w9]",
                           "completedAt": "2026-11-06"}])
        self.assertEqual(wh.linear("open", "week-held:2026:w9", "t", "b", "k", gql=lin), "linear: JEG-1 exists")

    def test_close_comments_on_every_open_incident(self):
        lin = FakeLinear([{"id": "a", "identifier": "JEG-1", "title": "x [week-held:2026:w9]"},
                          {"id": "b", "identifier": "JEG-2", "title": "y [week-held:2026:w8]", "completedAt": "z"},
                          {"id": "c", "identifier": "JEG-3", "title": "unrelated child"}])
        self.assertEqual(wh.linear("close", "week-held:2026:w0", "", "", "k", gql=lin), "linear: commented on JEG-1")

    def test_drill_archives_what_it_opened(self):
        lin = FakeLinear()
        out = wh.linear("open", wh.linear_key("drill", 2, True), "[drill] t", "b", "k", gql=lin, drill=True)
        self.assertIn("archived drill JEG-9999", out)
        self.assertTrue(any(v == {"id": "N"} for _, v in lin.calls))

    def test_without_a_key_it_only_prints(self):
        self.assertTrue(wh.linear("open", "k", "t", "b", None).startswith("linear dry run"))


class Cli(unittest.TestCase):
    def _run(self, status, history, *args):
        with tempfile.TemporaryDirectory() as d:
            st, hi = Path(d, "s.json"), Path(d, "h.json")
            st.write_text(json.dumps(status))
            hi.write_text(json.dumps(history))
            with patch.dict("os.environ", {"GITHUB_TOKEN": "", "LINEAR_API_KEY": ""}), \
                    patch("builtins.print") as out:
                rc = wh.main(["--status", str(st), "--history", str(hi), *args])
            return rc, " ".join(str(c.args[0]) for c in out.call_args_list)

    def test_week9_replay_raises_an_error_annotation(self):
        rc, out = self._run(WEEK9_STATUS, PUBLISHED, "--mode", "chain", "--chain-outcome", "failure")
        self.assertEqual(rc, 0)
        self.assertIn("::error title=Week 9 is held: the site still shows week 8", out)
        self.assertIn("linear dry run: would open [week-held:2026:w9]", out)

    def test_malformed_files_never_fail_the_job(self):
        for status in ({"source_vintages": "x", "held_detail": 3}, {"run_at": 5}):
            rc, _ = self._run(status, {"served": 7}, "--mode", "tripwire")
            self.assertEqual(rc, 0)

    def test_drill_runs_without_inputs(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "", "LINEAR_API_KEY": ""}), patch("builtins.print") as out:
            self.assertEqual(wh.main(["--mode", "drill"]), 0)
        self.assertIn("[drill] Week 2 is held", str(out.call_args_list))


class Delivery(unittest.TestCase):
    """Review of PR #1381: unpushed runs, GitHub failures, close comments."""

    def _main(self, *args, gh=None, lin=None, history=PUBLISHED, status=WEEK9_STATUS):
        with tempfile.TemporaryDirectory() as d:
            st = Path(d, "s.json")
            st.write_text(json.dumps(status))
            with patch.dict("os.environ", {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r", "LINEAR_API_KEY": "k"}), \
                    patch.object(wh, "committed_history", return_value=history) as hist, \
                    patch.object(wh, "github", side_effect=gh or (lambda *a, **k: "github: opened #1")), \
                    patch.object(wh, "linear", side_effect=lin or (lambda *a, **k: "linear: opened JEG-1")) as li, \
                    patch("builtins.print") as out:
                self.assertEqual(wh.main(["--status", str(st), *args]), 0)
            return hist, li, " ".join(str(c.args[0]) for c in out.call_args_list)

    def test_an_unpushed_run_compares_with_the_checkout_commit(self):
        hist, _, _ = self._main("--mode", "chain", "--chain-outcome", "success", "--published", "false",
                                "--history-rev", "abc123")
        hist.assert_called_once_with("abc123")

    def test_a_github_failure_still_files_linear_and_says_so(self):
        def boom(*a, **k):
            raise OSError("api down")
        _, li, out = self._main("--mode", "chain", "--chain-outcome", "failure", gh=boom)
        li.assert_called_once()
        self.assertIn("github: NOT DELIVERED", out)
        self.assertIn("::error title=week-held alert::", out)

    def test_linear_close_comment_only_when_github_closed_an_issue(self):
        done = dict(status=dict(WEEK9_STATUS, source_vintages={s: {"content_week": 8} for s in SOURCES}))
        _, li, _ = self._main("--mode", "chain", "--chain-outcome", "success", "--published", "true",
                              gh=lambda *a, **k: "github: published; no open issue", **done)
        li.assert_not_called()
        _, li, _ = self._main("--mode", "chain", "--chain-outcome", "success", "--published", "true",
                              gh=lambda *a, **k: "github: closed #5", **done)
        self.assertEqual(li.call_args.args[0], "close")


class ChainStuckReadsCommittedHistory(unittest.TestCase):
    """JEG-1194's alert read the in-run index, which make sync stamps with the
    unpublished candidate's built_at, so it never opened. It must read HEAD."""

    def test_default_history_is_the_committed_copy(self):
        candidate = {"fixture_built_at": NOW.isoformat()}  # what make sync left on disk
        with patch.object(stuck, "committed_history", return_value=PUBLISHED), \
                patch.object(stuck, "_read", side_effect=lambda p: {} if "status" in str(p) else candidate), \
                patch.object(stuck, "run", return_value="x") as run, \
                patch.object(stuck, "datetime") as dt:
            dt.now.return_value = NOW
            stuck.main(["--chain-outcome", "failure", "--published", "true"])
        self.assertEqual(run.call_args.args[0], "open")

    def test_committed_history_reads_git(self):
        doc = stuck.committed_history()
        self.assertIn("served", doc)
        self.assertEqual(wh.committed_history().get("served"), doc.get("served"))


class Workflows(unittest.TestCase):
    def test_chain_escalates_on_main_with_both_tokens(self):
        wf = (ROOT / ".github" / "workflows" / "rebuild-chain.yml").read_text(encoding="utf-8")
        step = wf.split("pipelines/week_held_alert.py --mode chain")[0].rsplit("- name:", 1)[1]
        for needle in ("always()", "refs/heads/main", "secrets.GITHUB_TOKEN", "secrets.LINEAR_API_KEY",
                       "continue-on-error: true", "CHECKOUT_SHA"):
            self.assertIn(needle, step)
        self.assertIn('--history-rev "$rev"', wf)
        self.assertIn("CHECKOUT_SHA=$(git rev-parse HEAD)", wf)
        self.assertLess(wf.index("week_held_alert.py"), wf.index("Fail the job if the chain failed"))

    def test_tripwire_and_drill_run_on_the_hourly_schedule_workflow(self):
        wf = (ROOT / ".github" / "workflows" / "source-lateness.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "50 * * * *"', wf)
        self.assertIn("week_held_alert.py --mode tripwire", wf)
        self.assertIn("week_held_alert.py --mode drill", wf)
        self.assertIn("week_held_drill", wf)


if __name__ == "__main__":
    unittest.main()
