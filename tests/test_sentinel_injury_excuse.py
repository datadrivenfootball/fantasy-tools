"""JEG-1630: an injured sentinel below his band is excused, not held (2026-11-13).

Week 10: ESPN projected 0 rest of season for Lamar Jackson (Sleeper IR, thumb)
and Puka Nacua (IR, knee); CBS ROS priced Lamar at 10.1/g over the games he has
left. Every value matched the publisher exactly, yet the JEG-592 sentinel held
ESPN and CBS ROS red from Wed Nov 11 because it judged the numbers against a
healthy star's band.

Each rule has its negative:
  - below band + IR/Out/PUP          -> excused, listed, source green
  - below band + healthy (no status) -> red (a scrape that zeroed a star)
  - below band + Questionable        -> red (a one-week tag does not move ROS)
  - above band + IR                  -> red (an injury never explains a column shift)
  - injured player missing from players.json -> red (fail closed)
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import fidelity_pulse as fp  # noqa: E402

NOW = datetime(2026, 11, 13, 22, 0, tzinfo=timezone.utc)

PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 506, "full_name": "Lamar Jackson", "position": "QB", "active": True},
    {"player_key": 3594, "full_name": "Patrick Mahomes", "position": "QB", "active": True},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB", "active": True},
    {"player_key": 1370, "full_name": "Puka Nacua", "position": "WR", "active": True},
    {"player_key": 51, "full_name": "Brock Bowers", "position": "TE", "active": True},
]

HEALTHY = {869: 21.5, 3594: 20.4, 2227: 22.2, 51: 12.2}


def row(name, key, pos, cbs, injury=None, roster="active_roster"):
    return {"name": name, "player_key": key, "pos": pos, "injury_status": injury, "roster_status": roster,
            "cbsros_ppg": {"standard": cbs, "half_ppr": cbs, "ppr": cbs}}


def players_data(lamar_injury="IR", lamar_roster="injured_reserve", nacua_injury="IR",
                 nacua_roster="injured_reserve"):
    return [
        row("Josh Allen", 869, "QB", 22.0),
        row("Lamar Jackson", 506, "QB", 10.1, lamar_injury, lamar_roster),
        row("Patrick Mahomes", 3594, "QB", 20.0),
        row("Jahmyr Gibbs", 2227, "RB", 20.0),
        row("Puka Nacua", 1370, "WR", 16.075, nacua_injury, nacua_roster),
        row("Brock Bowers", 51, "TE", 12.0),
    ]


def validity(values, data, source="espn"):
    ident = fp.Identity.load(PLAYERS)
    chart = {"half|1": {k: {"value": v, "text": None, "name": str(k), "pos": None} for k, v in values.items()}}
    return fp.stage_scrape_validity(source, {"players_data": data}, ident, publisher=None, stored=None,
                                    chart=chart, chart_week=None, now=NOW)


class InjuredSentinelBelowBandIsExcused(unittest.TestCase):
    def test_week10_espn_zeroes_for_ir_players_do_not_hold(self):
        """The live Week 10 case: ESPN 0 for Lamar and Nacua, both IR."""
        res = validity({**HEALTHY, 506: 0.0, 1370: 0.0}, players_data())
        self.assertEqual(res["status"], "green", res["summary"])
        self.assertEqual(res["signals"]["sentinel_failures"], [])
        excused = {e["name"]: e["injury"] for e in res["signals"]["sentinel_excused"]}
        self.assertEqual(excused, {"Lamar Jackson": "IR", "Puka Nacua": "IR"})
        self.assertIn("JEG-1630", res["summary"])

    def test_out_and_pup_and_roster_ir_excuse(self):
        for injury, roster in (("Out", "active_roster"), ("PUP", "active_roster"), (None, "injured_reserve")):
            with self.subTest(injury=injury, roster=roster):
                res = validity({**HEALTHY, 506: 0.0, 1370: 17.0},
                               players_data(lamar_injury=injury, lamar_roster=roster))
                self.assertEqual(res["status"], "green", res["summary"])

    def test_cbsros_low_ros_for_ir_qb_is_excused(self):
        """CBS ROS Lamar 10.1 against the fallback band 16 to 30 (no other source prices him)."""
        data = players_data()
        for p in data:
            p.pop("cbsros_ppg", None)
        res = validity({**HEALTHY, 506: 10.1, 1370: 16.0}, data, source="cbsros")
        self.assertEqual(res["signals"]["sentinel_failures"], [])
        self.assertEqual([e["name"] for e in res["signals"]["sentinel_excused"]], ["Lamar Jackson"])


class NegativesStillHold(unittest.TestCase):
    def test_healthy_star_at_zero_still_holds(self):
        res = validity({**HEALTHY, 506: 0.0, 1370: 17.0},
                       players_data(lamar_injury=None, lamar_roster="active_roster"))
        self.assertEqual(res["status"], "red")
        self.assertEqual([b["name"] for b in res["signals"]["sentinel_failures"]], ["Lamar Jackson"])
        self.assertEqual(res["signals"]["sentinel_excused"], [])

    def test_questionable_or_doubtful_does_not_excuse(self):
        for tag in ("Questionable", "Doubtful"):
            with self.subTest(tag=tag):
                res = validity({**HEALTHY, 506: 0.0, 1370: 17.0},
                               players_data(lamar_injury=tag, lamar_roster="active_roster"))
                self.assertEqual(res["status"], "red")

    def test_above_band_never_excused_by_injury(self):
        """A column shift (season total in a per-game field) stays red even for an IR player."""
        res = validity({**HEALTHY, 506: 280.0, 1370: 17.0}, players_data())
        self.assertEqual(res["status"], "red")
        self.assertEqual([b["name"] for b in res["signals"]["sentinel_failures"]], ["Lamar Jackson"])

    def test_missing_players_row_fails_closed(self):
        data = [p for p in players_data() if p["name"] != "Lamar Jackson"]
        res = validity({**HEALTHY, 506: 0.0, 1370: 17.0}, data)
        self.assertEqual(res["status"], "red")


if __name__ == "__main__":
    unittest.main()
