"""Pasted Vegas season player props (JEG-1667; Jeremy, 2026-11-27: "I'll
paste the lines."): app/draft/vegas-paste.js and tools/draft_vegas_paste.mjs.

The sample (tests/fixtures/draft_vegas_paste/sample_ok.txt) is an invented
page in the shapes a select-all copy of a sportsbook's season props page
produces: page chrome, market headers, name lines with O/U and odds lines,
"Player - market" headers, one-line "Player Over N market odds" rows, a
unicode minus, and a nickname. Anything that looks like prop data but cannot
be read must fail closed and be listed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "draft_vegas_paste"
SAMPLE = (FIX / "sample_ok.txt").read_text()
PLAYERS = json.loads((FIX / "players.json").read_text())


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def parse(text, season=2026):
    js = ("const V=require('./app/draft/vegas-paste.js');"
          f"process.stdout.write(JSON.stringify(V.parse({json.dumps(text)},{json.dumps(PLAYERS)},"
          f"{{season:{season},snapshotDate:'2026-08-20'}})))")
    return json.loads(subprocess.run([_node(), "-e", js], capture_output=True, text=True, check=True, cwd=ROOT).stdout)


class ReadsTheSample(unittest.TestCase):
    def test_every_line_read(self):
        r = parse(SAMPLE)
        self.assertTrue(r["ok"], r["errors"])
        got = {(x["key"], x["market"]): x["line"] for x in r["rows"]}
        self.assertEqual(got, {
            ("101", "season_pass_yds"): 4150.5, ("102", "season_pass_yds"): 3875.5,
            ("101", "season_pass_tds"): 28.5, ("102", "season_rush_yds"): 525.5,
            ("201", "season_rush_yds"): 1350.5, ("202", "season_rush_yds"): 1225.5,
            ("301", "season_receptions"): 104.5, ("302", "season_receptions"): 101.5,
            ("203", "season_receptions"): 38.5, ("301", "season_rec_yds"): 1375.5,
            ("302", "season_rec_yds"): 1210.5, ("301", "season_rec_tds"): 10.5})

    def test_under_used_only_without_an_over(self):
        sides = {(x["key"], x["market"]): x["side"] for x in parse(SAMPLE)["rows"]}
        self.assertEqual(sides[("301", "season_rec_tds")], "under")
        self.assertEqual(sides[("101", "season_pass_yds")], "over")


class FailsClosed(unittest.TestCase):
    def _bad(self, extra, why, season=2026):
        r = parse(SAMPLE + "\n" + extra, season=season)
        self.assertFalse(r["ok"])
        self.assertTrue(any(why in e["reason"] for e in r["errors"]), r["errors"])
        return r

    def test_unknown_player_is_listed(self):
        r = self._bad("Regular Season Rushing Yards\nZed Unknownson\nO 900.5\n-110", "unknown player: Zed Unknownson")
        self.assertIn("O 900.5", [e["text"] for e in r["errors"]])

    def test_out_of_range_line(self):
        self._bad("Regular Season Receiving Yards\nJa'Marr Chase\nO 13755", "outside")

    def test_wrong_season(self):
        self._bad("Regular Season Passing Yards 2027\nJosh Allen\nO 3900.5", "season 2027 is not 2026")

    def test_conflicting_lines(self):
        self._bad("Regular Season Passing Yards\nJosh Allen\nO 3925.5", "two different over lines")

    def test_garbled_over_under(self):
        self._bad("Regular Season Passing Yards\nJosh Allen\nover the line at 39x5", "unreadable")

    def test_empty_paste_is_not_ok(self):
        self.assertFalse(parse("Home\nLive\nBet Slip")["ok"])

    # Review of f662c66, blocker 2: each of these returned ok=true before.
    def test_combined_rush_rec_yards_refused(self):
        r = self._bad("Rush + Rec Yards Regular Season\nBijan Robinson\nO 1900.5", "combined market")
        self.assertNotIn(1900.5, [x["line"] for x in r["rows"]])

    def test_combined_rush_rec_tds_refused(self):
        self._bad("Rushing & Receiving TDs Regular Season\nBijan Robinson\nO 12.5", "combined market")

    def test_longest_reception_refused(self):
        self._bad("Longest Reception Regular Season\nJa'Marr Chase\nO 62.5", "longest-play market")

    def test_unknown_header_resets_the_market(self):
        # Without the reset, 255.5 attempts would be stored as rushing yards.
        r = self._bad("Regular Season Rushing Attempts\nBijan Robinson\nO 255.5", "attempts market")
        self.assertEqual([x["line"] for x in r["rows"] if x["key"] == "201"], [1350.5])

    def test_targets_refused(self):
        self._bad("Regular Season Targets\nJa'Marr Chase\nO 150.5", "targets market")

    def test_interceptions_thrown_refused(self):
        self._bad("Interceptions Thrown Regular Season\nJosh Allen\nO 11.5", "interceptions market")

    def test_weekly_page_refused(self):
        r = parse("Week 12 Player Props\nReceiving Yards\nJa'Marr Chase\nO 85.5\n-115")
        self.assertFalse(r["ok"])
        # Rule tightened by the review of f0fcfb1: each market needs its own
        # season marker, and a "Week N" line starts a weekly section.
        self.assertEqual(r["rows"], [])

    def test_last_season_line_refused(self):
        self._bad("2025 Regular Season\nRegular Season Receiving Yards\nJa'Marr Chase\nO 1375.5", "season 2025 is not 2026")

    def test_conflicting_unders_refused(self):
        self._bad("Regular Season Receiving Touchdowns\nJa'Marr Chase\nUnder 11.5", "two different under lines")

    # Delta review of f0fcfb1: each probe below returned ok=true at f0fcfb1.
    def _stored(self, r, key, market):
        return [x["line"] for x in r["rows"] if x["key"] == key and x["market"] == market]

    def test_combined_rec_and_rush_any_order(self):
        r = self._bad("Receiving and Rushing Yards Regular Season\nBijan Robinson\nO 1850.5", "combined market")
        self.assertEqual(self._stored(r, "201", "season_rush_yds"), [1350.5])

    def test_combined_yds_plus_yds(self):
        r = self._bad("Receiving Yds plus Rushing Yds Regular Season\nBijan Robinson\nO 1850.5", "combined market")
        self.assertEqual(self._stored(r, "201", "season_rush_yds"), [1350.5])

    def test_combined_rush_and_pass(self):
        r = self._bad("Rushing and Passing Yards Regular Season\nJosh Allen\nO 4400.5", "combined market")
        self.assertEqual(self._stored(r, "102", "season_pass_yds"), [3875.5])

    def test_weekly_page_with_season_menu_link(self):
        r = parse("Season Futures\nWeek 12 Player Props\nReceiving Yards\nJa'Marr Chase\nO 85.5\n-115\n"
                  "Receptions\nJa'Marr Chase\nO 6.5\n-120")
        self.assertFalse(r["ok"])
        self.assertEqual(r["rows"], [])

    def test_game_lines_after_a_season_page(self):
        r = self._bad("Game Lines\nLions vs Bears\nReceptions\nAmon-Ra St. Brown\nO 6.5\n-110", "season marker")
        self.assertEqual(self._stored(r, "302", "season_receptions"), [101.5])

    def test_year_checked_on_every_line(self):
        r = self._bad("2025 Receiving Yards\nJa'Marr Chase\nO 1708.5", "season 2025 is not 2026")
        self.assertEqual(self._stored(r, "301", "season_rec_yds"), [1375.5])

    def test_first_half_market_refused(self):
        self._bad("1st Half Receiving Yards Regular Season\nJa'Marr Chase\nO 700.5", "half or quarter market")

    def test_playoffs_market_refused(self):
        self._bad("Receiving Yards incl. Playoffs Regular Season\nJa'Marr Chase\nO 1450.5", "includes the playoffs")

    def test_unknown_name_line_clears_the_player(self):
        r = self._bad("Regular Season Receiving Touchdowns\nJaxon Smith-Njigba (SEA)\nO 8.5",
                      "unknown player: Jaxon Smith-Njigba (SEA)")
        self.assertEqual(self._stored(r, "301", "season_rec_tds"), [10.5])

    def test_team_tag_in_parentheses_is_stripped(self):
        r = parse(SAMPLE + "\nRegular Season Receiving Touchdowns\nAmon-Ra St. Brown (DET)\nO 8.5")
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(self._stored(r, "302", "season_rec_tds"), [8.5])

    def test_over_and_under_far_apart(self):
        self._bad("Regular Season Receiving Yards\nAmon-Ra St. Brown\nU 1300.5", "more than 5% apart")

    # Third review (bc19862): each probe below returned ok=true or stored a
    # wrong line at bc19862.
    def test_menu_line_cannot_make_a_weekly_section_seasonal(self):
        for page in ("Receiving Yards\nGame | Season Futures\nJa'Marr Chase\nO 85.5\nReceptions\nSeason Futures\nJa'Marr Chase\nO 6.5",
                     "Receiving Yards\nSeason Futures\nJa'Marr Chase\nO 85.5",
                     "Receiving Yards\nPrices for the regular season are posted separately\nJa'Marr Chase\nO 85.5"):
            r = parse(page)
            self.assertFalse(r["ok"], page)
            self.assertEqual(r["rows"], [], page)

    def test_one_line_game_prop_in_a_season_section_refused(self):
        r = self._bad("Regular Season Receiving Yards\nJa'Marr Chase Over 55.5 Receiving Yards -110", "one-line prop")
        self.assertEqual(self._stored(r, "301", "season_rec_yds"), [1375.5])

    def test_season_floors_refuse_game_sized_lines(self):
        self._bad("Regular Season Receiving Yards\nBijan Robinson\nO 55.5", "outside")
        self._bad("Regular Season Receptions\nBijan Robinson\nO 6.5", "outside")

    def test_first_n_games_refused(self):
        self._bad("Receiving Yards - First 4 Games of Regular Season\nJa'Marr Chase\nO 300.5", "weekly or game market")

    def test_regular_plus_post_season_refused(self):
        self._bad("Receiving Yards Regular + Post Season\nJa'Marr Chase\nO 1450.5", "includes the playoffs")

    def test_two_digit_season_label_checked(self):
        self._bad("Receiving Yards - 25/26 Regular Season\nJa'Marr Chase\nO 1375.5", "season 2025 is not 2026")

    def test_opening_week_section_refused(self):
        self._bad("Regular Season Receiving Yards\nOpening Week Specials\nBijan Robinson\nO 285.5", "weekly or game section")

    def test_bare_team_or_initials_line_clears_the_player(self):
        r = self._bad("Regular Season Receiving Touchdowns\nJa'Marr Chase\nCIN\nJSN\nO 8.5", "unknown player: JSN")
        self.assertEqual(self._stored(r, "301", "season_rec_tds"), [10.5])

    def test_split_over_and_number_lines_are_read(self):
        # The sample prints St. Brown's receptions as "Over" then "101.5".
        self.assertEqual(self._stored(parse(SAMPLE), "302", "season_receptions"), [101.5])
        self._bad("Regular Season Receiving Yards\nBijan Robinson\nOver\n-110", "no line after it")

    def test_thousands_separator(self):
        r = parse(SAMPLE.replace("O 3875.5", "O 3,875.5"))
        self.assertTrue(r["ok"], r["errors"])
        self.assertIn(3875.5, [x["line"] for x in r["rows"] if x["key"] == "102"])


class SnapshotTool(unittest.TestCase):
    def _run(self, text, extra=()):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "paste.txt").write_text(text)
        players = [{"key": int(k), **v} for k, v in PLAYERS.items()]
        (tmp / "players.json").write_text(json.dumps(players))
        out = subprocess.run([_node(), "tools/draft_vegas_paste.mjs", "--in", str(tmp / "paste.txt"),
                              "--players", str(tmp / "players.json"), "--season", "2026", "--date", "2026-08-20",
                              "--out", str(tmp / "out"), *extra], capture_output=True, text=True, cwd=ROOT)
        return out, tmp / "out"

    def test_writes_dated_snapshot_in_the_0912_shape(self):
        out, d = self._run(SAMPLE)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = json.loads((d / "vegas_2026-08-20.json").read_text())
        self.assertEqual(len(rows), 12)
        self.assertEqual(set(rows[0]), {"name", "player_key", "team", "market", "line"})
        meta = json.loads((d / "vegas_2026-08-20.meta.json").read_text())
        self.assertEqual((meta["snapshot_date"], meta["season"], meta["label"]), ("2026-08-20", 2026, "2026 data"))

    def test_sql_load_script_is_idempotent_and_escaped(self):
        out, d = self._run(SAMPLE, extra=("--sql",))
        self.assertEqual(out.returncode, 0, out.stderr)
        sql = (d / "vegas_2026-08-20.sql").read_text()
        self.assertIn("delete from public.draft_vegas_lines where snapshot_date = '2026-08-20';", sql)
        self.assertEqual(sql.count("('2026-08-20', 2026, 'paste',"), 12)
        self.assertIn("'Ja''Marr Chase'", sql)
        self.assertTrue(sql.strip().endswith("commit;"))

    def test_refuses_to_save_on_any_error(self):
        out, d = self._run(SAMPLE + "\nRegular Season Rushing Yards\nZed Unknownson\nO 900.5")
        self.assertEqual(out.returncode, 1)
        self.assertIn("Zed Unknownson", out.stderr)
        self.assertFalse(d.exists())


class FeedsOurs(unittest.TestCase):
    def test_pasted_lines_move_ours_through_the_vegas_path(self):
        js = """
const E=require('./app/draft/draft-engine.js'),V=require('./app/draft/vegas-paste.js'),fs=require('fs');
const P=JSON.parse(fs.readFileSync('tests/fixtures/draft_vegas_paste/players.json','utf8'));
const lineup=JSON.parse(fs.readFileSync('config/lineup_parameters.json','utf8'));
const players={},proj={},mkt={};let n=0;
Object.entries(P).forEach(([k,p])=>{players[k]={pos:p.pos,name:p.name}});
for(const [pos,count,top] of [['QB',30,330],['RB',60,250],['WR',80,240],['TE',30,180]]){
  for(let i=0;i<count;i+=1){const k=String(5000+(n+=1));players[k]={pos,name:pos+i};}
}
Object.keys(players).forEach((k,i)=>{const p=players[k];const base={QB:300,RB:220,WR:210,TE:150}[p.pos]*Math.pow(0.975,i%80);
  proj[k]=p.pos==='QB'?{pass_yds:base*12,pass_tds:base/12,rush_yds:base/2}:{rec:base/3,rec_yds:base*4,rec_tds:base/40,rush_yds:p.pos==='RB'?base*4:0};
  mkt[k]=Math.max(0,50*Math.pow(0.95,i%80));});
const league={teams:10,budget:200,scoring:'half',slots:{QB:1,RB:2,WR:3,TE:1,FLEX:1,K:1,DST:1,BN:6}};
const parsed=V.parse(fs.readFileSync('tests/fixtures/draft_vegas_paste/sample_ok.txt','utf8'),P,{season:2026});
const lines=V.lineMap(parsed.rows);
const vegas={};Object.entries(lines).forEach(([k,l])=>{const s=E.vegasStatLine(l,proj[k]);if(s)vegas[k]=s;});
const run=v=>E.ourPrices(E.ddfDraftValues({league,players,projections:{fp:proj},vegas:v,markets:{m:mkt},lineupConfig:lineup}).values,league);
const hi=JSON.parse(JSON.stringify(vegas));hi['301'].rec_yds*=1.5;hi['301'].rec*=1.5;
process.stdout.write(JSON.stringify({keys:Object.keys(vegas).sort(),base:run(vegas)['301'],up:run(hi)['301']}));
"""
        r = json.loads(subprocess.run([_node(), "-e", js], capture_output=True, text=True, check=True, cwd=ROOT).stdout)
        self.assertEqual(r["keys"], ["101", "102", "201", "202", "203", "301", "302"])
        self.assertGreater(r["up"] - r["base"], 1.0)


if __name__ == "__main__":
    unittest.main()
