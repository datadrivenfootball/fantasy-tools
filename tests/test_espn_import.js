// test_espn_import.js — ESPN public league import (app/next/espn-import.js). No live calls: fixture responses.
// Run: node tests/test_espn_import.js
// 1. Link and ID forms parse (fantasy.espn.com links with leagueId= and seasonId=, bare IDs, junk; Sleeper-length numbers are not ESPN).
// 2. A loaded league reads like a pasted rosters page of the same lines: the same teams and players; K and DEF not evaluated.
// 3. Settings from the league: scoring from reception points, every lineup slot, superflex (OP), team count rounded up.
// 4. Errors: private (401, 403), not found (404), empty league, network failure, the time budget; plain-words messages.
// 5. Calls go to ESPN's league data service only, without cookies, and ask for the settings, team and roster views.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
const LP = require(path.join(ROOT, "app", "next", "league-paste.js"));
const ES = require(path.join(ROOT, "app", "next", "espn-import.js"));
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
const FX = n => JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "espn", n + ".json"), "utf8"));
const ID = "1086064";
const BASE = `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/${ID}`;

/* responses by view: settings for view=mSettings, teams for view=mTeam&view=mRoster */
function fakeFetch(opts, calls) {
  opts = opts || {};
  return (url, init) => {
    if (calls) calls.push({url, init});
    const settingsCall = /[?&]view=mSettings\b/.test(url);
    const which = settingsCall ? "settings" : "teams";
    const v = opts[which];
    if (v instanceof Error) return Promise.reject(v);
    if (typeof v === "number") return Promise.resolve({ok: false, status: v, json: () => Promise.resolve({messages: ["x"]})});
    if (v === "hang") return new Promise((_, reject) => { if (init && init.signal) init.signal.addEventListener("abort", () => reject(new Error("aborted"))); });
    return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(v || FX(which))});
  };
}
const NOW = "2026-11-25T12:00:00Z";

let passed = 0, failed = 0;
const queue = [];
function test(name, fn) { queue.push([name, fn]); }

test("link and ID forms", () => {
  for (const [t, id, season] of [[ID, ID, null], [` ${ID} `, ID, null], [`https://fantasy.espn.com/football/league?leagueId=${ID}`, ID, null],
    [`fantasy.espn.com/football/league/rosters?leagueId=${ID}&seasonId=2025`, ID, 2025], [`https://fantasy.espn.com/football/team?leagueId=${ID}&teamId=3&seasonId=2026#x`, ID, 2026],
    ["336358", "336358", null], [`${ID}/`, ID, null]]) {
    assert.deepStrictEqual(ES.parseId(t), {id, season}, t);
  }
  for (const t of ["", "hello", "123", "100000000000000001", "https://sleeper.com/leagues/100000000000000001"]) {
    assert.strictEqual(ES.parseId(t), null, t);
  }
  assert.strictEqual(ES.seasonNow("2026-11-25T12:00:00Z"), 2026);
  assert.strictEqual(ES.seasonNow("2027-01-20T12:00:00Z"), 2026, "January finishes last season");
  assert.strictEqual(ES.seasonNow("2027-08-20T12:00:00Z"), 2027);
});

test("a loaded league reads like a paste of the same rosters", async () => {
  const calls = [];
  const progress = [];
  const out = await ES.load(ID, {fetch: fakeFetch({}, calls), rows: ROWS, table: TABLE, now: NOW, onProgress: p => progress.push(p)});
  assert.strictEqual(out.ok, true, JSON.stringify(out));
  assert.deepStrictEqual(calls.map(c => c.url), [`${BASE}?view=mSettings`, `${BASE}?view=mTeam&view=mRoster`]);
  assert.ok(calls.every(c => c.init.credentials === "omit" && !c.init.headers), "no cookies, no custom headers (so no preflight)");
  assert.deepStrictEqual(progress, [{step: "settings", name: "La Lega dei Test", teams: 12}]);
  const teams = FX("teams").teams;
  assert.deepStrictEqual(out.result.teams.map(t => t.name), teams.map(t => t.name));
  // the same lines pasted as a rosters page read to the same players
  const blocks = ES.asBlocks(teams);
  const text = blocks.map(b => b.name + "\n" + b.text).join("\n\n");
  const pasted = LP.readWithNames(text, blocks.map(b => b.name), ROWS, {table: TABLE});
  assert.deepStrictEqual(pasted.teams.map(t => t.players.map(p => p.key)), out.result.teams.map(t => t.players.map(p => p.key)));
  // every skill player in the fixture is matched; each team's kicker and defense is shown, not evaluated
  out.result.teams.forEach(t => {
    assert.ok(t.players.length >= 12, `${t.name}: ${t.players.length} matched; unmatched ${JSON.stringify(t.unmatched.filter(u => u.reason !== "kdef"))}`);
    assert.deepStrictEqual(t.unmatched.filter(u => u.reason === "kdef").map(u => u.pos).sort(), ["DEF", "K"], t.name);
  });
  assert.strictEqual(out.result.look + out.result.missing, 0, "nothing to check");
  assert.ok(blocks[0].text.split("\n").includes("CIN Defense DEF"), "a D/ST is the team's defense");
  assert.ok(blocks[0].text.split("\n").includes("Brandon Aubrey K DAL"));
  const rec = LP.record(out.result, "espn");
  assert.strictEqual(rec.suggestedName, "La Lega dei Test");
  assert.strictEqual(rec.leagueId, ID);
  assert.strictEqual(rec.platform, "espn");
  assert.strictEqual(rec.me, null, "ESPN's public data does not say which team is yours");
  assert.deepStrictEqual(out.settings, {scoring: "half_ppr", superflex: false, teams: 12,
    roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5, K: 1, DST: 1}});
  assert.strictEqual(out.result.fit, null);
});

test("settings: scoring, slots, superflex, team count, TE premium", () => {
  const lg = n => ({settings: Object.assign({size: 12, rosterSettings: {lineupSlotCounts: {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "20": 6}}, scoringSettings: {scoringItems: [{statId: 53, points: 1}]}}, n)});
  assert.strictEqual(ES.settingsOf(lg()).scoring, "ppr");
  assert.strictEqual(ES.settingsOf(lg({scoringSettings: {scoringItems: [{statId: 53, points: 0.5}]}})).scoring, "half_ppr");
  assert.strictEqual(ES.settingsOf(lg({scoringSettings: {scoringItems: []}})).scoring, "standard");
  const sf = ES.settingsOf(lg({rosterSettings: {lineupSlotCounts: {"0": 1, "7": 1, "2": 2, "4": 2, "6": 1, "3": 1, "5": 1, "23": 1, "20": 6, "17": 0, "16": 0}}}));
  assert.deepStrictEqual([sf.superflex, sf.superflexSlots, sf.roster.FLEX, sf.roster.K, sf.roster.DST], [true, undefined, 3, 0, 0], "OP is superflex; RB/WR, WR/TE and FLEX are flex");
  assert.strictEqual(ES.settingsOf(lg({rosterSettings: {lineupSlotCounts: {"0": 1, "7": 2, "20": 6}}})).superflexSlots, 2);
  const counts = [2, 6, 8, 9, 10, 11, 12, 13, 14, 16, 20];
  assert.deepStrictEqual(counts.map(n => ES.settingsOf(lg({size: n})).teams), [8, 8, 8, 10, 10, 12, 12, 14, 14, 14, 14], "the shipped round-up rule");
  assert.deepStrictEqual(ES.fitOf(lg({size: 9})), {teams: 9, usedTeams: 10});
  assert.deepStrictEqual(ES.fitOf(lg({scoringSettings: {scoringItems: [{statId: 53, points: 1, pointsOverrides: {"6": 1.5}}]}})), {tePremium: 0.5});
  assert.strictEqual(ES.fitOf(lg()), null);
  assert.strictEqual(ES.settingsOf(lg({rosterSettings: {}})).roster, undefined, "no slot counts: settings.html asks");
});

test("every ESPN team code, and defensive players left off", () => {
  // ESPN proTeamId -> the player table's team codes, stated here (matching goes by name, so a wrong code would pass unseen)
  const WANT = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND",
    12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT",
    24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"};
  const entry = (name, pos, pro) => ({playerPoolEntry: {player: {fullName: name, defaultPositionId: pos, proTeamId: pro}}});
  const ids = Object.keys(WANT).map(Number);
  const lines = ES.asBlocks([{id: 1, name: "A", roster: {entries: ids.map(id => entry("Player " + id, 1, id))}}])[0].text.split("\n");
  assert.deepStrictEqual(lines, ids.map(id => `Player ${id} QB ${WANT[id]}`));
  const defs = ES.asBlocks([{id: 1, name: "A", roster: {entries: ids.map(id => entry("x D/ST", 16, id))}}])[0].text.split("\n");
  assert.deepStrictEqual(defs, ids.map(id => `${WANT[id]} Defense DEF`));
  // the player table writes Jacksonville JAC; the live matcher reads JAX as JAC (roster-paste.js team aliases), as for Sleeper
  assert.deepStrictEqual(Object.values(WANT).map(t => t === "JAX" ? "JAC" : t).sort(),
    [...new Set(TABLE.map(r => r.split("|")[2]).filter(t => /^[A-Z]{2,3}$/.test(t)))].sort(), "the codes are the player table's");
  // IDP: a linebacker named like a quarterback is left off, never matched to him; the league says how many it starts
  const idp = ES.asBlocks([{id: 1, name: "A", roster: {entries: [entry("Josh Allen", 1, 2), entry("Josh Allen", 11, 30), entry("Some Punter", 7, 3)]}}])[0];
  assert.strictEqual(idp.text, "Josh Allen QB BUF");
  assert.deepStrictEqual(ES.fitOf({settings: {size: 12, rosterSettings: {lineupSlotCounts: {"0": 1, "10": 2, "14": 1, "15": 0}}}}), {idp: 3});
});

test("errors fall through with a reason", async () => {
  const o = {rows: ROWS, table: TABLE, now: NOW};
  assert.strictEqual((await ES.load(ID, Object.assign({fetch: fakeFetch({settings: 401})}, o))).code, "private");
  assert.strictEqual((await ES.load(ID, Object.assign({fetch: fakeFetch({settings: 403})}, o))).code, "private");
  assert.strictEqual((await ES.load(ID, Object.assign({fetch: fakeFetch({teams: 401})}, o))).code, "private");
  const nf = await ES.load(ID, Object.assign({fetch: fakeFetch({settings: 404})}, o));
  assert.deepStrictEqual([nf.code, nf.season], ["notfound", 2026]);
  assert.strictEqual((await ES.load(ID, Object.assign({fetch: fakeFetch({settings: 500})}, o))).code, "network");
  assert.strictEqual((await ES.load(ID, Object.assign({fetch: fakeFetch({settings: new TypeError("Failed to fetch")})}, o))).code, "network", "CORS or offline");
  assert.strictEqual((await ES.load(ID, Object.assign({fetch: fakeFetch({teams: {teams: [{id: 1, name: "A", roster: {entries: []}}]}})}, o))).code, "empty");
  const t0 = Date.now();
  const slow = await ES.load(ID, Object.assign({fetch: fakeFetch({teams: "hang"}), timeoutMs: 300}, o));
  assert.strictEqual(slow.code, "timeout");
  assert.ok(Date.now() - t0 < 2000, "the budget ends the wait");
  assert.strictEqual((await ES.load("abc", {fetch: fakeFetch({})})).code, "invalid");
  const s2025 = [];
  await ES.load(ID, Object.assign({fetch: fakeFetch({}, s2025), season: 2025}, o));
  assert.ok(s2025[0].url.includes("/seasons/2025/"), "a season in the link is used");
  const banned = /\b(choose|set up|demo|sample|mock|illustrative|player pool|market)\b/i;
  for (const [code, fn] of Object.entries(ES.MESSAGES)) {
    const m = fn({season: 2026});
    assert.ok(m.length > 20 && /\.$/.test(m), code);
    assert.ok(!banned.test(m), `${code}: ${m}`);
  }
  assert.ok(ES.MESSAGES.notfound({season: 2026}).includes("2026 season"));
  // the fallback button opens the league on ESPN (its data view), not the rosters page: the messages say so
  for (const code of ["empty", "timeout", "network"]) {
    assert.ok(ES.MESSAGES[code]().includes("open your league on ESPN below"), code);
    assert.ok(!/rosters page/.test(ES.MESSAGES[code]()), code);
  }
});

(async () => {
  for (const [name, fn] of queue) {
    try { await fn(); passed++; console.log(`  ok  ${name}`); } catch (e) { failed++; console.log(`  FAIL ${name}\n       ${e.message}`); }
  }
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
