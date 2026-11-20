// test_kdef_paste_matching.js — kickers and defenses in a pasted roster are never read as another player.
// Run: node tests/test_kdef_paste_matching.js
// The bug (Jeremy, 2026-11-19): "Jason Sanders" (the kicker) was read as Ja'Tavion Sanders (TE). The initial-form
// fallback turned "jason sanders" into "j sanders" and took the only player with that form. The rules this file holds:
//   1. a line with a K or DEF tag (or a team-only defense name) only reaches a kicker or defense, and the engine
//      prices neither, so it stays not evaluated;
//   2. an initial form never replaces a different full first name, and a nickname or initial never crosses a position
//      the line names (an exact full name still wins);
//   3. an unmatched kicker or defense is reported as one, never given to another player;
//   4. a line that fits more than one player is reported with each one's position, and none is chosen.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
const P = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
globalThis.DDFRosterPaste = P;
require(path.join(ROOT, "app", "next", "rosterparse.js"));
const LP = require(path.join(ROOT, "app", "next", "league-paste.js"));

// Real names whose surnames are shared with kickers (no K or DEF rows: the engine prices neither).
const ROWS = [
  {player_key: 3925, name: "Ja'Tavion Sanders", pos: "TE", team: "CAR"},
  {player_key: 2030, name: "Raheim Sanders", pos: "RB", team: "CLE"},
  {player_key: 3602, name: "Shedeur Sanders", pos: "QB", team: "CLE"},
  {player_key: 11, name: "John Bates", pos: "TE", team: "WAS"},
  {player_key: 12, name: "Tyler Badie", pos: "RB", team: "DEN"},
  {player_key: 13, name: "Tucker Kraft", pos: "TE", team: "GB"},
  {player_key: 14, name: "Tre Tucker", pos: "WR", team: "LV"},
  {player_key: 15, name: "Bijan Robinson", pos: "RB", team: "ATL"},
  {player_key: 16, name: "Brian Robinson Jr.", pos: "RB", team: "SF"},
  {player_key: 17, name: "Josh Allen", pos: "QB", team: "BUF"},
  {player_key: 18, name: "Derrick Henry", pos: "RB", team: "BAL"},
  {player_key: 19, name: "Chigoziem Okonkwo", pos: "TE", team: "WAS"},
];
const KICKERS = {defenses: [], kickers: [
  {name: "Jason Sanders", team: "MIA"}, {name: "Jake Bates", team: "DET"}, {name: "Tyler Bass", team: "BUF"},
  {name: "Brandon McManus", team: "GB"}]};

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ok  ${name}`); }
  catch (error) { failed++; console.log(`  FAIL ${name}\n       ${error.message}`); }
}
function withKickers(fn) {
  globalThis.TradeValueKDef = KICKERS;
  try { return fn(); } finally { delete globalThis.TradeValueKDef; }
}
const read = line => P.extractPlayers(line, ROWS);
const ids = res => res.players.map(p => Number(p.id));

// --- 1. the Sanders case, both ways ---
test("a kicker line stays a kicker: Jason Sanders is never Ja'Tavion Sanders", () => {
  ["Jason Sanders K", "Sanders (K, MIA)", "Jason Sanders - K - MIA", "K Jason Sanders MIA", "Jason Sanders K MIA"].forEach(line => {
    const res = read(line);
    assert.deepStrictEqual(ids(res), [], line);
    assert.ok(res.unmatched.some(u => u.pos === "K"), `${line}: reported as a kicker`);
  });
  assert.deepStrictEqual(ids(read("Jason Sanders")), [], "untagged, no kicker list: not read as the TE");
});
test("a TE line stays the TE", () => {
  ["Ja'Tavion Sanders", "Ja'Tavion Sanders TE", "J. Sanders TE", "TE\tJa'Tavion Sanders\tCAR TE", "J. Sanders"].forEach(line => {
    assert.deepStrictEqual(ids(read(line)), [3925], line);
  });
});
test("the candidate matcher (team pages): a K entry only reaches a kicker; a TE entry reaches the TE", () => {
  const index = P.buildIndex(ROWS);
  const k = P.matchCandidate({name: "Jason Sanders", posHint: "K", teamHint: "MIA"}, index, {});
  assert.strictEqual(k.match, null);
  assert.strictEqual(k.reason, "kicker not matched");
  assert.strictEqual(P.matchCandidate({name: "J. Sanders", posHint: "K"}, index, {}).match, null, "even an initial that fits");
  assert.strictEqual(P.matchCandidate({name: "Jason Sanders", posHint: "TE"}, index, {}).match, null, "a different first name");
  assert.strictEqual(P.matchCandidate({name: "J. Sanders", posHint: "TE", teamHint: "CAR"}, index, {}).match.player_key, 3925);
});
test("a name over a 'Mia - K' line is not read as the TE; the kicker is reported", () => {
  const res = P.parse(["Jason SandersPlayer Note", "Mia - K", "Ja'Tavion SandersPlayer Note", "Car - TE"].join("\n"), ROWS);
  assert.deepStrictEqual(res.players.map(p => Number(p.id)), [3925]);
  assert.ok(res.unmatched.some(u => u.pos === "K"), JSON.stringify(res.unmatched));
});

// --- 2. a full first name beats an initial or a surname; fuzzy forms never cross positions ---
test("other kicker collisions: Jake Bates, Tyler Bass, Brandon McManus, Younghoe Koo", () => {
  ["Jake Bates", "Jake Bates K DET", "Tyler Bass", "Tyler Bass K", "Brandon McManus", "Younghoe Koo", "Koo (K, ATL)"].forEach(line => {
    assert.deepStrictEqual(ids(read(line)), [], line);
  });
});
test("an initial still reaches its player; a short first name still fits", () => {
  assert.deepStrictEqual(ids(read("D. Henry RB")), [18]);
  assert.deepStrictEqual(ids(read("Chig Okonkwo")), [19]);
});
test("a slot label is not a first name: 'TE Tucker Kraft' is Tucker Kraft, not Tre Tucker", () => {
  assert.deepStrictEqual(ids(read("TE\tTucker Kraft\tGB TE")), [13]);
});
test("an initial at another position is reported with that player's position, not matched", () => {
  const res = read("J. Sanders QB");
  assert.deepStrictEqual(ids(res), []);
  const u = res.unmatched.find(x => /^position does not match/.test(x.reason));
  assert.ok(u, JSON.stringify(res.unmatched));
  assert.deepStrictEqual(u.candidates, [{name: "Ja'Tavion Sanders", pos: "TE", team: "CAR"}]);
});
test("an exact full name is kept even under another slot label", () => {
  assert.deepStrictEqual(ids(read("RB  Josh Allen  BUF")), [17]);
});

// --- 3. unmatched kickers and defenses are reported as such ---
test("with the kicker list (kdef-names.js), an untagged kicker name is a kicker", () => withKickers(() => {
  const res = read("Jason Sanders");
  assert.deepStrictEqual(ids(res), []);
  assert.deepStrictEqual(res.unmatched.map(u => [u.pos, u.team]), [["K", "MIA"]]);
  const list = read("Josh Allen QB BUF, Jason Sanders");
  assert.deepStrictEqual(ids(list), [17]);
  assert.ok(list.unmatched.some(u => u.pos === "K" && u.line === "Jason Sanders"), JSON.stringify(list.unmatched));
}));
test("defenses: tagged or team-only, each kept as that team's defense", () => {
  const want = {"Dolphins D/ST": "MIA", "Miami": "MIA", "MIA DEF": "MIA", "49ers": "SF", "San Francisco 49ers": "SF",
    "49ers D/ST": "SF", "Miami Dolphins": "MIA", "Jets D/ST": "NYJ", "New York Jets": "NYJ"};
  Object.keys(want).forEach(line => {
    const res = read(line);
    assert.deepStrictEqual(ids(res), [], line);
    assert.deepStrictEqual(res.unmatched.map(u => [u.pos, u.team]), [["DEF", want[line]]], line);
  });
  assert.deepStrictEqual(read("New York").unmatched, [], "two teams: no defense guessed");
});
test("a defense name line and its position line are one defense", () => {
  const res = read("Jaguars\nJax - DEF");
  assert.strictEqual(res.unmatched.filter(u => u.pos === "DEF").length, 1);
});

// --- 4. ambiguous lines are surfaced with positions ---
test("an initial that fits two players is ambiguous, with each one's position", () => {
  const res = read("B. Robinson RB");
  assert.deepStrictEqual(ids(res), []);
  const u = res.unmatched.find(x => /^ambiguous/.test(x.reason));
  assert.deepStrictEqual(u.candidates.map(c => c.name + " " + c.pos).sort(), ["Bijan Robinson RB", "Brian Robinson Jr. RB"]);
  const c = P.matchCandidate({name: "B. Robinson", posHint: "RB"}, P.buildIndex(ROWS), {});
  assert.strictEqual(c.match, null);
  assert.ok(/^ambiguous/.test(c.reason) && c.candidates.length === 2, c.reason);
});

// --- the connect.html reader (league-paste.js) ---
const LEAGUE = [
  "Kick Six (5-1)", "QB Josh Allen BUF", "TE Ja'Tavion Sanders CAR", "K Jason Sanders MIA", "B. Robinson RB",
  "Field Goal Unit (4-2)", "Shedeur Sanders", "Jason Sanders", "MIA K", "Dolphins D/ST", "Jaguars", "Jax - DEF",
].join("\n");
test("league paste: the kicker is not evaluated, the TE is matched, the ambiguous line carries its options", () => {
  const res = LP.read(LEAGUE, ROWS);
  assert.ok(res.ok, res.reason);
  const [one, two] = res.teams;
  assert.deepStrictEqual(one.players.map(p => p.name), ["Josh Allen", "Ja'Tavion Sanders"]);
  assert.deepStrictEqual(one.unmatched.filter(u => u.reason === "kdef").map(u => [u.pos, u.key]), [["K", "x:K:MIA"]]);
  const look = one.unmatched.find(u => u.reason === "look");
  assert.deepStrictEqual(look.options.map(o => `${o.name} ${o.pos} ${o.team}`).sort(), ["Bijan Robinson RB ATL", "Brian Robinson Jr. RB SF"]);
  assert.deepStrictEqual(two.players.map(p => p.name), ["Shedeur Sanders"], "Jason Sanders is not Ja'Tavion Sanders");
  // "Jason Sanders" over "MIA K" is the kicker (its position line), and Jaguars / Jax - DEF one defense
  assert.deepStrictEqual(two.unmatched.filter(u => u.reason === "kdef").map(u => u.key).sort(), ["x:DEF:JAC", "x:DEF:MIA", "x:K:MIA"]);
});
test("league paste with the kicker list: an untagged kicker line is a kicker", () => withKickers(() => {
  const res = LP.read(LEAGUE, ROWS);
  assert.ok(res.teams[1].unmatched.some(u => u.reason === "kdef" && u.pos === "K" && u.line === "Jason Sanders"),
    JSON.stringify(res.teams[1].unmatched));
}));
test("league paste with the kicker list: a bare kicker line is a kicker, not a team name", () => withKickers(() => {
  const table = ROWS.map(r => `${r.name}|${r.pos}|${r.team}|${r.player_key}`);
  const text = ["Kick Six (5-1)", "Josh Allen QB BUF", "Ja'Tavion Sanders TE CAR", "Field Goal Unit (4-2)", "Shedeur Sanders QB CLE",
    "Jason Sanders", "Bijan Robinson RB ATL"].join("\n");
  const res = LP.read(text, ROWS, {table});
  assert.deepStrictEqual(res.teams.map(t => t.name.replace(/ \(.*\)$/, "")), ["Kick Six", "Field Goal Unit"]);
  assert.deepStrictEqual(res.teams[1].players.map(p => p.name), ["Shedeur Sanders", "Bijan Robinson"]);
  assert.ok(res.teams[1].unmatched.some(u => u.reason === "kdef" && u.pos === "K" && u.line === "Jason Sanders"));
}));
test("Sleeper import blocks ('Name POS TEAM'): the kicker is a kicker, the TE is the TE", () => {
  const res = LP.fromBlocks([{name: "A", text: "Jason Sanders K MIA\nJa'Tavion Sanders TE CAR"}, {name: "B", text: "MIA Defense DEF\nJosh Allen QB BUF"}], ROWS);
  assert.deepStrictEqual(res.teams[0].players.map(p => p.name), ["Ja'Tavion Sanders"]);
  assert.deepStrictEqual(res.teams[0].unmatched.map(u => [u.reason, u.pos]), [["kdef", "K"]]);
  assert.deepStrictEqual(res.teams[1].unmatched.map(u => [u.reason, u.key]), [["kdef", "x:DEF:MIA"]]);
});

// --- the published player table: the reported case on real rows ---
test("published player table: Jason Sanders and Jake Bates are never a TE", () => {
  const table = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"))
    .map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
  ["Jason Sanders", "Jason Sanders K", "Sanders (K, MIA)", "Jason Sanders - K - MIA", "Jake Bates", "Tyler Bass"].forEach(line => {
    assert.deepStrictEqual(P.extractPlayers(line, table).players, [], line);
  });
  const te = table.find(r => r.name === "Ja'Tavion Sanders");
  if (te) assert.deepStrictEqual(P.extractPlayers("Ja'Tavion Sanders TE", table).players.map(p => Number(p.id)), [te.player_key]);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
