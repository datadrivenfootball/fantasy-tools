"""Post-validation isolation accepts only a named changed source and a green retry."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipelines import isolate_post_validate as iso
from pipelines import rebuild_comparison_chain as chain
from pipelines import record_post_rebuild_validation


def fixture(cbs_value=1, espn_value=1):
    return {"sources": {
        "cbs": {"combos": {"full_12": {"values": {"x": cbs_value}}},
                "week_designated": "Week 8"},
        "espn": {"combos": {"full_12": {"values": {"x": espn_value}}},
                 "week_designated": "Week 8"}},
        "source_validation": {"cbs": {"ok": cbs_value == 1}, "espn": {"ok": True}}}


def fail(message):
    return ("FAIL: test_values (tests.test_source_integrity.TestSource)\n"
            "----------------------------------------------------------------------\n"
            f"AssertionError: {message}\n"
            "Ran 1 test in 0.1s\nFAILED (failures=1)\nmake: *** [test-core] Error 1\n")


class TestAttribution(unittest.TestCase):
    def test_long_alias_does_not_also_name_cbs(self):
        self.assertEqual(iso.failing_roots(fail("CBS rest of season malformed")), {"cbsros"})

    def test_unknown_multiple_or_traceback_only_declined(self):
        for message in ("invalid value", "CBS and ESPN invalid", "cbsros and cbs invalid"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                iso.failing_roots(fail(message))
        log = ("ERROR: test_values (tests.test_source_integrity.TestSource)\n"
               "  File '/tmp/cbs.py', line 1\nValueError: malformed data\n")
        with self.assertRaises(ValueError):
            iso.failing_roots(log)

    def test_every_failure_must_name_same_source(self):
        with self.assertRaises(ValueError):
            iso.failing_roots(fail("cbs malformed") + fail("unknown output"))

    def test_subtest_failure_without_source_cannot_be_ignored(self):
        log = ("FAIL: test_values (tests.test_source_integrity.TestSource.test_values) (case='unknown')\n"
               "----------------------------------------------------------------------\n"
               "AssertionError: invalid output\n"
               "FAIL: test_values (tests.test_source_integrity.TestSource.test_values)\n"
               "----------------------------------------------------------------------\n"
               "AssertionError: CBS invalid values\n"
               "Ran 2 tests in 0.1s\nFAILED (failures=2)\n")
        with self.assertRaisesRegex(ValueError, "attributable sources"):
            iso.failing_roots(log)

    def test_failure_count_must_cover_every_reported_failure(self):
        log = fail("cbs malformed").replace("failures=1", "failures=2")
        with self.assertRaisesRegex(ValueError, "failure count"):
            iso.failing_roots(log)
        with self.assertRaisesRegex(ValueError, "failure count"):
            iso.failing_roots(fail("cbs malformed").replace("FAILED (failures=1)", ""))
        with self.assertRaisesRegex(ValueError, "unattributed unexpected unittest success"):
            iso.failing_roots(fail("cbs malformed").replace(
                "FAILED (failures=1)", "FAILED (failures=1, unexpected successes=1)"))
        with self.assertRaisesRegex(ValueError, "unrecognized unittest failure summary field"):
            iso.failing_roots(fail("cbs malformed").replace(
                "FAILED (failures=1)", "FAILED (failures=1, mystery=1)"))

    def test_two_named_subtests_for_one_source_are_attributed(self):
        log = ("FAIL: test_values (tests.test_source_integrity.TestSource.test_values) (case='one')\n"
               "AssertionError: cbs malformed one\n"
               "FAIL: test_values (tests.test_source_integrity.TestSource.test_values) (case='two')\n"
               "AssertionError: cbs malformed two\n"
               "Ran 1 test in 0.1s\nFAILED (failures=2)\n")
        self.assertEqual(iso.failing_roots(log), {"cbs"})


class TestIsolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.fixture_path = self.repo / chain.FIXTURE_REL
        self.fixture_path.parent.mkdir(parents=True)
        self.fixture_path.write_text(json.dumps(fixture()), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "commit", "-qm", "baseline"], cwd=self.repo, check=True)
        status = {"success": True, "outcome": "green", "held": [], "held_detail": {},
                  "sources": {"cbs": "promoted", "espn": "promoted"},
                  "detail": {"cbs": {"status": "ok", "promoted": 1, "sections": 1},
                             "espn": {"status": "ok", "promoted": 1, "sections": 1}}}
        path = self.repo / iso.STATUS_RELS[0]
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(status), encoding="utf-8")

    def _change(self, cbs=2, espn=1):
        doc = fixture(cbs, espn)
        if cbs != 1:
            doc["sources"]["cbs"]["promoted_at"] = "2026-10-28T12:00:00Z"
            directory = self.repo / chain.PROMOTIONS_REL
            directory.mkdir(parents=True, exist_ok=True)
            record = directory / "cbs-2026-10-28-promotion.json"
            record.write_text(json.dumps({"source_key": "cbs", "promoted_at": "2026-10-28T12:00:00Z",
                                          "review_verdict": "ready",
                                          "section_after_sha256": chain._canonical_sha(doc["sources"]["cbs"])}))
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")

    def _status(self):
        return json.loads((self.repo / iso.STATUS_RELS[0]).read_text(encoding="utf-8"))

    def _assert_incomplete(self, original_fixture):
        self.assertEqual(self.fixture_path.read_bytes(), original_fixture)
        self.assertFalse(self._status()["success"])
        self.assertEqual(self._status()["post_validate_isolation"]["stage"],
                         "isolation_in_progress")
        with self.assertRaisesRegex(ValueError, "no pending"):
            iso.confirm(self.repo)

    def test_bad_cbs_keeps_last_section_and_needs_retry_confirmation(self):
        self._change()
        self.assertEqual(iso.isolate(self.repo, fail("cbs invalid values"), 9), "cbs")
        result = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(result["sources"]["cbs"]["combos"]["full_12"]["values"]["x"], 1)
        self.assertEqual(result["sources"]["espn"], fixture()["sources"]["espn"])
        self.assertEqual(result["source_validation"]["cbs"], {"ok": True})
        self.assertEqual(result["sources"]["cbs"]["validationHold"]["root"], "cbs")
        self.assertFalse(self._status()["success"])
        self.assertEqual(iso.confirm(self.repo), "cbs")
        self.assertEqual(self._status()["outcome"], "published_with_holds")

    def test_unknown_or_unchanged_never_mutates(self):
        self._change()
        original = self.fixture_path.read_bytes()
        for log in (fail("invalid values"), fail("espn invalid values")):
            with self.subTest(log=log), self.assertRaises(ValueError):
                iso.isolate(self.repo, log, 9)
            self.assertEqual(self.fixture_path.read_bytes(), original)

    def test_espn_anchor_is_not_isolated(self):
        self._change(espn=2)
        with self.assertRaisesRegex(ValueError, "shared reindex anchor"):
            iso.isolate(self.repo, fail("espn invalid values"), 9)

    def test_projection_with_shared_players_change_is_not_isolated(self):
        # Simulate a valid earlier cbsros section and players bake in HEAD.
        doc = json.loads(self.fixture_path.read_text())
        doc["sources"]["cbsros"] = {"combos": {"full_12": {"values": {"x": 1}}}}
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        players = self.repo / "data/fixtures/current/players.json"
        players.write_text('{"players":[]}', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "commit", "-qm", "projection baseline"], cwd=self.repo, check=True)
        doc["sources"]["cbsros"]["combos"]["full_12"]["values"]["x"] = 2
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        players.write_text('{"players":[{"player_key":"x"}]}', encoding="utf-8")
        status = self._status()
        status["detail"]["cbsros"] = {"status": "ok", "promoted": 1, "sections": 1}
        status["sources"]["cbsros"] = "promoted"
        (self.repo / iso.STATUS_RELS[0]).write_text(json.dumps(status), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "players.json changed"):
            iso.isolate(self.repo, fail("CBS ROS malformed"), 9)

    def test_leg_restore_failure_rolls_back_and_stays_non_green(self):
        doc = json.loads(self.fixture_path.read_text())
        doc["sources"]["cbsros"] = {"combos": {"full_12": {"values": {"x": 1}}}}
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        players = self.repo / "data/fixtures/current/players.json"
        players.write_text('{"players":[]}', encoding="utf-8")
        leg = (self.repo / "data/ddf-two-tier/ddf-20261028-cbsros-ppr-12t-0p15"
               / "ddf_leg_cbsros.json")
        leg.parent.mkdir(parents=True)
        leg.write_text('{"leg":1}', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "commit", "-qm", "projection baseline"], cwd=self.repo, check=True)
        doc["sources"]["cbsros"]["combos"]["full_12"]["values"]["x"] = 2
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        leg.write_text('{"leg":2}', encoding="utf-8")
        status = self._status()
        status["detail"]["cbsros"] = {"status": "ok", "promoted": 1, "sections": 1}
        status["sources"]["cbsros"] = "promoted"
        (self.repo / iso.STATUS_RELS[0]).write_text(json.dumps(status), encoding="utf-8")
        original = self.fixture_path.read_bytes()
        real = iso.chain._restore_legs
        calls = 0

        def fail_first_legs(repo, root, legs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("DDF leg restore failed")
            return real(repo, root, legs)

        with mock.patch.object(iso.chain, "_restore_legs", side_effect=fail_first_legs):
            with self.assertRaisesRegex(ValueError, "DDF leg restore failed"):
                iso.isolate(self.repo, fail("CBS ROS malformed"), 9)
        self._assert_incomplete(original)
        self.assertEqual(leg.read_text(), '{"leg":2}')

    def test_confirm_requires_hold(self):
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        doc = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        del doc["sources"]["cbs"]["validationHold"]
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hold disappeared"):
            iso.confirm(self.repo)
        self.assertFalse(self._status()["success"])

    def test_confirm_rejects_falsey_malformed_validation_metadata(self):
        baseline = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        del baseline["source_validation"]
        self.fixture_path.write_text(json.dumps(baseline), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "commit", "-qm", "baseline without validation"], cwd=self.repo, check=True)
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        doc = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        doc["source_validation"] = []
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "validation metadata changed"):
            iso.confirm(self.repo)
        self.assertFalse(self._status()["success"])

    def test_failed_retry_stays_blocked(self):
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        record_post_rebuild_validation.record(self.repo, fail("unknown later failure"))
        with self.assertRaisesRegex(ValueError, "no pending"):
            iso.confirm(self.repo)
        self.assertEqual(self._status()["outcome"], "failed")

    def test_matching_promotion_record_is_retired(self):
        self._change()
        doc = json.loads(self.fixture_path.read_text())
        directory = self.repo / chain.PROMOTIONS_REL
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / "cbs-2026-10-28-promotion.json"
        record.write_text(json.dumps({"source_key": "cbs", "promoted_at": "2026-10-28T12:00:00Z",
                                      "review_verdict": "ready",
                                      # The shared reindex changes the section hash later.
                                      "section_after_sha256": "0" * 64}))
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertFalse(record.exists())
        self.assertTrue(record.with_name("cbs-2026-10-28-promotion.rolled-back.json").exists())

    def test_unmatched_promotion_record_declines_without_changes(self):
        self._change()
        directory = self.repo / chain.PROMOTIONS_REL
        directory.mkdir(parents=True, exist_ok=True)
        record = directory / "cbs-2026-10-28-promotion.json"
        record.write_text(json.dumps({"source_key": "cbs", "promoted_at": "different",
                                      "section_after_sha256": "wrong"}))
        original = self.fixture_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot be identified"):
            iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertEqual(self.fixture_path.read_bytes(), original)

    def test_existing_rolled_back_record_is_not_overwritten(self):
        self._change()
        record = self.repo / chain.PROMOTIONS_REL / "cbs-2026-10-28-promotion.json"
        target = record.with_name("cbs-2026-10-28-promotion.rolled-back.json")
        target.write_text("prior rollback", encoding="utf-8")
        original = self.fixture_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertEqual(self.fixture_path.read_bytes(), original)
        self.assertEqual(target.read_text(encoding="utf-8"), "prior rollback")
        self.assertTrue(self._status()["success"])

    def test_dangling_rolled_back_record_symlink_is_not_overwritten(self):
        self._change()
        record = self.repo / chain.PROMOTIONS_REL / "cbs-2026-10-28-promotion.json"
        target = record.with_name("cbs-2026-10-28-promotion.rolled-back.json")
        target.symlink_to("missing-prior-rollback.json")
        original = self.fixture_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertEqual(self.fixture_path.read_bytes(), original)
        self.assertTrue(target.is_symlink())
        self.assertTrue(self._status()["success"])

    def test_pending_status_write_failure_does_not_touch_fixture(self):
        self._change()
        original = self.fixture_path.read_bytes()
        real = iso._atomic_write_bytes

        def fail_output_status(path, data):
            if path == self.repo / iso.STATUS_RELS[0]:
                raise OSError("status output unavailable")
            return real(path, data)

        with mock.patch.object(iso, "_atomic_write_bytes", side_effect=fail_output_status):
            with self.assertRaisesRegex(OSError, "status output unavailable"):
                iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertEqual(self.fixture_path.read_bytes(), original)
        self.assertTrue(self._status()["success"])

    def test_fixture_replace_failure_leaves_status_non_green(self):
        self._change()
        original = self.fixture_path.read_bytes()
        real = iso._atomic_write_bytes
        attempts = 0

        def fail_first_fixture(path, data):
            nonlocal attempts
            if path == self.fixture_path:
                attempts += 1
                if attempts == 1:
                    raise OSError("fixture replace failed")
            return real(path, data)

        with mock.patch.object(iso, "_atomic_write_bytes", side_effect=fail_first_fixture):
            with self.assertRaisesRegex(ValueError, "fixture replace failed"):
                iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self._assert_incomplete(original)

    def test_fixture_verification_failure_rolls_back_and_stays_non_green(self):
        self._change()
        original = self.fixture_path.read_bytes()
        with mock.patch.object(iso.chain, "_read_fixture", return_value={"sources": {"cbs": {}}}):
            with self.assertRaisesRegex(ValueError, "could not be verified"):
                iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self._assert_incomplete(original)

    def test_promotion_rename_failure_rolls_back_and_stays_non_green(self):
        self._change()
        original = self.fixture_path.read_bytes()
        record = self.repo / chain.PROMOTIONS_REL / "cbs-2026-10-28-promotion.json"
        real = Path.rename

        def fail_promotion(path, target):
            if path == record:
                raise OSError("promotion rename failed")
            return real(path, target)

        with mock.patch.object(Path, "rename", fail_promotion):
            with self.assertRaisesRegex(ValueError, "promotion rename failed"):
                iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self._assert_incomplete(original)
        self.assertTrue(record.is_file())

    def test_ready_status_failure_rolls_back_and_stays_non_green(self):
        self._change()
        original = self.fixture_path.read_bytes()
        real = iso._write_status
        calls = 0

        def fail_second_status(repo, status):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("retry status unavailable")
            return real(repo, status)

        with mock.patch.object(iso, "_write_status", side_effect=fail_second_status):
            with self.assertRaisesRegex(ValueError, "retry status unavailable"):
                iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self._assert_incomplete(original)

    def test_failed_rollback_still_cannot_leave_green_status(self):
        self._change()
        real_write = iso._atomic_write_bytes
        real_rename = Path.rename
        fixture_writes = 0

        def fail_rollback_write(path, data):
            nonlocal fixture_writes
            if path == self.fixture_path:
                fixture_writes += 1
                if fixture_writes == 2:
                    raise OSError("fixture rollback failed")
            return real_write(path, data)

        def fail_rename(path, target):
            if path.name.endswith("-promotion.json"):
                raise OSError("promotion rename failed")
            return real_rename(path, target)

        with mock.patch.object(iso, "_atomic_write_bytes", side_effect=fail_rollback_write):
            with mock.patch.object(Path, "rename", fail_rename):
                with self.assertRaisesRegex(ValueError, "rollback incomplete"):
                    iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertFalse(self._status()["success"])
        self.assertEqual(self._status()["post_validate_isolation"]["stage"],
                         "isolation_in_progress")
        with self.assertRaisesRegex(ValueError, "no pending"):
            iso.confirm(self.repo)

    def test_lost_status_ack_and_failed_rollback_cannot_confirm(self):
        self._change()
        real_status = iso._write_status
        real_write = iso._atomic_write_bytes
        status_writes = 0
        fixture_writes = 0

        def write_then_lose_ack(repo, status):
            nonlocal status_writes
            status_writes += 1
            real_status(repo, status)
            if status_writes == 2:
                raise OSError("lost status acknowledgement")

        def fail_fixture_rollback(path, data):
            nonlocal fixture_writes
            if path == self.fixture_path:
                fixture_writes += 1
                if fixture_writes == 2:
                    raise OSError("fixture rollback failed")
            return real_write(path, data)

        with mock.patch.object(iso, "_write_status", side_effect=write_then_lose_ack):
            with mock.patch.object(iso, "_atomic_write_bytes", side_effect=fail_fixture_rollback):
                with self.assertRaisesRegex(ValueError, "rollback incomplete"):
                    iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertEqual(self._status()["post_validate_isolation"]["stage"], "retry_pending")
        self.assertFalse(self._status()["success"])
        with self.assertRaisesRegex(ValueError, "promotion was not retired"):
            iso.confirm(self.repo)
        self.assertFalse(self._status()["success"])

    def test_corrected_save_releases_only_post_validate_hold(self):
        self._change()
        iso.isolate(self.repo, fail("cbs invalid values"), 9)
        self.assertTrue(chain.release_post_validate_hold(self.repo, "cbs"))
        doc = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.assertNotIn("validationHold", doc["sources"]["cbs"])
        doc["sources"]["espn"]["validationHold"] = {"reason": "fidelity: bad", "root": "espn"}
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")
        self.assertFalse(chain.release_post_validate_hold(self.repo, "espn"))
        self.assertIn("validationHold", json.loads(self.fixture_path.read_text())["sources"]["espn"])


if __name__ == "__main__":
    unittest.main()


class TestRecoveryHoldIsReindexed(unittest.TestCase):
    """JEG-1700 (Jeremy, 2026-11-25, "Re-index after a recovery hold"): a post-validate
    recovery hold restores the last published section, which was indexed on the
    anchor of the run that published it (JEG-1583). isolate() re-indexes it on this
    run's ESPN leg, so the static-export held-chart checks (25% band) hold however far
    the anchor stepped: real steps reach 29-33% (2026-10-17 rebuild) and week-long gaps 30%."""

    SLUGS = {"qb-a": (1, "QB"), "qb-b": (2, "QB"), "rb-a": (3, "RB"), "rb-b": (4, "RB"),
             "wr-a": (5, "WR"), "wr-b": (6, "WR"), "te-a": (7, "TE"), "te-b": (8, "TE")}
    NATIVE = {"qb-a": 60, "qb-b": 40, "rb-a": 80, "rb-b": 50, "wr-a": 70, "wr-b": 45, "te-a": 30, "te-b": 20}
    ESPN = {"qb-a": 30.0, "qb-b": 20.0, "rb-a": 40.0, "rb-b": 25.0, "wr-a": 35.0, "wr-b": 22.0,
            "te-a": 15.0, "te-b": 10.0}

    def _doc(self, espn_scale, cbs_native_scale=1.0):
        from pipelines.reindex_published_fixture import reindex_fixture
        doc = {"player_keys": {s: k for s, (k, _) in self.SLUGS.items()},
               "sources": {
                   "espn": {"combos": {"full_12": {"values": {s: v * espn_scale for s, v in self.ESPN.items()}}},
                            "week_designated": "Week 8"},
                   "cbs": {"combos": {"full_12": {"native": {s: v * cbs_native_scale for s, v in self.NATIVE.items()}}},
                           "week_designated": "Week 8"}},
               "source_validation": {"cbs": {"ok": cbs_native_scale == 1.0}, "espn": {"ok": True}}}
        reindex_fixture(doc, self.players)
        if cbs_native_scale != 1.0:
            doc["sources"]["cbs"]["promoted_at"] = "2026-11-25T03:00:00Z"
        return doc

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.players = {"players": [{"player_key": k, "pos": pos} for k, pos in self.SLUGS.values()]}
        players_path = self.repo / "data/fixtures/current/players.json"
        players_path.parent.mkdir(parents=True)
        players_path.write_text(json.dumps(self.players), encoding="utf-8")
        self.fixture_path = self.repo / chain.FIXTURE_REL
        # Published: CBS indexed on last week's ESPN anchor.
        self.fixture_path.write_text(json.dumps(self._doc(1.0)), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                        "commit", "-qm", "baseline"], cwd=self.repo, check=True)
        status = {"success": True, "outcome": "green", "held": [], "held_detail": {},
                  "sources": {"cbs": "promoted", "espn": "promoted"},
                  "detail": {"cbs": {"status": "ok", "promoted": 1, "sections": 1},
                             "espn": {"status": "ok", "promoted": 1, "sections": 1}}}
        path = self.repo / iso.STATUS_RELS[0]
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(status), encoding="utf-8")

    def _stage_anchor_step(self, step):
        # This run: ESPN's anchor stepped by `step` and a changed CBS save fails post-validate.
        doc = self._doc(1.0 - step, cbs_native_scale=1.1)
        directory = self.repo / chain.PROMOTIONS_REL
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "cbs-2026-11-25-promotion.json").write_text(json.dumps({
            "source_key": "cbs", "promoted_at": doc["sources"]["cbs"]["promoted_at"], "review_verdict": "ready",
            "section_after_sha256": chain._canonical_sha(doc["sources"]["cbs"])}))
        self.fixture_path.write_text(json.dumps(doc), encoding="utf-8")

    def _isolate_after_anchor_step(self, step):
        self._stage_anchor_step(step)
        self.assertEqual(iso.isolate(self.repo, fail("CBS invalid values"), 9), "cbs")
        return json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def test_held_chart_sits_on_todays_anchor_after_a_30_percent_step(self):
        from tests.test_static_export import held_pie_problems
        doc = self._isolate_after_anchor_step(0.30)
        cbs = doc["sources"]["cbs"]
        combo = cbs["combos"]["full_12"]
        self.assertEqual(cbs["validationHold"]["stage"], "post_validate")
        self.assertEqual(combo["native"], self.NATIVE, "the published natives are kept")
        today = sum(v * 0.70 for v in self.ESPN.values())
        self.assertAlmostEqual(sum(combo["reindexed"].values()), today, delta=0.05)
        self.assertEqual(held_pie_problems(doc, "cbs", "full_12", combo), [])
        # The order the chart publishes is unchanged by the re-index.
        order = lambda d: sorted(d, key=lambda s: -d[s])
        self.assertEqual(order(combo["reindexed"]), order(self.NATIVE))
        self.assertEqual(iso.confirm(self.repo), "cbs")

    def test_without_the_reindex_the_band_would_reblock(self):
        from tests.test_static_export import held_pie_problems
        with mock.patch.object(iso, "_reindex_on_todays_anchor"):
            doc = self._isolate_after_anchor_step(0.30)
        combo = doc["sources"]["cbs"]["combos"]["full_12"]
        self.assertTrue(any("within 25%" in p for p in held_pie_problems(doc, "cbs", "full_12", combo)))

    def test_the_band_still_catches_a_halved_held_chart(self):
        from tests.test_static_export import held_pie_problems
        doc = self._isolate_after_anchor_step(0.30)
        combo = doc["sources"]["cbs"]["combos"]["full_12"]
        combo["reindexed"] = {s: v * 0.5 for s, v in combo["reindexed"].items()}
        for t in combo["index_total"].values():
            t["target_total"] *= 0.5
        self.assertTrue(any("within 25%" in p for p in held_pie_problems(doc, "cbs", "full_12", combo)))

    def test_a_chart_that_cannot_be_reindexed_declines_recovery(self):
        self._stage_anchor_step(0.30)
        before = self.fixture_path.read_bytes()
        (self.repo / "data/fixtures/current/players.json").write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "players.json is unavailable"):
            iso.isolate(self.repo, fail("CBS invalid values"), 9)
        self.assertEqual(self.fixture_path.read_bytes(), before)
