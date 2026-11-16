"""JEG-1641 weekly projection warehouse: row builders, savers, freshness check, migration.

Offline only (no network, no database): fake payloads, a fake Supabase client
and the migration text.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import check_projection_warehouse as chk  # noqa: E402
import espn_weekly as ew  # noqa: E402
import projection_warehouse as pw  # noqa: E402
import save_espn_weekly as sew  # noqa: E402
import save_projection_warehouse as spw  # noqa: E402
from player_key_index import PlayerIndex  # noqa: E402

MIGRATION = ROOT / "supabase" / "migrations" / "jeg1641_weekly_projection_warehouse_20261114.sql"
COMMON = {"run_id": "r1", "as_of": "2026-11-14T13:30:00+00:00", "season": 2026}

PLAYERS = [
    {"id": "u1", "player_key": 11, "full_name": "Josh Allen", "position": "QB", "active": True,
     "metadata": {"sleeper_id": "4984", "gsis_id": "00-0034857"}},
    {"id": "u2", "player_key": 22, "full_name": "Will Mallory", "position": "TE", "active": True,
     "metadata": {"sleeper_id": "10220"}},
]
BASE = {"by_sleeper_id": {"4984": {"gsis_id": "00-0034857", "espn_id": "3918298", "name": "Josh Allen"},
                          "10220": {"gsis_id": "00-0039000", "name": "Will Mallory"}}}


def index():
    return PlayerIndex(PLAYERS, BASE)


def sleeper_entry(pid, pos, stats, first="Josh", last="Allen"):
    return {"player_id": pid, "team": "BUF", "opponent": "NYJ", "company": "rotowire",
            "updated_at": 1794663614603, "stats": stats,
            "player": {"first_name": first, "last_name": last, "position": pos}}


class SleeperRows(unittest.TestCase):
    def test_keeps_points_rows_future_weeks_and_skill_positions_only(self):
        payload = {
            9: [sleeper_entry("4984", "QB", {"pts_ppr": 20.1})],                       # past week
            10: [sleeper_entry("4984", "QB", {"pts_std": 19.0, "pts_half_ppr": 19.0, "pts_ppr": 19.0,
                                              "pass_yd": 251.3}),
                 sleeper_entry("777", "K", {"pts_std": 8.0}),                           # kicker
                 sleeper_entry("888", "WR", {"adp_dd_ppr": 120}),                       # ADP only
                 sleeper_entry("999", "RB", {"pts_ppr": 0.0}, "Hurt", "Back")],         # projected 0
        }
        rows, rep = pw.sleeper_rows(payload, index(), content_week=10, **COMMON)
        self.assertEqual([(r["source_player_id"], r["target_week"]) for r in rows], [("4984", 10), ("999", 10)])
        allen, hurt = rows
        self.assertEqual(allen["player_key"], 11)
        self.assertEqual(allen["stats"]["pass_yd"], 251.3)
        self.assertEqual(allen["stats"]["_company"], "rotowire")
        self.assertEqual(allen["coverage"], "every_week")
        # a format Sleeper did not give is null, never 0; a real 0 stays 0
        self.assertIsNone(hurt["points_std"])
        self.assertEqual(hurt["points_ppr"], 0.0)
        self.assertIsNone(hurt["player_key"])  # unresolved, still stored
        self.assertEqual(rep["unresolved_rows"], 1)


class EspnRows(unittest.TestCase):
    def test_future_weeks_three_formats_and_applied_total(self):
        stats = {"passing_yards": 250, "passing_tds": 2, "receptions": 0}
        rows_in = [{"espn_id": "3918298", "name": "Josh Allen", "pos": "QB", "team": "BUF", "week": w,
                    "season": 2026, "stats": stats, "applied_total": 21.5} for w in (9, 10, 18)]
        rows, _ = pw.espn_rows(rows_in, index(), content_week=10, points_fn=ew.points, **COMMON)
        self.assertEqual([r["target_week"] for r in rows], [10, 18])
        r = rows[0]
        self.assertEqual((r["player_key"], r["sleeper_id"], r["source_points"]), (11, "4984", 21.5))
        self.assertEqual(r["points_std"], round(ew.points(stats, "standard"), 2))
        self.assertIn("appliedTotal", r["scoring_basis"])

    def test_weekly_rows_carry_espn_applied_total(self):
        payload = {"QB": [{"player": {"id": 1, "fullName": "A B", "defaultPositionId": 1, "proTeamId": 2,
                                      "stats": [{"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1,
                                                 "scoringPeriodId": 11, "appliedTotal": 17.25,
                                                 "stats": {"3": 200}},
                                                {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1,
                                                 "scoringPeriodId": 12, "stats": {"3": 210}}]}}]}
        rows, _ = ew.weekly_rows(payload, ew.PROJECTION, {2: "BUF"})
        self.assertEqual([(r["week"], r["applied_total"]) for r in rows], [(11, 17.25), (12, None)])


class Cbs(unittest.TestCase):
    def test_cbs_rows_tagged_with_the_served_week(self):
        weekly = {"weeks": {"9": [{"player_name": "Josh Allen", "player_norm": "josh allen", "pos": "QB",
                                   "team": "BUF", "points_standard": 1, "points_half_ppr": 1, "points_ppr": 1}],
                            "10": [{"player_name": "Josh Allen", "player_norm": "josh allen", "pos": "QB",
                                    "team": "BUF", "points_standard": 22.4, "points_half_ppr": 22.4,
                                    "points_ppr": 22.4}]}}
        rows, _ = pw.cbs_rows(weekly, index(), content_week=10, **COMMON)
        self.assertEqual([(r["target_week"], r["player_key"], r["coverage"], r["source_player_id"])
                          for r in rows], [(10, 11, "current_week", "josh allen|QB|BUF")])


SCHEDULE_CSV = """game_id,season,game_type,week,gameday,gametime,away_team,away_score,home_team,home_score,spread_line,total_line
2025_01_A_B,2025,REG,1,2025-09-07,13:00,A,,B,,,
2026_01_A_B,2026,REG,1,2026-09-13,13:00,A,20,B,17,3,44.5
2026_02_A_C,2026,REG,2,2026-09-20,13:00,A,,C,,,
2026_02_B_D,2026,REG,2,2026-09-20,13:00,B,,D,,,
"""

INJURY_CSV = """season,season_type,game_type,team,week,gsis_id,position,full_name,first_name,last_name,report_primary_injury,report_secondary_injury,report_status,practice_primary_injury,practice_secondary_injury,practice_status
2026,REG,REG,BUF,9,00-0034857,QB,Josh Allen,Josh,Allen,Ankle,,Questionable,Ankle,,Limited
2026,REG,REG,BUF,10,00-0034857,QB,Josh Allen,Josh,Allen,,,,Rest,,Full
2026,REG,REG,BUF,10,00-0099999,LB,Some Backer,Some,Backer,Knee,,Out,Knee,,DNP
2026,REG,REG,IND,10,00-0039000,TE,Will Mallory,Will,Mallory,Hamstring,,Questionable,Hamstring,,Limited
"""


class Nflverse(unittest.TestCase):
    def test_schedule_season_only_and_byes(self):
        rows = pw.schedule_rows(SCHEDULE_CSV, **COMMON)
        self.assertEqual([g["game_id"] for g in rows], ["2026_01_A_B", "2026_02_A_C", "2026_02_B_D"])
        self.assertEqual(rows[0]["spread_line"], 3.0)
        self.assertIsNone(rows[1]["away_score"])
        self.assertEqual(pw.byes(rows, last_week=2), {"A": [], "B": [], "C": [1], "D": [1]})

    def test_injuries_latest_week_skill_positions_with_ids(self):
        rows, rep = pw.injury_rows(INJURY_CSV, index(), pw.gsis_to_sleeper(BASE), **COMMON)
        self.assertEqual(rep["report_week"], 10)
        self.assertEqual([(r["gsis_id"], r["player_key"], r["sleeper_id"]) for r in rows],
                         [("00-0034857", 11, "4984"), ("00-0039000", 22, "10220")])  # Mallory by name
        self.assertIsNone(rows[0]["report_status"])  # blank is null, not ''


class FloorsAndDedupe(unittest.TestCase):
    def test_floor_per_week(self):
        rows = [{"target_week": 10}] * 250 + [{"target_week": 11}] * 199
        self.assertEqual(pw.floor_problems("sleeper", rows), ["sleeper week 11: 199 rows (floor 200)"])

    def test_dedupe_first_wins_and_drops_empty(self):
        a = pw.projection_row(source="cbs", target_week=10, source_player_id="x", player_key=None,
                              sleeper_id=None, full_name="X", position="QB", points_std=1,
                              content_week=10, **COMMON)
        b = dict(a, points_std=2)
        empty = dict(a, source_player_id="y", points_std=None, points_half_ppr=None, points_ppr=None)
        self.assertEqual(pw.dedupe([a, b, empty]), [a])


class FakeSb:
    def __init__(self, runs=None, sizes=None, fail_on=None):
        self.posts, self.runs, self.sizes, self.fail_on = [], runs or {}, sizes or [], fail_on

    def post(self, table, rows, params="", prefer=""):
        if self.fail_on == table:
            raise RuntimeError("boom")
        self.posts.append((table, len(rows), prefer))

    def get(self, table, params=""):
        src = params.split("source=eq.")[1].split("&")[0]
        return [self.runs[src]] if src in self.runs else []

    def rpc(self, fn, payload):
        return self.sizes

    def get_all(self, table, *a, **k):
        return PLAYERS if table == "players" else []


class EspnSaverWarehouse(unittest.TestCase):
    def _rows(self, n, wk=10):
        return [pw.projection_row(source="espn", target_week=wk, source_player_id=str(i), player_key=None,
                                  sleeper_id=None, full_name="p", position="WR", points_std=1.0,
                                  content_week=10, **COMMON) for i in range(n)]

    def test_rows_then_run_row_plain_inserts(self):
        sb, rep = FakeSb(), {}
        self.assertFalse(sew.write_warehouse(sb, self._rows(300), rep, 2026, 10, COMMON["as_of"]))
        self.assertEqual([p[0] for p in sb.posts], ["source_weekly_projections"] + ["source_projection_runs"])
        self.assertTrue(all("merge-duplicates" not in p[2] for p in sb.posts))
        self.assertEqual(rep["written"], 300)

    def test_short_pull_writes_nothing(self):
        sb, rep = FakeSb(), {}
        self.assertTrue(sew.write_warehouse(sb, self._rows(299), rep, 2026, 10, COMMON["as_of"]))
        self.assertEqual(sb.posts, [])
        self.assertIn("floor 300", rep["error"])


class EspnSaverMain(unittest.TestCase):
    """The warehouse append runs after the existing ESPN writes and a fault in
    it fails the run (exit 1) without holding them back."""

    def _main(self, sb, today=None):
        import tempfile
        d = Path(tempfile.mkdtemp())
        proj_rows = [{"espn_id": str(i), "name": f"P{i}", "pos": "WR", "team": "BUF", "week": 10,
                      "season": 2026, "stats": {"receptions": 3}, "applied_total": 5.0} for i in range(400)]
        (d / "espn_weekly_actuals.json").write_text(json.dumps({"season": 2026, "rows": []}))
        (d / "espn_weekly_projections.json").write_text(json.dumps(
            {"season": 2026, "rows": proj_rows, "played_weeks": [1], "ros_weeks": [10]}))
        act_rep = {"resolved": 10, "n_no_game": 0, "rows_in": 10, "to_upsert": 1,
                   "comparison_with_existing": {"by_position": {}}}
        patches = [
            mock.patch.object(sew, "_sb", return_value=sb),
            mock.patch.object(sew, "game_index", return_value={}),
            mock.patch.object(sew, "plan_actuals", return_value=([{"a": 1}], act_rep)),
            mock.patch.object(sew, "plan_projections", return_value=([{"p": 1}], {"rows_written": 1})),
            mock.patch.object(sew, "plan_captures", return_value=([], {})),
            mock.patch.object(sew, "content_week", return_value=10),
            mock.patch.object(sew.pc, "capture_exists", return_value=True),
        ]
        if today:
            patches.append(mock.patch.object(sew.pw, "SEASON_END", today))
        with contextlib.ExitStack() as st:
            for pt in patches:
                st.enter_context(pt)
            st.enter_context(redirect_stdout(io.StringIO()))
            st.enter_context(redirect_stderr(io.StringIO()))
            rc = sew.main(["--in", str(d), "--summary", str(d / "s.json")])
        return rc, json.loads((d / "s.json").read_text())

    def test_warehouse_fault_fails_run_after_existing_writes(self):
        sb = FakeSb(fail_on="source_weekly_projections")
        rc, summary = self._main(sb)
        self.assertEqual(rc, 1)
        self.assertEqual([p[0] for p in sb.posts], ["player_game_stats", "projection_snapshots"])
        self.assertIn("boom", summary["warehouse"]["error"])

    def test_warehouse_appends_after_existing_writes(self):
        sb = FakeSb()
        rc, summary = self._main(sb)
        self.assertEqual(rc, 0)
        self.assertEqual([p[0] for p in sb.posts], ["player_game_stats", "projection_snapshots",
                                                    "source_weekly_projections", "source_projection_runs"])
        self.assertEqual(summary["warehouse"]["rows_by_week"], {"10": 400})

    def test_nothing_due_after_the_season(self):
        from datetime import date  # noqa: PLC0415
        sb = FakeSb()
        rc, summary = self._main(sb, today=date(2000, 1, 1))
        self.assertEqual(rc, 0)
        self.assertNotIn("source_weekly_projections", [p[0] for p in sb.posts])
        self.assertIn("note", summary["warehouse"])


class WarehouseSaver(unittest.TestCase):
    def _run(self, built, sb, argv=("--sources", "sleeper,cbs")):
        def fake_build(source, *a, **k):
            if isinstance(built[source], Exception):
                raise built[source]
            return built[source]
        out = Path(self.tmp) / "s.json"
        with mock.patch.object(spw, "build", side_effect=fake_build), \
                mock.patch.object(spw, "_sb", return_value=sb), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = spw.main([*argv, "--summary", str(out)])
        return rc, json.loads(out.read_text())

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def test_failed_source_writes_no_run_row_others_still_land(self):
        good = ("source_weekly_projections", [{"target_week": 10}] * 250, {}, [])
        sb = FakeSb()
        rc, summary = self._run({"sleeper": RuntimeError("HTTP 500"), "cbs": good}, sb)
        self.assertEqual(rc, 1)
        self.assertEqual(summary["failed"], ["sleeper"])
        self.assertEqual([p[0] for p in sb.posts], ["source_weekly_projections", "source_projection_runs"])

    def test_floor_problem_writes_nothing_for_that_source(self):
        short = ("source_weekly_projections", [{"target_week": 10}] * 5, {}, ["sleeper week 10: 5 rows (floor 200)"])
        sb = FakeSb()
        rc, _ = self._run({"sleeper": short}, sb, ("--sources", "sleeper"))
        self.assertEqual((rc, sb.posts), (1, []))

    def test_current_week_source_with_no_week_yet_records_an_empty_run(self):
        sb = FakeSb()
        rc, _ = self._run({"cbs": ("source_weekly_projections", [], {"not_offered_weeks": [10]}, [])},
                          sb, ("--sources", "cbs"))
        self.assertEqual(rc, 0)
        self.assertEqual(sb.posts, [("source_projection_runs", 1, "return=minimal")])

    def test_dry_run_writes_nothing(self):
        good = ("source_weekly_projections", [{"target_week": 10}] * 250, {}, [])
        sb = FakeSb()
        rc, _ = self._run({"sleeper": good}, sb, ("--sources", "sleeper", "--dry-run"))
        self.assertEqual((rc, sb.posts), (0, []))


NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def fresh_runs(hours=2.0):
    return {s: {"as_of": (NOW - timedelta(hours=hours)).isoformat(), "rows_written": 1} for s in chk.RULES}


class Freshness(unittest.TestCase):
    def test_all_fresh(self):
        rep = chk.judge(fresh_runs(), {"database": 1_200_000_000, "source_weekly_projections": 10}, NOW)
        self.assertFalse(chk.problem(rep))

    def test_stale_and_missing_sources_alert(self):
        runs = fresh_runs()
        runs["sleeper"]["as_of"] = (NOW - timedelta(hours=27)).isoformat()
        del runs["nflverse_injuries"]
        rep = chk.judge(runs, {}, NOW)
        self.assertEqual(rep["stale"], ["sleeper", "nflverse_injuries"])
        self.assertTrue(chk.problem(rep))

    def test_fantasypros_dropped_never_checked_or_saved(self):
        # Jeremy 2026-11-14: FantasyPros dropped (anonymous page = top 10 per position)
        self.assertNotIn("fantasypros", chk.RULES)
        self.assertNotIn("fantasypros", spw.SOURCES)
        self.assertNotIn("fantasypros", pw.SCORING_BASIS)
        rep = chk.judge(fresh_runs(), {}, NOW)
        self.assertNotIn("fantasypros", rep["sources"])
        self.assertFalse(chk.problem(rep))

    def test_offseason_nothing_due(self):
        rep = chk.judge({}, {}, datetime(2027, 2, 1, tzinfo=timezone.utc))
        self.assertFalse(chk.problem(rep))

    def test_size_lines(self):
        rep = chk.judge(fresh_runs(), {"database": chk.DB_ALERT_BYTES + 1,
                                       "source_weekly_projections": chk.WAREHOUSE_ALERT_BYTES + 1}, NOW)
        self.assertEqual(len(rep["over_size"]), 2)

    def test_main_exit_codes(self):
        stale = fresh_runs()
        stale["espn"]["as_of"] = (NOW - timedelta(hours=30)).isoformat()
        fake = FakeSb(runs=stale, sizes=[{"relation": "database", "bytes": 1}])
        with mock.patch.dict(sys.modules, {"sbclient": fake}), \
                mock.patch.object(chk, "datetime", wraps=datetime) as dt, redirect_stdout(io.StringIO()):
            dt.now.return_value = NOW
            self.assertEqual(chk.main([]), 1)
            self.assertEqual(chk.main(["--alert"]), 0)  # no token: dry alert, the issue is the alert

    def test_alert_opens_then_closes(self):
        calls = []

        def call(method, path, token, payload=None):
            calls.append((method, path))
            if method == "GET":
                return [{"number": 7, "title": chk.TITLE, "labels": [], "body": "", "updated_at": None}] \
                    if any(c[0] == "PATCH" for c in calls) else []
            return {"number": 7}
        stale = chk.judge({}, {}, NOW)
        self.assertEqual(chk.alert(stale, "o/r", "t", NOW, call), "opened #7")
        calls.append(("PATCH", "x"))
        self.assertEqual(chk.alert(chk.judge(fresh_runs(), {}, NOW), "o/r", "t", NOW, call), "closed #7")


class Migration(unittest.TestCase):
    sql = MIGRATION.read_text()
    tables = ("source_projection_runs", "source_weekly_projections",
              "nflverse_schedule_snapshots", "nflverse_injury_snapshots")

    def test_tables_are_append_only_rls_service_role(self):
        for t in self.tables:
            self.assertIn(f"create table if not exists public.{t}", self.sql)
            self.assertIn(f"'{t}'", self.sql.split("foreach t in array")[1].split("loop")[0])
        self.assertIn("before update or delete", self.sql)
        self.assertIn("before truncate", self.sql)
        self.assertIn("enable row level security", self.sql)
        self.assertIn("revoke all on public.%I from anon, authenticated", self.sql)

    def test_no_ros_rows_and_weekly_only(self):
        self.assertNotIn("'ros'", self.sql)
        self.assertNotIn("horizon", self.sql)
        self.assertFalse(any("ros" in k for k in pw.projection_row(
            source="espn", target_week=10, source_player_id="1", player_key=None, sleeper_id=None,
            full_name=None, position="QB", content_week=10, **COMMON)))
        self.assertIn("check (target_week >= content_week)", self.sql)

    def test_cron_jobs_match_monitoring_coverage(self):
        cov = json.loads((ROOT / "config" / "monitoring_coverage.json").read_text())
        jobs = {p["pg_cron_job"] for p in cov["pipelines"] if p["workflow"] == "weekly-projection-warehouse.yml"}
        self.assertEqual(jobs, {"weekly-projection-warehouse-daily", "weekly-projection-warehouse-sunday"})
        for j in jobs:
            self.assertIn(f"'{j}'", self.sql)
        self.assertIn("'weekly_projection_warehouse'", self.sql)

    def test_row_builders_only_emit_migration_columns(self):
        proj_cols = set(pw.projection_row(source="espn", target_week=10, source_player_id="1", player_key=None,
                                          sleeper_id=None, full_name=None, position="QB", content_week=10,
                                          **COMMON))
        body = self.sql.split("create table if not exists public.source_weekly_projections")[1].split("\n);")[0]
        for col in proj_cols:
            self.assertRegex(body, rf"\n\s+{col}\s", col)
        run_cols = set(pw.run_row(source="espn", content_week=10, rows_written=0, **COMMON))
        body = self.sql.split("create table if not exists public.source_projection_runs")[1].split("\n);")[0]
        for col in run_cols:
            self.assertRegex(body, rf"\n\s+{col}\s", col)

    def test_nflverse_rows_only_emit_migration_columns(self):
        for table, rows in (("nflverse_schedule_snapshots", pw.schedule_rows(SCHEDULE_CSV, **COMMON)),
                            ("nflverse_injury_snapshots",
                             pw.injury_rows(INJURY_CSV, index(), {}, **COMMON)[0])):
            body = self.sql.split(f"create table if not exists public.{table}")[1].split("\n);")[0]
            for col in rows[0]:
                self.assertRegex(body, rf"\n\s+{col}\s", f"{table}.{col}")


if __name__ == "__main__":
    unittest.main()
