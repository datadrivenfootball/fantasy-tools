"""Draft tool Phase 1 core (JEG-1667): app/draft/draft-core.js and draft-data.js under Node.

Gates covered here (no browser):
- the engine.md worked example through DraftCore.board (state -> teams -> engine) matches to the dollar,
  with room and with personal inflation, and the rival-cap variant;
- a mid-draft state encodes to a "#s=<token>+<check>" link and decodes to a deep-equal state; a cut or
  mistyped link fails its check; a trade-site (version 1) token is refused;
- the stale warning turns on when the pull is older than a day;
- a full 12-team board recomputes in under 200 ms;
- the data bundle is assembled without guessing names.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.draft_app_fixture import PULLED_AT, bundle

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "draft_worked_example.json").read_text())

PRELUDE = """
const C = require('./app/draft/draft-core.js');
const D = require('./app/draft/draft-data.js');
const E = require('./app/draft/draft-engine.js');
const LINEUP = require('./config/lineup_parameters.json');
const input = JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'));
"""


def run(body: str, payload=None):
    """Run an async JS body with C, D, E, LINEUP and `input`; it must return a JSON value."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
    js = PRELUDE + "(async () => {" + body + "})().then(v => process.stdout.write(JSON.stringify(v)));"
    proc = subprocess.run([node, "-e", js, f.name], capture_output=True, text=True, cwd=ROOT, timeout=120)
    Path(f.name).unlink()
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[-2000:])
    return json.loads(proc.stdout)


# The worked example as a draft state: 3 teams with $30, sales in order, and a
# fixed price model (ours and market straight from the fixture).
WORKED_JS = """
const a = input.auction;
const ids = ['A', 'B', 'C'];
const league = C.normalizeLeague({ teams: ids.map(n => ({ name: n, budget: 30 })), budget: 30, minBid: 1,
  slots: Object.assign({ QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0, K: 0, DST: 0, BN: 0 }, a.league.slots),
  scoring: E.SCORING_PRESETS.half });
const pos = {}, ours = {}, market = {}, source = {}, players = {};
Object.entries(a.players).forEach(([k, p]) => { pos[k] = p.pos; ours[k] = p.ours; market[k] = p.market; source[k] = 'proj'; players[k] = { key: k, name: k, pos: p.pos }; });
(input.sales || a.sold).forEach(s => { pos[s.key] = s.pos; players[s.key] = { key: s.key, name: s.key, pos: s.pos }; });
const order = Object.keys(a.players).concat((input.sales || a.sold).map(s => s.key));
const model = { league: C.engineLeague(league), players, pos, prices: { ours, market, source }, values: {}, tiers: {}, order };
const state = C.newState(league);
state.me = 0;
state.ourFactor = input.factor;
state.picks = (input.sales || a.sold).map(s => [s.key, ids.indexOf(s.team), s.price]);
const b = C.board(state, model);
return { rows: b.rows, maxBids: b.board.maxBids, inflation: b.inflation, teams: b.derived.teams };
"""


class WorkedExample(unittest.TestCase):
    """engine.md "Worked example": the board the page draws, from a draft state."""

    def check(self, factor, expected_rows, sales=None):
        out = run(WORKED_JS, {"auction": FIXTURE["auction"], "factor": factor, "sales": sales})
        for key, exp in expected_rows.items():
            row = out["rows"][key]
            for field in ("walkAway", "pushFloor", "buyLimit"):
                if field in exp:
                    self.assertEqual(row[field], exp[field], f"{key} {field} ({factor})")
            for field in ("oursInflated", "marketInflated"):
                if field in exp:
                    self.assertAlmostEqual(row[field], exp[field], places=6, msg=f"{key} {field} ({factor})")
        return out

    def test_room_inflation_matches_to_the_dollar(self):
        exp = FIXTURE["auction"]["expected"]
        out = self.check("room", exp["rows"])
        self.assertEqual(out["maxBids"], {"0": 13, "1": 13, "2": 27})
        self.assertAlmostEqual(out["inflation"]["room"], 1.25)
        self.assertAlmostEqual(out["inflation"]["market"], 1.25)
        self.assertEqual(out["inflation"]["moneyLeft"], 58)
        self.assertEqual([t["budgetLeft"] for t in out["teams"]], [15, 14, 29])
        self.assertEqual({k: v for k, v in out["teams"][0]["open"].items() if v}, {"QB": 1, "WR": 1, "TE": 1})
        # the doc's table, spelled out
        self.assertEqual([out["rows"][k]["walkAway"] for k in ("P5", "P6", "P7", "P8", "P9", "P11", "P12")], [13, 12, 0, 7, 7, 2, 2])
        self.assertEqual([out["rows"][k]["pushFloor"] for k in ("P5", "P6", "P7", "P8", "P9", "P11", "P12")], [13, 12, None, 7, 7, 2, 2])

    def test_personal_inflation_matches_to_the_dollar(self):
        out = self.check("personal", FIXTURE["auction"]["expected_personal"]["rows"])
        self.assertAlmostEqual(out["inflation"]["personal"], 0.8)
        self.assertEqual([out["rows"][k]["walkAway"] for k in ("P5", "P6", "P7", "P8", "P9", "P11", "P12")], [9, 8, 0, 5, 5, 1, 1])
        self.assertEqual([out["rows"][k]["pushFloor"] for k in ("P5", "P6", "P8", "P9", "P11", "P12")], [9, 8, 5, 5, 1, 1])

    def test_rival_cap_variant(self):
        # Only B has an open QB slot: B bought the RB and TE instead, C the QB.
        sales = [{"key": "P1", "pos": "RB", "team": "A", "price": 15}, {"key": "P2", "pos": "RB", "team": "B", "price": 10},
                 {"key": "P3", "pos": "TE", "team": "B", "price": 6}, {"key": "P4", "pos": "QB", "team": "C", "price": 1}]
        out = run(WORKED_JS, {"auction": FIXTURE["auction"], "factor": "room", "sales": sales})
        self.assertEqual({k: v for k, v in out["teams"][1]["open"].items() if v}, {"QB": 1, "WR": 1})
        self.assertEqual(out["rows"]["P5"]["buyLimit"], 13)
        self.assertEqual(out["rows"]["P5"]["pushFloor"], 12)


class LinkRoundTrip(unittest.TestCase):
    def setUp(self):
        self.out = run("""
const st = C.newState(C.defaultLeague());
const m = C.buildModel(input, st.league, {}, LINEUP);
st.league.teams[3].budget = 185; st.league.teams[0].name = "Tiny Hands"; st.me = 4; st.ourFactor = 'room';
for (let i = 0; i < 61; i++) st.picks.push([m.order[i * 2], i % 12, 1 + (i * 7) % 40]);
st.overrides[m.order[5]] = 61.25; st.overrides[m.order[80]] = 0;
const token = await C.encodeState(st);
const back = await C.decodeLink('https://example.test/draft/#s=' + token);
const cut = await C.decodeLink('#s=' + token.slice(0, 40) + token.slice(41));
const spaced = await C.decodeLink('#s=' + token.replace('+', ' ') + '.');
const encoded = await C.decodeLink('#s=' + token.replace('+', '%2B') + '&x=1');
const v1 = 'LAECAwEBBgMBf_AwHclLCoAgFAXQrcRt6sSavSVEmzC7qPRFxAixtUed6SnIEK2QAy8IrKddoJDMtPKPFM1MSIELmRC03TMwcgu38c14ZELBMX2joXCamHZGSF_rCw+Pa';
return { token, want: C.normalizeState(st), back, cut, spaced, encoded, tradeSite: await C.decodeLink('#s=' + v1),
  none: await C.decodeLink('#find-trade'), crc: C.crc16('123456789'), check: C.checkChars(token.split('+')[0]) };
""", bundle())

    def test_mid_draft_link_reopens_deep_equal(self):
        self.assertEqual(self.out["back"], self.out["want"])
        self.assertEqual(len(self.out["back"]["picks"]), 61)
        self.assertEqual(self.out["back"]["league"]["teams"][3]["budget"], 185)
        self.assertEqual(self.out["back"]["me"], 4)
        self.assertEqual(self.out["back"]["ourFactor"], "room")
        self.assertEqual(sorted(self.out["back"]["overrides"].values()), [0, 61.3])

    def test_check_and_separators(self):
        self.assertEqual(self.out["crc"], 0x29B1)  # LINK-FORMAT.md check value
        self.assertEqual(self.out["token"].split("+")[1], self.out["check"])
        self.assertEqual(self.out["cut"], {"error": "checksum"})
        self.assertEqual(self.out["spaced"], self.out["want"])
        self.assertEqual(self.out["encoded"], self.out["want"])
        self.assertIsNone(self.out["none"])

    def test_trade_site_token_is_refused(self):
        # LINK-FORMAT.md section 6: a version 1 league link is not a draft state.
        self.assertEqual(self.out["tradeSite"], {"error": "format"})

    def test_link_is_short_enough_to_share(self):
        self.assertLess(len(self.out["token"]), 2000)


class Staleness(unittest.TestCase):
    def test_stale_only_when_the_pull_is_older_than_a_day(self):
        out = run("""
const at = Date.parse(input.asOf.pulledAt), H = 3600000;
return [at + H, at + 24 * H, at + 26 * H, at + 80 * H].map(t => D.staleness(input, t))
  .concat([D.staleness({ asOf: {} }, at), D.staleness({ asOf: { pullDate: '2026-11-20' } }, at)]);
""", bundle())
        self.assertEqual([s["stale"] for s in out], [False, False, True, True, True, True])
        self.assertEqual(out[0]["pullDate"], "2026-11-28")
        self.assertIsNone(out[4]["pullDate"])
        self.assertEqual(PULLED_AT[:10], "2026-11-28")


class BoardSpeed(unittest.TestCase):
    def test_a_sale_recomputes_under_200_ms(self):
        out = run("""
const st = C.newState(C.defaultLeague());
const m = C.buildModel(input, st.league, {}, LINEUP);
const times = [];
for (let i = 0; i < 120; i++) {
  st.picks.push([C.board(st, m).derived.available[0], i % 12, 1]);
  const t = performance.now(); C.board(st, m); times.push(performance.now() - t);
}
return { max: Math.max(...times), players: m.order.length };
""", bundle())
        self.assertLess(out["max"], 200)
        self.assertGreater(out["players"], 250)


class ModelAndRoster(unittest.TestCase):
    def setUp(self):
        self.out = run("""
const st = C.newState(C.defaultLeague());
const m = C.buildModel(input, st.league, {}, LINEUP);
const ours = Object.values(m.prices.ours).reduce((a, b) => a + b, 0);
const sh = E.leagueShape(m.league);
const byName = n => m.order.find(k => m.players[k].name === n);
st.me = 2;
[['RB Player 01', 30], ['RB Player 02', 28], ['RB Player 03', 20], ['RB Player 04', 9], ['WR Player 01', 31], ['QB Player 01', 12], ['QB Player 02', 3], ['K Player 01', 1]]
  .forEach(([n, p]) => st.picks.push([byName(n), 2, p]));
const b = C.board(st, m);
const sum = C.rosterSummary(st, m, b.derived);
const over = Object.assign({}, st, { overrides: { [byName('WR Player 40')]: 90 } });
const m2 = C.buildModel(input, st.league, over.overrides, LINEUP);
st.league.teams[5].budget = 150;
const m3 = C.buildModel(input, C.normalizeLeague(st.league), {}, LINEUP);
return { ours, total: sh.teams * sh.budget, minSlots: sh.teams * sh.minBidSlotsPerTeam, counts: m.counts,
  sources: [...new Set(Object.values(m.prices.source))].sort(), tiers: ['RB Player 01', 'RB Player 30', 'RB Player 60'].map(n => m.tiers[byName(n)]),
  slots: sum.slots.filter(s => s.key).map(s => [s.slot, s.name]), open: b.derived.teams[2].open, summary: sum,
  before: m.prices.ours[byName('WR Player 40')], after: m2.prices.ours[byName('WR Player 40')], afterSource: m2.prices.source[byName('WR Player 40')],
  uneven: Object.values(m3.prices.ours).reduce((a, b) => a + b, 0), cliffs: C.tierCliffs(m, b.derived.available) };
""", bundle())

    def test_prices_add_up_to_the_room(self):
        o = self.out
        self.assertAlmostEqual(o["ours"] + o["minSlots"], o["total"], places=6)
        # a traded budget ($150 for one team) shrinks the room by $50
        self.assertAlmostEqual(o["uneven"] + o["minSlots"], o["total"] - 50, places=6)

    def test_every_price_names_its_source(self):
        self.assertEqual(self.out["sources"], ["proj", "vegas", "vegas+proj"])
        self.assertEqual(self.out["counts"]["vegas"], 6)

    def test_tiers_step_down_a_position(self):
        t = self.out["tiers"]
        self.assertEqual(t[0], 1)
        self.assertTrue(t[0] <= t[1] <= t[2] and t[2] > t[0], t)

    def test_slots_fill_position_then_flex_then_bench(self):
        slots = dict()
        for slot, name in self.out["slots"]:
            slots.setdefault(slot, []).append(name)
        self.assertEqual(len(slots["RB"]), 2)
        self.assertEqual(len(slots["FLEX"]), 1)
        self.assertEqual(slots["QB"], ["QB Player 01"])
        self.assertEqual(sorted(slots["BN"]), ["QB Player 02"] + [n for n in ["RB Player 01", "RB Player 02", "RB Player 03", "RB Player 04"]
                                                              if n not in slots["RB"] + slots["FLEX"]])
        self.assertEqual(slots["K"], ["K Player 01"])
        self.assertEqual({k: v for k, v in self.out["open"].items() if v}, {"WR": 1, "TE": 1, "DST": 1, "BN": 4})

    def test_roster_summary(self):
        s = self.out["summary"]
        self.assertEqual([o["slot"] for o in s["openStarters"]], ["WR", "TE", "DST"])
        self.assertEqual(s["spent"], 134)
        self.assertEqual(s["rosterDollars"], 134)
        self.assertLess(s["starterValue"], s["rosterValue"])
        self.assertTrue(0 < s["starterShare"] < 1)
        for c in s["byeCollisions"]:
            self.assertGreaterEqual(len(c["players"]), 2)

    def test_override_replaces_ddf_value(self):
        self.assertGreater(self.out["after"], self.out["before"] + 10)

    def test_tier_cliffs_count_what_is_left(self):
        by = {c["pos"]: c for c in self.out["cliffs"]}
        self.assertEqual(set(by), {"QB", "RB", "WR", "TE"})
        self.assertGreater(by["WR"]["left"], 0)
        self.assertGreater(by["RB"]["tier"], 0)


class AssembleBundle(unittest.TestCase):
    def test_names_join_and_nothing_is_guessed(self):
        raw = {
            "pulls": [{"pull_date": "2026-11-27", "source": "espn", "season": 2026, "status": "ok", "pulled_at": "2026-11-27T11:15:00+00:00"},
                      {"pull_date": "2026-11-28", "source": "espn", "season": 2026, "status": "ok", "pulled_at": "2026-11-28T11:15:00+00:00"},
                      {"pull_date": "2026-11-28", "source": "fantasypros_ecr", "season": 2026, "status": "failed"},
                      {"pull_date": "2026-11-27", "source": "fantasypros_ecr", "season": 2026, "status": "ok", "pulled_at": "2026-11-27T11:14:00+00:00"}],
            "names": ["Alpha Back|RB|DET|1", "Beta Wideout|WR|CIN|2"],
            "projections": [
                {"player_key": 1, "position": "RB", "team": "DET", "rushing_yards": 1200, "receptions": 50, "passing_yards": None},
                {"player_key": 2, "position": "WR", "team": "CIN", "receiving_yards": 1400},
                {"player_key": 3, "position": "TE", "team": "KC", "receiving_yards": 900},
                {"player_key": 4, "position": "TE", "team": "SF", "receiving_yards": 800}],
            "market": [
                {"source": "fantasypros_ecr", "scoring": "HALF", "source_player_id": "11", "player_name": "Alpha Back Jr.", "pos": "RB", "team": "DET", "bye": 6, "rank_overall": 1, "tier": 1, "credit": "Rankings: FantasyPros"},
                {"source": "espn", "scoring": "PPR", "source_player_id": "91", "player_name": "Alpha Back", "pos": "RB", "team": "DET", "dollars": 57, "aav": 73.2, "credit": "ESPN"},
                {"source": "fantasypros_ecr", "scoring": "HALF", "source_player_id": "13", "player_name": "Gamma End", "pos": "TE", "team": "KC", "bye": 10, "rank_overall": 30, "tier": 4},
                {"source": "fantasypros_ecr", "scoring": "HALF", "source_player_id": "14", "player_name": "Delta End", "pos": "TE", "team": "SF", "bye": 9, "rank_overall": 40, "tier": 5},
                {"source": "fantasypros_ecr", "scoring": "HALF", "source_player_id": "15", "player_name": "Epsilon End", "pos": "TE", "team": "SF", "bye": 9, "rank_overall": 90, "tier": 9},
                {"source": "fantasypros_ecr", "scoring": "HALF", "source_player_id": "16", "player_name": "Zeta Kicker", "pos": "K", "team": "DAL", "bye": 7, "rank_overall": 160, "tier": 12}],
            "vegas": [{"player_name": "Alpha Back", "market": "season_rush_yds", "line": 1100.5, "book": "a"},
                      {"player_name": "Alpha Back", "market": "season_rush_yds", "line": 1099.5, "book": "b"},
                      {"player_name": "Alpha Back", "market": "season_rush_tds", "line": None, "book": "b"},
                      {"player_name": "Nobody Known", "market": "season_rec_yds", "line": 700.5, "book": "a"}],
            "projectionSnapshot": "2026-09-11", "vegasSnapshot": "2026-09-12", "vegasSource": "books"}
        b = run("return D.assemble(input);", raw)
        by = {p["name"]: p for p in b["players"]}
        alpha = by["Alpha Back"]
        self.assertEqual(alpha["key"], "1")
        self.assertEqual(alpha["proj"]["rush_yds"], 1200)
        self.assertEqual(alpha["proj"]["pass_yds"], 0)
        self.assertEqual(alpha["ecr"]["HALF"]["rank"], 1)  # "Alpha Back Jr." is the same player
        self.assertEqual(alpha["espn"], {"PPR": 57, "aav": 73.2})
        self.assertEqual(alpha["bye"], 6)
        self.assertEqual(alpha["vegas"], {"season_rush_yds": 1100.0})  # two books averaged; a null line is missing, not 0
        # key 3 (TE, KC) has one market-only TE on that team: named. Key 4 (TE, SF) has two: left out, counted.
        self.assertEqual(by["Gamma End"]["key"], "3")
        self.assertEqual(by["Gamma End"]["proj"]["rec_yds"], 900)
        self.assertIsNone(by["Delta End"]["proj"])
        self.assertEqual(b["dropped"], {"unnamedProjections": 1, "vegasUnmatched": 1})
        self.assertEqual(by["Zeta Kicker"]["pos"], "K")
        # the oldest of the latest ok pulls decides freshness
        self.assertEqual(b["asOf"]["pullDate"], "2026-11-27")
        self.assertEqual(b["asOf"]["sources"]["espn"]["pullDate"], "2026-11-28")
        self.assertEqual(b["credits"], ["ESPN", "Rankings: FantasyPros"])


if __name__ == "__main__":
    unittest.main()
