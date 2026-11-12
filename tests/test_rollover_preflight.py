"""Week 10 rollover retro (2026-11-12): the Tuesday pre-flight's verdicts.
Pure functions on canned inputs; no network, gh or browser."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
import rollover_preflight as P  # noqa: E402

NOW = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)


class PagesCheck(unittest.TestCase):
    def test_a_failed_run_that_deployed_passes(self):
        # Decision A: run 42942807394 failed on test-core shards but deployed Week 10.
        runs = [{"databaseId": 1, "headSha": "676afdf18aa", "jobs": [
            {"name": "validate-shard (1)", "conclusion": "failure"}, {"name": "deploy", "conclusion": "success"}]}]
        self.assertEqual(P.check_pages(runs)[0], "PASS")

    def test_a_failed_deploy_fails(self):
        runs = [{"databaseId": 2, "headSha": "x", "jobs": [{"name": "deploy", "conclusion": "failure"}]}]
        self.assertEqual(P.check_pages(runs)[0], "FAIL")

    def test_skipped_deploys_are_passed_over_for_the_newest_finished_one(self):
        runs = [{"databaseId": 3, "headSha": "a", "jobs": [{"name": "deploy", "conclusion": "skipped"}]},
                {"databaseId": 4, "headSha": "b", "jobs": [{"name": "deploy", "conclusion": "failure"}]}]
        verdict, msg = P.check_pages(runs)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("run 4", msg)

    def test_no_deploy_at_all_fails(self):
        self.assertEqual(P.check_pages([{"databaseId": 5, "jobs": []}])[0], "FAIL")


class ChainCheck(unittest.TestCase):
    def run_(self, conclusion, hours_ago):
        return {"databaseId": hours_ago, "conclusion": conclusion,
                "createdAt": (NOW.replace(microsecond=0) - __import__("datetime").timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")}

    def test_newest_success_with_few_failures_passes(self):
        self.assertEqual(P.check_chain([self.run_("success", 1), self.run_("failure", 2)], NOW)[0], "PASS")

    def test_newest_failure_fails(self):
        self.assertEqual(P.check_chain([self.run_("failure", 1), self.run_("success", 2)], NOW)[0], "FAIL")

    def test_flapping_chain_fails_even_when_newest_is_green(self):
        # 2026-11-12: the chain alternated green and red for eight hours.
        runs = [self.run_("success", 1)] + [self.run_("failure", h) for h in (2, 3, 4)]
        self.assertEqual(P.check_chain(runs, NOW)[0], "FAIL")

    def test_old_failures_do_not_count(self):
        runs = [self.run_("success", 1)] + [self.run_("failure", h) for h in (13, 14, 15)]
        self.assertEqual(P.check_chain(runs, NOW)[0], "PASS")

    def test_no_runs_fails(self):
        self.assertEqual(P.check_chain([], NOW)[0], "FAIL")


class LiveAndConnector(unittest.TestCase):
    STATUS = {"nfl_week": 10, "held": ["espn"], "run_at": "t",
              "source_weeks": {"cbs": {"served_week": 10}, "fantasypros": {"served_week": 10}}}

    def test_previous_week_fully_live_before_the_flip_passes(self):
        self.assertEqual(P.check_live(self.STATUS, 11)[0], "PASS")

    def test_a_source_two_weeks_behind_fails(self):
        status = {**self.STATUS, "source_weeks": {"cbs": {"served_week": 9}, "fantasypros": {"served_week": 10}}}
        verdict, msg, _ = P.check_live(status, 11)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("cbs", msg)

    def test_holds_are_reported_not_failed(self):
        verdict, msg, week = P.check_live(self.STATUS, 10)
        self.assertEqual((verdict, week), ("PASS", 10))
        self.assertIn("espn", msg)

    def test_connector_must_match_the_site(self):
        self.assertEqual(P.check_connector({"default_week": 10}, 10)[0], "PASS")
        self.assertEqual(P.check_connector({"default_week": 9}, 10)[0], "FAIL")
        self.assertEqual(P.check_connector({"default_week": 10}, None)[0], "FAIL")


if __name__ == "__main__":
    unittest.main()
