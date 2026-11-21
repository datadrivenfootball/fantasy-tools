// Connector walkthrough 2026-11-21 (Jeremy: "Do all recommendations"): league entry for the chat tools.
// - scoring and superflex are asked for, never assumed ("ask for them, never default silently");
// - 4 to 20 teams priced at the nearest supported count, slots in plain words, saved in the state;
// - league_paste read by the site's paste reader (the repo's own files here), league_teams + my_team, new-line rosters;
// - a later call needs only the state: settings, slots and every roster come back from it;
// - "K Brandon McManus" and a known kicker's bare name are kickers, and a miss is never offered another surname.
// Stub get-values, no network. Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { evalPasteReader, nearestTeams, parseSlots } from "../../supabase/functions/mcp/league.ts";
import { matchName, notEvaluated, setKnownKickers, splitNames } from "../../supabase/functions/mcp/names.ts";

const require = createRequire(import.meta.url);
const codec = require("../../app/v2/ddf-state.js");
const finder = require("../../app/v2/finder.js");
const ORIGIN = "https://site.test";
const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const kdef = `window.TradeValueKDef = ${JSON.stringify({ kickers: [{ name: "Brandon McManus", team: "GB" }, { name: "Chris Boswell", team: "PIT" }], defenses: [] })};`;
const { reader: paste, kickers } = evalPasteReader([kdef, read("../../app/v2/roster-paste.js"), read("../../app/next/rosterparse.js"), read("../../app/next/league-paste.js")]);
assert.ok(paste, "the site's paste reader loads in a sandbox");
assert.deepEqual(kickers, ["Brandon McManus", "Chris Boswell"]);

const chart = (v) => ({ usatoday: v, fantasycalc: v, fantasypros: v, cbs: v });
const rows = [
  [1, "Josh Allen", "QB", 40], [2, "Bijan Robinson", "RB", 70], [3, "George Pickens", "WR", 30], [4, "Trey McBride", "TE", 21],
  [5, "Jahmyr Gibbs", "RB", 80], [6, "Justin Jefferson", "WR", 50], [7, "Hunter Henry", "TE", 1], [8, "Jared Goff", "QB", 12],
  [9, "Rachaad White", "RB", 9], [10, "Garrett Wilson", "WR", 28], [11, "Chris Bell", "WR", 2], [12, "Tyler Goodson", "RB", 1],
].map(([player_key, name, pos, value]) => ({ player_key, name, pos, value, tier: "starter", chart_values: chart(value), chart_indexed: chart(value), ddf_value_charts: value, ddf_value_projections: value }));
const leagues = [];
const values = async (scoring, teams, superflex, league) => {
  leagues.push({ scoring, teams, superflex, league: league ?? null });
  return { attribution: "Data Driven Football", as_of: "2026-11-21", setting: { scoring, teams, superflex }, players: rows,
    sources_included: ["usatoday", "fantasycalc", "fantasypros", "cbs"], sources_excluded: [] };
};
const deps = { codec, siteOrigin: ORIGIN, paste };
const finderDeps = { finder, fetchCharts: values };
const call = async (name, args, d = deps) => (await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, values, d, finderDeps)).result;
const text = (r) => r.content[0].text;

// ---------- settings are asked for ----------
let r = await call("get_values", { limit: 1 });
assert.equal(r.isError, true);
assert.match(text(r), /^Missing league settings: scoring \(ppr, half_ppr or standard\) and superflex \(yes or no\)\. Ask the user/);
r = await call("get_values", { scoring: "half", limit: 1 });
assert.match(text(r), /^Missing league settings: superflex \(yes or no\)\. Ask the user for it/);
for (const tool of ["get_player_value", "trade_targets", "compare_trade", "make_state", "find_trades", "find_trades_league"]) {
  r = await call(tool, { superflex: false, names: "Josh Allen", player_name: "Josh Allen", side_a: "Josh Allen", side_b: "Jared Goff", mine: "Josh Allen", theirs: "Jared Goff", opponents: [{ name: "B", roster: "Jared Goff" }] });
  assert.match(text(r), /^Missing league settings: scoring/, tool);
}
// a superflex slot answers superflex; an older client's settings object is read like top-level fields
r = await call("get_values", { scoring: "ppr", slots: "QB, RB, RB, WR, WR, TE, W/R/T, Q/W/R/T, K, DEF, BN, BN", limit: 1 });
assert.notEqual(r.isError, true, text(r));
assert.equal(leagues.at(-1).superflex, 1);
assert.deepEqual(leagues.at(-1).league, { roster: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, BENCH: 2 } }, "slots priced as the league's roster");
r = await call("get_values", { settings: { scoring: "half_ppr", teams: 10, superflex: true }, limit: 1 });
assert.deepEqual([leagues.at(-1).scoring, leagues.at(-1).teams, leagues.at(-1).superflex], ["half_ppr", 10, 1]);
assert.match(text(await call("get_values", { scoring: "ppr", superflex: false, limit: 1 })), /Team count not given: priced as 12 teams/);

// ---------- team counts and slots ----------
assert.deepEqual([4, 7, 9, 11, 13, 16, 20].map(nearestTeams), [8, 8, 10, 12, 14, 14, 14]);
assert.deepEqual(parseSlots({ QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, K: 1, DEF: 1, BN: 5 }), { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5 });
assert.deepEqual(parseSlots("QB, RB, RB, WR, WR, WR, TE, W/R/T, K, DEF, BN, BN, BN, BN, BN, IR"), { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5 });
assert.deepEqual(parseSlots("QB 1, RB 2, WR x3, TE: 1, OP 1, BN (6)"), { QB: 1, RB: 2, WR: 3, TE: 1, SUPERFLEX: 1, BENCH: 6 });
assert.deepEqual(parseSlots([1, 2, 3, 1, 1, 5]), { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5 });
assert.throws(() => parseSlots("QB, Wizard"), /unknown slot "Wizard"/);
r = await call("get_values", { scoring: "ppr", superflex: false, slots: "QB, Wizard" });
assert.match(text(r), /unknown slot/);

// ---------- names: new lines, list markers, kickers ----------
assert.deepEqual(splitNames("WR George Pickens\nRB Rachaad White\n# a comment\n1. Trey McBride\n- Josh Allen; Jared Goff"),
  ["WR George Pickens", "RB Rachaad White", "Trey McBride", "Josh Allen", "Jared Goff"]);
assert.equal(notEvaluated("K Brandon McManus")?.pos, "K", "a leading slot label before a full name is a kicker");
assert.equal(notEvaluated("K Allen"), null, "K Allen stays a name");
assert.equal(notEvaluated("K. J. Osborn"), null);
setKnownKickers([]);
assert.doesNotMatch(matchName(rows, "Chris Boswell").note, /Chris Bell/, "a miss is never offered a different surname");
assert.doesNotMatch(matchName(rows, "Tyler Loop").note, /Goodson/);
setKnownKickers(kickers);
assert.match(matchName(rows, "Chris Boswell").note, /kicker, not valued/, "a known kicker's bare name is a kicker");
assert.equal(matchName(rows, "Chris Bell").player?.player_key, 11, "the WR keeps his own name");
// A bare kicker surname is a kicker; with no kicker list it is NOT FOUND with no cross-surname guesses.
assert.match(matchName(rows, "Boswell").note, /^Boswell: kicker, not valued/, "a bare kicker surname is a kicker");
assert.equal(notEvaluated("Boswell", rows)?.pos, "K");
assert.equal(matchName(rows, "Bell").player?.player_key, 11, "a priced player's surname is never a kicker");
setKnownKickers([]);
assert.equal(matchName(rows, "Boswell").note, "Boswell: NOT FOUND", "a bare surname is offered no other surname");
setKnownKickers(kickers);

// ---------- league_paste + my_team is enough; the state carries everything ----------
const leaguePaste = [
  "Team A", "QB Josh Allen", "RB Bijan Robinson", "WR George Pickens", "TE Hunter Henry", "RB Rachaad White", "K Brandon McManus", "DEF Seahawks",
  "", "Team B", "QB Jared Goff", "RB Jahmyr Gibbs", "WR Justin Jefferson", "TE Trey McBride", "K Chris Boswell", "DEF Bengals",
  "", "Team C", "WR Garrett Wilson", "WR Chris Bell", "RB Tyler Goodson",
].join("\n");
r = await call("make_state", { scoring: "half_ppr", superflex: "no", teams: 12, slots: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, K: 1, DEF: 1, BN: 5 },
  league_paste: leaguePaste, my_team: "Team A" });
assert.notEqual(r.isError, true, text(r));
assert.match(text(r), /^Saved 3 teams, yours is Team A and slots with the league settings\./);
assert.match(text(r), /Read 3 teams from the paste: Team A \(5\), Team B \(4\), Team C \(3\)\./);
assert.match(text(r), /Left out: 2 kickers and 2 defenses \(not valued\)\./);
const saved = r.structuredContent.state;
assert.equal(saved.league.scoring, "half_ppr");
assert.deepEqual(saved.league.roster, { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 5 });
assert.equal(saved.work.teams.length, 3);
assert.equal(saved.work.my_team, 0);
assert.deepEqual(saved.work.mine.map((p) => p.key), ["1", "2", "3", "7", "9"]);
// the link carries the league too, and reads back the same
const link = r.structuredContent.site_url;
assert.match(link, /[?&]lt=Team%2520A:1,2,3,7,9\|Team%2520B:8,5,6,4\|Team%2520C:10,11,12&mt=0/);
assert.deepEqual(codec.decodeBlock(link).state.work.teams, saved.work.teams.map((t) => ({ name: t.name, players: t.players.map((p) => ({ key: p.key })) })));
assert.equal(codec.decodeBlock(link).state.work.my_team, 0);

// a later call passes only the state: settings, slots and rosters come back from it
const block = codec.encodeBlock(saved);
r = await call("find_trades_league", { state: block });
assert.notEqual(r.isError, true, text(r));
assert.deepEqual([leagues.at(-1).scoring, leagues.at(-1).superflex], ["half_ppr", 0]);
assert.deepEqual(leagues.at(-1).league.roster, { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5 });
assert.equal(r.structuredContent.perOpponent.map((o) => o.name).join(","), "Team B,Team C");
assert.equal(r.structuredContent.mine.matched, 5);
r = await call("find_trades", { state: block, their_team: "Team B" });
assert.notEqual(r.isError, true, text(r));
assert.match(text(r), /Trading with Team B\./);
r = await call("find_trades", { state: block });
assert.match(text(r), /needs their_team .* Teams: 0 Team A, 1 Team B, 2 Team C/);

// league_teams with new-line rosters, my_team by index
r = await call("find_trades_league", { scoring: "ppr", superflex: false, teams: 12,
  league_teams: [{ name: "Mine", players: "Josh Allen\nBijan Robinson\nGeorge Pickens" }, { name: "Them", players: ["Jared Goff", "Jahmyr Gibbs"] }], my_team: 0 });
assert.notEqual(r.isError, true, text(r));
assert.equal(r.structuredContent.mine.matched, 3);
r = await call("make_state", { scoring: "ppr", superflex: false, league_teams: [{ name: "Mine", players: "Josh Allen" }, { name: "Them", players: "Jared Goff" }], my_team: "Nobody" });
assert.match(text(r), /my_team: no team named "Nobody"\. Teams: 0 Mine, 1 Them\./);
r = await call("make_state", { scoring: "ppr", superflex: false, my_team: 1 });
assert.match(text(r), /my_team needs the league/);
// with the paste reader down, league_paste says so instead of guessing
r = await call("make_state", { scoring: "ppr", superflex: false, league_paste: leaguePaste, my_team: 0 }, { codec, siteOrigin: ORIGIN, paste: null });
assert.match(text(r), /league paste reader is unavailable/);

// ---------- review fixes (2026-11-21) ----------
// a saved partner never overrides their_team; saved teams pick the rosters
r = await call("find_trades", { state: block, their_team: "Team C" });
assert.match(text(r), /Trading with Team C\./);
// "K. Walker III" is the running back, not a kicker
const walkerRows = [...rows, { ...rows[0], player_key: 13, name: "Kenneth Walker III", pos: "RB", value: 30 }];
assert.equal(matchName(walkerRows, "K. Walker III").player?.player_key, 13);
assert.doesNotMatch(matchName(walkerRows, "K Walker III").note, /kicker/, "K Walker III is not a kicker");
assert.match(matchName(walkerRows, "K Brandon McManus").note, /kicker, not valued/);
// a superflex state plus slots without a superflex slot keeps the state's superflex
const sfState = codec.encodeBlock({ league: { scoring: "ppr", teams: 12, roster: { QB: 1, SUPERFLEX: 1 } } });
r = await call("get_values", { state: sfState, slots: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BN: 5 }, limit: 1 });
assert.notEqual(r.isError, true, text(r));
assert.equal(leagues.at(-1).superflex, 1);
// names with % : | , survive the link
const odd = codec.normalize({ league: { scoring: "ppr" }, work: { teams: [{ name: "100% Juice: A|B, C&D=E", players: [{ name: "Odd % Name" }, { key: "7" }] }, { name: "Two", players: [] }], my_team: 0 } }).state;
const back = codec.decodeQuery(codec.encodeQuery(odd)).state.work;
assert.deepEqual(back.teams[0], { name: "100% Juice: A|B, C&D=E", players: [{ name: "Odd % Name" }, { key: "7" }] });
assert.equal(back.my_team, 0);
assert.equal(codec.decodeQuery("scoring=ppr&lt=A:1|B:2&mt=&v=1").state.work.my_team, undefined, "an empty mt= is not team 0");
// "#1 Josh Allen" is a ranked line, not a comment; a "# note" line is skipped
assert.deepEqual(splitNames("# my team\n#1 Josh Allen\n#2 Jared Goff\n#12"), ["Josh Allen", "Jared Goff", "#12"]);

console.log("ok");
