"""League settings loader for the DDF auction draft tool (JEG-1672).
Tests for app/draft/draft-league.js.

Gate: python3 -m unittest tests.test_draft_league

Fixture provenance: see tests/fixtures/draft_league/README.md.
  - sleeper_{league,users,drafts}.json: real Sleeper API data, sanitized
  - espn_league.json: reconstructed (all public ESPN leagues returned 401/404)
  - *-reconstructed.txt: paste text reconstructions (login-walled platform pages)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "draft_league"


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def _run(js: str) -> object:
    """Run a JS snippet in the module's cwd, return parsed JSON."""
    full = (
        "const DL=require('./app/draft/draft-league.js');"
        + js
    )
    result = subprocess.run(
        [_node(), "-e", full],
        capture_output=True, text=True, check=True, cwd=ROOT
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# parseRef
# ---------------------------------------------------------------------------

class ParseRef(unittest.TestCase):

    def _ref(self, text):
        return _run(f"process.stdout.write(JSON.stringify(DL.parseRef({json.dumps(text)})))")

    def test_sleeper_url(self):
        r = self._ref("https://sleeper.com/leagues/784452439588028416/team")
        self.assertEqual(r["platform"], "sleeper")
        self.assertEqual(r["id"], "784452439588028416")

    def test_sleeper_app_url(self):
        r = self._ref("sleeper.app/leagues/123456789012345678")
        self.assertEqual(r["platform"], "sleeper")

    def test_espn_url_with_season(self):
        r = self._ref("https://fantasy.espn.com/football/league?leagueId=336358&seasonId=2026")
        self.assertEqual(r["platform"], "espn")
        self.assertEqual(r["id"], "336358")
        self.assertEqual(r["season"], "2026")

    def test_espn_url_without_season(self):
        r = self._ref("https://fantasy.espn.com/football/league/settings?leagueId=12345")
        self.assertEqual(r["platform"], "espn")
        self.assertEqual(r["id"], "12345")
        self.assertNotIn("season", r or {})

    def test_yahoo_url(self):
        r = self._ref("https://football.fantasysports.yahoo.com/f1/848938")
        self.assertEqual(r["platform"], "yahoo")
        self.assertEqual(r["id"], "848938")

    def test_bare_sleeper_id(self):
        r = self._ref("784452439588028416")
        self.assertEqual(r["platform"], "sleeper")

    def test_bare_espn_id(self):
        r = self._ref("336358")
        self.assertEqual(r["platform"], "espn")

    def test_null_on_garbage(self):
        r = self._ref("not a league")
        self.assertIsNone(r)

    def test_null_on_empty(self):
        r = self._ref("")
        self.assertIsNone(r)


# ---------------------------------------------------------------------------
# settingsUrl
# ---------------------------------------------------------------------------

class SettingsUrl(unittest.TestCase):

    def _url(self, platform, id_):
        return _run(
            f"process.stdout.write(JSON.stringify(DL.settingsUrl({{platform:{json.dumps(platform)},id:{json.dumps(id_)}}})))"
        )

    def test_espn(self):
        u = self._url("espn", "336358")
        self.assertIn("336358", u)
        self.assertIn("espn.com", u)

    def test_yahoo(self):
        u = self._url("yahoo", "848938")
        self.assertIn("848938", u)
        self.assertIn("yahoo.com", u)

    def test_sleeper(self):
        u = self._url("sleeper", "784452439588028416")
        self.assertIn("784452439588028416", u)
        self.assertIn("sleeper.com", u)


# ---------------------------------------------------------------------------
# fromSleeper
# ---------------------------------------------------------------------------

class FromSleeper(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.league  = json.loads((FIX / "sleeper_league.json").read_text())
        cls.users   = json.loads((FIX / "sleeper_users.json").read_text())
        cls.drafts  = json.loads((FIX / "sleeper_drafts.json").read_text())

    def _convert(self):
        js = (
            f"const lg={json.dumps(self.league)};"
            f"const us={json.dumps(self.users)};"
            f"const dr={json.dumps(self.drafts)};"
            "process.stdout.write(JSON.stringify(DL.fromSleeper(lg,us,dr)))"
        )
        return _run(js)

    def test_platform(self):
        r = self._convert()
        self.assertEqual(r["platform"], "sleeper")

    def test_league_id(self):
        r = self._convert()
        self.assertEqual(r["leagueId"], str(self.league["league_id"]))

    def test_name(self):
        r = self._convert()
        self.assertEqual(r["name"], self.league["name"])

    def test_teams_count(self):
        r = self._convert()
        self.assertEqual(len(r["teams"]), len(self.users))

    def test_teams_names_from_metadata(self):
        # Users with team_name in metadata should use it
        r = self._convert()
        # First user (index 0) has team_name "Team 1" in fixture
        self.assertEqual(r["teams"][0]["name"], "Team 1")

    def test_teams_names_fallback_to_display_name(self):
        # Users without team_name should fall back to display_name
        r = self._convert()
        # Second user (index 1) has empty team_name in fixture -> uses display_name
        self.assertEqual(r["teams"][1]["name"], "user2")

    def test_budget_default(self):
        # No budget key in draft settings -> default 200
        r = self._convert()
        self.assertEqual(r["budget"], 200)

    def test_budget_on_teams(self):
        r = self._convert()
        for t in r["teams"]:
            self.assertEqual(t["budget"], 200)

    def test_min_bid(self):
        r = self._convert()
        self.assertEqual(r["minBid"], 1)

    def test_slots_qb(self):
        r = self._convert()
        # Fixture has QB, QB -> 2 QBs
        self.assertEqual(r["slots"]["QB"], 2)

    def test_slots_rb(self):
        r = self._convert()
        self.assertEqual(r["slots"]["RB"], 3)

    def test_slots_wr(self):
        r = self._convert()
        self.assertEqual(r["slots"]["WR"], 3)

    def test_slots_te(self):
        r = self._convert()
        self.assertEqual(r["slots"]["TE"], 2)

    def test_slots_flex(self):
        r = self._convert()
        self.assertEqual(r["slots"]["FLEX"], 3)

    def test_slots_bn(self):
        r = self._convert()
        self.assertEqual(r["slots"]["BN"], 14)

    def test_scoring_pass_yds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["pass_yds"], 0.04)

    def test_scoring_pass_tds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["pass_tds"], 4.0)

    def test_scoring_ints(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["ints"], -2.0)

    def test_scoring_rush_yds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rush_yds"], 0.1)

    def test_scoring_rush_tds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rush_tds"], 6.0)

    def test_scoring_rec(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rec"], 1.0)

    def test_scoring_rec_yds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rec_yds"], 0.1)

    def test_scoring_rec_tds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rec_tds"], 6.0)

    def test_scoring_fum_lost(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["fum_lost"], -2.0)

    def test_scoring_label_ppr(self):
        r = self._convert()
        self.assertEqual(r["scoringLabel"], "PPR")

    def test_budget_from_draft_settings(self):
        """When draft.settings.budget is present, use it."""
        drafts_with_budget = [dict(self.drafts[0], settings={"budget": 250})]
        js = (
            f"const lg={json.dumps(self.league)};"
            f"const us={json.dumps(self.users)};"
            f"const dr={json.dumps(drafts_with_budget)};"
            "process.stdout.write(JSON.stringify(DL.fromSleeper(lg,us,dr)))"
        )
        r = _run(js)
        self.assertEqual(r["budget"], 250)

    def test_half_ppr_label(self):
        lg = dict(self.league, scoring_settings=dict(self.league["scoring_settings"], rec=0.5))
        js = (
            f"const lg={json.dumps(lg)};"
            f"const us={json.dumps(self.users)};"
            "process.stdout.write(JSON.stringify(DL.fromSleeper(lg,us,[])))"
        )
        r = _run(js)
        self.assertEqual(r["scoringLabel"], "Half PPR")

    def test_standard_label(self):
        lg = dict(self.league, scoring_settings=dict(self.league["scoring_settings"], rec=0))
        js = (
            f"const lg={json.dumps(lg)};"
            f"const us={json.dumps(self.users)};"
            "process.stdout.write(JSON.stringify(DL.fromSleeper(lg,us,[])))"
        )
        r = _run(js)
        self.assertEqual(r["scoringLabel"], "Standard")


# ---------------------------------------------------------------------------
# fromEspn
# ---------------------------------------------------------------------------

class FromEspn(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((FIX / "espn_league.json").read_text())

    def _convert(self):
        js = (
            f"const f={json.dumps(self.fixture)};"
            "process.stdout.write(JSON.stringify(DL.fromEspn(f)))"
        )
        return _run(js)

    def test_platform(self):
        r = self._convert()
        self.assertEqual(r["platform"], "espn")

    def test_league_id(self):
        r = self._convert()
        self.assertEqual(r["leagueId"], str(self.fixture["id"]))

    def test_name(self):
        r = self._convert()
        self.assertEqual(r["name"], self.fixture["settings"]["name"])

    def test_teams_count(self):
        r = self._convert()
        self.assertEqual(len(r["teams"]), 10)

    def test_team_names(self):
        r = self._convert()
        self.assertEqual(r["teams"][0]["name"], "Team One")
        self.assertEqual(r["teams"][1]["name"], "Team Two")

    def test_budget(self):
        r = self._convert()
        self.assertEqual(r["budget"], 200)

    def test_min_bid(self):
        r = self._convert()
        self.assertEqual(r["minBid"], 1)

    def test_slots_qb(self):
        r = self._convert()
        self.assertEqual(r["slots"]["QB"], 1)

    def test_slots_rb(self):
        r = self._convert()
        self.assertEqual(r["slots"]["RB"], 2)

    def test_slots_wr(self):
        r = self._convert()
        self.assertEqual(r["slots"]["WR"], 2)

    def test_slots_te(self):
        r = self._convert()
        self.assertEqual(r["slots"]["TE"], 1)

    def test_slots_flex(self):
        r = self._convert()
        self.assertEqual(r["slots"]["FLEX"], 1)

    def test_slots_k(self):
        r = self._convert()
        self.assertEqual(r["slots"]["K"], 1)

    def test_slots_dst(self):
        r = self._convert()
        self.assertEqual(r["slots"]["DST"], 1)

    def test_slots_bn(self):
        r = self._convert()
        self.assertEqual(r["slots"]["BN"], 6)

    def test_scoring_pass_yds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["pass_yds"], 0.04)

    def test_scoring_pass_tds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["pass_tds"], 4.0)

    def test_scoring_ints(self):
        # statId=20, isReversal=true, points=2.0 -> -2
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["ints"], -2.0)

    def test_scoring_rush_yds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rush_yds"], 0.1)

    def test_scoring_rush_tds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rush_tds"], 6.0)

    def test_scoring_rec(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rec"], 0.5)

    def test_scoring_rec_yds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rec_yds"], 0.1)

    def test_scoring_rec_tds(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["rec_tds"], 6.0)

    def test_scoring_fum_lost(self):
        r = self._convert()
        self.assertAlmostEqual(r["scoring"]["fum_lost"], -2.0)

    def test_scoring_label_half_ppr(self):
        r = self._convert()
        self.assertEqual(r["scoringLabel"], "Half PPR")

    def test_budget_on_teams(self):
        r = self._convert()
        for t in r["teams"]:
            self.assertEqual(t["budget"], 200)


# ---------------------------------------------------------------------------
# load() with injected fetch
# ---------------------------------------------------------------------------

class Load(unittest.TestCase):

    def _load(self, ref: dict, fetch_js: str) -> dict:
        """Run load() with an injected fetch and return the result."""
        ref_json = json.dumps(ref)
        js = (
            f"const ref={ref_json};"
            f"const f={fetch_js};"
            "DL.load(ref,{fetch:f}).then(function(r){"
            "process.stdout.write(JSON.stringify(r));process.exit(0);"
            "}).catch(function(e){"
            "process.stdout.write(JSON.stringify({ok:false,err:String(e)}));"
            "process.exit(0);});"
        )
        return _run(js)

    def test_yahoo_returns_paste(self):
        r = self._load({"platform": "yahoo", "id": "12345"}, "null")
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "paste")
        self.assertIn("settingsUrl", r)

    def test_sleeper_ok(self):
        """Injected fetch returning 200 with league+users+drafts data."""
        league = json.loads((FIX / "sleeper_league.json").read_text())
        users  = json.loads((FIX / "sleeper_users.json").read_text())
        drafts = json.loads((FIX / "sleeper_drafts.json").read_text())
        fetch_js = (
            "(function(){"
            + "var lg=" + json.dumps(league) + ";"
            + "var us=" + json.dumps(users) + ";"
            + "var dr=" + json.dumps(drafts) + ";"
            + "return function(url){"
            + "var body=url.indexOf('/users')>=0?us:url.indexOf('/drafts')>=0?dr:lg;"
            + "return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(body)}});"
            + "}})()"
        )
        r = self._load({"platform": "sleeper", "id": str(league["league_id"])}, fetch_js)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["league"]["platform"], "sleeper")
        self.assertEqual(r["league"]["scoring"]["rec"], 1.0)

    def test_sleeper_404_returns_notfound(self):
        fetch_js = (
            "function(url){return Promise.resolve({ok:false,status:404,json:function(){return Promise.resolve(null)}})}"
        )
        r = self._load({"platform": "sleeper", "id": "799999999999999999"}, fetch_js)
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "notfound")
        self.assertIn("settingsUrl", r)

    def test_sleeper_network_error(self):
        fetch_js = "function(url){return Promise.reject(new Error('connection refused'))}"
        r = self._load({"platform": "sleeper", "id": "799999999999999999"}, fetch_js)
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "network")

    def test_espn_ok(self):
        """Injected fetch returning the ESPN fixture."""
        espn_fix = json.loads((FIX / "espn_league.json").read_text())
        fetch_js = (
            "(function(){"
            + "var body=" + json.dumps(espn_fix) + ";"
            + "return function(url){"
            + "return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(body)}});"
            + "}})()"
        )
        r = self._load({"platform": "espn", "id": "336358"}, fetch_js)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["league"]["platform"], "espn")
        self.assertEqual(r["league"]["budget"], 200)

    def test_espn_401_returns_private(self):
        fetch_js = (
            "function(url){return Promise.resolve({ok:false,status:401,json:function(){return Promise.resolve({})}})}"
        )
        r = self._load({"platform": "espn", "id": "336358"}, fetch_js)
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "private")
        self.assertIn("settingsUrl", r)

    def test_espn_403_returns_private(self):
        fetch_js = (
            "function(url){return Promise.resolve({ok:false,status:403,json:function(){return Promise.resolve({})}})}"
        )
        r = self._load({"platform": "espn", "id": "336358"}, fetch_js)
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "private")

    def test_espn_404_returns_notfound(self):
        fetch_js = (
            "function(url){return Promise.resolve({ok:false,status:404,json:function(){return Promise.resolve({})}})}"
        )
        r = self._load({"platform": "espn", "id": "999"}, fetch_js)
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "notfound")

    def test_no_credentials_sent_to_sleeper(self):
        """The injected fetch must receive no authorization/cookie headers."""
        js = (
            "var ref={platform:'sleeper',id:'799999999999999999'};"
            "var headers=null;"
            "var f=function(url,opts){"
            "headers=opts&&opts.headers?opts.headers:null;"
            "return Promise.reject(new Error('captured'));};"
            "DL.load(ref,{fetch:f}).then(function(){"
            "process.stdout.write(JSON.stringify({headers:headers}));process.exit(0);"
            "}).catch(function(){"
            "process.stdout.write(JSON.stringify({headers:headers}));process.exit(0);"
            "});"
        )
        r = _run(js)
        # headers must be null (no opts passed) or not contain auth/cookie
        h = r.get("headers")
        self.assertIsNone(h, "fetch should not be called with custom headers; got: " + str(h))

    def test_no_credentials_sent_to_espn(self):
        js = (
            "var ref={platform:'espn',id:'336358'};"
            "var headers=null;"
            "var f=function(url,opts){"
            "headers=opts&&opts.headers?opts.headers:null;"
            "return Promise.reject(new Error('captured'));};"
            "DL.load(ref,{fetch:f}).then(function(){"
            "process.stdout.write(JSON.stringify({headers:headers}));process.exit(0);"
            "}).catch(function(){"
            "process.stdout.write(JSON.stringify({headers:headers}));process.exit(0);"
            "});"
        )
        r = _run(js)
        h = r.get("headers")
        self.assertIsNone(h, "fetch should not be called with custom headers; got: " + str(h))


# ---------------------------------------------------------------------------
# parsePaste
# ---------------------------------------------------------------------------

class ParsePasteEspn(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = (FIX / "espn_settings_paste-reconstructed.txt").read_text()

    def _parse(self, text=None):
        t = text if text is not None else self.text
        js = f"process.stdout.write(JSON.stringify(DL.parsePaste({json.dumps(t)})))"
        return _run(js)

    def test_platform(self):
        r = self._parse()
        self.assertEqual(r["platform"], "espn")

    def test_ok(self):
        r = self._parse()
        self.assertTrue(r["ok"], r)

    def test_budget(self):
        r = self._parse()
        self.assertEqual(r["league"]["budget"], 200)

    def test_slot_qb(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["QB"], 1)

    def test_slot_rb(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["RB"], 2)

    def test_slot_wr(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["WR"], 2)

    def test_slot_te(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["TE"], 1)

    def test_slot_flex(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["FLEX"], 1)

    def test_slot_k(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["K"], 1)

    def test_slot_dst(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["DST"], 1)

    def test_slot_bn(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["BN"], 6)

    def test_scoring_pass_yds(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["pass_yds"], 0.04)

    def test_scoring_pass_tds(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["pass_tds"], 4.0)

    def test_scoring_ints(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["ints"], -2.0)

    def test_scoring_rec(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["rec"], 0.5)

    def test_scoring_fum_lost(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["fum_lost"], -2.0)

    def test_scoring_label_half_ppr(self):
        r = self._parse()
        self.assertEqual(r["league"]["scoringLabel"], "Half PPR")


class ParsePasteYahoo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = (FIX / "yahoo_settings_paste-reconstructed.txt").read_text()

    def _parse(self, text=None):
        t = text if text is not None else self.text
        js = f"process.stdout.write(JSON.stringify(DL.parsePaste({json.dumps(t)})))"
        return _run(js)

    def test_platform(self):
        r = self._parse()
        self.assertEqual(r["platform"], "yahoo")

    def test_ok(self):
        r = self._parse()
        self.assertTrue(r["ok"], r)

    def test_budget(self):
        r = self._parse()
        self.assertEqual(r["league"]["budget"], 200)

    def test_slot_qb(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["QB"], 1)

    def test_slot_rb(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["RB"], 2)

    def test_slot_wr(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["WR"], 2)

    def test_slot_te(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["TE"], 1)

    def test_slot_flex(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["FLEX"], 1)

    def test_slot_dst(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["DST"], 1)

    def test_slot_bn(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["BN"], 6)

    def test_scoring_rec(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["rec"], 0.5)

    def test_scoring_ints_yahoo_default(self):
        # Yahoo default is -1 for ints
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["ints"], -1.0)

    def test_scoring_fum_lost(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["fum_lost"], -2.0)

    def test_scoring_label(self):
        r = self._parse()
        self.assertEqual(r["league"]["scoringLabel"], "Half PPR")


class ParsePasteSleeper(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = (FIX / "sleeper_settings_paste-reconstructed.txt").read_text()

    def _parse(self, text=None):
        t = text if text is not None else self.text
        js = f"process.stdout.write(JSON.stringify(DL.parsePaste({json.dumps(t)})))"
        return _run(js)

    def test_platform(self):
        r = self._parse()
        self.assertEqual(r["platform"], "sleeper")

    def test_ok(self):
        r = self._parse()
        self.assertTrue(r["ok"], r)

    def test_budget(self):
        r = self._parse()
        self.assertEqual(r["league"]["budget"], 200)

    def test_slot_qb(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["QB"], 2)

    def test_slot_flex(self):
        r = self._parse()
        self.assertEqual(r["league"]["slots"]["FLEX"], 3)

    def test_scoring_rec(self):
        r = self._parse()
        self.assertAlmostEqual(r["league"]["scoring"]["rec"], 1.0)

    def test_scoring_label_ppr(self):
        r = self._parse()
        self.assertEqual(r["league"]["scoringLabel"], "PPR")


class ParsePasteFailClosed(unittest.TestCase):

    def _parse(self, text):
        js = f"process.stdout.write(JSON.stringify(DL.parsePaste({json.dumps(text)})))"
        return _run(js)

    def test_garbage_text_ok_false(self):
        r = self._parse("zxqwerty garbage text nothing here 12345")
        self.assertFalse(r["ok"])

    def test_empty_text_ok_false(self):
        r = self._parse("")
        self.assertFalse(r["ok"])

    def test_missing_budget_in_missing(self):
        """ESPN paste without auction budget should put 'budget' in missing."""
        text = (
            "League Settings\n"
            "Fantasy Football\n"
            "Scoring Settings\n"
            "Passing Yards (PY)\t0.04 pts\n"
            "Interceptions Thrown (INT)\t-2 pts\n"
            "Quarterback (QB)\t1\n"
            "Bench\t6\n"
        )
        r = self._parse(text)
        self.assertIn("budget", r["missing"])
        # Budget defaults to 200 when missing
        self.assertEqual(r["league"]["budget"], 200)

    def test_found_and_missing_disjoint(self):
        """found and missing should not overlap for the same field."""
        text = (FIX / "espn_settings_paste-reconstructed.txt").read_text()
        r = self._parse(text)
        for f in r["found"]:
            self.assertNotIn(f, r["missing"], f"'{f}' in both found and missing")


# ---------------------------------------------------------------------------
# rosters-page paste: the live site's reader (reused, not re-written)
# ---------------------------------------------------------------------------

ROSTERS_JS = """
const fs=require('fs');
const rows=JSON.parse(fs.readFileSync('app/next/players-table-1.json','utf8')).map(r=>{const f=r.split('|');return {player_key:f[3],name:f[0],pos:f[1],team:f[2]}});
const out={};
for (const f of %s) out[f]=DL.parsePaste(fs.readFileSync('tests/fixtures/'+f+'.txt','utf8'),{rows});
out.noRows=DL.parsePaste(fs.readFileSync('tests/fixtures/league_paste/yahoo-league-rosters.txt','utf8'));
process.stdout.write(JSON.stringify(out));
"""
ROSTER_PAGES = ["league_paste/yahoo-league-rosters", "league_paste/espn-league-rosters", "league_paste/sleeper-league-rosters",
                "paste_defaults/espn-10team", "paste_defaults/sleeper-14team", "paste_defaults/yahoo-12team-superflex"]


class RostersPagePaste(unittest.TestCase):
    """A league rosters page pasted instead of a settings page (page shapes of tests/fixtures/league_paste and
    paste_defaults, the live site's own fixtures): team names and roster slots come from the live reader
    (app/next/league-paste.js); scoring and budget are not on the page and are listed as missing."""

    @classmethod
    def setUpClass(cls):
        cls.out = _run(ROSTERS_JS % json.dumps(ROSTER_PAGES))

    def test_team_names_and_platform(self):
        for f, platform in (("league_paste/yahoo-league-rosters", "yahoo"), ("league_paste/espn-league-rosters", "espn"),
                            ("league_paste/sleeper-league-rosters", "sleeper")):
            r = self.out[f]
            self.assertTrue(r["ok"], f)
            self.assertEqual(r["source"], "rosters")
            self.assertEqual(r["platform"], platform)
            self.assertEqual([t["name"] for t in r["league"]["teams"]][:2], ["Team Alpha", "Team Beta"])
            self.assertEqual(len(r["league"]["teams"]), 5)

    def test_league_sizes_and_slots(self):
        want = {"paste_defaults/espn-10team": (10, {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "K": 1, "DST": 1, "BN": 6}),
                "paste_defaults/sleeper-14team": (14, {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 2, "SUPERFLEX": 0, "K": 1, "DST": 1, "BN": 5}),
                "paste_defaults/yahoo-12team-superflex": (12, {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SUPERFLEX": 1, "K": 1, "DST": 1, "BN": 6})}
        for f, (teams, slots) in want.items():
            r = self.out[f]
            self.assertEqual(len(r["league"]["teams"]), teams, f)
            self.assertEqual(r["league"]["slots"], slots, f)

    def test_scoring_and_budget_are_missing_not_guessed(self):
        for f in ROSTER_PAGES:
            r = self.out[f]
            self.assertIn("budget", r["missing"], f)
            self.assertIn("scoring", r["missing"], f)
            self.assertEqual(r["league"]["budget"], 200)
            self.assertEqual(r["league"]["scoring"]["rec"], 0)
        # a slot the teams disagree on is listed, and keeps the default
        self.assertIn("slots.DST", self.out["league_paste/sleeper-league-rosters"]["missing"])

    def test_no_player_rows_means_not_read(self):
        self.assertFalse(self.out["noRows"]["ok"])


if __name__ == "__main__":
    unittest.main()
