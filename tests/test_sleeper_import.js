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
// Sleeper id -> player_key for players the pipeline matched (data/inputs/sleeper_projection_idmap.csv)
const IDMAP = {};
fs.readFileSync(path.join(ROOT, "data", "inputs", "sleeper_projection_idmap.csv"), "utf8").split(/\n/).slice(1).forEach(l => {
  const c = l.split(","); if (c[6] === "matched" && c[5]) IDMAP[c[0]] = c[5];
});
const PRICED = new Set(ROWS.map(r => String(r.player_key)));
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
const queue = [];
function test(name, fn) { queue.push([name, fn]); }

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

test("a loaded league reads like a paste of the same rosters", async () => {
  const calls = [];
  const out = await SL.load(ID, {fetch: fakeFetch(GOOD, calls), rows: ROWS, table: TABLE});
  assert.strictEqual(out.ok, true, JSON.stringify(out));
  assert.strictEqual(calls.filter(u => u.startsWith("https://api.sleeper.app/v1/")).length, 4, "4 Sleeper calls");
  assert.ok(calls.every(u => u.startsWith("https://api.sleeper.app/v1/") || u === "sleeper-players.json"), "calls go to Sleeper only");
  // the expected players, stated from the fixture rosters and the identity table (not from the code under test)
  const want = FX("rosters").map(r => r.players.map(id => IDMAP[id]).filter(k => k && PRICED.has(k)));
  out.result.teams.forEach((t, i) => assert.deepStrictEqual(t.players.map(p => p.key), want[i], t.name));
  // and a pasted rosters page with the same lines reads to the same players
  const text = out.result.teams.map((t, i) => [`Team ${i + 1}`].concat(FX("rosters")[i].players.map(id => PLAYERS.p[id]).filter(Boolean)
    .map(p => `${p[0]} ${p[1]} ${p[2]}`)).join("\n")).join("\n");
  const pasted = LP.readWithNames(text, out.result.teams.map((_, i) => `Team ${i + 1}`), ROWS, {table: TABLE});
  assert.deepStrictEqual(pasted.teams.map(t => t.players), out.result.teams.map(t => t.players));
  const rec = LP.record(out.result, "sleeper");
  assert.strictEqual(rec.suggestedName, "Gridiron Test League");
  assert.strictEqual(rec.leagueId, ID);
  assert.strictEqual(rec.platform, "sleeper");
  assert.strictEqual(rec.me, null);
});

test("team names, defenses, unknown ids, settings", async () => {
  const out = await SL.load(ID, {fetch: fakeFetch(GOOD), rows: ROWS, table: TABLE});
  const teams = out.result.teams;
  // an emoji-only name and a name that differs only by punctuation keep their own rosters
  assert.deepStrictEqual(teams.map(t => t.name), ["Alpha Squad", "beta_user", "🔥🔥🔥", "Alpha-Squad"]);
  const want = FX("rosters").map(r => r.players.filter(id => IDMAP[id] && PRICED.has(IDMAP[id])).length);
  assert.deepStrictEqual(teams.map(t => t.players.length), want);
  assert.ok(want.every(n => n >= 5));
  assert.strictEqual(teams[0].players.length, 7, "QB, 2 RB, 3 WR, TE matched");
  assert.deepStrictEqual(teams[0].unmatched.map(u => u.reason), ["kdef"]);
  assert.deepStrictEqual(teams[1].unmatched.map(u => [u.line, u.reason]), [["A player not in our list yet (Sleeper id 99999999)", "missing"]]);
  assert.ok(teams.every(t => t.players.every(p => /^\d+$/.test(p.key))));
  // JEG-1632: the K and DEF slots come through as the engine's K / DST roster keys
  // League entry (Jeremy, 2026-11-20): a size the site does not offer uses the closest one (4 -> 8), and the record says so
  assert.deepStrictEqual(out.settings, {scoring: "half_ppr", superflex: true, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5, K: 1, DST: 1}, teams: 8});
  assert.deepStrictEqual(out.result.fit, {teams: 4, usedTeams: 8});
});

test("team counts outside 8 to 14 use the closest size; TE premium is reported, not valued", () => {
  const S = DDF.sleeper;
  const lg = n => ({total_rosters: n, roster_positions: ["QB", "RB", "WR", "TE", "BN"], scoring_settings: {rec: 1}});
  // a count between sizes rounds up (9 -> 10, 11 -> 12, 13 -> 14); below 8 uses 8, above 14 uses 14 (Jeremy, 2026-11-24)
  assert.deepStrictEqual([4, 6, 8, 9, 10, 11, 12, 13, 16, 18, 32].map(n => S.settingsOf(lg(n)).teams), [8, 8, 8, 10, 10, 12, 12, 14, 14, 14, 14]);
  assert.strictEqual(S.fitOf(lg(12)), null, "a league that fits has nothing to say");
  assert.deepStrictEqual(S.fitOf(lg(18)), {teams: 18, usedTeams: 14});
  assert.deepStrictEqual(S.fitOf({total_rosters: 12, scoring_settings: {rec: 1, bonus_rec_te: 0.5}}), {tePremium: 0.5});
  assert.deepStrictEqual(S.fitOf({total_rosters: 18, scoring_settings: {bonus_rec_te: 1}}), {teams: 18, usedTeams: 14, tePremium: 1});
  assert.strictEqual(S.fitOf({total_rosters: 10, scoring_settings: {bonus_rec_te: 0}}), null);
});

test("kicker and defense slot counts (JEG-1632)", async () => {
  const lg = JSON.parse(JSON.stringify(FX("league")));
  lg.roster_positions = lg.roster_positions.filter(p => p !== "K").concat(["DEF", "DEF", "DEF"]);
  const out = await SL.load(ID, {fetch: fakeFetch(Object.assign({}, GOOD, {[`/league/${ID}`]: lg})), rows: ROWS, table: TABLE});
  assert.strictEqual(out.settings.roster.K, 0, "a league without a kicker slot");
  assert.strictEqual(out.settings.roster.DST, 3, "four DEF slots cap at the site's 3");
});

test("a missing player table is an error, not an empty league, and is not cached", async () => {
  const noTable = Object.assign({}, GOOD); delete noTable["sleeper-players.json"];
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(noTable), rows: ROWS})).code, "network");
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(GOOD), rows: ROWS, table: TABLE})).ok, true);
});

test("errors", async () => {
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

test("a username finds the leagues, and the user's own team", async () => {
  for (const t of ["gamma_user", " gamma_user ", "@gamma_user", "Gamma_User", "ab"]) assert.ok(SL.parseUsername(t), t);
  for (const t of ["", "a", "not a league", ID, "123456", "https://sleeper.com/leagues/1", "x".repeat(31)]) assert.strictEqual(SL.parseUsername(t), null, t);
  const USER = {"/user/alpha_user": FX("user"), "/state/nfl": FX("state"), "/user/u1/leagues/nfl/2026": FX("user-leagues")};
  const calls = [];
  const found = await SL.findLeagues("alpha_user", {fetch: fakeFetch(USER, calls)});
  assert.strictEqual(found.ok, true, JSON.stringify(found));
  assert.deepStrictEqual(found.user, {id: "u1", name: "alpha_user"});
  assert.deepStrictEqual(found.leagues, [{id: ID, name: "Gridiron Test League", teams: 4, scoring: "Half PPR"},
    {id: "100000000000000002", name: "Office League", teams: 10, scoring: "PPR"}]);
  assert.ok(calls.every(u => u.startsWith("https://api.sleeper.app/v1/")), "calls go to Sleeper only");
  assert.strictEqual(calls.length, 3, "user, season, leagues");
  assert.deepStrictEqual(await SL.findLeagues("nobody_here", {fetch: fakeFetch(USER)}), {ok: false, code: "nouser", name: "nobody_here"});
  const none = await SL.findLeagues("alpha_user", {fetch: fakeFetch({"/user/alpha_user": FX("user"), "/state/nfl": FX("state"), "/user/u1/leagues/nfl/2026": []})});
  assert.deepStrictEqual([none.code, none.name, none.season], ["noleagues", "alpha_user", "2026"]);
  assert.strictEqual((await SL.findLeagues("alpha_user", {fetch: fakeFetch({"/user/alpha_user": new Error("offline")})})).code, "network");
  // the league loaded for that user: their roster (owner u1, roster 1) is the first team; u3 owns the third
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(GOOD), rows: ROWS, table: TABLE, userId: "u1"})).mine, 0);
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(GOOD), rows: ROWS, table: TABLE, userId: "u3"})).mine, 2);
  assert.strictEqual((await SL.load(ID, {fetch: fakeFetch(GOOD), rows: ROWS, table: TABLE})).mine, null, "a league ID alone does not say which team is yours");
  assert.strictEqual(SL.mineOf([{roster_id: 2, owner_id: "x", co_owners: ["u9"]}, {roster_id: 1, owner_id: "y"}], "u9"), 1, "a co-owner's team, in roster order");
  assert.strictEqual(SL.mineOf(FX("rosters"), "u404"), null);
  assert.ok(SL.MESSAGES.nouser({name: "nobody_here"}).includes("nobody_here"));
  assert.ok(SL.MESSAGES.noleagues({name: "gamma_user", season: "2026"}).includes("2026 season"));
});

(async () => {
  for (const [name, fn] of queue) {
    SL._reset();   // each test starts without the cached player table
    try { await fn(); passed++; console.log(`  ok  ${name}`); } catch (e) { failed++; console.log(`  FAIL ${name}\n       ${e.message}`); }
  }
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
