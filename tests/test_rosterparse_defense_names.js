// test_rosterparse_defense_names.js — a defense line is never a team name in the league paste reader.
// Run: node tests/test_rosterparse_defense_names.js
// The bug (2026-11-22): a whole league pasted as bare player names (no slot labels) ends every team with its defense
// ("Lions", "Jaguars", "49ers"). rosterparse.js read that line as the next team's name: on the USO paste 11 of 12 teams
// were renamed and 11 defenses lost; a Yahoo Starting Rosters screenshot paste lost both defenses.
// Rule held here: a line that IS a defense (nickname, "City Nickname", "Nickname D/ST") is a roster row, not a team
// name, except where the page marks it as a header (markdown heading, above a "Pos Player" table, before a ":" list,
// or the first line of the paste). A line with other words ("Lions Fans") is a team name as before.
// Fixtures in tests/fixtures/defense_names hold real player names; team names are scrubbed ("Team 1", "Team A").
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
const DIR = path.join(ROOT, "tests", "fixtures", "defense_names");
global.window = globalThis;
globalThis.TradeValueKDef = JSON.parse(fs.readFileSync(path.join(DIR, "kickers.json"), "utf8"));
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
const LP = require(path.join(ROOT, "app", "next", "league-paste.js"));
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
const RP = window.DDF.rosterParse;

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ok  ${name}`); }
  catch (error) { failed++; console.log(`  FAIL ${name}\n       ${error.message}`); }
}
const fixture = f => fs.readFileSync(path.join(DIR, f), "utf8");
const names = text => RP.teams(text, {players: TABLE}).map(t => t.name);
const kdefCount = res => res.teams.reduce((a, t) => a + t.unmatched.filter(u => u.reason === "kdef").length, 0);

test("USO bare-name paste: all 12 team names come back, no defense is a team name", () => {
  const text = fixture("uso-bare-names.txt");
  assert.deepStrictEqual(names(text), Array.from({length: 12}, (_, i) => `Team ${i + 1}`));
  const res = LP.read(text, ROWS, {table: TABLE});
  assert.strictEqual(res.ok, true, res.reason);
  assert.deepStrictEqual(res.teams.map(t => t.name), Array.from({length: 12}, (_, i) => `Team ${i + 1}`));
  assert.strictEqual(res.teams.reduce((a, t) => a + t.players.length, 0), 156, "skill players kept");
  assert.strictEqual(kdefCount(res), 24, "12 kickers and 12 defenses kept as not evaluated");
  res.teams.forEach(t => assert.strictEqual(t.unmatched.filter(u => u.reason === "kdef").length, 2, `${t.name}: K and DEF`));
});

test("Yahoo Starting Rosters screenshot shape (bare names): all 4 teams, both defenses and both kickers kept", () => {
  const text = fixture("yahoo-screenshot-bare-names.txt");
  assert.deepStrictEqual(names(text), ["Team A", "Team B", "Team C", "Team D"]);
  const res = LP.read(text, ROWS, {table: TABLE});
  assert.strictEqual(res.ok, true, res.reason);
  assert.strictEqual(kdefCount(res), 4, "2 kickers and 2 defenses");
  const first = res.teams[0].unmatched.map(u => u.line);
  assert.ok(first.includes("Lions"), "Lions kept on the first team");
  assert.ok(res.teams[1].unmatched.map(u => u.line).includes("Jaguars"), "Jaguars kept on the second team");
});

test("every defense spelling is skipped as a team name", () => {
  ["Lions", "Detroit Lions", "Lions D/ST", "Lions DST", "Lions DEF", "Lions Defense", "49ers", "San Francisco 49ers", "New York Giants", "Washington Commanders", "lions"].forEach(def => {
    const text = `Team 1\nJosh Allen\nBijan Robinson\n${def}\nTeam 2\nJordan Love\nSaquon Barkley\n`;
    assert.deepStrictEqual(names(text), ["Team 1", "Team 2"], def);
  });
});

test("a real team named like a defense is not broken where the page marks the header", () => {
  const tableHeader = "Lions\nPos Player\nQB Josh Allen\nRB Bijan Robinson\nTeam 2\nPos Player\nQB Jordan Love\nRB Saquon Barkley\n";
  assert.deepStrictEqual(names(tableHeader), ["Lions", "Team 2"], "above a table header");
  const markdown = "## Lions\nJosh Allen\nBijan Robinson\n## Team 2\nJordan Love\nSaquon Barkley\n";
  assert.deepStrictEqual(names(markdown), ["Lions", "Team 2"], "markdown heading");
  const first = "Lions\nJosh Allen\nBijan Robinson\nTeam 2\nJordan Love\nSaquon Barkley\n";
  assert.deepStrictEqual(names(first), ["Lions", "Team 2"], "first line of the paste");
  const inline = "Lions: Josh Allen, Bijan Robinson, Jordan Love, Saquon Barkley\nJaguars: Mike Evans, Tyreek Hill, Derrick Henry, Josh Jacobs\n";
  assert.deepStrictEqual(names(inline), ["Lions", "Jaguars"], "before a colon list");
});

test("a team whose name only holds a defense word is still a team name", () => {
  const text = "Team 1\nJosh Allen\nBijan Robinson\nJaguars Fans\nJordan Love\nSaquon Barkley\nMiami\nMike Evans\nDerrick Henry\n";
  assert.deepStrictEqual(names(text), ["Team 1", "Jaguars Fans", "Miami"], "'Jaguars Fans' and a lone city are kept as names");
});

test("pastes with slot labels or tags read as before", () => {
  const labeled = "Team 1\nQB Josh Allen\nRB Bijan Robinson\nDEF Lions\nTeam 2\nQB Jordan Love\nRB Saquon Barkley\nDEF Jaguars\n";
  assert.deepStrictEqual(names(labeled), ["Team 1", "Team 2"]);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
