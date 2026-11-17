// test_paste_settings.js — JEG-1689: league settings read from a pasted league (app/next/league-paste.js inferSettings,
// enginePatch, pasteNotice). Run: node tests/test_paste_settings.js
// Jeremy, 2026-11-16: "Pasting leagues should allow for getting to at least the total number of rostered players. It may
// allow for inferring the roster construction as well. Update so what is set to default takes advantage of the paste.
// For example team count will also be known."
// 1. Each provider shape at a real league size (tests/fixtures/paste_defaults, built by make.js): team count, lineup,
//    bench, K and DEF read from the slot labels; a paste cut off mid-team infers nothing and says so.
// 2. Before/after on the live reader's fixtures (tests/fixtures/league_paste) and the real Yahoo pastes (entry_paste 01,
//    02): what moves off the site default, and what does not.
// 3. A field the reader confirmed or changed is never set again; a league with no paste is never touched.
// 4. The settings.html notice for each case (all read, partly read, cut off, unsupported size, nothing read).
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
const LP = require(path.join(ROOT, "app", "next", "league-paste.js"));

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ok  ${name}`); }
  catch (error) { failed++; console.log(`  FAIL ${name}\n       ${error.message}`); }
}

// the site default (curve-widget.js DEFAULT_ROSTER, 12 teams): the "before" of every paste
const STANDARD = {teams: 12, QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, K: 1, DST: 1, BENCH: 7};
function after(ps, confirmed) {
  const out = Object.assign({}, STANDARD), patch = LP.enginePatch(ps, confirmed) || {};
  if (patch.teams) out.teams = patch.teams;
  if (Number.isInteger(patch.superflexSlots)) out.SUPERFLEX = patch.superflexSlots;
  Object.assign(out, patch.roster || {});
  return out;
}
function changed(ps) {
  const a = after(ps), out = {};
  Object.keys(STANDARD).forEach(k => { if (a[k] !== STANDARD[k]) out[k] = [STANDARD[k], a[k]]; });
  return out;
}
function notice(ps, confirmed) {
  return LP.pasteNotice(ps, {pending: LP.pendingFields(ps, confirmed), values: after(ps, confirmed), standard: STANDARD});
}

const DEF_DIR = path.join(ROOT, "tests", "fixtures", "paste_defaults");
const DEF_ROWS = JSON.parse(fs.readFileSync(path.join(DEF_DIR, "players.json"), "utf8"))
  .map(([name, pos, team], i) => ({player_key: i + 1, name, pos, team}));
const readDef = f => LP.read(fs.readFileSync(path.join(DEF_DIR, f), "utf8"), DEF_ROWS);

// 1. providers
const PROVIDERS = {
  "espn-10team.txt": {teams: 10, roster: {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, K: 1, DST: 1, BENCH: 6}, perTeam: 16, total: 159},
  "yahoo-12team-superflex.txt": {teams: 12, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 1, K: 1, DST: 1, BENCH: 6}, perTeam: 18, total: 216},
  "sleeper-14team.txt": {teams: 14, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 2, SUPERFLEX: 0, K: 1, DST: 1, BENCH: 5}, perTeam: 16, total: 224},
};
Object.keys(PROVIDERS).forEach(f => test(`provider shape: ${f}`, () => {
  const res = readDef(f), want = PROVIDERS[f], ps = res.pasteSettings;
  assert.strictEqual(res.ok, true, res.reason);
  assert.strictEqual(res.teams.length, want.teams, "every team read");
  assert.strictEqual(ps.partial, false);
  assert.strictEqual(ps.teams, want.teams, "team count");
  assert.deepStrictEqual(ps.roster, want.roster, "lineup, bench, K and DEF");
  assert.deepStrictEqual(ps.why, {}, "nothing left unread");
  assert.strictEqual(ps.rostered.total, want.total, "players across the league");
  assert.strictEqual(ps.rostered.max, want.perTeam, "players on the biggest roster");
  assert.deepStrictEqual(LP.record(res, "paste").pasteSettings, ps, "ddf:pasted keeps it");
}));
test("ESPN: an empty bench slot is still a bench slot (the label shows)", () => {
  const ps = readDef("espn-10team.txt").pasteSettings;
  assert.deepStrictEqual(ps.rostered.perTeam.map(t => t.count), [16, 16, 16, 16, 16, 16, 16, 16, 16, 15]);
  assert.strictEqual(ps.roster.BENCH, 6);
});
test("partial paste: one team cut off, nothing inferred, the paste says so", () => {
  const ps = readDef("espn-10team-partial.txt").pasteSettings;
  assert.strictEqual(ps.partial, true);
  assert.strictEqual(ps.teams, null);
  assert.strictEqual(ps.why.teams, "partial");
  assert.ok(Object.values(ps.roster).every(v => v === null), "no lineup from a cut-off paste");
  assert.strictEqual(LP.enginePatch(ps, {}), null, "the engine is not touched");
  assert.strictEqual(ps.rostered.total, 148, "rostered players still known");
  const n = notice(ps, {});
  assert.strictEqual(n.show, true);
  assert.deepStrictEqual(n.lines, ["Your paste looks cut off: Bench Mob shows only 4 players, while other teams show up to 16. We left your team count (12) and lineup as they were. Copy the whole rosters page again, or set them below."]);
});

// 2. before/after on the live reader's fixtures and real pastes
const LIVE_DIR = path.join(ROOT, "tests", "fixtures", "league_paste");
const LIVE_TEAMS = JSON.parse(fs.readFileSync(path.join(LIVE_DIR, "teams.json"), "utf8"));
const LIVE_ROWS = [];
Object.values(LIVE_TEAMS).forEach(rows => rows.forEach(([name, team, pos]) => {
  if (pos !== "K" && pos !== "D/ST") LIVE_ROWS.push({player_key: name.toLowerCase().replace(/[^a-z]/g, "_"), name, pos, team});
}));
const readLive = f => LP.read(fs.readFileSync(path.join(LIVE_DIR, f), "utf8"), LIVE_ROWS);
["espn-league-rosters.txt", "espn-league-rosters-split-record.txt", "yahoo-league-rosters.txt"].forEach(f => test(`before/after: ${f} (5 teams)`, () => {
  const ps = readLive(f).pasteSettings;
  // the lineup matches the site default; the bench (5 shown on every team) is the one value that moves; 5 teams is not a size we run
  assert.deepStrictEqual(changed(ps), {BENCH: [7, 5]});
  assert.strictEqual(ps.why.teams, "unsupported");
  assert.strictEqual(ps.rostered.total, 72);
}));
test("before/after: sleeper-league-rosters.txt (a bench DEF without its BN label: DEF not read)", () => {
  const ps = readLive("sleeper-league-rosters.txt").pasteSettings;
  assert.deepStrictEqual(changed(ps), {BENCH: [7, 5]});
  assert.strictEqual(ps.roster.DST, null);
  assert.strictEqual(ps.why.DST, "mixed");
  assert.strictEqual(ps.roster.K, 1);
});
test("before/after: espn-10team.txt (every value read)", () => {
  assert.deepStrictEqual(changed(readDef("espn-10team.txt").pasteSettings), {teams: [12, 10], BENCH: [7, 6]});
  assert.deepStrictEqual(changed(readDef("yahoo-12team-superflex.txt").pasteSettings), {WR: [2, 3], SUPERFLEX: [0, 1], BENCH: [7, 6]});
  assert.deepStrictEqual(changed(readDef("sleeper-14team.txt").pasteSettings), {teams: [12, 14], WR: [2, 3], FLEX: [1, 2], BENCH: [7, 5]});
});
const ENTRY_DIR = path.join(ROOT, "tests", "fixtures", "entry_paste");
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const TABLE_ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
test("real pastes (Yahoo phone tab, Yahoo markdown): trimmed rosters change nothing", () => {
  ["01-yahoo-iphone.txt", "02-yahoo-markdown.txt"].forEach(f => {
    const res = LP.read(fs.readFileSync(path.join(ENTRY_DIR, f), "utf8"), TABLE_ROWS, {table: TABLE});
    assert.strictEqual(res.ok, true, f);
    assert.strictEqual(LP.enginePatch(res.pasteSettings, {}), null, f);
    assert.strictEqual(res.pasteSettings.teams, null, f);
  });
  const one = LP.read(fs.readFileSync(path.join(ENTRY_DIR, "01-yahoo-iphone.txt"), "utf8"), TABLE_ROWS, {table: TABLE}).pasteSettings;
  assert.strictEqual(one.partial, true, "one team shows 3 players, the others 1 or 2");
});

// slot labels: only a slot, never a position line or a team code
test("published player table: a kicker also read as a skill player (Jake Bates / John Bates) is one roster row", () => {
  const res = LP.read(fs.readFileSync(path.join(DEF_DIR, "sleeper-14team.txt"), "utf8"), TABLE_ROWS, {table: TABLE});
  const team = res.teams.find(t => t.name === "Run It Back");
  assert.ok(team.players.some(p => p.line === "Jake Bates") && team.unmatched.some(u => u.line === "Jake Bates"), "the reader still reads that line twice");
  assert.deepStrictEqual(res.pasteSettings.rostered.perTeam.map(t => t.count), Array(14).fill(16));
  assert.deepStrictEqual(res.pasteSettings.roster, PROVIDERS["sleeper-14team.txt"].roster);
});
test("slot labels", () => {
  const yes = {"QB": "QB", "D/ST": "DST", "Bench": "BENCH", "BN": "BENCH", "W/R/T": "FLEX", "Q/W/R/T": "SUPERFLEX", "OP": "SUPERFLEX",
    "QB\t": "QB", "| QB | Drake Maye NE - QB |": "QB", "QB Josh Allen BUF": "QB", "IR": "IR", "WR1": "WR", "K": "K", "DEF": "DST"};
  Object.keys(yes).forEach(l => assert.strictEqual(LP.slotOf(l), yes[l], l));
  ["SF", "SF WR", "Sf - RB", "QB - HOU", "K - SEA", "HOU QB", "NYJ D/ST", "Jets D/ST", "Pos\tKickers\tAction", "Josh Allen", "Free Agency"]
    .forEach(l => assert.strictEqual(LP.slotOf(l), null, l));
});
test("a paste without slot labels reads the team count only", () => {
  const text = ["Team One", "Josh Allen", "Bijan Robinson", "CeeDee Lamb", "Sam LaPorta", "", "Team Two", "Jordan Love", "Saquon Barkley", "Puka Nacua", "Trey McBride"].join("\n");
  const ps = LP.inferSettings(text, {teams: [
    {name: "Team One", players: [1, 2, 3, 4], unmatched: []}, {name: "Team Two", players: [1, 2, 3, 4], unmatched: []}]});
  assert.strictEqual(ps.teamsRead, 2);
  assert.ok(Object.values(ps.roster).every(v => v === null));
  assert.strictEqual(ps.why.QB, "no-labels");
});

// 3. confirmations win; no paste, no change
test("a confirmed or changed field is never set from the paste again", () => {
  const ps = readDef("sleeper-14team.txt").pasteSettings;
  const patch = LP.enginePatch(ps, {teams: 12, BENCH: 7});
  assert.strictEqual(patch.teams, undefined);
  assert.strictEqual(patch.roster.BENCH, undefined);
  assert.strictEqual(patch.roster.FLEX, 2);
  assert.deepStrictEqual(LP.pendingFields(ps, {teams: 12, BENCH: 7}), ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST"]);
  const all = {}; LP.FIELDS.forEach(f => { all[f] = 1; });
  assert.strictEqual(LP.enginePatch(ps, all), null);
});
test("no paste: nothing to set, no notice", () => {
  assert.strictEqual(LP.enginePatch(null, {}), null);
  assert.strictEqual(LP.enginePatch(undefined), null);
  assert.deepStrictEqual(LP.pendingFields(null), []);
  assert.strictEqual(LP.pasteNotice(null, {}).show, false);
});
test("the same league read again keeps its confirmations; another league does not", () => {
  const a = LP.record(readDef("espn-10team.txt"), "paste"), b = LP.record(readDef("espn-10team.txt"), "paste");
  assert.strictEqual(LP.sameLeague(a, b), true);
  assert.strictEqual(LP.sameLeague(a, LP.record(readDef("sleeper-14team.txt"), "paste")), false);
  assert.strictEqual(LP.sameLeague(null, b), false);
});

// 4. the settings.html notice
test("notice: everything read (ESPN, 10 teams)", () => {
  const n = notice(readDef("espn-10team.txt").pasteSettings, {});
  assert.deepStrictEqual(n.lines, [
    "We read 10 teams and 159 players from your paste, up to 16 on a roster.",
    "We set the team count to 10 and guessed your lineup as 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K and 1 DEF, plus 6 bench spots.",
    "Please check each one marked “From your paste” against your league's settings. A paste shows who is on each roster, not every league rule, and it doesn't show scoring.",
  ]);
  assert.strictEqual(n.rosterInferred, true);
});
test("notice: superflex named when the paste shows one", () => {
  assert.ok(notice(readDef("yahoo-12team-superflex.txt").pasteSettings, {}).lines[1].includes("1 FLEX, 1 SUPERFLEX, 1 K"));
});
test("notice: partly read, an unsupported size, DEF left at the standard roster", () => {
  const n = notice(readLive("sleeper-league-rosters.txt").pasteSettings, {});
  assert.deepStrictEqual(n.lines, [
    "We read 5 teams and 72 players from your paste, up to 15 on a roster.",
    "We guessed your lineup as 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX and 1 K, plus 5 bench spots.",
    "We can value leagues of 8, 10, 12 or 14 teams, so the team count stays at 12. Pick the closest size below.",
    "Your paste didn't clearly show your DEF spots, so we kept the standard 1 DEF.",
    "Please check each one marked “From your paste” against your league's settings. A paste shows who is on each roster, not every league rule, and it doesn't show scoring.",
  ]);
});
test("notice: everything confirmed", () => {
  const ps = readDef("espn-10team.txt").pasteSettings, all = {};
  LP.FIELDS.forEach(f => { all[f] = after(ps)[f]; });
  assert.strictEqual(notice(ps, all).lines.slice(-1)[0], "You've checked these. You can still change any of them below.");
});
test("notice: nothing read (no labels, supported size not reached) keeps the page's own text", () => {
  const ps = LP.inferSettings("A\nx\nB\ny", {teams: [{name: "A", players: [1], unmatched: []}, {name: "B", players: [1], unmatched: []}]});
  ps.why.teams = undefined;   // as if the size were supported but not read
  assert.strictEqual(LP.pasteNotice(ps, {values: STANDARD, standard: STANDARD}).show, false);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
