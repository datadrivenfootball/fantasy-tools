// test_sleeper_import.js — JEG-1570: Sleeper league import (app/next/sleeper-import.js). No live calls: fixture responses.
// Run: node tests/test_sleeper_import.js
// 1. Link and ID forms parse (sleeper.com and sleeper.app links, bare ID, query strings, junk).
// 2. A loaded league equals the paste path: the same teams and players as DDF.leaguePaste reading the rosters page text.
// 3. Team names (team name, else display name, duplicates made unique, ownerless "Team N"), defenses not evaluated,
//    unknown ids listed as not found, league name and ID, settings read from the league.
// 4. Errors: not found (404), old season, empty league, network failure; plain-words messages with no banned words.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
const LP = require(path.join(ROOT, "app", "next", "league-paste.js"));
const SL = require(path.join(ROOT, "app", "next", "sleeper-import.js"));
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
const FX = n => JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "sleeper", n + ".json"), "utf8"));
const sys = require("child_process");
const PLAYERS = JSON.parse(sys.execFileSync("python3", ["-c",
  "import sys,json; sys.path.insert(0,'pipelines'); import build_root_pages as b; print(json.dumps(b.sleeper_players()))"], {cwd: ROOT}).toString());

function fakeFetch(map, calls) {
  return url => {
    if (calls) calls.push(url);
    const hit = Object.keys(map).find(k => url.endsWith(k));
    if (hit === undefined) return Promise.resolve({ok: false, status: 404, json: () => Promise.resolve(null)});
    const v = map[hit];
    if (v instanceof Error) return Promise.reject(v);
    return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(v)});
  };
}
const ID = "100000000000000001";
const GOOD = {
  [`/league/${ID}`]: FX("league"), [`/league/${ID}/users`]: FX("users"), [`/league/${ID}/rosters`]: FX("rosters"),
  "/state/nfl": FX("state"), "sleeper-players.json": PLAYERS,
};

let passed = 0, failed = 0;
const pending = [];
function test(name, fn) {
  pending.push(Promise.resolve().then(fn).then(() => { passed++; console.log(`  ok  ${name}`); },
    e => { failed++; console.log(`  FAIL ${name}\n       ${e.message}`); }));
}

test("link and ID forms", () => {
  const want = "1313051744942428160";
  for (const t of [want, ` ${want} `, `https://sleeper.com/leagues/${want}`, `sleeper.com/leagues/${want}/team`,
    `https://sleeper.app/leagues/${want}/matchup?tab=1`, `https://sleeper.com/leagues/${want}?utm=x#top`, `${want}/`, `${want}?x=1`]) {
    assert.strictEqual(SL.parseId(t), want, t);
  }
  for (const t of ["", "hello", "12345", "https://sleeper.com/settings", "https://fantasy.espn.com/football/league?leagueId=123456"]) {
    assert.strictEqual(SL.parseId(t), null, t);
  }
});

test("a loaded league equals the paste path", async () => {
  SL._reset();
  const calls = [];
  const out = await SL.load(ID, {fetch: fakeFetch(GOOD, calls), rows: ROWS, table: TABLE});
  assert.strictEqual(out.ok, true, JSON.stringify(out));
  assert.strictEqual(calls.filter(u => u.startsWith("https://api.sleeper.app/v1/")).length, 4, "4 Sleeper calls");
  assert.ok(calls.every(u => u.startsWith("https://api.sleeper.app/v1/") || u === "sleeper-players.json"), "calls go to Sleeper only");
  const page = SL.asPaste(FX("users"), FX("rosters"), PLAYERS.p);
  const viaPaste = LP.readWithNames(page.text, page.names, ROWS, {table: TABLE});
  // the same teams and players as the paste path; ids Sleeper's table does not know yet are added as "not found"
  assert.deepStrictEqual(out.result.teams.map(t => [t.name, t.players]), viaPaste.teams.map(t => [t.name, t.players]));
  assert.deepStrictEqual(out.result.teams.map(t => t.unmatched.filter(u => !/^Sleeper player /.test(u.line))), viaPaste.teams.map(t => t.unmatched));
  const rec = LP.record(out.result, "sleeper");
  assert.strictEqual(rec.suggestedName, "Sample Sleeper League");
  assert.strictEqual(rec.leagueId, ID);
  assert.strictEqual(rec.platform, "sleeper");
  assert.strictEqual(rec.me, null);
});

test("team names, defenses, unknown ids, settings", async () => {
  SL._reset();
  const out = await SL.load(ID, {fetch: fakeFetch(GOOD), rows: ROWS, table: TABLE});
  const teams = out.result.teams;
  assert.deepStrictEqual(teams.map(t => t.name), ["Alpha Squad", "beta_user", "Alpha Squad (2)", "Team 4"]);
  assert.strictEqual(teams[0].players.length, 7, "QB, 2 RB, 3 WR, TE matched");
  assert.deepStrictEqual(teams[0].unmatched.map(u => u.reason), ["kdef"]);
  assert.deepStrictEqual(teams[1].unmatched.map(u => [u.line, u.reason]), [["Sleeper player 99999999", "missing"]]);
  assert.ok(teams.every(t => t.players.every(p => /^\d+$/.test(p.key))));
  assert.deepStrictEqual(out.settings, {scoring: "half_ppr", superflex: true, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5}});
  assert.ok(!("teams" in out.settings), "4 teams is not a league size the site offers, so it is left to settings.html");
});

test("errors", async () => {
  SL._reset();
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch({"/state/nfl": FX("state")}), rows: ROWS})).code, "notfound");
  const old = Object.assign({}, GOOD, {[`/league/${ID}`]: FX("old-league").league});
  const o = await SL.load(ID, {fetch: fakeFetch(old), rows: ROWS});
  assert.deepStrictEqual([o.code, o.season], ["oldseason", "2025"]);
  const empty = Object.assign({}, GOOD, {[`/league/${ID}/rosters`]: FX("rosters").map(r => Object.assign({}, r, {players: []}))});
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(empty), rows: ROWS})).code, "empty");
  const down = Object.assign({}, GOOD, {[`/league/${ID}/users`]: new Error("offline")});
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(down), rows: ROWS})).code, "network");
  assert.strictEqual((await SL.load(null, {fetch: fakeFetch(GOOD)})).code, "invalid");
  const banned = /\b(choose|set up|demo|sample|mock|illustrative|player pool|market)\b/i;
  for (const [code, fn] of Object.entries(SL.MESSAGES)) {
    const m = fn({season: "2025"});
    assert.ok(m.length > 20 && /\.$/.test(m), code);
    assert.ok(!banned.test(m), `${code}: ${m}`);
  }
  assert.ok(SL.MESSAGES.oldseason({season: "2025"}).includes("2025 season"));
});

Promise.all(pending).then(() => { console.log(`\n${passed} passed, ${failed} failed`); process.exit(failed ? 1 : 0); });
